"""Public Job path from paused checkpoint through native pair and explicit resume."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from contextlib import closing
from copy import deepcopy

from showcase.flask_app import create_app
from tests.test_faithful_s03_job import REPLIES, SPEC


class FaithfulInterventionProductPathTest(unittest.TestCase):
    """Verify API ownership, native Solver execution, report projection and resume."""

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
        self.addCleanup(self.close_app)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": self.csrf}
        self.session_id = self.client.post("/api/new_chat", headers=headers).get_json()[
            "new_session_id"
        ]
        self.job_id = self.app.extensions["showcase_workspace_service"].store.create_job(
            user_id="local-user", session_id=self.session_id, problem=SPEC["original_problem"],
            idempotency_key=uuid.uuid4().hex, request_digest=uuid.uuid4().hex,
        )[0]["job_id"]
        self.base = f"/api/agent/jobs/{self.job_id}/interventions"
        self.headers = headers

    def close_app(self):
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            resource = self.app.extensions.get(name)
            if resource is not None:
                resource.close()

    def seed_paused_checkpoint(self):
        from showcase.faithful_intervention_control import ensure_control_schema
        from showcase.run_budget import RunBudgetLedger, RunBudgetLimits
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.routes import sync_plan_route
        from showcase.storage import SQLiteStore

        database_path = self.app.config["SHOWCASE_DATABASE_PATH"]
        store = SQLiteStore(database_path)
        self.addCleanup(store.close)
        applied = {
            "name": "offline-test-model", "thinking_mode": None, "temperature": 0.2,
            "max_output_tokens": 256, "request_timeout_seconds": 30, "retry": 1,
        }
        config = {"max_model_calls": 20, "features": {
            "problem_spec": True, "progress_scheduling": True, "serial_routes": True,
            "stream_recovery": True, "persistent_sessions": True,
            "proof_graph": True,
            "final_generation": True, "final_solution_review": True,
        }}
        spec = deepcopy(SPEC)
        spec["original_problem"] = "2+2"
        spec["root_obligations"][0]["statement"] = "2+2=4"
        plan = deepcopy(REPLIES[1])
        plan["steps"][0]["method_id"] = "direct"
        with closing(sqlite3.connect(database_path)) as connection:
            ensure_control_schema(connection)
            connection.execute(
                "UPDATE workspace_jobs SET status='running',result_json=? WHERE job_id=?",
                (json.dumps({"solver_mode": "star_limited"}), self.job_id),
            )
            connection.commit()
        with SolverHarness(store=store, config=config) as harness:
            run = harness.solve("2+2", {"run_id": self.job_id, "problem_spec": spec, "plan": plan})
            run = harness.commit_event(
                self.job_id, expected_revision=run["state_revision"],
                event={"event_id": "initial-plan", "type": "initial_plan_generated"},
                state_updates={"phase": "STEP_EXECUTE", "plan": plan, "plan_version": 1,
                               "current_step": plan["steps"][0]["step_id"]},
            )
            run = sync_plan_route(harness, run)
            run = harness.commit_event(
                self.job_id, expected_revision=run["state_revision"],
                event={"event_id": "source-challenge", "type": "step_reviewed",
                       "valid": True, "verdict": "CHALLENGE",
                       "step_id": plan["steps"][0]["step_id"]},
            )
        RunBudgetLedger(connection=store._connection).ensure(
            self.job_id, RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=0,
                max_tokens=20_000, max_runtime_seconds=120,
            ),
        )
        import hashlib

        applied_fingerprint = hashlib.sha256(
            json.dumps(applied, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute(
                "UPDATE workspace_jobs SET status='waiting_input' WHERE job_id=?", (self.job_id,)
            )
            connection.execute(
                "INSERT INTO faithful_intervention_control "
                "(job_id,run_id,status,checkpoint_revision,config_json,applied_config_json,"
                "applied_config_fingerprint,closing_reserve_json,updated_at) "
                "VALUES(?,?,'paused',?,?,?,?,?,0)",
                (self.job_id, self.job_id, run["state_revision"], json.dumps(config),
                 json.dumps(applied), applied_fingerprint,
                 json.dumps({"model_calls": 0, "http_attempts": 0, "tokens": 0,
                             "tool_calls": 0, "time_seconds": 0})),
            )
            connection.commit()
        return store, config, applied, run

    def register_pair(self):
        view = self.client.get(self.base, headers=self.headers).get_json()["interventions"]
        source = view["failure_sources"][0]
        body = {
            "hypothesis_id": "hypothesis-1", "failure_category": "method_mismatch",
            "source_event_id": source["source_event_id"],
            "source_state_revision": source["source_state_revision"],
            "affected_roots": [{"obligation_id": "root:value", "proposition": "2+2=4"}],
            "failure_symptom": "The checkpoint step was challenged.",
            "diagnostic_evidence": {
                "event_type": "step_reviewed",
                "verdict": "CHALLENGE",
            },
            "candidate_action_ids": ["control", "variant"],
            "falsification_criteria": {"condition": "independent review accepts"},
            "priority": 50,
        }
        response = self.client.post(self.base + "/hypotheses", json=body, headers=self.headers)
        self.assertEqual(201, response.status_code, response.get_json())
        for action_id, method in (("control", "direct"), ("variant", "induction")):
            response = self.client.post(
                self.base + "/actions",
                json={"action_id": action_id, "action_type": "reasoning_method",
                      "target": "current_step", "parameters": {"method_id": method}},
                headers=self.headers,
            )
            self.assertEqual(201, response.status_code, response.get_json())
        self.app.config["SHOWCASE_FAITHFUL_INTERVENTION_RESERVATION_ESTIMATOR"] = (
            lambda *_args: {"input_estimate": 1000, "output_cap": 1000,
                            "model_calls": 3, "http_attempts": 1,
                            "tool_calls": 0, "time_seconds": 20}
        )
        response = self.client.post(
            self.base + "/pairs",
            json={"pair_id": "pair-1", "hypothesis_id": "hypothesis-1",
                  "control_action_id": "control", "intervention_action_id": "variant", "seed": 41},
            headers=self.headers,
        )
        self.assertEqual(201, response.status_code, response.get_json())

    def test_invalid_resume_idempotency_key_leaves_checkpoint_resumable(self):
        store, _, _, _ = self.seed_paused_checkpoint()

        response = self.client.post(
            self.base + "/resume", json={},
            headers={**self.headers, "Idempotency-Key": "not-a-uuid-v4"},
        )

        self.assertEqual(400, response.status_code, response.get_json())
        control = store._connection.execute(
            "SELECT status,resume_authorized FROM faithful_intervention_control WHERE job_id=?",
            (self.job_id,),
        ).fetchone()
        job = store._connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id=?", (self.job_id,)
        ).fetchone()
        self.assertEqual(("paused", 0), tuple(control))
        self.assertEqual("waiting_input", job[0])

    def test_hypothesis_diagnostic_is_bound_to_public_source_event(self):
        self.seed_paused_checkpoint()
        view = self.client.get(self.base, headers=self.headers).get_json()["interventions"]
        source = view["failure_sources"][0]
        body = {
            "hypothesis_id": "hypothesis-1",
            "failure_category": "method_mismatch",
            "source_event_id": source["source_event_id"],
            "source_state_revision": source["source_state_revision"],
            "affected_roots": [{"obligation_id": "root:value", "proposition": "2+2=4"}],
            "failure_symptom": "The checkpoint step was challenged.",
            "diagnostic_evidence": {
                "event_type": source["event_type"],
                "verdict": source["verdict"],
            },
            "candidate_action_ids": ["control", "variant"],
            "falsification_criteria": {"condition": "independent review accepts"},
            "priority": 50,
        }

        unbound = {**body, "diagnostic_evidence": {
            **body["diagnostic_evidence"], "summary": "caller-asserted evidence",
        }}
        response = self.client.post(self.base + "/hypotheses", json=unbound, headers=self.headers)
        self.assertEqual(400, response.status_code, response.get_json())
        self.assertEqual("intervention_structured_failure_invalid", response.get_json()["code"])

        internal_id = {**body, "source_event_id": "source-challenge"}
        response = self.client.post(self.base + "/hypotheses", json=internal_id, headers=self.headers)
        self.assertEqual(404, response.status_code, response.get_json())

        response = self.client.post(self.base + "/hypotheses", json=body, headers=self.headers)
        self.assertEqual(201, response.status_code, response.get_json())

    def test_public_api_runs_native_pair_projects_effect_and_resumes_parent(self):
        from showcase.run_budget import RunBudgetLedger, current_budget
        from showcase.solver_harness.faithful_intervention import FaithfulInterventionEngine
        from showcase.solver_harness.faithful_intervention_native import NativeCheckpointExecutor
        from showcase.solver_harness.storage import SolverStateStore

        store, config, applied, parent = self.seed_paused_checkpoint()
        self.register_pair()
        requests = []

        class Adapter:
            def applied_config(self):
                return applied

        class Port:
            adapter = Adapter()

            def reply(self, request, result):
                requests.append(deepcopy(request))
                budget = current_budget()
                call = budget.model_call(request["role"], solver_call_id=request["call_id"])
                attempt = {"attempt_id": f"offline:{len(requests)}", "max_tokens": 256}
                call.before_attempt(attempt, input_estimate=1000)
                call.after_attempt({**attempt, "status": "success", "prompt_tokens": 8,
                                    "completion_tokens": 5, "total_tokens": 13})
                return deepcopy(result)

            def complete(self, request):
                from tests.test_faithful_s03_job import REPLIES as replies

                return self.reply(request, replies[2])

            def verify(self, request):
                from tests.test_faithful_s03_job import REPLIES as replies

                return self.reply(request, replies[3])

        port = Port()

        def execution_factory(connection, job_id, _pair_id, _report, _gate):
            engine = FaithfulInterventionEngine(connection)
            ledger = RunBudgetLedger(connection=connection)
            executor = NativeCheckpointExecutor(
                engine, config=config, problem="2+2", model_port=port, verifier_port=port,
            )
            return executor, ledger

        self.app.config["SHOWCASE_FAITHFUL_INTERVENTION_EXECUTION_FACTORY"] = execution_factory
        response = self.client.post(
            self.base + "/pairs/pair-1/execute", json={}, headers=self.headers
        )
        self.assertEqual(202, response.status_code, response.get_json())
        deadline = time.monotonic() + 5
        owner_status = None
        while time.monotonic() < deadline:
            with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as connection:
                owner = connection.execute(
                    "SELECT execution_status FROM faithful_intervention_pair_owners WHERE pair_id=?",
                    (f"{self.job_id}:pair-1",),
                ).fetchone()
            owner_status = owner[0] if owner is not None else None
            if owner_status in {"completed", "interrupted"}:
                break
            self.client.get(self.base + "/reports", headers=self.headers)
            time.sleep(0.01)
        from showcase.faithful_intervention_control import _WORKERS

        worker = _WORKERS.get(f"{self.job_id}:pair-1")
        if worker is not None:
            worker.join(timeout=5)
        report = self.client.get(self.base + "/reports", headers=self.headers).get_json()
        self.assertTrue(report["reports"], report)
        pair = report["reports"][0]
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as connection:
            children = connection.execute(
                "SELECT arm,status FROM faithful_intervention_children "
                "WHERE pair_id=? ORDER BY arm", (f"{self.job_id}:pair-1",),
            ).fetchall()
            owner = connection.execute(
                "SELECT execution_status FROM faithful_intervention_pair_owners WHERE pair_id=?",
                (f"{self.job_id}:pair-1",),
            ).fetchone()
        self.assertEqual("completed", pair["status"], {"pair": pair, "owner": owner_status})
        self.assertEqual("native_solver_checkpoint", pair["branch_engine"])
        self.assertEqual(1, pair["evaluable_pairs"])
        self.assertEqual(1, report["effects"]["denominator"])
        self.assertEqual([("control", "reviewed"), ("intervention", "reviewed")], children)
        for arm in ("control", "intervention"):
            self.assertEqual("ACCEPT", pair["arms"][arm]["branch_verifier_verdict"])
            self.assertEqual("ACCEPT", pair["arms"][arm]["independent_recheck_verdict"])
            self.assertEqual("verified", pair["arms"][arm]["evidence_integrity"])
        self.assertEqual({"direct", "induction"}, {
            item["step"]["method_id"] for item in requests if item["role"] == "reasoner"
        })
        self.assertEqual(4, sum(item["role"] == "step_verifier" for item in requests))
        self.assertEqual(parent, SolverStateStore(store._connection).get_run(self.job_id))

        response = self.client.post(
            self.base + "/resume", json={}, headers={**self.headers, "Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(202, response.status_code, response.get_json())
        job = store._connection.execute(
            "SELECT status FROM workspace_jobs WHERE job_id=?", (self.job_id,)
        ).fetchone()
        self.assertEqual("queued", job[0])
        self.assertEqual(parent, SolverStateStore(store._connection).get_run(self.job_id))


if __name__ == "__main__":
    unittest.main()
