"""Offline single-route math verification through the CLI and Runtime."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from ricl_runtime import DeterministicModelPort, Runtime
from ricl_runtime.__main__ import main
from ricl_runtime.port import ModelPortFailure, ModelReply

PROBLEM = "√(x+6)=x"
ANSWER = "The complete solution set is {3}."
CHECKS = (
    {"kind": "necessary_conditions", "radicand_lower_bound": "-6", "rhs_lower_bound": "0"},
    {"kind": "candidate_constraint", "coefficients": ["1", "-1", "-6"], "direction": "forward"},
    {"kind": "candidate_coverage", "candidates": ["-2", "3"]},
    {"kind": "original_equation_filter", "accepted": ["3"], "rejected": ["-2"]},
)


def increment(*checks: dict[str, object], answer: str = ANSWER) -> str:
    return json.dumps({"answer": answer, "checks": checks})


class ScriptedModelPort:
    name = "scripted-math"

    def __init__(self, *responses: ModelReply | ModelPortFailure) -> None:
        self.responses = iter(responses)
        self.prompts: list[str] = []

    def complete(self, problem: str) -> ModelReply:
        self.prompts.append(problem)
        response = next(self.responses)
        if isinstance(response, ModelPortFailure):
            raise response
        return response


class RuntimeMathVerificationTests(unittest.TestCase):
    def test_cli_persists_complete_radical_equation_certificate(self) -> None:
        stdout = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(stdout):
            exit_code = main([
                "--problem", PROBLEM,
                "--offline-answer", increment(*CHECKS),
                "--output-root", directory,
            ])
            run = json.loads(stdout.getvalue())
            saved = json.loads(Path(run["artifacts"]["run"]).read_text(encoding="utf-8"))
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved, run)
        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["verification"]["completeness"]["solutions"], ["3"])
        self.assertEqual(run["verification"]["review"]["status"], "unknown")
        checks = {item["kind"]: item for item in run["verification"]["checks"]}
        self.assertEqual(checks["necessary_conditions"]["evidence"]["lower_bound"], "0")
        self.assertEqual(checks["candidate_constraint"]["direction"], "forward")
        self.assertEqual(checks["candidate_coverage"]["evidence"]["candidates"], ["-2", "3"])
        self.assertEqual(checks["original_equation_filter"]["evidence"]["rejected"], ["-2"])
        self.assertTrue(all(item["status"] == "verified" for item in checks.values()))
        goals = run["verification"]["goals"]
        self.assertEqual(len(goals), 4)
        self.assertEqual({goal["weight"] for goal in goals}, {1})
        self.assertEqual({goal["id"] for goal in goals}, {item["goal_id"] for item in checks.values()})
        events = [event["event"] for event in trace]
        self.assertLess(events.index("verification_goals_frozen"), events.index("model_request_sent"))
        self.assertTrue(run["source"]["revision"])
        self.assertEqual(len(run["config_sha256"]), 64)
        self.assertEqual(run["run"]["stop_reason"], "answer_generated")
        self.assertNotIn(ANSWER, json.dumps(trace))
        self.assertNotIn(PROBLEM, json.dumps(trace, ensure_ascii=False))

    def test_affine_radical_equation_checks_exact_rational_bounds_and_scaled_coefficients(self) -> None:
        problem = "Solve sqrt(8*x+9)=2*x+1."
        answer = increment(
            {"kind": "necessary_conditions", "radicand_lower_bound": "-9/8", "rhs_lower_bound": "-1/2"},
            {"kind": "candidate_constraint", "coefficients": ["2", "-2", "-4"], "direction": "forward"},
            {"kind": "candidate_coverage", "candidates": ["2", "-1"]},
            {"kind": "original_equation_filter", "accepted": ["2"], "rejected": ["-1"]},
            answer="Only 2 also satisfies the original equation.\nSolution set: {2}",
        )
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(DeterministicModelPort(answer)).run(problem, output_root=Path(directory))

        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["verification"]["completeness"]["solutions"], ["2"])
        self.assertEqual(run["verification"]["checks"][0]["evidence"]["lower_bound"], "-1/2")

    def test_only_checking_one_root_verifies_membership_without_granting_completeness(self) -> None:
        reply = increment({"kind": "original_equation_filter", "accepted": ["3"], "rejected": []})
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(DeterministicModelPort(reply)).run(PROBLEM, output_root=Path(directory))

        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
        self.assertEqual(run["verification"]["structure"], "valid")
        self.assertEqual(run["verification"]["review"]["status"], "unknown")
        (substitution,) = run["verification"]["checks"]
        self.assertEqual(substitution["status"], "verified")
        self.assertEqual(substitution["evidence"]["accepted"], ["3"])
        self.assertIsNone(substitution["goal_id"])

    def test_unguarded_equivalence_cannot_complete_the_certificate(self) -> None:
        equivalence = {**CHECKS[1], "direction": "equivalent"}
        reply = increment(CHECKS[0], equivalence, *CHECKS[2:])
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(DeterministicModelPort(reply)).run(PROBLEM, output_root=Path(directory))

        self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
        _, step, *_ = run["verification"]["checks"]
        self.assertEqual(step["status"], "unknown")
        self.assertEqual(step["reason"], "missing_equivalence_premise")

    def test_unsupported_criterion_cannot_grade_free_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(DeterministicModelPort(ANSWER)).run(
                "Solve x^5 + x = 1.", output_root=Path(directory),
            )

        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertEqual(run["verification"]["reason"], "no_applicable_criterion")

    def test_irrational_candidates_and_self_reported_review_do_not_complete_the_certificate(self) -> None:
        reply = json.dumps({
            "answer": "The positive root of the resulting quadratic.",
            "checks": [
                {"kind": "necessary_conditions", "radicand_lower_bound": "-1", "rhs_lower_bound": "0"},
                {"kind": "candidate_coverage", "candidates": ["1"]},
            ],
            "review": {"status": "reviewed"},
        })
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(DeterministicModelPort(reply)).run("sqrt(x+1)=x", output_root=Path(directory))

        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertEqual(run["verification"]["review"]["status"], "unknown")
        self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
        conditions, coverage = run["verification"]["checks"]
        self.assertEqual(conditions["status"], "verified")
        self.assertEqual(coverage["status"], "unknown")

    def test_complete_certificate_is_bound_to_an_unambiguous_free_answer(self) -> None:
        cases = {
            "Solution set: {-2, 3}": "failed",
            "The answer is the positive number discussed above.": "unknown",
        }
        with tempfile.TemporaryDirectory() as directory:
            for answer, expected in cases.items():
                with self.subTest(answer=answer):
                    run = Runtime(DeterministicModelPort(increment(*CHECKS, answer=answer))).run(
                        PROBLEM, output_root=Path(directory),
                    )
                    self.assertEqual(run["result"]["answer"], answer)
                    self.assertEqual(run["verification"]["status"], expected)
                    self.assertEqual(run["verification"]["completeness"]["solutions"], ["3"])

    def test_root_request_budget_blocks_admission_and_then_limits_continuation(self) -> None:
        for limit in (0, 1):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory() as directory:
                port = ScriptedModelPort(ModelReply(increment(CHECKS[0])))
                run = Runtime(port).run(PROBLEM, model_request_limit=limit, output_root=Path(directory))

                self.assertEqual(len(port.prompts), limit)
                self.assertEqual(run["budget"]["model_requests"], {"limit": limit, "used": limit})
                self.assertEqual(run["run"]["stop_reason"], "model_request_budget_exhausted")
                self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
                self.assertEqual(len(run["verification"]["goals"]), 4)
                if limit:
                    self.assertEqual(run["result"]["answer"], ANSWER)
                else:
                    self.assertIsNone(run["result"])

    def test_second_increment_reuses_verified_checks_and_freezes_goals_once(self) -> None:
        port = ScriptedModelPort(
            ModelReply(increment(*CHECKS[:2], answer="I derived the squared constraint.")),
            ModelReply(increment(*CHECKS[2:])),
        )
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port).run(PROBLEM, model_request_limit=3, output_root=Path(directory))
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 2)
        self.assertNotIn(ANSWER, port.prompts[0])
        self.assertNotIn('\"-2\"', port.prompts[0])
        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 3, "used": 2})
        self.assertEqual(sum(event["event"] == "verification_goals_frozen" for event in trace), 1)
        for check in run["verification"]["supporting_checks"]:
            self.assertIn(check["evidence_id"], port.prompts[1])

    def test_later_remote_unknown_stops_without_retry_and_retains_supported_result(self) -> None:
        failure = ModelPortFailure("inert unredacted provider failure")
        failure.request_sent = True
        partial_answer = "The principal square root requires a nonnegative right-hand side."
        port = ScriptedModelPort(
            ModelReply(
                increment(CHECKS[0], answer=partial_answer), model=ScriptedModelPort.name,
                input_tokens=20, output_tokens=8, usage_source="fixture",
            ),
            failure,
        )
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port).run(PROBLEM, model_request_limit=4, output_root=Path(directory))
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")

        self.assertEqual(len(port.prompts), 2)
        self.assertEqual(run["run"]["stop_reason"], "unknown_outcome")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 4, "used": 2})
        self.assertEqual(run["usage"]["tokens"], "unknown")
        self.assertEqual(run["provider_requests"][0]["usage"]["output_tokens"], 8)
        self.assertIs(run["provider_requests"][1]["request_sent"], True)
        self.assertEqual(run["provider_requests"][1]["status"], "unknown_outcome")
        self.assertEqual(run["result"]["answer"], partial_answer)
        self.assertEqual(run["verification"]["checks"][0]["status"], "verified")
        self.assertNotIn("inert unredacted provider failure", trace + json.dumps(run))
