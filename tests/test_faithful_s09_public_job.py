"""S09/F3 public HTTP and persistence acceptance through the existing Job seam."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from showcase.formal import LeanTacticProver, normalize_target
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.specification import normalize_problem_spec
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

PROBLEM = "For every rational x, x + x = 2 * x."
SPEC = normalize_problem_spec({
    "specification_version": 1,
    "original_problem": PROBLEM,
    "domain": "rationals",
    "quantifiers": ["forall x"],
    "assumptions": [],
    "directions": ["equality"],
    "output_requirements": ["state the identity"],
    "root_obligations": [{
        "obligation_id": "root:identity", "obligation_type": "universal",
        "statement": "x + x = 2 * x", "direction": "equality",
    }],
    "auxiliary_goals": [],
})
TARGET = normalize_target({
    "domain": "rationals", "variables": ["x"], "lhs": "x + x", "rhs": "2 * x",
    "quantifiers": ["forall x"], "assumptions": [], "direction": "equality",
})
POLICY = {
    "enabled": True, "requested_backend": "lean_tactic_prover",
    "allowed_backends": ["lean_tactic_prover"], "require_formal": False,
    "timeout_seconds": 30, "max_output_bytes": 12000,
    "resource_limits": {"memory_mb": 512, "cpu_count": 1},
    "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
    "environment": {"lean_version": "4.19.0", "mathlib_version": "v4.19.0",
                    "toolchain": "leanprover/lean4:v4.19.0",
                    "image_digest": "sha256:" + "b" * 64,
                    "manifest_digest": "c" * 64, "template_version": "rational-polynomial-v1"},
    "target": TARGET,
}


class FakeTransport:
    def __init__(self, statuses=("unavailable",), *, solved=False):
        self.solved = solved
        self.statuses = list(statuses)
        self.calls = []

    def execute(self, source, *, run_id, call_id, **kwargs):
        self.calls.append({"source": source, "run_id": run_id, "call_id": call_id,
                           "parent_attempt_id": kwargs.get("parent_attempt_id")})
        status = self.statuses.pop(0)
        return {
            "status": status, "executed": self.solved, "cleanup_verified": True,
            "environment": {}, "duration_seconds": 0.1, "observed_output_bytes": 0,
            "stdout": "", "stderr": "fake transport", "reason": status,
        }


class FaithfulS09PublicJobTest(StarJobFixture, unittest.TestCase):
    def open_formal(self, statuses=("unavailable",), *, configured=True, grade=None,
                    solved=False, tool_budget=2):
        transport = FakeTransport(statuses, solved=solved)
        backend = LeanTacticProver(transport) if configured else None
        if backend is not None and grade is not None:
            backend.verify_result = lambda request, response, value=grade: value
        self.open_star(
            [SOLVED, POLISH, ACCEPT],
            SHOWCASE_STAR_FEATURES={"final_generation": True,
                                    "final_solution_review": True,
                                    "problem_spec": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=tool_budget,
                max_tokens=100_000, max_runtime_seconds=1_100,
            ),
            SHOWCASE_FORMAL_VERIFICATION_CONFIG=(POLICY if configured else None),
            SHOWCASE_FORMAL_BACKEND=backend,
        )
        self.transport = transport
        self.backend = backend

    def create(self, policy=POLICY):
        body = {"message": PROBLEM, "session_id": self.session,
                "solver_mode": "star_limited", "problem_spec": SPEC,
                "formal_policy": policy}
        return self.client.post("/api/agent/jobs", json=body, headers=self.headers())

    def test_default_closed_job_does_not_touch_backend_or_change_old_result(self):
        self.open_formal(configured=False)
        response = self.create()
        self.assertEqual(400, response.status_code, response.get_json())
        self.assertEqual("formal_verification_disabled", response.get_json()["error"])
        self.assertEqual([], self.transport.calls)

    def test_non_mapping_formal_policy_returns_structured_error(self):
        self.open_formal()
        response = self.create(policy=True)
        self.assertEqual(400, response.status_code, response.get_json())
        self.assertEqual("formal_policy_invalid", response.get_json()["error"])
        self.assertEqual([], self.transport.calls)

    def test_public_runtime_registers_backend_capability_and_rejects_out_of_scope_target(self):
        self.open_formal()
        service = self.app.extensions["showcase_workspace_service"]
        metadata = service.star_pipeline.formal_registry.describe()
        self.assertEqual(1, len(metadata))
        self.assertEqual("lean_tactic_prover", metadata[0]["id"])
        self.assertEqual(["rational-polynomial-identity-v1"], metadata[0]["target_types"])
        self.assertEqual("L2", metadata[0]["maximum_grade"])
        self.assertEqual("formal-request-v1", metadata[0]["input_format"])
        self.assertEqual("formal-attempt-v1", metadata[0]["output_format"])
        self.assertTrue(metadata[0]["deterministic"])
        response = self.create({**POLICY, "target": {**TARGET, "domain": "reals"}})
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertEqual("unsupported", job["result"]["formal_verification"]["status"])
        self.assertEqual("1+1=2", job["result"]["final_response"])
        self.assertEqual("completed_llm_reviewed", job["result"]["solver"]["status"])
        self.assertEqual([], self.transport.calls)

    def test_explicit_job_keeps_original_answer_and_persists_unavailable_everywhere(self):
        self.open_formal()
        response = self.create()
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        formal = job["result"]["formal_verification"]
        self.assertEqual("unavailable", formal["status"])
        self.assertIsNone(formal["grade"])
        self.assertEqual(formal["current_attempt_id"], formal["current"]["attempt_id"])
        self.assertEqual(1, len(self.transport.calls))
        call = self.transport.calls[0]
        self.assertEqual(job_id, call["run_id"])
        self.assertIn("theorem polynomial_identity", call["source"])
        self.assertEqual("root:identity",
                         formal["current"]["specifications"]["original_to_spec"]["root_obligations"][0]["obligation_id"])
        report_response = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        self.assertEqual(formal, report_response["solver"]["solver"]["formal_verification"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(formal, evidence["formal_verification"])
        self.assertEqual("accepted", report_response["report"]["semantics"]["whole_review"])
        self.assertEqual("unavailable", report_response["report"]["semantics"]["formal_verification"])
        read_count = len(self.outbound)
        for _ in range(2):
            self.client.get(f"/api/agent/jobs/{job_id}")
            self.client.get(f"/api/agent/jobs/{job_id}/report")
            self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(read_count, len(self.outbound))
        self.assertEqual(1, len(self.transport.calls))
        self.assertEqual(1, job["result"]["budget"]["tool_calls"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").data.decode()
        self.assertIn("formal_verification_dispatched", events)
        self.assertIn("formal_verification_completed", events)

    def test_dispatched_formal_is_not_reissued_by_the_product_adapter(self):
        self.open_formal()
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            execute_reserved_attempt,
            mark_inflight_unknown,
            reserve_formal_attempt,
        )

        state = FormalIntegrationState(job_id="job", run_id="run", problem=PROBLEM,
                                       problem_spec=SPEC, policy=POLICY, target=TARGET)
        record = reserve_formal_attempt(state)
        self.assertEqual("dispatched", record["status"])
        completed = execute_reserved_attempt(
            state, backend=self.backend, record=record,
        )
        self.assertEqual("unavailable", completed["status"])
        self.assertEqual("unavailable", execute_reserved_attempt(
            state, backend=self.backend, record=completed,
        )["status"])
        self.assertEqual(1, len(self.transport.calls))
        unknown = mark_inflight_unknown(record)
        self.assertEqual("unknown", unknown["status"])
        self.assertIsNone(unknown["grade"])
        self.assertEqual("unknown", execute_reserved_attempt(
            state, backend=self.backend, record=unknown,
        )["status"])
        self.assertEqual(1, len(self.transport.calls))

    def test_explicit_formal_retry_creates_child_attempt_and_keeps_deadline(self):
        self.open_formal(statuses=("timeout", "unavailable"))
        created = self.create()
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        first_job = self.terminal(job_id)
        first = first_job["result"]["formal_verification"]
        deadline = first_job["result"]["budget"]["deadline_at"]
        retried = self.client.post(
            f"/api/agent/jobs/{job_id}/formal-attempts",
            json={"expected_attempt_id": first["current_attempt_id"], "operation": "retry"},
            headers=self.headers(),
        )
        self.assertEqual(202, retried.status_code, retried.get_json())
        child_id = retried.get_json()["attempt_id"]
        reserved = self.job(job_id)["result"]["formal_verification"]
        self.assertEqual(child_id, reserved["current_attempt_id"])
        self.assertIn(reserved["status"], {"dispatched", "unavailable"})
        self.assertEqual(first["current_attempt_id"], reserved["current"]["parent_attempt_id"])

        def child_finished():
            value = self.job(job_id)["result"]["formal_verification"]
            return value if (value["current_attempt_id"] == child_id
                             and value["status"] != "dispatched") else None

        try:
            second = self.wait_for(child_finished)
        except AssertionError:
            stuck = self.job(job_id)["result"].get("formal_verification")
            print("RETRY_STUCK_STATUS", stuck.get("status") if isinstance(stuck, dict) else None)
            print("RETRY_STUCK_ATTEMPT", stuck.get("current_attempt_id") if isinstance(stuck, dict) else None)
            print("RETRY_STUCK_STATUS_CODE", self.job(job_id)["status"])
            raise
        persisted = self.job(job_id)["result"]["formal_verification"]
        self.assertEqual(second["current_attempt_id"], persisted["current_attempt_id"])
        self.assertEqual(first["current_attempt_id"], second["current"]["parent_attempt_id"])
        self.assertNotEqual(first["current_attempt_id"], second["current_attempt_id"])
        self.assertEqual(2, len(second["attempts"]))
        self.assertEqual(2, len(self.transport.calls), self.job(job_id))
        self.assertEqual(first["current_attempt_id"], second["current"]["parent_attempt_id"])
        self.assertEqual(2, second["current"]["lineage"]["sequence"])
        self.assertGreaterEqual(second["lineage"]["total_cost"]["elapsed_seconds"], 0.1)
        persisted_job = self.job(job_id)
        self.assertEqual(deadline, persisted_job["result"]["budget"]["deadline_at"])
        self.assertEqual(2, persisted_job["result"]["budget"]["tool_calls"])
        self.assertEqual(persisted_job["result"]["budget"]["tool_calls"], len(self.transport.calls))
        self.assertEqual("timeout", second["attempts"][0]["status"])
        self.assertEqual("unavailable", second["attempts"][1]["status"])
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(second, report["solver"]["solver"]["formal_verification"])
        self.assertEqual(second, evidence["formal_verification"])

    def test_explicit_backend_switch_without_a_selectable_backend_is_rejected(self):
        self.open_formal(statuses=("unavailable",))
        job_id = self.create().get_json()["job_id"]
        first = self.terminal(job_id)["result"]["formal_verification"]
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/formal-attempts",
            json={"expected_attempt_id": first["current_attempt_id"],
                  "operation": "switch", "requested_backend": "unregistered_backend"},
            headers=self.headers(),
        )
        self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual("formal_backend_unsupported", response.get_json()["error"])
        self.assertEqual(first["current_attempt_id"],
                         self.job(job_id)["result"]["formal_verification"]["current_attempt_id"])
        self.assertEqual(1, len(self.transport.calls))

    def test_public_single_tool_budget_prevents_a_second_explicit_dispatch(self):
        self.open_formal(statuses=("unavailable", "solved"), tool_budget=1)
        job_id = self.create().get_json()["job_id"]
        first_job = self.terminal(job_id)
        first = first_job["result"]["formal_verification"]
        self.assertEqual(1, first_job["result"]["budget"]["limits"]["max_tool_calls"])
        self.assertEqual(1, first_job["result"]["budget"]["tool_calls"])
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/formal-attempts",
            json={"expected_attempt_id": first["current_attempt_id"], "operation": "retry"},
            headers=self.headers(),
        )
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.wait_for(lambda: (
            self.job(job_id)["result"]["formal_verification"]
            if self.job(job_id)["result"]["formal_verification"]["status"] != "dispatched"
            else None
        ))
        self.assertNotEqual(first["current_attempt_id"], final["current_attempt_id"])
        self.assertEqual("unavailable", final["status"], self.job(job_id))
        self.assertEqual(first["current_attempt_id"], final["current"]["parent_attempt_id"])
        self.assertEqual([first["current_attempt_id"], final["current_attempt_id"]],
                         final["lineage"]["attempt_ids"])
        self.assertEqual(1, len(self.transport.calls))
        budget = self.job(job_id)["result"]["budget"]
        self.assertEqual(1, budget["tool_calls"])
        self.assertEqual(1, budget["limits"]["max_tool_calls"])

    def test_explicit_retry_recovers_one_solver_revision_conflict_without_replacing_attempt(self):
        from showcase.solver_harness.storage import (
            SolverRevisionConflictError,
            SolverStateStore,
        )

        self.open_formal(statuses=("timeout", "unavailable"))
        job_id = self.create().get_json()["job_id"]
        first = self.terminal(job_id)["result"]["formal_verification"]
        service = self.app.extensions["showcase_workspace_service"]
        state_store = SolverStateStore(service.store._connection)
        commit = state_store.commit_event
        calls = 0

        def conflict_once(state_store, run_id, *, expected_revision, state_updates,
                          event, request_hash, **kwargs):
            nonlocal calls
            self.assertIs(service.store._connection, state_store._connection)
            if calls == 0:
                calls += 1
                snapshot = state_store.get_run(run_id)
                commit(
                    run_id, expected_revision=snapshot["state_revision"],
                    state_updates={"formal_verification": snapshot["state"]["formal_verification"]},
                    event={"event_id": "s09-test-cas-interleave",
                           "type": "formal_verification_interleave",
                           "status": snapshot["state"]["formal_verification"]["status"],
                           "grade": None},
                    request_hash="s09-test-cas-interleave",
                )
                raise SolverRevisionConflictError(
                    run_id, expected_revision, expected_revision + 1,
                )
            return commit(
                run_id, expected_revision=expected_revision,
                state_updates=state_updates, event=event,
                request_hash=request_hash, **kwargs,
            )

        with patch.object(SolverStateStore, "commit_event", autospec=True,
                          side_effect=conflict_once):
            response = self.client.post(
                f"/api/agent/jobs/{job_id}/formal-attempts",
                json={"expected_attempt_id": first["current_attempt_id"], "operation": "retry"},
                headers=self.headers(),
            )
            self.assertEqual(202, response.status_code, response.get_json())
            child_id = response.get_json()["attempt_id"]
            persisted = state_store.get_run(job_id)["state"]["formal_verification"]

        self.assertEqual(1, calls)
        self.assertEqual(child_id, persisted["current_attempt_id"])
        self.assertEqual(first["current_attempt_id"], persisted["current"]["parent_attempt_id"])
        self.assertEqual(first["current_attempt_id"], persisted["lineage"]["parent_attempt_id"])
        self.assertEqual(2, persisted["current"]["lineage"]["sequence"])
        self.assertGreaterEqual(
            persisted["lineage"]["total_cost"]["elapsed_seconds"],
            first["current"]["cost"]["elapsed_seconds"],
        )
        completed = self.wait_for(lambda: (
            self.job(job_id)["result"]["formal_verification"]
            if self.job(job_id)["result"]["formal_verification"]["status"] != "dispatched"
            else None
        ))
        self.assertEqual(child_id, completed["current_attempt_id"])
        self.assertEqual([first["current_attempt_id"], child_id], completed["lineage"]["attempt_ids"])
        self.assertEqual("timeout", completed["attempts"][0]["status"])
        self.assertEqual("unavailable", completed["attempts"][1]["status"])

    def test_retry_action_and_solver_attempt_roll_back_together(self):
        from showcase.solver_harness.storage import SolverStateStore

        self.open_formal(statuses=("timeout", "unavailable"))
        job_id = self.create().get_json()["job_id"]
        first_job = self.terminal(job_id)
        first = first_job["result"]["formal_verification"]
        service = self.app.extensions["showcase_workspace_service"]
        state_store = SolverStateStore(service.store._connection)
        before = state_store.get_run(job_id)
        service.store._connection.execute(
            "CREATE TEMP TRIGGER reject_formal_action BEFORE INSERT ON workspace_actions "
            "BEGIN SELECT RAISE(ABORT, 'injected action write failure'); END"
        )
        try:
            response = self.client.post(
                f"/api/agent/jobs/{job_id}/formal-attempts",
                json={"expected_attempt_id": first["current_attempt_id"], "operation": "retry"},
                headers=self.headers(),
            )
        finally:
            service.store._connection.execute("DROP TRIGGER reject_formal_action")
        after = state_store.get_run(job_id)
        self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual(before["state_revision"], after["state_revision"])
        self.assertEqual(first["current_attempt_id"],
                         after["state"]["formal_verification"]["current_attempt_id"])
        self.assertEqual("succeeded", self.job(job_id)["status"])

    def test_require_formal_timeout_and_error_are_terminal_unmet_without_answer_loss(self):
        for status in ("timeout", "error", "unknown"):
            with self.subTest(status=status):
                self.open_formal(statuses=(status,))
                response = self.create({**POLICY, "require_formal": True})
                self.assertEqual(202, response.status_code, response.get_json())
                job = self.terminal(response.get_json()["job_id"])
                formal = job["result"]["formal_verification"]
                self.assertEqual(status, formal["status"])
                self.assertIsNone(formal["grade"])
                self.assertEqual("unmet", job["result"]["solver"]["semantics"]["formal_requirement"])
                self.assertTrue(job["result"]["final_response"])
                self.assertEqual(1, len(self.transport.calls))

    def test_boolean_review_inside_policy_is_rejected_even_when_nested(self):
        self.open_formal()
        policy = {**POLICY, "review": {"reviewed": True}}
        response = self.create(policy)
        self.assertEqual(400, response.status_code, response.get_json())
        self.assertEqual("formal_policy_invalid", response.get_json()["error"])
        self.assertEqual([], self.transport.calls)


    def test_server_policy_conflict_is_rejected_before_provider_dispatch(self):
        self.open_formal()
        cases = (
            ({**POLICY, "timeout_seconds": 31}, "formal_policy_timeout_seconds_conflict"),
            ({**POLICY, "max_output_bytes": 999999},
             "formal_policy_max_output_bytes_conflict"),
            ({**POLICY, "allowed_axioms": []}, "formal_policy_allowed_axioms_conflict"),
        )
        for policy, error in cases:
            with self.subTest(error=error):
                response = self.create(policy)
                self.assertEqual(400, response.status_code, response.get_json())
                self.assertEqual(error, response.get_json()["error"])
        self.assertEqual([], self.transport.calls)

    def test_non_finite_timeout_is_rejected(self):
        self.open_formal()
        for timeout in (float("nan"), float("inf")):
            with self.subTest(timeout=timeout):
                response = self.create({**POLICY, "timeout_seconds": timeout})
                self.assertEqual(400, response.status_code, response.get_json())
                self.assertIn(response.get_json()["error"], {
                    "formal_timeout_invalid", "formal_policy_timeout_seconds_conflict",
                })
        self.assertEqual([], self.transport.calls)

    def test_require_formal_failure_keeps_answer_and_marks_requirement_unmet(self):
        self.open_formal(statuses=("unavailable",))
        response = self.create({**POLICY, "require_formal": True})
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertEqual("unavailable", job["result"]["formal_verification"]["status"])
        semantics = job["result"]["solver"]["semantics"]
        self.assertEqual("unmet", semantics["formal_requirement"])
        self.assertTrue(job["result"]["final_response"])
        report = self.client.get(f"/api/agent/jobs/{job['job_id']}/report").get_json()["report"]
        self.assertEqual("unmet", report["semantics"]["formal_requirement"])

    def test_require_formal_met_requires_solved_and_a_valid_verified_grade(self):
        from showcase.star_result_semantics import result_semantics

        run = {"state": {
            "status": "completed_llm_reviewed", "phase": "TERMINAL", "calls": {},
            "formal_policy": {**POLICY, "require_formal": True},
            "formal_verification": {"status": "solved", "grade": "L2"},
        }}
        self.assertEqual("met", result_semantics(run, "", verification_mode="required")["formal_requirement"])
        run["state"]["formal_verification"]["grade"] = None
        self.assertEqual("unmet", result_semantics(run, "", verification_mode="required")["formal_requirement"])

    def test_old_result_without_formal_policy_keeps_formal_requirement_absent(self):
        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_STAR_FEATURES={
            "final_generation": True, "final_solution_review": True,
            "problem_spec": True,
        })
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": PROBLEM, "session_id": self.session,
                  "solver_mode": "star_limited", "problem_spec": SPEC},
            headers=self.headers(),
        )
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertNotIn("formal_requirement", job["result"]["solver"]["semantics"])

if __name__ == "__main__":
    unittest.main()
