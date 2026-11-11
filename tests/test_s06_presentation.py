"""S06 output artifacts retain answer identity and conservative evidence scope."""

import copy
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.final_evidence import artifact_identity, bind_verification
from showcase.flask_app import create_app
from showcase.presentation import build_presentation, presentation_snapshot, revalidate
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_faithful_s03_job import (
    CAPACITY_POLICY,
    ENDPOINT,
    SPEC,
)
from tests.test_faithful_s03_job import (
    FEATURES as SPEC_FEATURES,
)
from tests.test_faithful_s03_job import (
    REPLIES as SPEC_REPLIES,
)
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN


def job_fixture():
    answer = "1+1=2"
    return {
        "job_id": "run_s06", "status": "succeeded",
        "result": {
            "final_response": answer,
            "verification": bind_verification(answer, {
                "status": "unknown", "scope": "whole_solution_llm_review",
                "findings": ["llm_whole_review_accept"],
            }),
            "solver": {
                "state_revision": 12,
                "semantics": {"whole_review": "accepted", "binding": "same_artifact",
                              "formal_verification": "not_verified"},
                "progress": {"root_obligations": {
                    "covered": 1, "total": 2,
                    "items": [{"ordinal": 1, "type": "universal", "status": "satisfied"},
                              {"ordinal": 2, "type": "existential", "status": "unresolved"}],
                }},
            },
        },
    }


class PresentationBindingTest(unittest.TestCase):
    def test_modes_have_separate_artifacts_and_never_replace_original_answer(self):
        job = job_fixture()
        old = copy.deepcopy(job)
        snapshot = presentation_snapshot(job)
        artifacts = [build_presentation(snapshot, mode) for mode in ("solve", "teach", "report")]
        self.assertEqual(3, len({item["artifact"]["id"] for item in artifacts}))
        for artifact in artifacts:
            self.assertEqual(artifact_identity("1+1=2"), artifact["answer_artifact"])
            self.assertEqual("1+1=2", artifact["answer"])
            self.assertEqual("partial", artifact["completion"])
            self.assertEqual(1, artifact["scope"]["covered"])
            self.assertEqual([2], [item["ordinal"] for item in artifact["scope"]["unresolved"]])
        self.assertEqual(old, job)

    def test_rewritten_math_cannot_inherit_exact_text_review_even_with_valid_refs(self):
        snapshot = presentation_snapshot(job_fixture())
        quoted = build_presentation(snapshot, "teach")
        refs = quoted["paragraphs"][-1]["claim_refs"]
        rewritten = build_presentation(snapshot, "teach", paragraphs=[{
            "text": "1+1=3", "kind": "mathematical", "claim_refs": refs,
        }])
        paragraph = rewritten["paragraphs"][0]
        self.assertEqual("pending_verification", paragraph["status"])
        self.assertEqual("artifact_changed", paragraph["binding"])
        self.assertEqual("proposed", paragraph["proof_attempt"]["status"])
        self.assertEqual("not_verified", paragraph["grade"])
        self.assertEqual("not_verified", rewritten["formal_verification"])
        self.assertEqual("1+1=2", rewritten["answer"])

    def test_missing_or_invented_claim_sources_remain_pending(self):
        snapshot = presentation_snapshot(job_fixture())
        for refs in ([], ["verification:invented"]):
            with self.subTest(refs=refs):
                artifact = build_presentation(snapshot, "report", paragraphs=[{
                    "text": "1+1=2", "kind": "mathematical", "claim_refs": refs,
                }])
                self.assertEqual("pending_verification", artifact["paragraphs"][0]["status"])
                self.assertEqual([], artifact["paragraphs"][0]["claim_refs"])

    def test_current_evidence_change_marks_old_artifact_for_review_without_rewriting_it(self):
        job = job_fixture()
        artifact = build_presentation(presentation_snapshot(job), "teach")
        old = copy.deepcopy(artifact)
        job["result"]["solver"]["semantics"]["whole_review"] = "invalid_source"
        current = revalidate(artifact, presentation_snapshot(job))
        self.assertEqual("needs_review", current["status"])
        self.assertEqual("source_changed", current["revalidation_reason"])
        self.assertTrue(all(p["status"] != "current" for p in current["paragraphs"] if p["kind"] == "mathematical"))
        self.assertEqual(old, artifact)

    def test_public_snapshot_whitelists_sources_and_does_not_expose_private_proof(self):
        job = job_fixture()
        job["result"]["solver"]["private_proof"] = "PRIVATE_PROOF"
        job["result"]["verification"]["history"][0]["request"] = "PRIVATE_PROMPT"
        job["result"]["solver"]["progress"]["root_obligations"]["items"][0]["statement"] = "PRIVATE_ROOT"
        artifact = build_presentation(presentation_snapshot(job), "report")
        encoded = str(artifact)
        for secret in ("PRIVATE_PROOF", "PRIVATE_PROMPT", "PRIVATE_ROOT"):
            self.assertNotIn(secret, encoded)

    def test_no_answer_stays_incomplete_in_all_modes(self):
        job = job_fixture()
        job["result"]["final_response"] = ""
        for mode in ("solve", "teach", "report"):
            artifact = build_presentation(presentation_snapshot(job), mode)
            self.assertEqual("incomplete", artifact["completion"])
            self.assertEqual([], artifact["paragraphs"])


class PublicPresentationApiTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": str(Path(self.temp_dir.name) / "data"),
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_PRESENTATION_ENABLED": True,
        })
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _headers(self, key):
        return {"X-CSRF-Token": self.client.get("/api/check_auth").get_json()["csrf_token"],
                "Idempotency-Key": key}

    def _job(self, mode="teach", key="b8e43a9b-32a5-4bb3-bc4b-4c0e8e8d32a0"):
        headers = self._headers(key)
        session = self.client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        response = self.client.post("/api/agent/jobs", json={
            "message": "计算 1+1", "session_id": session, "presentation_mode": mode,
        }, headers=headers)
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        for _ in range(100):
            if self.client.get(f"/api/agent/jobs/{job_id}").get_json()["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        return job_id, headers

    def test_mode_is_frozen_and_idempotency_includes_it(self):
        job_id, headers = self._job("teach")
        job = self.client.get(f"/api/agent/jobs/{job_id}").get_json()
        self.assertEqual("teach", job["result"]["presentation_mode"])
        self.assertEqual("faithful-output-v2", job["result"]["presentation_policy_version"])
        session = job["session_id"]
        conflict = self.client.post("/api/agent/jobs", json={
            "message": "计算 1+1", "session_id": session, "presentation_mode": "report",
        }, headers=headers)
        self.assertEqual(409, conflict.status_code)
        self.assertEqual("idempotency_conflict", conflict.get_json()["code"])

    def test_explicit_outputs_keep_answer_and_persist_artifact(self):
        job_id, headers = self._job("teach")
        response = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=headers)
        self.assertEqual(200, response.status_code, response.get_json())
        body = response.get_json()
        self.assertEqual("teach", body["presentation"]["mode"])
        self.assertEqual("Fake Agent completed a deterministic showcase run.", body["answer"])
        self.assertNotEqual(body["answer"], body["presentation"]["paragraphs"][0]["text"])
        self.assertEqual(body["answer"], body["report"]["answer"])
        self.assertIn("artifact", body["presentation"])
        second = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=headers)
        self.assertEqual(body, second.get_json())

    def test_mode_mismatch_and_failed_presentation_keep_original_answer(self):
        job_id, headers = self._job("teach")
        mismatch = self.client.post(f"/api/agent/jobs/{job_id}/report", json={}, headers=headers)
        self.assertEqual(409, mismatch.status_code)
        self.assertEqual("presentation_mode_mismatch", mismatch.get_json()["code"])
        failure = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={"renderer": "fail"}, headers=headers)
        self.assertEqual(200, failure.status_code)
        body = failure.get_json()
        self.assertEqual("failed", body["presentation"]["status"])
        self.assertEqual(body["report"]["answer"], body["answer"])

    def test_old_job_without_mode_defaults_to_solve(self):
        job_id, headers = self._job("solve", "abf2a64c-8b3f-43f6-89d8-4c8e3d72cfd3")
        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock:
            row = store._connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            result = json.loads(row["result_json"])
            result.pop("presentation_mode", None)
            result.pop("presentation_schema_version", None)
            result.pop("presentation_policy_version", None)
            store._connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                                      (json.dumps(result), job_id))
            store._connection.commit()
        body = self.client.post(f"/api/agent/jobs/{job_id}/solve", json={}, headers=headers)
        self.assertEqual(409, body.status_code)
        self.assertEqual("presentation_run_not_frozen", body.get_json()["code"])

    def test_default_off_capability_rejects_explicit_mode_without_freezing_it(self):
        disabled_dir = Path(self.temp_dir.name) / "disabled"
        disabled = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(disabled_dir),
                               "SHOWCASE_PRESENTATION_ENABLED": False})
        try:
            client = disabled.test_client()
            caps = client.get("/api/capabilities").get_json()
            self.assertFalse(caps["presentation"]["enabled"])
            headers = {"X-CSRF-Token": client.get("/api/check_auth").get_json()["csrf_token"],
                       "Idempotency-Key": "90788e4c-9895-4df7-9aeb-3d073357c120"}
            session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
            response = client.post("/api/agent/jobs", json={
                "message": "计算 1+1", "session_id": session, "presentation_mode": "teach",
            }, headers=headers)
            self.assertEqual(503, response.status_code)
            self.assertEqual("capability_unavailable", response.get_json()["code"])
            self.assertEqual([], disabled.extensions["showcase_workspace_service"].store._connection.execute(
                "SELECT job_id FROM workspace_jobs").fetchall())
        finally:
            disabled.extensions["showcase_workspace_service"].close()
            disabled.extensions["showcase_run_service"].close()
            disabled.extensions["loopback_store"].close()

    def test_non_object_presentation_body_is_bad_request(self):
        job_id, headers = self._job("teach")
        response = self.client.post(f"/api/agent/jobs/{job_id}/teach", json=[], headers=headers)
        self.assertEqual(400, response.status_code)
        self.assertEqual("presentation_request_invalid", response.get_json()["code"])


