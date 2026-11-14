"""Committed state/control combinations through the public Job read API."""

import hashlib
import json
import uuid
import unittest
from unittest.mock import patch

from showcase.solver_harness.initial_state import initial_state
from showcase.solver_harness.storage import SolverStateStore
from tests import test_faithful_service_api as fixture


class BackendStateTest(unittest.TestCase):
    setUp = fixture.FaithfulServiceApiTest.setUp

    def seed(self, job_status, *, control=None, **updates):
        with patch.object(self.pipeline, "full_gaps", return_value=[]):
            response = self.client.post("/api/agent/jobs", headers=self.headers,
                json={"message": "1+1", "session_id": self.session})
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        from showcase.run_budget import RunBudgetLimits
        self.app.extensions["showcase_workspace_service"].budget_ledger.ensure(job_id, RunBudgetLimits())
        store = self.app.extensions["showcase_workspace_service"].store
        state = initial_state(job_id, hashlib.sha256(b"1+1").hexdigest(), "test")
        state.update(updates)
        with store._lock:
            SolverStateStore(store._connection).create_run(state, {
                "event_id": "seed", "state_revision": state["state_revision"],
                "created_at": state["created_at"], "type": "session_started"})
            store._connection.execute(
                "UPDATE workspace_jobs SET status=?,error_code=? WHERE job_id=?",
                (job_status, "needs_review" if job_status == "failed" else None, job_id))
            if control:
                from showcase.faithful_intervention_control import ensure_control_schema
                ensure_control_schema(store._connection)
                store._connection.execute(
                    "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) VALUES(?,?,?,0)",
                    (job_id, job_id, control))
            store._connection.commit()
        return job_id

    def read(self, job_id):
        response = self.client.get(f"/api/agent/jobs/{job_id}")
        self.assertEqual(200, response.status_code, response.get_json())
        return response.get_json()["result"]["faithful"]

    def test_pause_request_is_distinct_from_execution(self):
        job_id = self.seed("running", control="pause_requested", phase="STEP_EXECUTE")
        self.assertEqual("pause_requested", self.read(job_id)["phase"])
        self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])

    def test_paused_checkpoint_does_not_offer_generic_resume(self):
        job_id = self.seed("waiting_input", control="paused", phase="STEP_EXECUTE")
        self.assertEqual("paused", self.read(job_id)["phase"])
        self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])
        self.assertEqual(409, self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={}, headers=self.headers).status_code)

    def test_switch_convergence_is_projected(self):
        job_id = self.seed("running", execution_switch={"status": "converging"})
        self.assertEqual("converging", self.read(job_id)["phase"])

    def test_valid_paused_checkpoint_offers_dedicated_resume_only(self):
        job_id = self.seed("waiting_input", control="paused", phase="STEP_EXECUTE")
        store = self.app.extensions["showcase_workspace_service"].store
        revision = json.loads(store._connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])["state_revision"]
        store._connection.execute(
            "UPDATE faithful_intervention_control SET checkpoint_revision=?,applied_config_fingerprint='test' WHERE job_id=?",
            (revision, job_id))
        store._connection.commit()
        with patch.object(self.pipeline, "intervention_enabled", True):
            before = store._connection.execute(
                "SELECT status,resume_authorized FROM faithful_intervention_control WHERE job_id=?", (job_id,)).fetchone()
            self.assertEqual(["cancel", "resume_intervention"], self.read(job_id)["allowed_actions"])
            self.assertEqual(tuple(before), tuple(store._connection.execute(
                "SELECT status,resume_authorized FROM faithful_intervention_control WHERE job_id=?", (job_id,)).fetchone()))
            store._connection.execute(
                "UPDATE faithful_intervention_control SET checkpoint_revision=-1 WHERE job_id=?", (job_id,))
            store._connection.commit()
            self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])

    def test_pause_action_requires_existing_serial_feature_admission(self):
        job_id = self.seed("running")
        self.assertNotIn("pause", self.read(job_id)["allowed_actions"])
        with patch.object(self.pipeline, "intervention_enabled", True):
            with patch.object(self.pipeline, "preset_config", return_value={"features": {
                "problem_spec": True, "serial_routes": True, "concurrent_routes": False}}):
                self.assertEqual(["cancel", "pause"], self.read(job_id)["allowed_actions"])
            with patch.object(self.pipeline, "preset_config", return_value={"features": {
                "problem_spec": True, "serial_routes": True, "concurrent_routes": True}}):
                self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])


    def test_terminal_partial_is_incomplete(self):
        job_id = self.seed("failed", phase="TERMINAL", status="partial_aborted")
        self.assertEqual("incomplete", self.read(job_id)["phase"])
        self.assertEqual([], self.read(job_id)["allowed_actions"])

    def test_unknown_requires_explicit_retry_and_reads_do_not_mutate(self):
        job_id = self.seed("failed", calls={"old": {
            "call_id": "old", "status": "unknown_outcome", "role": "reasoner"}})
        store = self.app.extensions["showcase_workspace_service"].store
        before = store._connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0]
        faithful = self.read(job_id)
        self.assertEqual("unknown", faithful["phase"])
        self.assertEqual(["retry_unknown_call"], faithful["allowed_actions"])
        self.assertEqual(faithful, self.read(job_id))
        self.assertEqual(before, store._connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0])


