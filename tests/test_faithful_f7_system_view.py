"""Public read-only F7 system-view API contract."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from showcase.faithful_system_api import _public_presentation
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import SOLVED, StarJobFixture
from tests.test_s06_presentation import CAPACITY_POLICY, ENDPOINT, SPEC, SPEC_FEATURES, SPEC_REPLIES


class FaithfulF7SystemViewApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": str(Path(self.temp_dir.name) / "data"),
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_PRESENTATION_ENABLED": True,
            "SHOWCASE_F7_SYSTEM_VIEW_ENABLED": True,
        })
        self.client = self.app.test_client()
        self.headers = {"X-CSRF-Token": self.client.get("/api/check_auth").get_json()["csrf_token"],
                        "Idempotency-Key": str(uuid.uuid4())}
        self.session_id = self.client.post("/api/new_chat", headers=self.headers).get_json()["new_session_id"]
        response = self.client.post("/api/agent/jobs", json={
            "message": "PRIVATE_F7_PROMPT_SENTINEL", "session_id": self.session_id,
            "presentation_mode": "teach",
        }, headers=self.headers)
        self.assertEqual(202, response.status_code, response.get_json())
        self.run_id = response.get_json()["job_id"]
        for _ in range(200):
            job = self.client.get(f"/api/agent/jobs/{self.run_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(0.01)
        self.assertIn(job["status"], {"succeeded", "failed", "canceled"})
        output = self.client.post(f"/api/agent/jobs/{self.run_id}/teach", json={}, headers=self.headers)
        self.assertEqual(200, output.status_code, output.get_json())
        self.presentation = output.get_json()["presentation"]

    def tearDown(self):
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def test_f7_is_disabled_by_default(self):
        default_app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": str(Path(self.temp_dir.name) / "default-data"),
            "SHOWCASE_WORKER_ENABLED": False,
        })
        try:
            response = default_app.test_client().get("/api/faithful/runs")
            self.assertEqual(404, response.status_code)
        finally:
            default_app.extensions["showcase_workspace_service"].close()
            default_app.extensions["showcase_run_service"].close()
            default_app.extensions["loopback_store"].close()

    def test_system_api_surface_is_get_only(self):
        rules = [rule for rule in self.app.url_map.iter_rules()
                 if rule.rule.startswith("/api/faithful/")]
        self.assertTrue(rules)
        for rule in rules:
            with self.subTest(rule=rule.rule):
                self.assertLessEqual(rule.methods, {"GET", "HEAD", "OPTIONS"})

    def test_list_and_detail_only_read_persisted_public_artifacts(self):
        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock:
            before = store._connection.execute(
                "SELECT COUNT(*) FROM presentation_artifacts WHERE job_id=?", (self.run_id,),
            ).fetchone()[0]
            events_before = store._connection.execute(
                "SELECT COUNT(*) FROM workspace_events WHERE job_id=?", (self.run_id,),
            ).fetchone()[0]

        listing = self.client.get("/api/faithful/runs")
        self.assertEqual(200, listing.status_code, listing.get_json())
        payload = listing.get_json()
        self.assertNotIn("PRIVATE_F7_PROMPT_SENTINEL", json.dumps(payload))
        self.assertIn(self.run_id, {item["run_id"] for item in payload["items"]})

        detail = self.client.get(f"/api/faithful/runs/{self.run_id}", query_string={
            "scheme": "f7-deeplink-v1", "mode": "teach",
            "output": self.presentation["output_request"]["id"],
            "artifact": self.presentation["artifact"]["id"],
        })
        self.assertEqual(200, detail.status_code, detail.get_json())
        body = detail.get_json()
        self.assertEqual("f7-deeplink-v1", body["scheme"])
        self.assertEqual(self.run_id, body["run"]["run_id"])
        artifact = body["selection"]["presentation"]
        self.assertEqual(self.presentation["output_request"]["id"], artifact["output_request"]["id"])
        self.assertEqual(self.presentation["artifact"]["id"], artifact["artifact"]["id"])
        self.assertEqual([item["id"] for item in self.presentation["paragraphs"]],
                         [item["id"] for item in artifact["paragraphs"]])
        self.assertNotIn("PRIVATE_F7_PROMPT_SENTINEL", json.dumps(body))

        with store._lock:
            after = store._connection.execute(
                "SELECT COUNT(*) FROM presentation_artifacts WHERE job_id=?", (self.run_id,),
            ).fetchone()[0]
            events_after = store._connection.execute(
                "SELECT COUNT(*) FROM workspace_events WHERE job_id=?", (self.run_id,),
            ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(events_before, events_after)

    def test_missing_identity_lists_saved_outputs_without_guessing_a_selection(self):
        response = self.client.get(f"/api/faithful/runs/{self.run_id}?scheme=f7-deeplink-v1")
        body = response.get_json()
        self.assertEqual("unavailable", body["selection"]["status"])
        self.assertIsNone(body["selection"]["presentation"])
        self.assertEqual(self.presentation["artifact"]["id"], body["presentations"][0]["artifact_id"])

    def test_other_user_cannot_list_or_read_this_run(self):
        identity = self.app.extensions["loopback_store"]
        with identity._connection:
            identity._connection.execute("INSERT INTO loopback_users VALUES (?,?,?,?)",
                                         ("second-user", "second", "[]", "2026-11-11T00:00:00Z"))
            identity._connection.execute("INSERT INTO auth_sessions VALUES (?,?,?,?,?,?)", (
                "second-session", "second-user", "csrf", "2026-11-11T00:00:00Z",
                "2026-11-11T00:00:00Z", None,
            ))
        stranger = self.app.test_client()
        stranger.set_cookie("auth_session", "second-session")
        self.assertEqual([], stranger.get("/api/faithful/runs").get_json()["items"])
        self.assertEqual(404, stranger.get(
            f"/api/faithful/runs/{self.run_id}?scheme=f7-deeplink-v1",
        ).status_code)

    def test_opaque_identity_selects_mode_without_generating_output(self):
        with patch.object(self.app.extensions["showcase_workspace_service"], "save_presentation",
                          side_effect=AssertionError("F7 cannot write")):
            response = self.client.get(f"/api/faithful/runs/{self.run_id}", query_string={
                "scheme": "f7-deeplink-v1", "output": self.presentation["output_request"]["id"],
                "artifact": self.presentation["artifact"]["id"],
            })
        self.assertEqual(200, response.status_code)
        self.assertEqual("teach", response.get_json()["selection"]["mode"])

    def test_projection_distinguishes_scopes_and_never_grants_best_effort_without_a_candidate(self):
        versions = self.presentation["source_versions"]
        value = {**self.presentation, "sources": [
            {"id": "l2", "grade": "L2", "scope": "formal_target", "status": "current"},
            {"id": "l3", "grade": "L3", "scope": "original_problem", "status": "current"},
            {"id": "review", "grade": "llm_reviewed", "scope": "whole_solution_llm_review", "status": "current"},
            {"id": "wrong", "grade": "L3", "scope": "formal_target", "status": "current"},
        ], "delivery": {"selection": {"status": "none_eligible", "eligible": False}}}
        self.assertEqual(["VERIFIED L2", "VERIFIED L3", "REVIEWED"],
                         _public_presentation(value, versions)["grade_labels"])
        value["delivery"]["selection"] = {"status": "candidate_selected", "eligible": True,
                                            "completeness": "partial"}
        self.assertIn("BEST-EFFORT", _public_presentation(value, versions)["grade_labels"])
        self.assertEqual([], _public_presentation(value, {**versions, "state_revision": -1})["grade_labels"])

    def test_unknown_output_identity_degrades_without_selecting_another_artifact(self):
        response = self.client.get(
            f"/api/faithful/runs/{self.run_id}?scheme=f7-deeplink-v1&mode=teach&output=output%3Amissing&artifact=presentation%3Amissing"
        )
        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual("unavailable", response.get_json()["selection"]["status"])
        self.assertIsNone(response.get_json()["selection"]["presentation"])

    def test_partial_output_identity_keeps_the_run_without_selecting_a_saved_output(self):
        for identity in ({"output": self.presentation["output_request"]["id"]},
                         {"artifact": self.presentation["artifact"]["id"]}):
            response = self.client.get(f"/api/faithful/runs/{self.run_id}", query_string={
                "scheme": "f7-deeplink-v1", "paragraph": "paragraph:1", **identity,
            })
            self.assertEqual(200, response.status_code)
            self.assertEqual(self.run_id, response.get_json()["run"]["run_id"])
            self.assertIsNone(response.get_json()["selection"]["presentation"])

    def test_non_get_methods_are_not_registered_for_f7(self):
        response = self.client.post("/api/faithful/runs", headers=self.headers)
        self.assertEqual(405, response.status_code)


class FaithfulF7PersistedSolverTest(StarJobFixture, unittest.TestCase):
    def test_budget_stopped_persisted_candidate_keeps_best_effort_without_a_review_upgrade(self):
        self.open_star([SOLVED],
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=1, max_http_attempts=1, max_tool_calls=0),
            SHOWCASE_PRESENTATION_ENABLED=True, SHOWCASE_F7_SYSTEM_VIEW_ENABLED=True)
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_limited_best_effort",
            "presentation_mode": "report",
        }, headers=self.headers())
        run_id = response.get_json()["job_id"]
        self.assertEqual("failed", self.terminal(run_id)["status"])
        output = self.client.post(f"/api/agent/jobs/{run_id}/report", json={}, headers=self.headers())
        self.assertEqual(200, output.status_code, output.get_json())
        saved = output.get_json()["presentation"]
        response = self.client.get(f"/api/faithful/runs/{run_id}", query_string={
            "scheme": "f7-deeplink-v1", "output": saved["output_request"]["id"],
            "artifact": saved["artifact"]["id"],
        })
        viewed = response.get_json()["selection"]["presentation"]
        self.assertEqual(["BEST-EFFORT"], viewed["grade_labels"])
        self.assertEqual(saved["answer"], viewed["answer"])
        self.assertEqual(1, len(self.outbound))

    def test_current_revision_and_historical_graph_are_read_from_the_same_authoritative_snapshot(self):
        self.enterContext(patch.dict("os.environ", {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(SPEC_REPLIES,
            SHOWCASE_STAR_FEATURES={**SPEC_FEATURES, "proof_graph": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            SHOWCASE_PRESENTATION_ENABLED=True, SHOWCASE_F7_SYSTEM_VIEW_ENABLED=True)
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_limited",
            "presentation_mode": "teach", "problem_spec": SPEC,
        }, headers=self.headers())
        self.assertEqual(202, response.status_code)
        run_id = response.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(run_id)["status"])
        output = self.client.post(f"/api/agent/jobs/{run_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, output.status_code, output.get_json())
        artifact = output.get_json()["presentation"]
        query = {"scheme": "f7-deeplink-v1", "output": artifact["output_request"]["id"],
                 "artifact": artifact["artifact"]["id"], "paragraph": artifact["paragraphs"][0]["id"]}
        call_count = len(self.outbound)
        current = self.client.get(f"/api/faithful/runs/{run_id}", query_string=query).get_json()
        self.assertEqual("current", current["selection"]["presentation"]["freshness"])
        self.assertIn("REVIEWED", current["selection"]["presentation"]["grade_labels"])
        self.assertEqual("available", current["selection"]["paragraph_status"])
        inference_id = current["graph"]["attempts"][0]["id"]
        inference = self.client.get(f"/api/faithful/runs/{run_id}", query_string={
            **query, "graph": current["graph"]["graph_version"], "node": inference_id,
        }).get_json()
        self.assertEqual("available", inference["graph_target"]["status"])
        self.assertEqual(inference_id, inference["graph_target"]["node_id"])
        historical = self.client.get(f"/api/faithful/runs/{run_id}",
                                     query_string={**query, "graph": 0}).get_json()
        self.assertEqual("available", historical["graph_target"]["status"])
        self.assertEqual(0, historical["graph"]["graph_version"])
        missing = self.client.get(f"/api/faithful/runs/{run_id}",
                                  query_string={**query, "graph": 900, "node": "p1"}).get_json()
        self.assertEqual("unavailable", missing["graph_target"]["status"])
        self.assertIsNone(missing["graph"])
        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock, store._connection:
            store._connection.execute(
                "UPDATE solver_states SET state_revision=state_revision+1 WHERE run_id=?", (run_id,),
            )
        stale = self.client.get(f"/api/faithful/runs/{run_id}", query_string=query).get_json()
        self.assertEqual("needs_review", stale["selection"]["presentation"]["freshness"])
        self.assertEqual([], stale["selection"]["presentation"]["grade_labels"])
        self.assertEqual(call_count, len(self.outbound))


if __name__ == "__main__":
    unittest.main()
