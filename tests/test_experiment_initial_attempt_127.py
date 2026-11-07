"""Keep zero-based plan attempts in independently verified process evidence."""

from __future__ import annotations

import unittest

from showcase.experiment_verification_process import _check_process_path, _safe_process_path
from showcase.run_budget import public_solver_call_id


def completed_path(attempt_index):
    """Model the public initial-plan fields observed in readiness-06."""
    run_id = "initial-attempt-run"
    roles = {"planner", "reasoner", "step_verifier", "final_generator"}
    events = []
    attempts = []
    for revision, role in enumerate(("planner", "reasoner", "step_verifier", "final_generator"), 1):
        call_id = public_solver_call_id(run_id, role)
        events.append({
            "solver_event_type": "call_audit", "solver_revision": revision * 2,
            "run_id": run_id, "role": role, "solver_call_id": call_id,
            "call_status": "completed", "plan_version": 0 if role == "planner" else 1,
            "attempt_index": 0 if role == "planner" else attempt_index,
        })
        attempts.append({
            "run_id": run_id, "role": role, "solver_call_id": call_id,
            "status": "success", "dispatch_status": "transport_observed",
        })
    events.insert(1, {
        "solver_event_type": "initial_plan_generated", "solver_revision": 3,
        "run_id": run_id, "role": "planner", "plan_version": 1,
        "attempt_index": attempt_index,
    })
    evidence = {
        "evidence_id": run_id, "timeline": events,
        "solver": {"solver": {"progress": {
            "plan_version": 1, "attempt_index": attempt_index,
            "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}] * 2,
        }}},
        "budget": {"tool_calls": 0},
        "verification": {"history": [{"source": {
            "origin": "final_generator", "plan_version": 1, "attempt_index": attempt_index,
        }}]},
    }
    return evidence, attempts, roles


class InitialAttemptProcessTest(unittest.TestCase):
    def test_complete_initial_zero_attempt_keeps_successful_roles_and_passes(self):
        evidence, attempts, roles = completed_path(0)
        process = _safe_process_path(evidence, attempts, roles, "provider_live")

        self.assertEqual(0, process["attempt_index"])
        self.assertEqual(roles, set(process["successful_roles"]))
        result = _check_process_path(
            {"type": "multistep"}, {"execution_mode": "live", "process_path": process},
            {"status": "PASS"}, {"status": "PASS"},
        )
        self.assertEqual("PASS", result["status"])

    def test_invalid_attempt_values_are_not_inferred_as_zero(self):
        for value in (None, -1, True):
            with self.subTest(value=value):
                evidence, attempts, roles = completed_path(value)
                process = _safe_process_path(evidence, attempts, roles, "provider_live")
                self.assertIsNone(process["attempt_index"])
                result = _check_process_path(
                    {"type": "multistep"},
                    {"execution_mode": "live", "process_path": process},
                    {"status": "PASS"}, {"status": "PASS"},
                )
                self.assertEqual("FAIL", result["status"])

    def test_zero_attempt_does_not_inherit_review_from_another_attempt(self):
        evidence, attempts, roles = completed_path(0)
        evidence["verification"]["history"][-1]["source"]["attempt_index"] = 1
        process = _safe_process_path(evidence, attempts, roles, "provider_live")
        result = _check_process_path(
            {"type": "multistep"}, {"execution_mode": "live", "process_path": process},
            {"status": "PASS"}, {"status": "PASS"},
        )
        self.assertEqual("FAIL", result["status"])
        self.assertEqual("final_delivery_plan_mismatch", result["reason"])


if __name__ == "__main__":
    unittest.main()
