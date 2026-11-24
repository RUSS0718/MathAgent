"""Offline acceptance tests for paired Runtime counterfactual execution."""

import json
import tempfile
import unittest
from pathlib import Path

from ricl_runtime import (
    CounterfactualCheckpoint,
    DeterministicModelPort,
    InterventionAudit,
    ModelReply,
    Runtime,
    SharedReasoningState,
)


class ScriptedModelPort:
    """Capture deterministic branch prompts without contacting a Provider."""

    name = "scripted-counterfactual"

    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = iter(replies)
        self.prompts: list[str] = []

    def complete(self, problem: str) -> ModelReply:
        self.prompts.append(problem)
        return next(self.replies)


class CounterfactualRuntimeTests(unittest.TestCase):
    """Exercise paired branches only through the Runtime's public interface."""

    def _run(
        self,
        *,
        audit: object,
        feedback_kind: str = "diagnostic",
        treatment_answer: str = "4",
    ):
        state = SharedReasoningState()
        premise = state.add_verified_result("known premise", scope="checkpoint")
        checkpoint = CounterfactualCheckpoint(
            visible_prefix="We have reached a failed verification.",
            failure_count=1,
            trigger_count=0,
            current_action="continue",
            current_route=None,
            reasoning_state=state,
        )
        port = ScriptedModelPort([
            ModelReply("4", action="continue", route=None),
            ModelReply(treatment_answer, action="diagnose", route=None),
        ])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_counterfactual(
                "Compute 2 + 2.",
                checkpoint=checkpoint,
                intervention_feedback="Recheck the arithmetic.",
                feedback_kind=feedback_kind,
                intervention_auditor=lambda feedback, reply: audit,
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        return result, events, port, premise

    def test_pair_shares_checkpoint_and_budget_without_requiring_a_search_route(self) -> None:
        result, events, port, premise = self._run(
            audit=InterventionAudit(
                status="approved", source="offline-independent-review", feedback_consumed=True
            )
        )

        self.assertEqual(len(port.prompts), 2)
        self.assertEqual(port.prompts[0].split("\n\nIntervention feedback:")[0], port.prompts[1].split("\n\nIntervention feedback:")[0])
        self.assertNotIn("Recheck the arithmetic.", port.prompts[0])
        self.assertIn("Recheck the arithmetic.", port.prompts[1])
        self.assertEqual(result["budget"]["model_requests"], {"limit": 2, "used": 2})
        self.assertEqual(result["branches"]["control"]["verification"]["status"], "verified")
        self.assertEqual(result["branches"]["treatment"]["verification"]["status"], "verified")
        self.assertEqual(
            result["branches"]["control"]["checkpoint_sha256"],
            result["branches"]["treatment"]["checkpoint_sha256"],
        )
        self.assertIsNone(result["branches"]["control"]["route"])
        self.assertTrue(result["intervention"]["feedback_available_to_parent"])
        self.assertTrue(result["intervention"]["feedback_consumed_by_parent"])
        self.assertEqual(result["intervention"]["parent_feedback"], "4")
        self.assertEqual(result["parent_evidence"][0]["evidence_id"], premise.evidence_id)
        self.assertEqual(sum(event["event"] == "counterfactual_trigger_evaluated" for event in events), 1)
        consumed = next(event for event in events if event["event"] == "intervention_feedback_consumed")
        self.assertTrue(consumed["feedback_consumed"])
        self.assertTrue(any(event["event"] == "intervention_action_change_observed" for event in events))
        self.assertTrue(any(event["event"] == "intervention_route_change_observed" for event in events))

    def test_route_change_is_recorded_separately_and_can_be_effective(self) -> None:
        checkpoint = CounterfactualCheckpoint(
            visible_prefix="failed verification", failure_count=1, current_route=None
        )
        port = ScriptedModelPort([
            ModelReply("4", action="continue", route=None),
            ModelReply("4", action="continue", route="diagnostic"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_counterfactual(
                "Compute 2 + 2.", checkpoint=checkpoint,
                intervention_feedback="Recheck the arithmetic.",
                intervention_auditor=lambda feedback, reply: InterventionAudit(
                    status="approved", source="offline-independent-review", feedback_consumed=True
                ),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        self.assertFalse(result["intervention"]["action_changed"])
        self.assertTrue(result["intervention"]["route_changed"])
        route_event = next(event for event in events if event["event"] == "intervention_route_change_observed")
        self.assertTrue(route_event["changed"])
        self.assertTrue(result["intervention"]["feedback_consumed_by_parent"])

    def test_unapproved_or_unconsumed_feedback_is_never_exposed_to_parent(self) -> None:
        for audit in (
            InterventionAudit(status="rejected", source="offline-independent-review", feedback_consumed=True),
            InterventionAudit(status="approved", source="offline-independent-review", feedback_consumed=False),
        ):
            with self.subTest(audit=audit):
                result, events, _, _ = self._run(audit=audit)
                self.assertFalse(result["intervention"]["feedback_available_to_parent"])
                self.assertFalse(result["intervention"]["feedback_consumed_by_parent"])
                self.assertIsNone(result["intervention"]["parent_feedback"])
                consumed = next(event for event in events if event["event"] == "intervention_feedback_consumed")
                self.assertFalse(consumed["feedback_consumed"])
                self.assertEqual(
                    consumed["treatment_reported_feedback_consumed"], audit.feedback_consumed
                )

    def test_feedback_requires_an_effective_change_and_verified_treatment_outcome(self) -> None:
        cases = (
            (ModelReply("4", action="continue"), ModelReply("4", action="continue")),
            (ModelReply("4", action="continue"), ModelReply("5", action="diagnose")),
        )
        for control_reply, treatment_reply in cases:
            with self.subTest(treatment=treatment_reply):
                state = SharedReasoningState()
                checkpoint = CounterfactualCheckpoint(
                    visible_prefix="failed verification",
                    failure_count=1,
                    reasoning_state=state,
                )
                port = ScriptedModelPort([control_reply, treatment_reply])
                with tempfile.TemporaryDirectory() as directory:
                    result = Runtime(port).run_counterfactual(
                        "Compute 2 + 2.",
                        checkpoint=checkpoint,
                        intervention_feedback="Recheck the arithmetic.",
                        intervention_auditor=lambda feedback, reply: InterventionAudit(
                            status="approved", source="offline-independent-review", feedback_consumed=True
                        ),
                        output_root=Path(directory),
                    )
                self.assertFalse(result["intervention"]["feedback_available_to_parent"])
                self.assertFalse(result["intervention"]["feedback_consumed_by_parent"])
                self.assertIsNone(result["intervention"]["parent_feedback"])
                self.assertEqual(result["parent_evidence"], checkpoint.reasoning_state.public_snapshot())

    def test_checkpoint_trigger_count_prevents_repeated_intervention(self) -> None:
        checkpoint = CounterfactualCheckpoint(visible_prefix="failed", failure_count=1)
        replies = [ModelReply("4", action="continue"), ModelReply("4", action="diagnose")]
        with tempfile.TemporaryDirectory() as directory:
            first = Runtime(ScriptedModelPort(replies)).run_counterfactual(
                "Compute 2 + 2.", checkpoint=checkpoint,
                intervention_feedback="Recheck the arithmetic.", output_root=Path(directory),
            )
            second = Runtime(DeterministicModelPort("4")).run_counterfactual(
                "Compute 2 + 2.", checkpoint=checkpoint,
                intervention_feedback="unused", output_root=Path(directory),
            )
        self.assertEqual(first["intervention"]["trigger_count_after"], 1)
        self.assertEqual(checkpoint.trigger_count, 1)
        self.assertNotIn("intervention", second)

    def test_unknown_or_malformed_audit_does_not_consume_feedback_in_parent(self) -> None:
        audits = (
            InterventionAudit(status="unknown", source="offline-independent-review", feedback_consumed=True),
            object(),
        )
        for audit in audits:
            with self.subTest(audit=audit):
                result, events, _, _ = self._run(audit=audit)
                self.assertFalse(result["intervention"]["feedback_consumed_by_parent"])
                consumed = next(event for event in events if event["event"] == "intervention_feedback_consumed")
                self.assertFalse(consumed["feedback_consumed"])

    def test_unverified_treatment_does_not_consume_feedback_in_parent(self) -> None:
        result, events, _, _ = self._run(
            audit=InterventionAudit(
                status="approved", source="offline-independent-review", feedback_consumed=True
            ),
            treatment_answer="not an integer",
        )
        self.assertEqual(result["branches"]["treatment"]["verification"]["status"], "unknown")
        self.assertFalse(result["intervention"]["feedback_consumed_by_parent"])
        self.assertEqual(result["parent_evidence"], result["checkpoint"]["evidence"])
        self.assertEqual(
            result["branches"]["control"]["evidence"][0], result["checkpoint"]["evidence"][0]
        )
        self.assertEqual(
            result["branches"]["treatment"]["evidence"], result["checkpoint"]["evidence"]
        )
        consumed = next(event for event in events if event["event"] == "intervention_feedback_consumed")
        self.assertFalse(consumed["feedback_consumed"])

    def test_trigger_is_bounded_and_off_mode_emits_no_intervention_events(self) -> None:
        state = SharedReasoningState()
        exhausted = CounterfactualCheckpoint(
            visible_prefix="failed", failure_count=1, trigger_count=1, reasoning_state=state
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("4")).run_counterfactual(
                "Compute 2 + 2.", checkpoint=exhausted,
                intervention_feedback="unused", output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(result["budget"]["model_requests"]["used"], 1)
        self.assertEqual(exhausted.trigger_count, 1)
        self.assertNotIn("intervention", result)
        self.assertFalse(any("intervention" in event["event"] or "counterfactual" in event["event"] for event in events))

        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("4")).run_counterfactual(
                "Compute 2 + 2.", checkpoint=CounterfactualCheckpoint(
                    visible_prefix="failed", failure_count=1, reasoning_state=SharedReasoningState()
                ),
                intervention_feedback="unused", enabled=False, output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        self.assertNotIn("intervention", result)
        self.assertFalse(any("intervention" in event["event"] or "counterfactual" in event["event"] for event in events))

    def test_random_and_diagnostic_conditions_get_equal_branch_opportunity_and_budget(self) -> None:
        for kind in ("random", "diagnostic"):
            with self.subTest(kind=kind):
                result, _, port, _ = self._run(
                    audit=InterventionAudit(
                        status="approved", source="offline-independent-review", feedback_consumed=True
                    ),
                    feedback_kind=kind,
                )
                self.assertEqual(len(port.prompts), 2)
                self.assertEqual(result["budget"]["model_requests"], {"limit": 2, "used": 2})
                self.assertEqual(result["branches"]["control"]["request_count"], 1)
                self.assertEqual(result["branches"]["treatment"]["request_count"], 1)
                self.assertEqual(result["intervention"]["feedback_kind"], kind)
                self.assertTrue(result["intervention"]["qualified"])


if __name__ == "__main__":
    unittest.main()
