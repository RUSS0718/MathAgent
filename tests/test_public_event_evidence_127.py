"""Public solver-call and tool-receipt evidence contracts for issue #127."""

from __future__ import annotations

import unittest
from copy import deepcopy

from showcase.evidence import EvidencePackExporter
from showcase.run_budget import public_solver_call_id
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.calls import CallInterrupted
from showcase.solver_harness.tool_precheck import precheck_report
from showcase.star_product_events import decision_fields, public_solver_event_id


class PublicEventEvidence127Test(unittest.TestCase):
    def _run(self, run_id, *, tool_port=None):
        harness = SolverHarness(
            config={
                "features": {"stream_recovery": True, "local_code_tool": tool_port is not None},
                "allowed_tools": ["polynomial_check"],
                "max_model_calls": 4,
                "max_tool_calls": 2,
            },
            tool_port=tool_port,
        )
        run = harness.solve("private question", {"run_id": run_id})
        run = harness.commit_event(
            run_id,
            expected_revision=run["state_revision"],
            event={"event_id": "plan-started", "type": "plan_selected"},
            state_updates={
                "phase": "STEP_EXECUTE",
                "plan": {"version": 7, "steps": [{"step_id": "private-step"}]},
                "plan_version": 7,
                "attempt_index": 3,
                "current_step": "private-step",
            },
        )
        return harness, run

    def test_completed_solver_call_projects_public_identity_and_consumed_receipts(self):
        run_id = "public-call-evidence"
        harness, run = self._run(run_id)
        with harness:
            receipt_id = "tool:public-call-evidence:receipt-1"
            receipt_event = {
                "event_id": receipt_id,
                "type": "tool_receipt",
                "receipt": {
                    "receipt_id": receipt_id,
                    "run_id": run_id,
                    "plan_version": 7,
                    "attempt_index": 3,
                    "status": "success",
                    "executed": True,
                },
            }
            receipt_event["receipt"]["public_receipt_id"] = public_solver_event_id(
                {"run_id": run_id, "state": run["state"]}, receipt_event
            )
            run = harness.commit_event(
                run_id,
                expected_revision=run["state_revision"],
                event=receipt_event,
                state_updates={"tool_receipts": [receipt_event["receipt"]]},
            )
            harness.dispatch(
                run,
                lambda _request: {"verdict": "ACCEPT"},
                {
                    "run_id": run_id,
                    "role": "step_verifier",
                    "call_id": "private-internal-call-id",
                    "problem": "private prompt text",
                    "report": {
                        "tool_receipts": [{
                            "receipt_id": receipt_id,
                            "input": {"secret": "private argument"},
                            "output": "private result",
                        }],
                    },
                },
            )
            latest = harness.get_run(run_id)
            record = latest["state"]["calls"]["private-internal-call-id"]
            event = next(
                event for event in reversed(latest["events"])
                if event["type"] == "call_audit" and event.get("outcome") == "completed"
            )
            projected = decision_fields(event, latest["state"])

        self.assertEqual(7, record.get("plan_version"))
        self.assertEqual(3, record.get("attempt_index"))
        self.assertEqual(
            ["tool:public-call-evidence:receipt-1"], record.get("consumed_receipt_ids")
        )
        receipt_ref = public_solver_event_id(
            {"run_id": run_id, "state": latest["state"]}, receipt_event
        )
        self.assertEqual(public_solver_call_id(run_id, "private-internal-call-id"), projected.get("solver_call_id"))
        self.assertEqual(run_id, projected.get("run_id"))
        self.assertEqual(7, projected.get("plan_version"))
        self.assertEqual(3, projected.get("attempt_index"))
        self.assertEqual("step_verifier", projected.get("role"))
        self.assertEqual("completed", projected.get("call_status"))
        self.assertEqual([receipt_ref], projected.get("consumed_receipt_ids"))
        pack = EvidencePackExporter().export(
            {"run_id": "outer-evidence-run", "status": "running"},
            events=[{
                "type": "solver_progress",
                "job_id": run_id,
                "solver_event_type": "call_audit",
                "solver_revision": event["state_revision"],
                "solver_call_id": projected["solver_call_id"],
                "plan_version": projected["plan_version"],
                "attempt_index": projected["attempt_index"],
                "call_status": projected["call_status"],
                "role": projected["role"],
                "consumed_receipt_ids": projected["consumed_receipt_ids"],
                "run_id": projected["run_id"],
                "tool_call_id": "private-internal-tool-call-id",
            }],
        )
        timeline_event = pack["timeline"][0]
        self.assertEqual(run_id, timeline_event["run_id"])
        self.assertEqual("call_audit", timeline_event["solver_event_type"])
        self.assertEqual(event["state_revision"], timeline_event["solver_revision"])
        self.assertEqual(projected["solver_call_id"], timeline_event["solver_call_id"])
        self.assertEqual(projected["consumed_receipt_ids"], timeline_event["consumed_receipt_ids"])
        self.assertNotIn("tool_call_id", timeline_event)
        serialized = repr(projected)
        self.assertNotIn("private-internal-call-id", serialized)
        self.assertNotIn("private prompt text", serialized)
        self.assertNotIn("private argument", serialized)
        self.assertNotIn("private result", serialized)

    def test_started_call_without_completion_is_not_projected_as_success(self):
        run_id = "public-call-incomplete"
        harness, run = self._run(run_id)
        with harness:
            with self.assertRaises(CallInterrupted):
                harness.dispatch(
                    run,
                    lambda _request: (_ for _ in ()).throw(TimeoutError()),
                    {
                        "run_id": run_id,
                        "role": "reasoner",
                        "call_id": "private-incomplete-call",
                        "problem": "private prompt",
                    },
                )
            latest = harness.get_run(run_id)
            event = next(
                event for event in reversed(latest["events"])
                if event["type"] == "call_audit"
            )
            state = deepcopy(latest["state"])
            state["calls"]["private-incomplete-call"].pop("plan_version")
            state["calls"]["private-incomplete-call"].pop("attempt_index")
            projected = decision_fields(event, state)

        self.assertEqual("unknown_outcome", latest["state"]["calls"]["private-incomplete-call"]["status"])
        self.assertEqual("unknown", projected["call_status"])
        self.assertNotIn("plan_version", projected)
        self.assertNotIn("attempt_index", projected)

    def test_successful_tool_receipt_projects_identity_without_raw_values(self):
        class ToolPort:
            source = "test"
            registered_tools = {"polynomial_check"}

            def execute(self, _request):
                return {"status": "success", "output": "private tool result", "exit_code": 0}

        run_id = "public-tool-evidence"
        harness, run = self._run(run_id, tool_port=ToolPort())
        with harness:
            run = harness.commit_event(
                run_id,
                expected_revision=run["state_revision"],
                event={"event_id": "step-report", "type": "step_reported"},
                state_updates={"steps": {"private-step": {"report": {
                    "claims": [{
                        "label": "easy-verify",
                        "tool_request": {
                            "tool": "polynomial_check",
                            "arguments": {"value": "private tool argument"},
                        },
                    }],
                }}}},
            )
            completed = precheck_report(
                harness,
                run,
                config=harness._config,
                tool_port=harness._tool_port,
            )
            event = next(
                event for event in reversed(completed["events"])
                if event["type"] == "tool_receipt"
            )
            projected = decision_fields(event, completed["state"])

        receipt = completed["state"]["tool_receipts"][0]
        self.assertEqual(run_id, receipt.get("run_id"))
        self.assertEqual(7, receipt.get("plan_version"))
        self.assertEqual(3, receipt.get("attempt_index"))
        self.assertTrue(receipt["executed"])
        receipt_ref = public_solver_event_id(
            {"run_id": run_id, "state": completed["state"]}, event
        )
        self.assertEqual(receipt_ref, projected.get("receipt_id"))
        self.assertEqual(run_id, projected.get("run_id"))
        self.assertEqual(7, projected.get("plan_version"))
        self.assertEqual(3, projected.get("attempt_index"))
        self.assertEqual("success", projected.get("receipt_status"))
        self.assertTrue(projected.get("receipt_executed"))
        pack = EvidencePackExporter().export(
            {"run_id": "outer-evidence-run", "status": "running", "final_response": ""},
            events=[{
                "type": "solver_progress",
                "job_id": run_id,
                "solver_event_type": "tool_receipt",
                "solver_event_id": receipt_ref,
                **projected,
                "private": "do not export",
            }],
        )
        self.assertEqual(run_id, pack["timeline"][0]["job_id"])
        self.assertEqual(run_id, pack["timeline"][0]["run_id"])
        self.assertEqual("tool_receipt", pack["timeline"][0]["solver_event_type"])
        self.assertEqual(receipt_ref, pack["timeline"][0]["receipt_id"])
        self.assertEqual("success", pack["timeline"][0]["receipt_status"])
        self.assertTrue(pack["timeline"][0]["receipt_executed"])
        self.assertNotIn("private tool argument", repr(pack["timeline"]))
        self.assertNotIn("private tool result", repr(pack["timeline"]))
        self.assertNotIn("private", repr(pack["timeline"]))

    def test_evidence_tool_receipt_summary_is_allowlisted(self):
        pack = EvidencePackExporter().export(
            {"run_id": "receipt-summary-run", "status": "running"},
            tool_results=[{
                "name": "polynomial_check",
                "status": "success",
                "tool_call_id": "private internal call id",
                "receipt": {
                    "receipt_id": "tool:receipt-summary-run:private-internal-id",
                    "public_receipt_id": "solver_event_0123456789abcdef0123456789abcdef",
                    "run_id": "receipt-summary-run",
                    "plan_version": 2,
                    "attempt_index": 4,
                    "status": "success",
                    "executed": True,
                    "receipt_status": "success",
                    "receipt_executed": True,
                    "input": {"secret": "private tool argument"},
                    "output": "private tool result",
                    "call_id": "private internal call",
                },
            }],
        )
        self.assertEqual({
            "receipt_id": "solver_event_0123456789abcdef0123456789abcdef",
            "run_id": "receipt-summary-run",
            "plan_version": 2,
            "attempt_index": 4,
            "receipt_status": "success",
            "receipt_executed": True,
        }, pack["tools"][0]["receipt"])
        self.assertNotIn("tool_call_id", pack["tools"][0])
        self.assertNotIn("private", repr(pack["tools"]))

    def test_tool_summary_never_treats_a_raw_receipt_id_as_public(self):
        pack = EvidencePackExporter().export(
            {"run_id": "receipt-raw-id-run", "status": "running"},
            tool_results=[{
                "name": "polynomial_check",
                "receipt": {
                    "receipt_id": "solver_event_0123456789abcdef0123456789abcdef",
                    "status": "success",
                    "executed": True,
                },
            }],
        )
        self.assertNotIn("receipt_id", pack["tools"][0]["receipt"])

    def test_evidence_timeline_keeps_only_event_level_run_identity(self):
        pack = EvidencePackExporter().export(
            {"run_id": "event-run", "status": "running"},
            events=[
                {"type": "task_created", "job_id": "event-job"},
                {"type": "task_started", "run_id": "event-run-2"},
                {"type": "task_finished"},
            ],
        )
        self.assertEqual("event-job", pack["timeline"][0]["job_id"])
        self.assertEqual("event-run-2", pack["timeline"][1]["run_id"])
        self.assertNotIn("run_id", pack["timeline"][0])
        self.assertNotIn("run_id", pack["timeline"][2])

    def test_non_call_solver_event_uses_its_run_state_identity(self):
        run_id = "state-owned-event-run"
        harness, run = self._run(run_id)
        with harness:
            projected = decision_fields({"type": "plan_selected"}, run["state"])
            pack = EvidencePackExporter().export(
                {"run_id": "outer-evidence-run", "status": "running"},
                events=[{
                    "type": "solver_progress",
                    "job_id": run_id,
                    "solver_event_type": "plan_selected",
                    "solver_revision": run["state_revision"],
                    **projected,
                }],
            )
        self.assertEqual(run_id, pack["timeline"][0]["run_id"])
        self.assertEqual("plan_selected", pack["timeline"][0]["solver_event_type"])

if __name__ == "__main__":
    unittest.main()
