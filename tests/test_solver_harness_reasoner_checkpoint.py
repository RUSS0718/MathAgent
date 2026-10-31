"""Public Reasoner checkpoint handoff contracts for CP-04."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error

PLAN = {
    "version": 1,
    "steps": [{"step_id": "s1", "title": "证明", "objective": "derive"}],
}
FEATURES = {"reasoner_checkpoints": True, "meta_guidance": True}
CHALLENGE = {
    "goal_gate": "PARTIAL",
    "logic_gate": "UNCERTAIN",
    "verdict": "CHALLENGE",
    "objection": "close the missing implication",
}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}


def checkpoint(status="YIELD", *, marker="cp-1", blocked=False, tool_request=None):
    claim = {"statement": marker, "label": "hard-verify"}
    if tool_request is not None:
        claim = {"statement": marker, "label": "easy-verify", "tool_request": tool_request}
    return {
        "checkpoint": {
            "protocol_version": 1,
            "checkpoint_id": marker,
            "status": status,
        "objective": "derive",
            "argument": marker,
            "claims": [claim],
            "blocked": blocked,
            "dependencies": [],
            "evidence": [marker],
            "gaps": ["finish the implication"] if status == "YIELD" else [],
            "next_action": "finish the implication",
        }
    }


class ReasonerCheckpointTest(unittest.TestCase):
    def test_checkpoint_challenge_then_reasoner_response_reuses_verifier_gates(self):
        model = ScriptedModelPort([
            checkpoint(marker="cp-1"),
            checkpoint("FINAL", marker="cp-2"),
        ])
        verifier = ScriptedVerifierPort([CHALLENGE, ACCEPT])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 4},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-challenge", "plan": PLAN})

        state = result["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(["cp-1", "cp-2"], [item["checkpoint_id"] for item in state["reasoner_checkpoints"]])
        self.assertEqual(["s1"], [item["source"] for item in state["accepted_results"]])
        self.assertEqual(2, len(verifier.requests))
        self.assertEqual("cp-1", verifier.requests[0]["checkpoint"]["checkpoint_id"])
        self.assertEqual("cp-2", verifier.requests[1]["checkpoint"]["checkpoint_id"])
        self.assertEqual("close the missing implication", model.requests[1]["objection"])
        self.assertEqual("cp-1", model.requests[1]["parent_checkpoint_id"])

    def test_checkpoint_can_request_meta_guidance_then_continue(self):
        model = ScriptedModelPort([
            checkpoint(marker="blocked", blocked=True),
            checkpoint("FINAL", marker="guided"),
        ])
        meta = ScriptedModelPort([
            {
                "action_type": "retry_different_method",
                "specific_task": "derive a symbolic bound",
                "use_pure_reasoning": True,
                "trace_back_to": None,
                "rationale": "the first route is blocked",
            }
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 4},
            model_port=model,
            verifier_port=ScriptedVerifierPort([ACCEPT]),
            meta_port=meta,
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-guidance", "plan": PLAN})

        state = result["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual("retry_different_method", state["meta_guidance_decision"]["action_type"])
        self.assertEqual("derive a symbolic bound", model.requests[1]["specific_task"])
        self.assertEqual(["reasoner", "reasoner"], [item["role"] for item in model.requests])
        self.assertEqual("meta", meta.requests[0]["role"])

    def test_checkpoint_tool_request_uses_existing_real_receipt_precheck(self):
        from showcase.solver_harness import ScriptedToolPort

        tool_request = {
            "tool": "polynomial_check",
            "arguments": {"coefficients": [1]},
            "scope": "finite_computation",
            "expected_output": {"value": 4},
        }
        model = ScriptedModelPort([
            checkpoint(marker="computed", tool_request=tool_request),
            checkpoint("FINAL", marker="finished"),
        ])
        verifier = ScriptedVerifierPort([ACCEPT, ACCEPT])
        tool = ScriptedToolPort([{"status": "success", "output": {"value": 4}, "exit_code": 0}])
        with SolverHarness(
            config={
                "features": {**FEATURES, "local_code_tool": True},
                "allowed_tools": ["polynomial_check"],
                "max_model_calls": 5,
            },
            model_port=model,
            verifier_port=verifier,
            tool_port=tool,
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-tool", "plan": PLAN})

        receipt = result["state"]["tool_receipts"][0]
        self.assertEqual("success", receipt["status"])
        self.assertEqual([receipt["receipt_id"]], verifier.requests[0]["report"]["tool_evidence_refs"])
        self.assertEqual("verified", verifier.requests[0]["report"]["claims"][0]["label"])
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])

    def test_streaming_checkpoint_response_is_optional_and_keeps_same_handoff(self):
        class StreamModel:
            def __init__(self):
                self.requests = []

            def complete(self, request):
                self.requests.append(dict(request))
                marker = "stream-1" if len(self.requests) == 1 else "stream-final"
                return iter([
                    {"type": "text_delta", "text": "checkpoint"},
                    {"result": checkpoint("FINAL", marker=marker)},
                ])

        model = StreamModel()
        with SolverHarness(
            config={"features": {**FEATURES, "stream_recovery": True}, "max_model_calls": 3},
            model_port=model,
            verifier_port=ScriptedVerifierPort([ACCEPT]),
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-stream", "plan": PLAN})
        self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
        self.assertEqual("completed", next(iter(result["state"]["calls"].values()))["status"])

    def test_checkpoint_round_limit_stops_without_a_third_reasoner_dispatch(self):
        model = ScriptedModelPort([
            checkpoint(marker="round-1"),
            checkpoint(marker="round-2"),
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 5},
            model_port=model,
            verifier_port=ScriptedVerifierPort([ACCEPT, ACCEPT]),
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-limit", "plan": PLAN})
        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertEqual("reasoner_checkpoint_round_limit", result["state"]["result_reason"])
        self.assertEqual(2, len(model.requests))

    def test_product_presets_keep_checkpoint_feature_explicit(self):
        from showcase.run_budget import RunBudgetLimits
        from showcase.star_product_config import limited_config

        config = limited_config(RunBudgetLimits(max_model_calls=4, max_http_attempts=4, max_tool_calls=0))
        self.assertNotIn("reasoner_checkpoints", config["features"])
        enabled = limited_config(
            RunBudgetLimits(max_model_calls=4, max_http_attempts=4, max_tool_calls=0),
            {"reasoner_checkpoints": True},
        )
        self.assertTrue(enabled["features"]["reasoner_checkpoints"])

    def test_checkpoint_traceback_and_approved_replan_keep_new_identities(self):
        trace_model = ScriptedModelPort([
            checkpoint("FINAL", marker="old"),
            checkpoint("FINAL", marker="new"),
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 4},
            model_port=trace_model,
            verifier_port=ScriptedVerifierPort([
                {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK", "trace_back_to": 1},
                ACCEPT,
            ]),
        ) as harness:
            traced = harness.solve("prove", {"run_id": "checkpoint-trace", "plan": PLAN})
        self.assertEqual(1, traced["state"]["attempt_index"])
        self.assertNotEqual(trace_model.requests[0]["call_id"], trace_model.requests[1]["call_id"])
        self.assertEqual("trace_back", traced["state"]["failure_records"][0]["kind"])

        replan_model = ScriptedModelPort([
            checkpoint("FINAL", marker="before-replan"),
            {**PLAN, "version": 2},
            checkpoint("FINAL", marker="after-replan"),
        ])
        meta = ScriptedModelPort([
            {
                "decision": "APPROVE_REPLAN",
                "reason_summary": "use a new plan",
                "plan_summary": "replace the blocked route",
                "forbidden_directions": ["old route"],
                "reusable_results": [],
                "trace_back_to": None,
            }
        ])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 6},
            model_port=replan_model,
            verifier_port=ScriptedVerifierPort([
                {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN", "objection": "change route"},
                ACCEPT,
            ]),
            meta_port=meta,
        ) as harness:
            replanned = harness.solve("prove", {"run_id": "checkpoint-replan", "plan": PLAN})
        self.assertEqual(2, replanned["state"]["plan_version"])
        self.assertEqual("after-replan", replanned["state"]["reasoner_checkpoints"][-1]["checkpoint_id"])
        self.assertEqual("before-replan", replanned["state"]["failure_records"][0]["archived_steps"]["s1"]["report"]["argument"])

    def test_recovery_does_not_replay_checkpoint_tool_or_stale_revision(self):
        class Crash(BaseException):
            pass

        class CrashingModel:
            owner = None

            def complete(self, request):
                snapshot = self.owner.get_run(request["run_id"])
                self_test.assertLess(request["state_revision"], snapshot["state_revision"])
                raise Crash()

        self_test = self
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "checkpoint.db"
            with SolverHarness(
                database_path=database,
                config={"features": {"reasoner_checkpoints": True, "stream_recovery": True}},
                model_port=CrashingModel(),
            ) as harness:
                harness._model_port.owner = harness
                with self.assertRaises(Crash):
                    harness.solve("prove", {"run_id": "checkpoint-recovery", "plan": PLAN})
            replacement = ScriptedModelPort([checkpoint("FINAL", marker="recovered")])
            with SolverHarness(
                database_path=database,
                config={"features": {"reasoner_checkpoints": True, "stream_recovery": True}},
                model_port=replacement,
            ) as recovered:
                result = recovered.solve("prove", {"run_id": "checkpoint-recovery", "plan": PLAN})
            self.assertEqual([], replacement.requests)
            self.assertEqual("unknown_outcome", next(iter(result["state"]["calls"].values()))["status"])

    def test_schema_and_disabled_feature_preserve_old_reasoner_contract(self):
        schema = response_schema({"role": "reasoner", "checkpoint_protocol": True})
        valid = checkpoint()["checkpoint"]
        self.assertIsNone(schema_error({"checkpoint": valid}, schema))
        self.assertIsNotNone(schema_error({"checkpoint": {**valid, "unexpected": True}}, schema))

        wrong_goal = ScriptedModelPort([
            {"checkpoint": {**valid, "objective": "another goal"}},
        ])
        wrong_verifier = ScriptedVerifierPort([])
        with SolverHarness(
            config={"features": FEATURES, "max_model_calls": 2},
            model_port=wrong_goal,
            verifier_port=wrong_verifier,
        ) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-wrong-goal", "plan": PLAN})
        self.assertEqual("invalid_reasoner_checkpoint_objective", result["state"]["result_reason"])
        self.assertEqual([], wrong_verifier.requests)

        model = ScriptedModelPort([{"argument": "old", "claims": [], "blocked": False}])
        verifier = ScriptedVerifierPort([ACCEPT])
        with SolverHarness(model_port=model, verifier_port=verifier) as harness:
            result = harness.solve("prove", {"run_id": "checkpoint-disabled", "plan": PLAN})
        self.assertNotIn("reasoner_checkpoints", result["state"])
        self.assertNotIn("checkpoint_protocol", model.requests[0])