class DedicatedResumeApiTest(unittest.TestCase):
    seed = BackendStateTest.seed
    read = BackendStateTest.read

    def setUp(self):
        create_app = fixture.create_app
        with patch.object(fixture, "create_app", side_effect=lambda config: create_app({
                **config, "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": True})):
            fixture.FaithfulServiceApiTest.setUp(self)

    def test_get_action_matches_dedicated_post_and_stale_checkpoint_is_rejected(self):
        job_id = self.seed("waiting_input", control="paused", phase="STEP_EXECUTE")
        store = self.app.extensions["showcase_workspace_service"].store
        revision = store._connection.execute(
            "SELECT state_revision FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0]
        url = f"/api/agent/jobs/{job_id}/interventions/resume"
        headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])
        self.assertEqual(409, self.client.post(url, json={}, headers=headers).status_code)
        store._connection.execute(
            "UPDATE faithful_intervention_control SET checkpoint_revision=?,applied_config_fingerprint='test' WHERE job_id=?",
            (revision, job_id))
        store._connection.commit()
        self.assertEqual(["cancel", "resume_intervention"], self.read(job_id)["allowed_actions"])
        self.assertEqual(409, self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={}, headers=headers).status_code)
        response = self.client.post(url, json={}, headers=headers)
        self.assertEqual(202, response.status_code, response.get_json())
        store._connection.execute(
            "UPDATE run_budgets SET ledger_json=json_set(ledger_json,'$.deadline_at',0) WHERE run_id=?", (job_id,))
        store._connection.commit()
        repeated = self.client.post(url, json={}, headers=headers)
        self.assertEqual(200, repeated.status_code, repeated.get_json())
        self.assertTrue(repeated.get_json()["existing"])
        self.assertEqual(response.get_json()["job_id"], repeated.get_json()["job_id"])
        conflict = self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=headers)
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("idempotency_conflict", conflict.get_json()["code"])

    def test_expired_parent_has_no_dedicated_action_and_post_does_not_authorize(self):
        job_id = self.seed("waiting_input", control="paused", phase="STEP_EXECUTE")
        store = self.app.extensions["showcase_workspace_service"].store
        revision = store._connection.execute(
            "SELECT state_revision FROM solver_states WHERE run_id=?", (job_id,)).fetchone()[0]
        store._connection.execute(
            "UPDATE faithful_intervention_control SET checkpoint_revision=?,applied_config_fingerprint='test' WHERE job_id=?",
            (revision, job_id))
        store._connection.execute(
            "UPDATE run_budgets SET ledger_json=json_set(ledger_json,'$.deadline_at',0) WHERE run_id=?", (job_id,))
        store._connection.commit()
        service = self.app.extensions["showcase_workspace_service"]
        dispatch = self.enterContext(patch.object(service, "resubmit"))
        queries = [
            "SELECT * FROM workspace_jobs WHERE job_id=?",
            "SELECT * FROM faithful_intervention_control WHERE job_id=?",
            "SELECT * FROM run_budgets WHERE run_id=?",
            "SELECT * FROM workspace_actions WHERE job_id=?",
        ]
        before = [list(map(tuple, store._connection.execute(query, (job_id,)))) for query in queries]
        self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])
        response = self.client.post(f"/api/agent/jobs/{job_id}/interventions/resume", json={},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assertEqual(409, response.status_code)
        self.assertEqual("run_deadline_exhausted", response.get_json()["code"])
        self.assertEqual(before, [list(map(tuple, store._connection.execute(query, (job_id,))))
                                  for query in queries])
        dispatch.assert_not_called()
        self.assertEqual(("paused", 0), tuple(store._connection.execute(
            "SELECT status,resume_authorized FROM faithful_intervention_control WHERE job_id=?", (job_id,)).fetchone()))
        store._connection.execute("DELETE FROM run_budgets WHERE run_id=?", (job_id,))
        store._connection.commit()
        self.assertEqual(["cancel"], self.read(job_id)["allowed_actions"])
        missing = self.client.post(f"/api/agent/jobs/{job_id}/interventions/resume", json={},
            headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())})
        self.assertEqual(409, missing.status_code)
        self.assertEqual("run_deadline_exhausted", missing.get_json()["code"])
        dispatch.assert_not_called()

