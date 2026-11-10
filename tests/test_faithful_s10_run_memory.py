"""S10 Run Memory is a scoped view of the authoritative persisted Job state."""

import unittest
from copy import deepcopy
from unittest.mock import MagicMock, patch

from showcase.faithful_memory_api import project_run_memory
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import FEATURES, REPLIES, SPEC


class FaithfulS10RunMemoryTest(StarJobFixture, unittest.TestCase):
    def test_cli_requires_explicit_memory_review_flag(self):
        from showcase.flask_app import main

        app = MagicMock()
        with (
            patch("sys.argv", ["showcase_server.py", "--faithful-memory-review"]),
            patch("showcase.flask_app.create_app", return_value=app) as create,
        ):
            main()
        self.assertIs(create.call_args.args[0]["SHOWCASE_FAITHFUL_MEMORY_ENABLED"], True)

    def test_conjecture_and_invalidated_result_are_not_effective_evidence(self):
        state = {
            "proof_graph": {"current_version": 3, "snapshots": []},
            "verified_results_ledger": [
                {
                    "result_id": "a",
                    "proven": True,
                    "valid": True,
                    "evidence_level": "llm_reviewed",
                    "category": "Lemma",
                },
                {
                    "result_id": "b",
                    "proven": False,
                    "valid": True,
                    "evidence_level": "conjecture",
                    "category": "Conjecture",
                },
                {
                    "result_id": "c",
                    "proven": True,
                    "valid": False,
                    "evidence_level": "tool_verified",
                    "category": "Computation",
                },
            ],
        }
        memory = project_run_memory("run-1", 4, state)
        self.assertEqual(["a"], [item["result_id"] for item in memory["valid_evidence"]])
        self.assertEqual("llm_reviewed", memory["valid_evidence"][0]["evidence_level"])
        self.assertEqual(3, memory["graph_version"])
        self.assertEqual(1, memory["invalidated_count"])

    def test_public_memory_uses_persisted_run_without_promoting_evidence(self):
        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "message": "Compute 1+1",
                "session_id": self.session,
                "solver_mode": "star_limited",
            },
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        self.terminal(job_id)

        response = self.client.get(f"/api/agent/jobs/{job_id}/memory")
        self.assertEqual(200, response.status_code, response.get_json())
        memory = response.get_json()["run_memory"]
        self.assertEqual(job_id, memory["run_id"])
        self.assertIsInstance(memory["state_revision"], int)
        self.assertEqual("authoritative_run_snapshot", memory["source"])
        job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual(job["result"]["budget"], memory["budget"])
        self.assertIn("valid_evidence", memory)
        self.assertNotIn("problem", memory)
        self.assertNotIn("prompt_layers", memory)
        outbound_count = len(self.outbound)
        self.assertEqual(
            memory, self.client.get(f"/api/agent/jobs/{job_id}/memory").get_json()["run_memory"]
        )
        self.assertEqual(outbound_count, len(self.outbound))
        anonymous = self.app.test_client()
        denied = anonymous.get(f"/api/agent/jobs/{job_id}/memory")
        self.assertEqual(401, denied.status_code)
        self.assertEqual("auth_required", denied.get_json()["code"])
        identity = self.app.extensions["loopback_store"]
        with identity._connection:
            identity._connection.execute(
                "INSERT INTO loopback_users VALUES (?,?,?,?)",
                ("second-user", "second", "[]", "2026-11-10T00:00:00Z"),
            )
            identity._connection.execute(
                "INSERT INTO auth_sessions VALUES (?,?,?,?,?,?)",
                (
                    "second-session",
                    "second-user",
                    "csrf",
                    "2026-11-10T00:00:00Z",
                    "2026-11-10T00:00:00Z",
                    None,
                ),
            )
        other_user = self.app.test_client()
        other_user.set_cookie("auth_session", "second-session")
        self.assertEqual(404, other_user.get(f"/api/agent/jobs/{job_id}/memory").status_code)
        self.assertEqual(
            404, other_user.get(f"/api/sessions/{self.session}/population-memory").status_code
        )

    def test_memory_endpoint_is_disabled_by_default(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        response = self.client.get("/api/agent/jobs/any/memory")
        self.assertEqual(404, response.status_code)

    def test_run_memory_survives_new_app_process(self):
        from showcase.flask_app import create_app

        self.open_star([SOLVED, POLISH, ACCEPT], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        created = self.client.post(
            "/api/agent/jobs",
            json={"message": "Compute 1+1", "session_id": self.session, "solver_mode": "star_limited"},
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        self.terminal(job_id)
        before = self.client.get(f"/api/agent/jobs/{job_id}/memory").get_json()["run_memory"]

        restarted = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": self.data_dir,
            "SHOWCASE_FAITHFUL_MEMORY_ENABLED": True,
            "SHOWCASE_WORKER_ENABLED": False,
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(restarted.extensions[name].close)
        client = restarted.test_client()
        client.set_cookie("auth_session", self.client.get_cookie("auth_session").value)
        response = client.get(f"/api/agent/jobs/{job_id}/memory")
        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual(before, response.get_json()["run_memory"])

    def test_population_observation_is_scoped_to_chat_session(self):
        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "computation"
        self.open_star(
            replies,
            SHOWCASE_FAITHFUL_MEMORY_ENABLED=True,
            SHOWCASE_STAR_FEATURES={
                **FEATURES,
                "serial_routes": True,
                "progress_scheduling": True,
                "proof_graph": True,
                "context_pack": False,
            },
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8,
                max_http_attempts=8,
                max_tool_calls=0,
                max_tokens=100_000,
                max_runtime_seconds=1_100,
            ),
        )
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "message": SPEC["original_problem"],
                "session_id": self.session,
                "solver_mode": "star_limited",
                "problem_spec": SPEC,
            },
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal.get("error"))
        outbound_count = len(self.outbound)
        observed = self.client.get(f"/api/sessions/{self.session}/population-memory").get_json()
        self.assertEqual("observations_only", observed["authority"])
        self.assertEqual(job_id, observed["observations"][0]["source_run_id"])
        self.assertTrue(observed["observations"][0]["route_id"])
        self.assertIn("status", observed["observations"][0])
        self.assertNotIn("verified_gain", observed["observations"][0])
        self.assertNotIn("statement", str(observed))

        other_session = self.client.post("/api/new_chat", headers=self.headers()).get_json()
        other_id = other_session["new_session_id"]
        scoped = self.client.get(f"/api/sessions/{other_id}/population-memory")
        self.assertEqual(200, scoped.status_code)
        self.assertEqual([], scoped.get_json()["observations"])
        self.assertEqual(
            404, self.client.get("/api/sessions/unknown/population-memory").status_code
        )
        self.assertEqual(
            400,
            self.client.get(f"/api/sessions/{self.session}/population-memory?limit=0").status_code,
        )
        self.assertEqual(outbound_count, len(self.outbound))
