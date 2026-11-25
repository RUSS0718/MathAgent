"""Exercise online intervention through the normal single-route ModelPort seam."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from test_runtime_math_verification import ANSWER, CHECKS, PROBLEM, increment
from test_runtime_scoped_derivations import delivered

from ricl_runtime import Runtime
from ricl_runtime.__main__ import main
from ricl_runtime.port import ModelReply, ToolCall, ToolReceipt
from ricl_runtime.providers.chat_completions import (
    ProviderOutcomeUnknownError,
    ProviderTimeoutError,
)

BAD_COVERAGE = {**CHECKS[2], "candidates": ["3"]}
HYPOTHESIS = "The smaller root was dropped when factoring."
STRATEGY = "Recover both squared roots before any substitution."
DIAGNOSIS = json.dumps({"hypothesis": HYPOTHESIS, "strategy": STRATEGY})


class InterventionPort:
    name = "controlled-intervention"

    def __init__(self, *steps):
        self.steps = iter(steps)
        self.prompts = []

    def complete(self, prompt):
        self.prompts.append(prompt)
        step = next(self.steps)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, ModelReply):
            return step
        return ModelReply(
            step(prompt) if callable(step) else step, model=self.name,
            input_tokens=10, output_tokens=5, usage_source="controlled",
        )


class RuntimeOnlineInterventionTests(unittest.TestCase):
    def run_script(self, port, *, limit=5, tools=0, **runtime_options):
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port, **runtime_options).run(
                PROBLEM, output_root=Path(directory),
                counterfactual_enabled=True, model_request_limit=limit, tool_call_limit=tools,
            )
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        return run, trace

    def test_cli_can_replay_diagnosis_arms_and_parent_in_dispatch_order(self):
        replies = [
            increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS, increment(BAD_COVERAGE),
            increment(CHECKS[2]), increment(CHECKS[3]),
        ]
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stdout):
            exit_code = main([
                "--problem", PROBLEM, "--output-root", directory,
                "--counterfactual", "--model-request-limit", "5",
                *(item for reply in replies for item in ("--offline-answer", reply)),
            ])
            run = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 5, "used": 5})

    def test_online_diagnosis_delivers_evidence_and_only_minimal_repair_to_parent(self):
        def diagnose(prompt):
            self.assertIn("candidate_set_incorrect_or_incomplete", prompt)
            self.assertIn('"candidates":["3"]', prompt)
            self.assertIn("candidate_constraint", prompt)
            return DIAGNOSIS

        def parent(prompt):
            by_kind = {check["kind"]: check for check in delivered(prompt)}
            self.assertEqual(set(by_kind), {
                "necessary_conditions", "candidate_constraint", "candidate_coverage",
            })
            payload = json.loads(increment(CHECKS[3]))
            payload["used_evidence_ids"] = [by_kind["candidate_coverage"]["evidence_id"]]
            return json.dumps(payload)

        port = InterventionPort(
            increment(*CHECKS[:2], BAD_COVERAGE), diagnose,
            increment(BAD_COVERAGE, answer="A private control draft."),
            increment(*CHECKS[2:], answer="A private treatment draft."),
            parent,
        )
        run, trace = self.run_script(port)

        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 5, "used": 5})
        self.assertEqual(run["usage"]["tokens"], 75)
        self.assertEqual(
            [item["request_id"] for item in run["provider_requests"]],
            [item["request_id"] for item in trace if item["event"] == "model_request_sent"],
        )
        self.assertNotIn(STRATEGY, port.prompts[2])
        self.assertIn(STRATEGY, port.prompts[3])
        self.assertEqual(port.prompts[2], port.prompts[3].split("\n\nTargeted strategy:\n")[0])
        self.assertEqual(delivered(port.prompts[2]), delivered(port.prompts[3]))
        self.assertNotIn("private control draft", port.prompts[3])

        diagnosis = next(e for e in trace if e["event"] == "counterfactual_diagnosis")
        arms = [e for e in trace if e["event"] == "counterfactual_arm_checked"]
        merge = next(e for e in trace if e["event"] == "counterfactual_merge")
        action = next(e for e in trace if e["event"] == "counterfactual_parent_action")
        self.assertTrue(diagnosis["failure_evidence_ids"])
        self.assertEqual([e["arm"] for e in arms], ["control", "treatment"])
        self.assertEqual({e["checkpoint_id"] for e in arms}, {merge["checkpoint_id"]})
        self.assertEqual(arms[0]["budget"], arms[1]["budget"])
        self.assertEqual(arms[1]["strategy_id"], diagnosis["strategy_id"])
        self.assertEqual(merge["status"], "merged")
        self.assertEqual(len(merge["merged_evidence_ids"]), 1)
        self.assertEqual(action["used_evidence_ids"], merge["merged_evidence_ids"])
        for private_text in (HYPOTHESIS, STRATEGY, "private control draft", "private treatment draft"):
            self.assertNotIn(private_text, json.dumps(trace) + json.dumps(run))

    def test_admission_reserves_parent_request_and_distinguishes_unknown_from_failed(self):
        cases = (
            (BAD_COVERAGE, True, "insufficient_model_requests"),
            ({**CHECKS[2], "candidates": ["irrational"]}, False, "no_critical_failure"),
        )
        for check, eligible, reason in cases:
            with self.subTest(reason=reason):
                port = InterventionPort(increment(check))
                run, trace = self.run_script(port, limit=4)
                trigger = next(e for e in trace if e["event"] == "counterfactual_trigger_evaluated")
                self.assertEqual(trigger["reason"], reason)
                self.assertEqual(trigger["eligible"], eligible)
                self.assertEqual(run["budget"]["model_requests"]["used"], 1)
                self.assertEqual(len(port.prompts), 1)

    def test_intervention_diagnosis_cannot_overrun_the_root_token_budget(self):
        port = InterventionPort(increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS)
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port).run(
                PROBLEM,
                output_root=Path(directory),
                counterfactual_enabled=True,
                model_request_limit=8,
                token_limit=20,
            )
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(run["budget"]["model_requests"]["used"], 1)
        self.assertEqual(run["budget"]["tokens"]["used"], 15)
        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertEqual(run["budget"]["verifications"]["used"], 1)
        self.assertEqual(run["run"]["status"], "stopped")
        self.assertEqual(run["run"]["stop_reason"], "token_budget_exhausted")
        trigger = next(
            event for event in trace
            if event["event"] == "counterfactual_trigger_evaluated"
        )
        self.assertEqual(trigger["reason"], "insufficient_full_budget")
        self.assertEqual(trigger["budget_reserve_reason"], "token_budget_exhausted")
        self.assertFalse(any(
            event["event"] == "counterfactual_started" for event in trace
        ))
        self.assertFalse(any(
            str(event.get("request_kind", "")).startswith("counterfactual_")
            for event in trace if event["event"] == "model_request_sent"
        ))
        blocked = next(
            event for event in trace
            if event["event"] == "counterfactual_budget_blocked"
        )
        self.assertEqual(blocked["stage"], "admission")
        self.assertEqual(blocked["reason"], "token_budget_exhausted")
        self.assertFalse(any(
            event["event"] == "counterfactual_merge" for event in trace
        ))

    def test_unknown_and_tied_pairs_leave_parent_checkpoint_unchanged(self):
        cases = (
            (increment(answer="No checkable repair."), "independent_comparison_unknown"),
            (increment(CHECKS[2]), "tied"),
        )
        for control, reason in cases:
            with self.subTest(reason=reason):
                port = InterventionPort(
                    increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS, control, increment(CHECKS[2]),
                    increment(*CHECKS[2:]),
                )
                run, trace = self.run_script(port)
                self.assertEqual(run["verification"]["status"], "verified")
                merge = next(e for e in trace if e["event"] == "counterfactual_merge")
                self.assertEqual((merge["reason"], merge["merged_evidence_ids"]), (reason, []))
                self.assertEqual(delivered(port.prompts[2]), delivered(port.prompts[-1]))

    def test_pair_is_admitted_only_once_even_if_parent_fails_with_budget_left(self):
        failed = increment(BAD_COVERAGE)
        port = InterventionPort(failed, DIAGNOSIS, failed, failed, failed)
        run, trace = self.run_script(port, limit=9)
        admissions = [e["reason"] for e in trace if e["event"] == "counterfactual_trigger_evaluated"]
        self.assertEqual(admissions, ["admitted", "already_triggered"])
        self.assertEqual(run["run"]["stop_reason"], "no_progress")
        self.assertEqual(run["budget"]["model_requests"]["used"], 5)

    def test_greater_goal_progress_merges_the_smallest_independently_supported_delta(self):
        port = InterventionPort(
            increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS,
            increment(CHECKS[0]), increment(*CHECKS[2:]), increment(CHECKS[3]),
        )
        run, trace = self.run_script(port)
        self.assertEqual(run["verification"]["status"], "verified")
        merge = next(e for e in trace if e["event"] == "counterfactual_merge")
        self.assertEqual(merge["reason"], "greater_verified_progress")
        self.assertEqual(len(merge["merged_evidence_ids"]), 1)
        self.assertEqual(delivered(port.prompts[-1])[-1]["kind"], "candidate_coverage")

    def test_remote_unknown_or_timeout_is_charged_and_stops_without_a_resend(self):
        for error, reason in (
            (ProviderOutcomeUnknownError("private provider details"), "unknown_outcome"),
            (ProviderTimeoutError("private provider details"), "timeout"),
        ):
            with self.subTest(reason=reason):
                port = InterventionPort(increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS, error)
                run, trace = self.run_script(port)
                self.assertEqual(len(port.prompts), 3)
                self.assertEqual(run["budget"]["model_requests"]["used"], 3)
                self.assertEqual(run["usage"]["tokens"], "unknown")
                self.assertEqual(run["run"]["stop_reason"], reason)
                merge = next(e for e in trace if e["event"] == "counterfactual_merge")
                self.assertEqual(merge["reason"], "arm_" + reason)
                self.assertNotIn("private provider details", json.dumps(run) + json.dumps(trace))

    def test_lost_necessary_support_triggers_an_independent_alternative(self):
        def recheck(supports):
            return [s.evidence_id for s in supports if s.method == "exact_quadratic_discriminant"]

        def diagnose(prompt):
            self.assertIn("necessary_support_lost", prompt)
            self.assertNotIn("exact_quadratic_discriminant", json.dumps(delivered(prompt)))
            return DIAGNOSIS

        factorization = {**CHECKS[2], "factor_constants": ["2", "-3"]}
        port = InterventionPort(
            increment(*CHECKS[:3]), diagnose, increment(BAD_COVERAGE),
            increment(factorization), increment(CHECKS[3]),
        )
        run, trace = self.run_script(port, math_evidence_recheck=recheck)
        self.assertEqual(run["verification"]["status"], "verified")
        revoked = next(e for e in trace if e["event"] == "derivation_revoked")
        trigger = next(e for e in trace if e["event"] == "counterfactual_started")
        self.assertEqual(trigger["failure_evidence_ids"], [revoked["revoked_evidence_id"]])
        self.assertEqual(delivered(port.prompts[-1])[-1]["reason"], "exact_quadratic_factorization")

    def test_parent_recheck_rejects_a_repair_that_would_lose_checkpoint_evidence(self):
        rechecked_repair = False

        def recheck(supports):
            nonlocal rechecked_repair
            if any(s.kind == "candidate_coverage" for s in supports):
                if rechecked_repair:
                    return [s.evidence_id for s in supports if s.kind == "necessary_conditions"]
                rechecked_repair = True
            return []

        port = InterventionPort(
            increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS, increment(BAD_COVERAGE),
            increment(CHECKS[2]), increment(answer="Continue the original proof."),
        )
        run, trace = self.run_script(port, math_evidence_recheck=recheck)
        merge = next(e for e in trace if e["event"] == "counterfactual_merge")
        self.assertEqual(merge["reason"], "parent_recheck_failed")
        self.assertEqual(delivered(port.prompts[2]), delivered(port.prompts[-1]))
        self.assertEqual([e["kind"] for e in run["derivations"]["supports"]],
                         ["necessary_conditions", "candidate_constraint"])

    def test_arms_share_tool_reservations_and_keep_receipts_out_of_parent_state(self):
        class Tool:
            def execute(self, invocation_id, call):
                return ToolReceipt(invocation_id, invocation_id, call.tool_name, True, call.input)

        def step(text, detail):
            return ModelReply(
                text, model=InterventionPort.name,
                tool_calls=(ToolCall("math_tool", detail), ToolCall("math_tool", "excess")),
            )

        port = InterventionPort(
            increment(*CHECKS[:2], BAD_COVERAGE), DIAGNOSIS,
            step(increment(BAD_COVERAGE), "control output"),
            step(increment(CHECKS[2]), "treatment output"),
            step(increment(CHECKS[3]), "parent output"),
        )
        run, trace = self.run_script(port, tools=3, tool_executor=Tool())
        self.assertEqual(run["budget"]["tools"], {"used": 3, "limit": 3})
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(len(run["evidence"]), 1)
        self.assertEqual(
            [e["used"]["tool_calls"] for e in trace if e["event"] == "counterfactual_arm_checked"],
            [1, 1],
        )
        self.assertTrue(all("control output" not in prompt and "treatment output" not in prompt
                            for prompt in port.prompts))
