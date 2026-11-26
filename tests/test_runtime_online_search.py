"""Observe online route choices at the model request boundary."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from test_runtime_math_verification import CHECKS, PROBLEM, ScriptedModelPort, increment

from ricl_runtime import Runtime
from ricl_runtime.__main__ import main
from ricl_runtime.port import ModelReply

CANDIDATES = json.dumps({"candidates": [
    {"strategy": "Study the domain first."},
    {"strategy": "Derive the quadratic constraint first."},
]})


def measured(text, input_tokens=12, output_tokens=8):
    return ModelReply(text, input_tokens=input_tokens, output_tokens=output_tokens, usage_source="fixture")


def captured_route(prompt):
    _, _, route = prompt.partition("Route expansion:\n")
    return json.loads(route.split("\n\n", 1)[0])["route_id"]


class RuntimeOnlineSearchTests(unittest.TestCase):
    def run_search(self, *responses, mode="aprs", limit=None, **runtime_options):
        port = ScriptedModelPort(*responses)
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port, **runtime_options).run(
                PROBLEM, online_search=mode, model_request_limit=len(responses) if limit is None else limit,
                output_root=Path(directory),
            )
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        return port, run, trace

    def test_one_verified_check_changes_the_next_dispatched_route(self):
        def trial(constraint, mode="aprs"):
            return self.run_search(
                measured(CANDIDATES, 3, 5),
                measured(increment(CHECKS[0], answer="Domain restrictions established."), 24, 16),
                measured(increment(constraint, answer="Quadratic constraint proposed.")),
                measured(increment(answer="Continue investigating.")),
                mode=mode,
            )

        for mode, constraint, expected in (
            ("aprs", CHECKS[1], "route_02"),
            ("aprs", {**CHECKS[1], "coefficients": ["1", "-1", "-5"]}, "route_01"),
            ("round_robin", CHECKS[1], "route_01"),
        ):
            with self.subTest(mode=mode, expected=expected, constraint=constraint):
                port, run, trace = trial(constraint, mode)
                self.assertIn(PROBLEM, port.prompts[0])
                self.assertEqual([captured_route(p) for p in port.prompts[1:]],
                                 ["route_01", "route_02", expected])
                self.assertEqual(run["budget"]["model_requests"], {"limit": 4, "used": 4})
                self.assertEqual(run["usage"]["tokens"], 88)
                decisions = [event for event in trace if event["event"] == "route_selection"]
                self.assertEqual([item["strategy"] for item in decisions],
                                 ["cold_start", "cold_start", "gain" if mode == "aprs" else "round_robin"])
                decision = decisions[-1]
                row = {item["route_id"]: item for item in decision["routes"]}
                self.assertEqual(row["route_01"]["effective_gain"], 1)
                self.assertEqual(row["route_01"]["cost"]["tokens"], 40)
                self.assertEqual(row["route_02"]["effective_gain"], int(constraint == CHECKS[1]))
                self.assertEqual(row["route_02"]["cost"]["tokens"], 20)
                provider_request = run["provider_requests"][-1]
                self.assertEqual(provider_request["route_id"], expected)
                self.assertEqual(provider_request["decision_id"], decision["decision_id"])
                dispatched = next(
                    event for event in trace if event["event"] == "model_request_sent"
                    and event["request_id"] == decision["request_id"]
                )
                self.assertEqual(dispatched["route_id"], expected)
                self.assertLess(trace.index(decision), trace.index(dispatched))
                self.assertNotIn("Study the domain first.", json.dumps(trace))

    def test_inherited_support_is_counted_once_and_revocation_changes_next_choice(self):
        rechecks = iter((False, False, True, False))

        def recheck(supports):
            if next(rechecks):
                return [support.evidence_id for support in supports if support.kind == "candidate_constraint"]
            return []

        port, run, trace = self.run_search(
            measured(CANDIDATES),
            measured(increment(CHECKS[1], answer="Squared constraint derived.")),
            measured(increment(*CHECKS[:3], answer="Candidates found using the shared constraint."), 36, 24),
            measured(increment(answer="Checking earlier evidence.")),
            measured(increment(answer="The domain condition still holds.")),
            math_evidence_recheck=recheck,
        )
        self.assertEqual([captured_route(p) for p in port.prompts[1:]],
                         ["route_01", "route_02", "route_01", "route_02"])
        self.assertIn("Previously verified public claims:", port.prompts[2])
        _, _, checks = port.prompts[4].partition("Previously verified public claims:\n")
        self.assertEqual([check["kind"] for check in json.loads(checks.split("\n\n", 1)[0])],
                         ["necessary_conditions"])
        decisions = [e for e in trace if e["event"] == "route_selection"]
        self.assertEqual([row["effective_gain"] for row in decisions[2]["routes"]], [1, 2])
        self.assertEqual([row["effective_gain"] for row in decisions[3]["routes"]], [0, 1])
        first_credit, = decisions[2]["routes"][0]["credit"]
        revoked = next(e for e in trace if e["event"] == "derivation_revoked")
        self.assertEqual(first_credit["evidence_id"], revoked["revoked_evidence_id"])
        self.assertEqual(run["online_search"]["supported_goal_ids"],
                         [decisions[3]["routes"][1]["credit"][0]["goal_id"]])
        verification = next(e for e in trace if e["event"] == "verification_completed")
        self.assertEqual(verification["usage"], {
            "input_tokens": 0, "output_tokens": 0, "source": "local_independent_verification",
            "applicable": True, "checks": {"verified": 1},
        })

    def test_route_revisit_omits_oversized_draft_but_delivers_verified_claims(self):
        """Keep verified state and the selected route when its earlier answer is too large."""
        port = ScriptedModelPort(
            measured(CANDIDATES),
            measured(increment(CHECKS[0], answer="Long draft. " * 1300)),
            measured(increment(answer="No new checked claim.")),
            measured(increment(answer="Continue from the domain restriction.")),
        )
        port.max_prompt_bytes = 16 * 1024
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port).run(
                PROBLEM, online_search="aprs", model_request_limit=4, output_root=Path(directory),
            )
            trace = [json.loads(line) for line in Path(run["artifacts"]["trace"]).read_text().splitlines()]

        self.assertEqual(captured_route(port.prompts[-1]), "route_01")
        self.assertLessEqual(len(port.prompts[-1].encode()), port.max_prompt_bytes)
        self.assertNotIn("Long draft.", port.prompts[-1])
        self.assertIn('"kind":"necessary_conditions"', port.prompts[-1])
        omitted, = [event for event in trace if event["event"] == "route_draft_omitted"]
        self.assertEqual(omitted["request_id"], run["provider_requests"][-1]["request_id"])
        self.assertGreater(omitted["prompt_bytes_before"], omitted["prompt_byte_limit"])

    def test_two_gain_choices_are_followed_by_least_recently_expanded_route(self):
        quiet = measured(increment(answer="No additional checked step."))
        port, run, trace = self.run_search(
            measured(CANDIDATES),
            measured(increment(CHECKS[0], answer="Domain restrictions established.")),
            ModelReply(increment(answer="No verified progress yet.")),
            quiet, quiet, quiet, quiet,
        )
        self.assertEqual([captured_route(p) for p in port.prompts[1:]],
                         ["route_01", "route_02", "route_01", "route_01", "route_02", "route_01"])
        decisions = [e for e in trace if e["event"] == "route_selection"]
        self.assertEqual([e["strategy"] for e in decisions],
                         ["cold_start", "cold_start", "gain", "gain", "explore", "gain"])
        self.assertEqual(decisions[4]["routes"][1]["gain_ranking_exclusion"], "unknown_token_cost")
        self.assertEqual(run["online_search"]["selection_counts"],
                         {"cold_start": 2, "gain": 3, "explore": 1})

    def test_unknown_and_zero_token_cost_are_distinct_and_fall_back_to_rotation(self):
        quiet = measured(increment(answer="No additional checked step."))
        port, run, trace = self.run_search(
            measured(CANDIDATES),
            measured(increment(CHECKS[0], answer="Domain restrictions established."), 12, "unknown"),
            measured(increment(CHECKS[1], answer="Squared constraint derived."), 0, 0),
            quiet, quiet,
        )
        self.assertEqual([captured_route(p) for p in port.prompts[1:]],
                         ["route_01", "route_02", "route_01", "route_02"])
        decision = [e for e in trace if e["event"] == "route_selection"][-1]
        unknown, zero = decision["routes"]
        self.assertEqual(unknown["cost"]["tokens"], "unknown")
        self.assertEqual(unknown["cost"]["input_tokens"], 24)
        self.assertEqual(unknown["cost"]["unknown_request_ids"], [run["provider_requests"][1]["request_id"]])
        self.assertEqual(zero["cost"]["tokens"], 0)
        self.assertEqual(zero["cost"]["unknown_request_ids"], [])
        self.assertEqual(decision["strategy"], "fallback_round_robin")
        self.assertEqual(decision["reason"], "no_comparable_effective_gain")
        self.assertEqual(run["usage"]["tokens"], "unknown")

    def test_budget_records_candidate_without_cold_start_opportunity(self):
        port, run, _ = self.run_search(
            measured(CANDIDATES), measured(increment(CHECKS[0], answer="Domain restrictions established.")),
        )
        self.assertEqual(len(port.prompts), 2)
        self.assertEqual(run["online_search"]["untried_routes"], [
            {"route_id": "route_02", "reason": "model_request_budget_exhausted"},
        ])

    def test_candidate_protocol_failure_is_metered_and_does_not_dispatch(self):
        port, run, _ = self.run_search(measured('{"candidates": []}'), limit=4)
        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(run["run"]["failure_status"], "protocol_failed")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 4, "used": 1})
        self.assertEqual(run["usage"]["tokens"], 20)
        self.assertIsNone(run["result"])

    def test_cli_replays_candidate_generation_and_expansion_through_one_run(self):
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stdout):
            status = main([
                "--problem", PROBLEM,
                "--online-search", "aprs",
                "--model-request-limit", "3",
                "--offline-answer", CANDIDATES,
                "--offline-answer", increment(*CHECKS),
                "--offline-answer", increment(answer="Independently checked claims were available."),
                "--output-root", directory,
            ])
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
        self.assertEqual(status, 0)
        run = json.loads(stdout.getvalue())
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["online_search"]["selection_counts"], {"cold_start": 2})
        self.assertEqual(run["budget"]["model_requests"], {"limit": 3, "used": 3})
