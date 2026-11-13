"""InternModelPort intake through metered, entirely controlled HTTP responses."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.intern_port import InternModelPort
from tests.test_faithful_auto_intake import CONFIG, PROBLEM, SPEC


class AutoIntakeBudgetTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            "INTERN_API_KEY": "offline-intake-test", "INTERN_MODEL": "intern-s2",
            "INTERN_API_BASE": "http://127.0.0.1:19876/v1/chat/completions",
        }))
        self.requests = []
        self.replies = []
        transport = self.enterContext(patch("llm_client.requests.post", side_effect=self.respond))
        self.enterContext(patch("showcase.request_transport.strict_loopback_post", new=transport))
        self.port = InternModelPort(InternModelAdapter(
            InternChatClient(timeout=5, retry=1, loopback_only=True), max_tokens=512))

    def respond(self, *args, **kwargs):
        """Replace every outbound transport with a deterministic local response."""
        self.requests.append(json.loads(kwargs["data"]))
        value = self.replies.pop(0)
        if isinstance(value, BaseException):
            raise value
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps({
            "model": "intern-s2", "choices": [{"message": {"content": json.dumps(value)},
                                                  "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }).encode()
        response._content_consumed = True
        return response

    def test_intern_port_accepts_schema_and_charges_existing_budget_once(self):
        self.replies = [SPEC]
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("metered-intake", RunBudgetLimits(max_model_calls=1, max_http_attempts=1))
        with bind_budget(budget), SolverHarness(config=CONFIG, model_port=self.port) as harness:
            run = harness.solve(PROBLEM, {"run_id": "metered-intake"})
        snapshot = budget.snapshot()
        self.assertEqual(PROBLEM, run["state"]["problem_spec"]["original_problem"])
        self.assertEqual("completed", run["state"]["problem_intake"]["status"])
        self.assertEqual("partial_budget_exhausted", run["state"]["status"])
        self.assertEqual(1, snapshot["logical_calls"])
        self.assertEqual(1, snapshot["http_attempts"])
        self.assertEqual(1, len(self.requests))
        self.assertEqual("success", self.port.invocations[0]["status"])
        self.assertEqual("problem_intake", self.port.invocations[0]["role"])

    def test_unknown_recovery_keeps_deadline_hold_and_explicit_new_call_identity(self):
        from showcase.solver_harness.problem_intake import ensure_problem_spec

        self.replies = [requests.ReadTimeout("unknown remote result"), SPEC]
        with TemporaryDirectory() as folder:
            path = Path(folder) / "harness.sqlite3"
            ledger = RunBudgetLedger(database_path=Path(folder) / "budget.sqlite3")
            try:
                budget = ledger.ensure("metered-unknown", RunBudgetLimits(max_model_calls=2, max_http_attempts=2))
                with bind_budget(budget), SolverHarness(database_path=path, config=CONFIG,
                                                        model_port=self.port) as harness:
                    first = harness.solve(PROBLEM, {"run_id": "metered-unknown"})
                before = budget.snapshot()
                self.assertEqual(1, before["unknown_attempts"])
                self.assertEqual("interrupted", first["state"]["status"])
                old_id = "metered-unknown:problem-intake:1"
                with bind_budget(budget), SolverHarness(database_path=path, config=CONFIG,
                                                        model_port=self.port) as harness:
                    pending = harness.solve(PROBLEM, {"run_id": "metered-unknown"})
                    self.assertEqual(1, len(self.requests))
                    authorized = harness.commit_event(
                        pending["run_id"], expected_revision=pending["state_revision"],
                        event={"event_id": "explicit-intake-retry", "type": "call_retry_authorized"},
                        state_updates={"authorized_retry": {
                            "call_id": old_id, "new_call_id": "metered-intake-retry"}, "status": "running"},
                    )
                    restored = ensure_problem_spec(harness, authorized, PROBLEM)
                after = budget.snapshot()
                self.assertEqual("completed", restored["state"]["problem_intake"]["status"])
                self.assertEqual("unknown_outcome", restored["state"]["calls"][old_id]["status"])
                self.assertEqual(old_id, restored["state"]["calls"]["metered-intake-retry"]["retry_of_internal"])
                self.assertEqual(2, after["logical_calls"])
                self.assertEqual(2, after["http_attempts"])
                self.assertEqual(1, after["unknown_attempts"])
                self.assertEqual(before["deadline_at"], after["deadline_at"])
                self.assertEqual(2, len(self.requests))
            finally:
                ledger.close()

    def test_invalid_provider_schema_is_known_failure_and_never_enters_explore(self):
        self.replies = [{"not_a_specification": True}] * 2
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("invalid-provider-spec", RunBudgetLimits())
        with bind_budget(budget), SolverHarness(config=CONFIG, model_port=self.port) as harness:
            run = harness.solve(PROBLEM, {"run_id": "invalid-provider-spec"})
        self.assertEqual("TERMINAL", run["state"]["phase"])
        self.assertEqual("protocol_failure_unrepaired", run["state"]["result_reason"])
        self.assertNotIn("problem_spec", run["state"])
        self.assertEqual("protocol_failed", run["state"]["calls"]["invalid-provider-spec:problem-intake:1"]["status"])
        self.assertEqual(0, budget.snapshot()["unknown_attempts"])
        self.assertEqual(2, len(self.requests))

    def test_repair_reservation_and_completed_response_survive_process_exit(self):
        class ProcessExit(BaseException):
            pass

        for boundary in ("failure", "reservation", "response"):
            with self.subTest(boundary=boundary), TemporaryDirectory() as folder:
                path = Path(folder) / "intake.sqlite3"
                run_id = f"repair-crash-{boundary}"
                repair_id = f"{run_id}:problem-intake:1:repair-1"
                self.requests.clear()
                self.replies = [{"not_a_specification": True}, SPEC]

                def crash(run, event):
                    reserved = (boundary == "reservation" and event["type"] == "problem_intake_dispatched"
                                and run["state"]["problem_intake"].get("reserved_call_id") == repair_id)
                    responded = (boundary == "response" and event["type"] == "call_audit"
                                 and event.get("outcome") == "completed"
                                 and run["state"]["calls"].get(repair_id, {}).get("status") == "completed")
                    failed = (boundary == "failure" and event["type"] == "problem_intake_parse_failed")
                    if reserved or responded or failed:
                        raise ProcessExit()

                ledger = RunBudgetLedger(database_path=Path(folder) / "budget.sqlite3")
                try:
                    budget = ledger.ensure(run_id, RunBudgetLimits(max_model_calls=2, max_http_attempts=2))
                    with bind_budget(budget), SolverHarness(database_path=path, config=CONFIG,
                            model_port=self.port, event_observer=crash) as harness:
                        with self.assertRaises(ProcessExit):
                            harness.solve(PROBLEM, {"run_id": run_id})
                    before = budget.snapshot()
                    with bind_budget(budget), SolverHarness(database_path=path, config=CONFIG,
                                                            model_port=self.port) as harness:
                        restored = harness.solve(PROBLEM, {"run_id": run_id})
                    self.assertEqual("completed", restored["state"]["problem_intake"]["status"])
                    self.assertEqual(repair_id, restored["state"]["problem_intake"]["call_id"])
                    self.assertEqual(2, len(self.requests))
                    self.assertEqual(2, budget.snapshot()["http_attempts"])
                    self.assertEqual(before["deadline_at"], budget.snapshot()["deadline_at"])
                finally:
                    ledger.close()

    def test_failed_repair_is_terminal_after_process_exit_without_a_third_request(self):
        class ProcessExit(BaseException):
            pass

        def crash(run, event):
            if (event["type"] == "call_audit" and event.get("outcome") == "protocol_failed"
                    and any(call_id.endswith(":repair-1") and call["status"] == "protocol_failed"
                            for call_id, call in run["state"]["calls"].items())):
                raise ProcessExit()

        self.replies = [{"not_a_specification": True}] * 2
        with TemporaryDirectory() as folder:
            path = Path(folder) / "intake.sqlite3"
            with SolverHarness(database_path=path, config=CONFIG, model_port=self.port,
                               event_observer=crash) as harness:
                with self.assertRaises(ProcessExit):
                    harness.solve(PROBLEM, {"run_id": "failed-repair-crash"})
            with SolverHarness(database_path=path, config=CONFIG, model_port=self.port) as harness:
                restored = harness.solve(PROBLEM, {"run_id": "failed-repair-crash"})
                repeated = harness.solve(PROBLEM, {"run_id": "failed-repair-crash"})
            self.assertEqual("protocol_failure_unrepaired", restored["state"]["result_reason"])
            self.assertEqual("TERMINAL", restored["state"]["phase"])
            self.assertEqual(restored, repeated)
            self.assertEqual(2, len(self.requests))


if __name__ == "__main__":
    unittest.main()