class CurrentSolverPresentationTest(StarJobFixture, unittest.TestCase):
    def test_public_artifact_saves_with_authoritative_graph_and_specification_versions(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(SPEC_REPLIES,
            SHOWCASE_STAR_FEATURES={**SPEC_FEATURES, "proof_graph": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            SHOWCASE_PRESENTATION_ENABLED=True)
        headers = self.headers()
        created = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_limited",
            "presentation_mode": "teach", "problem_spec": SPEC,
        }, headers=headers)
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"], self.terminal(job_id))

        response = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())

        self.assertEqual(200, response.status_code, response.get_json())
        artifact = response.get_json()["presentation"]
        self.assertEqual(1, artifact["source_versions"]["specification_version"])
        self.assertEqual(2, artifact["source_versions"]["graph_version"])
        self.assertEqual(artifact, self.app.extensions["showcase_workspace_service"].get_presentation(
            user_id=self.app.extensions["loopback_store"].get(
                self.client.get_cookie("auth_session").value).user_id,
            job_id=job_id, mode="teach", source_fingerprint=artifact["source_fingerprint"],
        ))
        deadline = artifact["budget"]["deadline_at"]
        calls = len(self.outbound)
        with patch("showcase.run_budget.time.time", return_value=deadline + 1):
            expired = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, expired.status_code, expired.get_json())
        expired_output = expired.get_json()["presentation"]
        self.assertEqual(deadline, expired_output["budget"]["deadline_at"])
        self.assertFalse(expired_output["output_request"]["solver_resumed"])
        self.assertEqual(calls, len(self.outbound))

    def test_evidence_invalidation_marks_history_without_mutating_old_artifact(self):
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [{"step_id": "step", "title": "Add", "objective": "Add"}]},
            {"argument": "Addition", "claims": [], "blocked": False},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            SHOWCASE_PRESENTATION_ENABLED=True)
        headers = self.headers()
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_limited",
            "presentation_mode": "teach",
        }, headers=headers)
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        first = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, first.status_code, first.get_json())
        original = first.get_json()["presentation"]

        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock:
            row = store._connection.execute(
                "SELECT state_json,state_revision FROM solver_states WHERE run_id=?", (job_id,)
            ).fetchone()
            state = json.loads(row["state_json"])
            self.assertTrue(state.get("whole_solution_reviews"), state)
            state["whole_solution_reviews"][-1]["invalidated"] = True
            state["whole_solution_reviews"][-1]["invalidated_by_specification_version"] = 2
            state["state_revision"] = int(row["state_revision"]) + 1
            store._connection.execute(
                "UPDATE solver_states SET state_json=?,state_revision=? WHERE run_id=?",
                (json.dumps(state, ensure_ascii=False), state["state_revision"], job_id),
            )
            store._connection.commit()

        second = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(200, second.status_code, second.get_json())
        body = second.get_json()
        self.assertTrue(body["presentation_history"], body)
        historical = body["presentation_history"][0]
        self.assertEqual(original["artifact"], historical["artifact"])
        self.assertEqual("needs_review", historical["status"])
        self.assertEqual("source_changed", historical["revalidation_reason"])
        stored = store.get_presentation(job_id, self.app.extensions["loopback_store"].get(self.client.get_cookie("auth_session").value).user_id, "teach", original["source_fingerprint"])
        self.assertEqual(original, stored)
        self.assertEqual(body["report"]["budget"], body["presentation"]["budget"])

    def test_public_save_rejects_snapshot_when_solver_revision_races(self):
        self.open_star([
            NEED_PLAN,
            {"version": 1, "steps": [{"step_id": "step", "title": "Add", "objective": "Add"}]},
            {"argument": "Addition", "claims": [], "blocked": False},
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
            {"final_response": "2"}, ACCEPT,
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            SHOWCASE_PRESENTATION_ENABLED=True)
        headers = self.headers()
        created = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session, "solver_mode": "star_limited",
            "presentation_mode": "teach",
        }, headers=headers)
        job_id = created.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        store = self.app.extensions["showcase_workspace_service"].store
        from showcase.presentation import build_presentation as build

        def race_after_snapshot(snapshot, mode):
            artifact = build(snapshot, mode)
            with store._lock:
                store._connection.execute(
                    "UPDATE solver_states SET state_revision=state_revision+1 WHERE run_id=?", (job_id,)
                )
                store._connection.commit()
            return artifact

        with patch("showcase.presentation_api.build_presentation", side_effect=race_after_snapshot):
            response = self.client.post(f"/api/agent/jobs/{job_id}/teach", json={}, headers=self.headers())
        self.assertEqual(409, response.status_code, response.get_json())
        self.assertEqual("presentation_source_changed", response.get_json()["code"])
        auth_cookie = self.client.get_cookie("auth_session")
        user_id = self.app.extensions["loopback_store"].get(auth_cookie.value).user_id
        self.assertEqual([], store.list_presentations(job_id, user_id, "teach"))
        self.assertEqual("2", self.report(job_id)["answer"])


if __name__ == "__main__":
    unittest.main()
