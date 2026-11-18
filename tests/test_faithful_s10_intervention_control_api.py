"""Public and pause-control contracts for native F4 interventions."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
import uuid
from contextlib import closing
from copy import deepcopy

from showcase.flask_app import create_app


class FaithfulInterventionControlAPITest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": self.folder.name,
            "SHOWCASE_WORKER_ENABLED": False,
            "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": True,
        })
        self.addCleanup(self._close_app)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session_id = self.client.post(
            "/api/new_chat", headers=self.headers()
        ).get_json()["new_session_id"]
        self.job_id = self.app.extensions["showcase_workspace_service"].store.create_job(
            user_id="local-user",
            session_id=self.session_id,
            problem="2+2",
            idempotency_key=uuid.uuid4().hex,
            request_digest=uuid.uuid4().hex,
        )[0]["job_id"]
        self.base = f"/api/agent/jobs/{self.job_id}/interventions"

    def _close_app(self):
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            resource = self.app.extensions.get(name)
            if resource is not None:
                resource.close()

    def headers(self):
        return {"X-CSRF-Token": getattr(self, "csrf", "")}

    def test_routes_are_opt_in_authenticated_and_csrf_protected(self):
        self.assertTrue(callable(self.app.config[
            "SHOWCASE_FAITHFUL_INTERVENTION_RESERVATION_ESTIMATOR"
        ]))
        self.assertTrue(callable(self.app.config[
            "SHOWCASE_FAITHFUL_INTERVENTION_EXECUTION_FACTORY"
        ]))
        anonymous = self.app.test_client()
        self.assertEqual(401, anonymous.get(self.base).status_code)
        response = self.client.post(self.base + "/pause", json={})
        self.assertEqual(403, response.status_code)
        self.assertEqual("csrf_required", response.get_json()["code"])
        disabled = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": self.folder.name + "-disabled",
            "SHOWCASE_WORKER_ENABLED": False,
        })
        self.assertEqual(404, disabled.test_client().get(self.base).status_code)
        disabled.extensions["showcase_workspace_service"].close()
        disabled.extensions["showcase_run_service"].close()
        disabled.extensions["loopback_store"].close()

    def test_restart_recovery_preserves_explicitly_paused_intervention_job(self):
        from showcase.faithful_intervention_control import ensure_control_schema

        connection = self.app.extensions[
            "showcase_workspace_service"
        ].store._connection
        ensure_control_schema(connection)
        connection.execute(
            "UPDATE workspace_jobs SET status='waiting_input' WHERE job_id=?", (self.job_id,)
        )
        connection.execute(
            "INSERT INTO faithful_intervention_control(job_id,run_id,status,updated_at) "
            "VALUES(?,?,'paused',0)", (self.job_id, self.job_id),
        )
        connection.commit()

        self.app.extensions["showcase_workspace_service"].store.recover_incomplete_jobs()

        self.assertEqual("waiting_input", connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id=?", (self.job_id,)
        ).fetchone()[0])

    def test_public_pause_stops_real_star_run_before_reasoner_dispatch(self):
        import os
        import time
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.adapters import InternModelAdapter
        from showcase.run_budget import RunBudgetLimits
        from showcase.solver_harness.storage import SolverStateStore
        from tests.test_faithful_s03_job import CAPACITY_POLICY, REPLIES, SPEC

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "test-key"}))
        replies = deepcopy(REPLIES)

        class Response:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(replies.pop(0))}}], "model": "intern-s2",
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

        with patch("llm_client.requests.post", side_effect=lambda *_a, **_k: Response()) as post:
            replies[1]["steps"][0]["method_id"] = "direct"
            app = create_app({
                "TESTING": True, "SHOWCASE_DATA_DIR": folder.name,
                "SHOWCASE_JOB_DELAY_SECONDS": 0.6, "SHOWCASE_WORKER_ENABLED": True,
                "SHOWCASE_STAR_ENABLED": True,
                "SHOWCASE_STAR_FEATURES": {
                    "problem_spec": True, "serial_routes": True,
                    "final_generation": True, "final_solution_review": True,
                },
                "SHOWCASE_STAR_CONTEXT_CAPACITY": CAPACITY_POLICY,
                "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
                    max_model_calls=16, max_http_attempts=16, max_tool_calls=0,
                    max_tokens=100_000, max_runtime_seconds=60,
                ),
                "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                    InternChatClient(retry=1), max_tokens=256,
                ),
                "SHOWCASE_STAR_EVIDENCE_KIND": "scripted",
                "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": True,
            })
            self.addCleanup(lambda: [app.extensions[name].close() for name in (
                "showcase_workspace_service", "showcase_run_service", "loopback_store",
            )])
            client = app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
            session_id = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
            request = {"message": "1+1", "session_id": session_id,
                       "solver_mode": "star_limited", "problem_spec": SPEC}
            created = client.post("/api/agent/jobs", json=request, headers=headers)
            self.assertEqual(202, created.status_code, created.get_json())
            run_id = created.get_json()["job_id"]
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                job = client.get(f"/api/agent/jobs/{run_id}").get_json()
                if job["status"] == "running":
                    break
                time.sleep(0.01)
            self.assertEqual("running", job["status"], job)
            paused = client.post(
                f"/api/agent/jobs/{run_id}/interventions/pause", json={}, headers=headers,
            )
            self.assertEqual(202, paused.status_code, paused.get_json())
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                job = client.get(f"/api/agent/jobs/{run_id}").get_json()
                if job["status"] == "waiting_input":
                    break
                time.sleep(0.01)
            self.assertEqual("waiting_input", job["status"], job)
            solver_run = SolverStateStore(app.extensions[
                "showcase_run_service"
            ]._store._connection).get_run(run_id)
            state = solver_run["state"]
            self.assertEqual("STEP_EXECUTE", state["phase"])
            self.assertEqual(2, post.call_count)
            control = client.get(f"/api/agent/jobs/{run_id}/interventions").get_json()["interventions"]
            self.assertEqual("paused", control["status"])
            self.assertEqual(solver_run["state_revision"], control["checkpoint_revision"])

    def test_hypothesis_requires_owned_source_event_and_structured_failure(self):
        from showcase.faithful_intervention_control import ensure_control_schema
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.routes import sync_plan_route
        from showcase.storage import SQLiteStore
        from tests.test_faithful_s03_job import REPLIES, SPEC

        store = SQLiteStore(self.app.config["SHOWCASE_DATABASE_PATH"])
        self.addCleanup(store.close)
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            ensure_control_schema(db)
            db.execute("UPDATE workspace_jobs SET status='running' WHERE job_id=?", (self.job_id,))
            db.commit()
        config = {"max_model_calls": 20, "features": {
            "problem_spec": True, "progress_scheduling": True, "serial_routes": True,
            "final_generation": True, "final_solution_review": True,
        }}
        spec = deepcopy(SPEC)
        spec["original_problem"] = "2+2"
        spec["root_obligations"][0]["statement"] = "2+2=4"
        plan = deepcopy(REPLIES[1])
        plan["steps"][0]["method_id"] = "direct"
        with SolverHarness(store=store, config=config) as harness:
            run = harness.solve("2+2", {"run_id": self.job_id, "problem_spec": spec, "plan": plan})
            run = harness.commit_event(
                self.job_id,
                expected_revision=run["state_revision"],
                event={"event_id": "initial-plan", "type": "initial_plan_generated"},
                state_updates={
                    "phase": "STEP_EXECUTE",
                    "plan": plan,
                    "plan_version": 1,
                    "current_step": plan["steps"][0]["step_id"],
                },
            )
            run = sync_plan_route(harness, run)
            RunBudgetLedger(connection=store._connection).ensure(
                self.job_id,
                RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=0,
                                max_tokens=1000, max_runtime_seconds=60),
            )
            run = harness.commit_event(
                self.job_id,
                expected_revision=run["state_revision"],
                event={"event_id": "failure-review", "type": "step_reviewed",
                       "valid": True, "verdict": "CHALLENGE",
                       "step_id": plan["steps"][0]["step_id"]},
            )
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            db.execute("UPDATE workspace_jobs SET status='waiting_input' WHERE job_id=?", (self.job_id,))
            db.execute(
                "INSERT INTO faithful_intervention_control "
                "(job_id,run_id,status,checkpoint_revision,applied_config_fingerprint,updated_at) "
                "VALUES(?,?,'paused',?,?,0)",
                (self.job_id, self.job_id, run["state_revision"], "test-config-fingerprint"),
            )
            db.commit()
        source = self.client.get(self.base, headers=self.headers()).get_json()[
            "interventions"
        ]["failure_sources"][0]
        body = {
            "hypothesis_id": "hyp-1",
            "failure_category": "method_mismatch",
            "source_event_id": source["source_event_id"],
            "source_state_revision": source["source_state_revision"],
            "affected_roots": [{"obligation_id": "root:value", "proposition": "2+2=4"}],
            "failure_symptom": "The reviewed step received a challenge.",
            "diagnostic_evidence": {"event_type": "step_reviewed", "verdict": "CHALLENGE"},
            "candidate_action_ids": ["control", "intervention"],
            "falsification_criteria": {"condition": "independent review accepts"},
            "priority": 50,
        }
        invalid_source = {**body, "source_event_id": "event-from-another-run"}
        denied = self.client.post(self.base + "/hypotheses", json=invalid_source, headers=self.headers())
        self.assertEqual(404, denied.status_code)
        unknown = {**body, "failure_category": "unknown_transport"}
        denied = self.client.post(self.base + "/hypotheses", json=unknown, headers=self.headers())
        self.assertEqual(400, denied.status_code)
        self.assertEqual("hypothesis_category_noncausal", denied.get_json()["code"])
        extra = {**body, "caller_budget": {"model_calls": 10}}
        denied = self.client.post(self.base + "/hypotheses", json=extra, headers=self.headers())
        self.assertEqual(400, denied.status_code)
        accepted = self.client.post(self.base + "/hypotheses", json=body, headers=self.headers())
        self.assertEqual(201, accepted.status_code, accepted.get_json())
        repeated_hypothesis = self.client.post(self.base + "/hypotheses", json=body, headers=self.headers())
        self.assertEqual(200, repeated_hypothesis.status_code, repeated_hypothesis.get_json())
        for action_id, method in (("control", "direct"), ("intervention", "induction")):
            action = self.client.post(
                self.base + "/actions",
                json={"action_id": action_id, "action_type": "reasoning_method", "target": "current_step",
                      "parameters": {"method_id": method}},
                headers=self.headers(),
            )
            self.assertEqual(201, action.status_code, action.get_json())
            repeated_action = self.client.post(
                self.base + "/actions",
                json={"action_id": action_id, "action_type": "reasoning_method", "target": "current_step",
                      "parameters": {"method_id": method}},
                headers=self.headers(),
            )
            self.assertEqual(200, repeated_action.status_code, repeated_action.get_json())
        self.app.config["SHOWCASE_FAITHFUL_INTERVENTION_RESERVATION_ESTIMATOR"] = (
            lambda *_: {"input_estimate": 10, "output_cap": 20, "model_calls": 2,
                        "http_attempts": 1, "tool_calls": 0, "time_seconds": 10}
        )
        pair = self.client.post(
            self.base + "/pairs",
            json={"pair_id": "pair-1", "hypothesis_id": "hyp-1", "control_action_id": "control",
                  "intervention_action_id": "intervention", "seed": 17},
            headers=self.headers(),
        )
        self.assertEqual(201, pair.status_code, pair.get_json())
        repeated_pair = self.client.post(
            self.base + "/pairs",
            json={"pair_id": "pair-1", "hypothesis_id": "hyp-1", "control_action_id": "control",
                  "intervention_action_id": "intervention", "seed": 17},
            headers=self.headers(),
        )
        self.assertEqual(200, repeated_pair.status_code, repeated_pair.get_json())
        budget = RunBudgetLedger(connection=store._connection).snapshot(self.job_id)
        self.assertEqual(120, budget["reserved_tokens"])
        pair_id = f"{self.job_id}:pair-1"
        started = threading.Event()
        release = threading.Event()

        def blocked_factory(*_):
            started.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test worker release timed out")
            raise RuntimeError("intentional test executor stop")

        self.app.config["SHOWCASE_FAITHFUL_INTERVENTION_EXECUTION_FACTORY"] = blocked_factory
        execute = self.client.post(
            self.base + "/pairs/pair-1/execute", json={}, headers=self.headers()
        )
        self.assertEqual(202, execute.status_code, execute.get_json())
        self.assertTrue(started.wait(timeout=3))
        from showcase.faithful_intervention_control import _WORKERS

        worker = _WORKERS.get(pair_id)
        self.assertIsNotNone(worker)
        try:
            ordinary_resume = self.client.post(
                f"/api/agent/jobs/{self.job_id}/resume", json={},
                headers={**self.headers(), "Idempotency-Key": str(uuid.uuid4())},
            )
            self.assertEqual(409, ordinary_resume.status_code, ordinary_resume.get_json())
            self.assertEqual("intervention_pair_execution_active", ordinary_resume.get_json()["code"])
        finally:
            release.set()
            worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertEqual("interrupted", store._connection.execute(
            "SELECT execution_status FROM faithful_intervention_pair_owners WHERE pair_id=?",
            (pair_id,),
        ).fetchone()[0])
        current_budget = RunBudgetLedger(connection=store._connection).snapshot(self.job_id)
        self.assertEqual(budget["reserved_tokens"], current_budget["reserved_tokens"])
        self.assertEqual("waiting_input", self.app.extensions[
            "showcase_workspace_service"
        ].store._connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id=?", (self.job_id,)
        ).fetchone()[0])
        public = self.client.get(self.base, headers=self.headers()).get_json()["interventions"]
        self.assertEqual("current_step", public["actions"][0]["target"])
        self.assertEqual("step_reviewed", public["failure_sources"][0]["event_type"])
        self.assertEqual("CHALLENGE", public["failure_sources"][0]["verdict"])
        self.assertEqual("direct", public["current_method_id"])

    def test_pair_request_cannot_claim_budget_or_execute_without_reserved_pair(self):
        invalid = self.client.post(
            self.base + "/pairs",
            json={"pair_id": "pair-1", "reservation": {"model_calls": 100}},
            headers=self.headers(),
        )
        self.assertEqual(400, invalid.status_code)
        execute = self.client.post(
            self.base + "/pairs/missing/execute", json={}, headers=self.headers()
        )
        self.assertEqual(404, execute.status_code)

    def test_projection_is_job_scoped_and_contains_no_checkpoint_or_credentials(self):
        payload = self.client.get(self.base).get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(self.job_id, payload["interventions"]["job_id"])
        encoded = json.dumps(payload)
        self.assertNotIn("checkpoint_json", encoded)
        self.assertNotIn("api_key", encoded)


if __name__ == "__main__":
    unittest.main()
