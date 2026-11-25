"""Offline acceptance for the paired Baseline/RiCL-State rollback slice."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ricl_runtime.port import ModelReply, ToolCall, ToolReceipt
from ricl_runtime.providers.deepseek import ProviderTimeoutError
from ricl_runtime.reasoning_state import SharedReasoningState
from ricl_runtime.rollback_experiment import RollbackCheckpoint, RollbackStep, run_rollback_pair


class ScriptedRollbackModel:
    """Use the common Runtime port to simulate deterministic repair records."""

    name = "fixture-model"
    provider = "offline"
    thinking = "none"
    max_output_tokens = 128

    def __init__(self, include_citations=True):
        self.prompts = []
        self.include_citations = include_citations

    def complete(self, problem):
        self.prompts.append(problem)
        steps = {
            line.split(": evidence ", 1)[0].removeprefix("Step "): line.split(": evidence ", 1)[1]
            for line in problem.splitlines()
            if line.startswith("Step ") and ": evidence " in line
        }
        baseline = "Condition: Baseline" in problem
        if baseline:
            cited = (steps["bad-step"], steps["and-step"], steps["dependent-step"])
            answer = "Evidence used: " + ", ".join(cited) + chr(10) + "Final answer: 4"
            input_tokens, output_tokens = "unknown", 90
        else:
            cited = (steps["or-step"], steps["supported-step"], steps["unrelated-step"])
            answer = "Evidence used: " + ", ".join(cited) + chr(10) + "Final answer: 4"
            input_tokens, output_tokens = 45, 38
        if not self.include_citations:
            answer = "Final answer: 4"
        return ModelReply(
            answer,
            model=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_source="offline_fixture",
            tool_calls=(ToolCall("calculator", "check fixture"),),
        )


class CountingTool:
    def __init__(self):
        self.calls = []

    def execute(self, invocation_id, call):
        self.calls.append((invocation_id, call))
        return ToolReceipt(invocation_id, "fixture-receipt", call.tool_name, True, "checked")


def make_checkpoint():
    state = SharedReasoningState()
    bad = state.add_verified_result("failed derivation", scope="checkpoint")
    good = state.add_verified_result("independent premise", scope="checkpoint")
    alternative = state.add_verified_result("alternative derivation", scope="checkpoint")
    unrelated = state.add_verified_result("unrelated verified result", scope="checkpoint")
    or_result = state.add_verified_result(
        "supported by either derivation",
        scope="checkpoint",
        depends_on_any=(bad.evidence_id, alternative.evidence_id),
    )
    and_result = state.add_verified_result(
        "requires both premises",
        scope="checkpoint",
        depends_on_all=(bad.evidence_id, good.evidence_id),
    )
    dependent = state.add_verified_result(
        "depends on the AND result", scope="checkpoint", depends_on_all=(and_result.evidence_id,)
    )
    supported = state.add_verified_result(
        "downstream conclusion retains an alternate support",
        scope="checkpoint",
        depends_on_any=(dependent.evidence_id, alternative.evidence_id),
    )
    return RollbackCheckpoint(
        problem="Compute 2 + 2.",
        problem_id="rollback-fixture",
        original_trace=("step bad-step: failed derivation", "step later-step: continue"),
        steps=(
            RollbackStep("bad-step", bad.evidence_id),
            RollbackStep("or-step", or_result.evidence_id),
            RollbackStep("and-step", and_result.evidence_id),
            RollbackStep("dependent-step", dependent.evidence_id),
            RollbackStep("supported-step", supported.evidence_id),
            RollbackStep("unrelated-step", unrelated.evidence_id),
        ),
        failed_step_id="bad-step",
        diagnosis="The derivation at bad-step is invalid.",
        reasoning_state=state,
    )


class RollbackExperimentTests(unittest.TestCase):
    def test_suffix_replay_and_and_or_invalidation_share_frozen_inputs(self):
        model = ScriptedRollbackModel()
        tool = CountingTool()
        checkpoint = make_checkpoint()
        original_state = checkpoint.reasoning_state.public_snapshot()
        with tempfile.TemporaryDirectory() as directory:
            pair = run_rollback_pair(
                model,
                checkpoint,
                output_root=Path(directory),
                tool_executor=tool,
                tool_call_limit=1,
            )
            persisted = json.loads(Path(pair["artifacts"]["run"]).read_text(encoding="utf-8"))
            trace = Path(pair["artifacts"]["trace"]).read_text(encoding="utf-8")

        baseline, treatment = model.prompts
        for shared in (
            "Checkpoint SHA256:",
            "Diagnosis:",
            "step bad-step: failed derivation",
            "Verified content:",
        ):
            self.assertIn(shared, baseline)
            self.assertIn(shared, treatment)
        self.assertEqual(
            baseline.split("Checkpoint SHA256: ")[1].splitlines()[0],
            treatment.split("Checkpoint SHA256: ")[1].splitlines()[0],
        )
        self.assertEqual(
            baseline.split("Diagnosis: ")[1].splitlines()[0],
            treatment.split("Diagnosis: ")[1].splitlines()[0],
        )
        self.assertIn(
            "Replay suffix step IDs: bad-step, or-step, and-step, dependent-step, supported-step, unrelated-step",
            baseline,
        )
        self.assertIn(
            "Recompute invalidated step IDs: bad-step, and-step, dependent-step", treatment
        )
        self.assertNotIn("Recompute invalidated step IDs", baseline)
        self.assertNotIn("Replay suffix step IDs", treatment)
        self.assertEqual(
            pair["arms"]["baseline"]["checkpoint_sha256"],
            pair["arms"]["ricl_state"]["checkpoint_sha256"],
        )
        self.assertEqual(
            pair["arms"]["baseline"]["diagnosis_sha256"],
            pair["arms"]["ricl_state"]["diagnosis_sha256"],
        )
        self.assertEqual(
            pair["arms"]["baseline"]["budget"]["model_requests"], {"limit": 1, "used": 1}
        )
        self.assertEqual(
            pair["arms"]["ricl_state"]["budget"]["model_requests"], {"limit": 1, "used": 1}
        )
        self.assertEqual(pair["arms"]["baseline"]["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertEqual(pair["arms"]["ricl_state"]["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertEqual(len(tool.calls), 2)
        self.assertEqual(checkpoint.reasoning_state.public_snapshot(), original_state)
        self.assertEqual(pair["arms"]["baseline"]["rework_tokens"], 90)
        self.assertEqual(pair["arms"]["ricl_state"]["rework_tokens"], 38)
        self.assertEqual(pair["arms"]["baseline"]["usage"]["input_tokens"], "unknown")
        self.assertEqual(pair["arms"]["baseline"]["usage"]["tokens"], "unknown")
        self.assertEqual(
            pair["arms"]["baseline"]["evidence_use"]["invalidated_evidence_ids_used"],
            pair["arms"]["ricl_state"]["rollback"]["invalidated_evidence_ids"],
        )
        self.assertTrue(
            pair["arms"]["baseline"]["evidence_use"]["continued_using_invalidated_evidence"]
        )
        self.assertFalse(
            pair["arms"]["ricl_state"]["evidence_use"]["continued_using_invalidated_evidence"]
        )
        self.assertEqual(pair["arms"]["baseline"]["verification"]["status"], "verified")
        self.assertEqual(pair["arms"]["ricl_state"]["verification"]["status"], "verified")
        self.assertEqual(persisted, pair)
        self.assertNotIn("Compute 2 + 2.", trace)
        self.assertNotIn("The derivation at bad-step is invalid.", trace)
        self.assertNotIn("Recomputed invalidated steps.", trace)

    def test_missing_evidence_citations_remain_unknown(self):
        model = ScriptedRollbackModel(include_citations=False)
        with tempfile.TemporaryDirectory() as directory:
            pair = run_rollback_pair(model, make_checkpoint(), output_root=Path(directory))
        for arm in pair["arms"].values():
            self.assertEqual(arm["evidence_use"]["status"], "unknown")
            self.assertEqual(arm["evidence_use"]["continued_using_invalidated_evidence"], "unknown")

    def test_randomized_pair_keeps_timeout_and_both_denominator_entries(self):
        model = ScriptedRollbackModel()
        real_complete = model.complete

        def fail_baseline(prompt):
            if "Condition: Baseline" in prompt:
                raise ProviderTimeoutError("private fixture error")
            return real_complete(prompt)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(model, "complete", side_effect=fail_baseline) as complete,
        ):
            pair = run_rollback_pair(
                model, make_checkpoint(), output_root=Path(directory), order_seed=1
            )
            artifact = Path(pair["artifacts"]["run"]).read_text(encoding="utf-8")
        self.assertEqual(pair["condition_order"], ["ricl_state", "baseline"])
        self.assertEqual(pair["pair_status"], "incomplete")
        baseline = pair["arms"]["baseline"]
        self.assertEqual(baseline["stop_reason"], "timeout")
        self.assertEqual(baseline["rework_tokens"], "unknown")
        self.assertEqual(
            baseline["evidence_use"]["continued_using_invalidated_evidence"], "unknown"
        )
        self.assertEqual(pair["arms"]["ricl_state"]["status"], "completed")
        self.assertEqual(complete.call_count, 2)
        self.assertNotIn("private fixture error", artifact)

    def test_provider_backed_ports_are_rejected_before_any_request(self):
        model = ScriptedRollbackModel()
        model.provider = "remote"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "offline"):
                run_rollback_pair(model, make_checkpoint(), output_root=Path(directory))
        self.assertEqual(model.prompts, [])


if __name__ == "__main__":
    unittest.main()
