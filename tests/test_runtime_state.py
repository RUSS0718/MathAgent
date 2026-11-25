"""Offline behavior checks for shared reasoning state and Runtime consumption."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ricl_runtime import ModelReply, Runtime, SharedReasoningState, ToolCall, ToolReceipt


class ScriptedModelPort:
    """Record sent prompts while returning fixed offline replies."""

    name = "scripted-offline"

    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = iter(replies)
        self.prompts: list[str] = []

    def complete(self, problem: str) -> ModelReply:
        self.prompts.append(problem)
        return next(self.replies)


class ScriptedToolExecutor:
    """Return one successful receipt for a controlled invocation."""

    def __init__(self, success: bool = True) -> None:
        self.calls: list[tuple[str, ToolCall]] = []
        self.success = success

    def execute(self, invocation_id: str, call: ToolCall) -> ToolReceipt:
        self.calls.append((invocation_id, call))
        return ToolReceipt(invocation_id, "receipt-1", call.tool_name, self.success, "4")


class SharedReasoningStateTests(unittest.TestCase):
    """Check dependency validity and observable Runtime behavior."""

    def test_and_or_dependencies_invalidate_only_when_their_rule_is_broken(self) -> None:
        state = SharedReasoningState()
        premise = state.add_verified_result("premise")
        required = state.add_verified_result("requires premise", depends_on_all=(premise.evidence_id,))
        alternative = state.add_verified_result("independent alternative")
        either = state.add_verified_result(
            "requires one path", depends_on_any=(required.evidence_id, alternative.evidence_id)
        )
        both = state.add_verified_result(
            "requires both", depends_on_all=(required.evidence_id, alternative.evidence_id)
        )

        state.invalidate(premise.evidence_id)

        self.assertFalse(state.is_valid(required.evidence_id))
        self.assertNotIn(required.evidence_id, {item.evidence_id for item in state.valid_evidence()})
        self.assertTrue(state.is_valid(alternative.evidence_id))
        self.assertTrue(state.is_valid(either.evidence_id))
        self.assertFalse(state.is_valid(both.evidence_id))
        state.invalidate(alternative.evidence_id)
        self.assertFalse(state.is_valid(either.evidence_id))
        self.assertNotIn(either.evidence_id, {item.evidence_id for item in state.valid_evidence()})
        with self.assertRaises(ValueError):
            state.add_verified_result("stale", depends_on_all=(premise.evidence_id,))

    def test_result_and_evidence_ids_are_stable(self) -> None:
        first = SharedReasoningState().add_verified_result("four", scope="2 + 2")
        second = SharedReasoningState().add_verified_result("four", scope="2 + 2")
        self.assertEqual(first.evidence_id, second.evidence_id)
        self.assertEqual(first.result_id, second.result_id)

    def test_only_correlated_success_receipt_can_become_tool_evidence(self) -> None:
        state = SharedReasoningState()
        call = ToolCall("calculator", "2+2")
        invalid_receipts = (
            None,
            ToolReceipt("wrong", "r1", "calculator", True, "4"),
            ToolReceipt("invocation", "r2", "calculator", False, "4"),
            "model claims calculator returned 4",
        )
        for receipt in invalid_receipts:
            with self.subTest(receipt=receipt), self.assertRaises(ValueError):
                state.add_tool_receipt(receipt, invocation_id="invocation", call=call)
        self.assertEqual(state.public_snapshot(), [])

    def test_verified_result_is_in_later_sent_request_and_trace_only_proves_sending(self) -> None:
        port = ScriptedModelPort([ModelReply("4"), ModelReply("4")])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run(
                "Compute 2 + 2.", output_root=Path(directory), reasoning_state_enabled=True,
                model_request_limit=2,
            )
            trace = Path(result["artifacts"]["trace"]).read_text(encoding="utf-8")
            events = [json.loads(line) for line in trace.splitlines()]

        evidence = result["evidence"][0]
        sent = next(event for event in events if event.get("request_id", "").endswith("_002"))
        self.assertIn(evidence["evidence_id"], port.prompts[1])
        self.assertIn(evidence["result_id"], port.prompts[1])
        self.assertIn("4", port.prompts[1])
        self.assertEqual(sent["referenced_evidence_ids"], [evidence["evidence_id"]])
        self.assertEqual(sent["context_sha256"], hashlib.sha256(port.prompts[1].encode()).hexdigest())
        self.assertFalse(any(event["event"] == "model_adopted_evidence" for event in events))
        self.assertNotIn("Compute 2 + 2.", trace)
        self.assertNotIn('"content": "4"', trace)
        self.assertEqual(result["budget"]["model_requests"], {"limit": 2, "used": 2})

    def test_baseline_uses_tool_receipts_in_ordinary_context(self) -> None:
        port = ScriptedModelPort([
            ModelReply("5", tool_calls=(ToolCall("calculator", "2+2"),)),
            ModelReply("4"),
        ])
        executor = ScriptedToolExecutor()
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port, tool_executor=executor).run(
                "Compute 2 + 2.", output_root=Path(directory),
                visible_context="Use exact arithmetic.", model_request_limit=2, tool_call_limit=1,
            )
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")

        self.assertEqual(run["budget"]["model_requests"], {"limit": 2, "used": 2})
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertIn("Use exact arithmetic.", port.prompts[1])
        self.assertIn("Tool results:\ncalculator: 4", port.prompts[1])
        self.assertNotIn("Verified context:", port.prompts[1])
        self.assertNotIn("calculator: 4", trace)

    def test_tool_failure_persists_the_run_without_resending(self) -> None:
        port = ScriptedModelPort([ModelReply("4", tool_calls=(ToolCall("calculator", "2+2"),))])
        executor = ScriptedToolExecutor()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(executor, "execute", side_effect=OSError("private tool exception")),
        ):
            run = Runtime(port, tool_executor=executor).run(
                "Compute 2 + 2.", output_root=Path(directory), model_request_limit=2, tool_call_limit=1,
            )
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")
        self.assertEqual(run["run"]["stop_reason"], "tool_failed")
        self.assertEqual(run["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertEqual(len(port.prompts), 1)
        self.assertIn("tool_execution_failed", trace)
        self.assertNotIn("private tool exception", trace + json.dumps(run))

    def test_disabled_state_preserves_plain_request_and_independent_verifier(self) -> None:
        port = ScriptedModelPort([ModelReply("4")])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run("Compute 2 + 2.", output_root=Path(directory))
        self.assertEqual(port.prompts, ["Compute 2 + 2."])
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertEqual(result["evidence"], [])

    def test_model_tool_claim_without_executor_does_not_create_evidence(self) -> None:
        port = ScriptedModelPort([
            ModelReply("I used a calculator.", tool_calls=(ToolCall("calculator", "2+2"),)),
            ModelReply("4"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run(
                "Compute 2 + 2.", output_root=Path(directory), reasoning_state_enabled=True,
                model_request_limit=2, tool_call_limit=1,
            )
        self.assertFalse(any(item["source"] == "controlled_tool" for item in result["evidence"]))
        self.assertEqual(result["budget"]["tools"], {"limit": 1, "used": 0})

    def test_receipt_is_cited_and_tool_attempts_share_run_limit(self) -> None:
        port = ScriptedModelPort([
            ModelReply("4", tool_calls=(ToolCall("calculator", "2+2"),)),
            ModelReply("4", tool_calls=(ToolCall("calculator", "3+3"),)),
        ])
        executor = ScriptedToolExecutor()
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port, tool_executor=executor).run(
                "Compute 2 + 2.", output_root=Path(directory), reasoning_state_enabled=True,
                model_request_limit=2, tool_call_limit=1,
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        tool_item = next(item for item in result["evidence"] if item["source"] == "controlled_tool")
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(result["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertIn(tool_item["evidence_id"], port.prompts[1])
        self.assertIn("4", port.prompts[1])
        self.assertTrue(
            any(
                event["event"] == "tool_call_not_executed"
                and event["reason"] == "tool_budget_exhausted"
                and event["request_id"].endswith("_002")
                for event in events
            )
        )

    def test_failed_receipt_is_not_reused(self) -> None:
        port = ScriptedModelPort([
            ModelReply("calculator", tool_calls=(ToolCall("calculator", "2+2"),)),
            ModelReply("4"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port, tool_executor=ScriptedToolExecutor(False)).run(
                "Compute 2 + 2.", output_root=Path(directory), reasoning_state_enabled=True,
                model_request_limit=2, tool_call_limit=1,
            )
        self.assertFalse(any(item["source"] == "controlled_tool" for item in result["evidence"]))
        self.assertNotIn("receipt-1", port.prompts[1])

    def test_no_progress_gets_one_diagnosis_then_stops(self) -> None:
        port = ScriptedModelPort(
            [ModelReply("5"), ModelReply("6"), ModelReply("6"), ModelReply("6")]
        )
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run(
                "Compute 2 + 2.", output_root=Path(directory), reasoning_state_enabled=True,
                model_request_limit=5,
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(len(port.prompts), 4)
        self.assertEqual(result["result"]["answer"], "6")
        self.assertEqual(sum(event.get("request_kind") == "diagnosis" for event in events), 1)
        self.assertEqual(result["run"]["stop_reason"], "no_progress")
        self.assertEqual(
            [event["substantive_change"] for event in events if event["event"] == "progress_checked"],
            [True, True, False, False],
        )


if __name__ == "__main__":
    unittest.main()
