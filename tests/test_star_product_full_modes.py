"""Full presets use public Job admission and real isolated Registry readiness."""

import json
import os
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_star_product_python import NEED_PLAN, PLAN, STEP, VERDICT

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")
CORE = {
    "star_routing", "persistent_sessions", "stream_recovery", "final_generation",
    "final_solution_review", "local_code_tool", "meta_guidance", "reexplore_after_replan", "skills",
}


@unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
class StarFullModeTest(StarJobFixture, unittest.TestCase):
    def open_full(self, replies, **config):
        self.open_star(replies, SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE, **config)

    def submit(self, mode="star_reference", **body):
        return self.client.post("/api/agent/jobs", json={
            "message": "Factor x^2-1.", "session_id": self.session, "solver_mode": mode, **body,
        }, headers=self.headers())

    def test_reference_runs_same_public_job_with_real_tool_and_whole_review(self):
        self.open_full([NEED_PLAN, PLAN, STEP, VERDICT,
                        {"final_response": "x^2-1=(x-1)(x+1)."}, ACCEPT])
        response = self.submit()
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        report = self.report(job_id)
        self.assertEqual(6, report["budget"]["logical_calls"])
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(48, report["budget"]["limits"]["max_model_calls"])
        self.assertEqual(48, report["budget"]["limits"]["max_http_attempts"])
        self.assertEqual(8, report["budget"]["limits"]["max_tool_calls"])
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(IMAGE, receipt["image"])
        self.assertEqual("same_artifact", report["checks"]["binding"])
        # The final generator and the whole-solution reviewer receive the
        # complete proof body of the accepted step with its real isolated
        # receipt; the delivered basis is identical for both roles.
        final = next(r for r in self.outbound if r["role"] == "final_generator")
        proofs = final["step_proofs"]
        self.assertEqual(["factor"], [p["step_id"] for p in proofs])
        self.assertEqual("Factor the difference of squares", proofs[0]["argument"])
        proof_receipts = proofs[0]["tool_receipts"]
        self.assertEqual(1, len(proof_receipts))
        self.assertTrue(proof_receipts[0]["executed"])
        self.assertEqual("success", proof_receipts[0]["status"])
        self.assertEqual("docker_isolated", proof_receipts[0]["source"])
        self.assertEqual(IMAGE, proof_receipts[0]["image"])
        self.assertEqual("(x - 1)*(x + 1)\n", proof_receipts[0]["output"])
        self.assertEqual("verified", proofs[0]["claims"][0]["label"])
        self.assertEqual("finite_computation", proofs[0]["claims"][0]["verification_scope"])
        review = next(r for r in self.outbound if r["role"] == "whole_solution_verifier")
        self.assertEqual(final["step_proofs"], review["step_proofs"])
        initial = self.outbound[0]
        self.assertIn("exploration-protocol", initial["active_skill_ids"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual("star_reference", evidence["mode"])
        modes = self.client.get("/api/capabilities").get_json()["solver_modes"]
        full = next(item for item in modes if item["solver_mode"] == "star_reference")
        self.assertTrue(full["enabled"])
        self.assertEqual([], full["missing_capabilities"])
        self.assertNotIn("acceptance_passed", full)

    def test_capabilities_expose_verifiable_preflight_artifact_reference(self):
        from showcase.tool_artifacts import ToolArtifactStore

        self.open_full([])
        self.assertEqual(202, self.submit().status_code)
        record = next(item for item in self.client.get("/api/capabilities").get_json()["solver_modes"]
                      if item["solver_mode"] == "star_reference")
        preflight = record.get("last_preflight")
        self.assertIsNotNone(preflight, record)
        self.assertTrue(preflight["run_id"].startswith("star-preflight-"))
        self.assertEqual(IMAGE, preflight["image_id"])
        receipt_ref = preflight["receipt_ref"]
        self.assertEqual("isolation-probe", receipt_ref["call_id"])
        receipt = json.loads(ToolArtifactStore(
            Path(self.data_dir) / "tool_artifacts").read(preflight["run_id"], receipt_ref["sha256"]))
        self.assertEqual("success", receipt["status"])
        self.assertEqual("(x - 1)*(x + 1)\n", receipt["stdout"])
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(IMAGE, receipt["environment"]["image_id"])

    def test_reference_preset_is_exactly_nine_core_features_and_registry_inactive(self):
        from showcase.solver_harness.harness_config import _hash_json
        from showcase.star_product_config import full_config

        self.open_full([NEED_PLAN, PLAN, STEP, VERDICT,
                        {"final_response": "x^2-1=(x-1)(x+1)."}, ACCEPT])
        job_id = self.submit().get_json()["job_id"]
        result = self.terminal(job_id)["result"]
        self.assertEqual("star_reference", result["execution_mode"])
        expected = {**full_config(RunBudgetLimits(
            max_model_calls=48, max_http_attempts=48, max_tool_calls=8)),
            "hint_mode": "none", "tool_timeout_seconds": 20}
        self.assertEqual(set(CORE), set(expected["features"]))
        self.assertNotIn("candidate_registry", expected["features"])
        self.assertNotIn("best_effort", expected["features"])
        self.assertEqual(_hash_json(expected), result["solver"]["config_hash"])
        self.assertEqual([], result["solver"]["candidate_history"])
        self.assertIsNone(result["solver"]["best_effort"])

    def test_capabilities_expose_verifiable_preflight_budget_ledger(self):
        from showcase.tool_artifacts import ToolArtifactStore

        self.open_full([])
        self.assertEqual(202, self.submit().status_code)
        record = next(item for item in self.client.get("/api/capabilities").get_json()["solver_modes"]
                      if item["solver_mode"] == "star_reference")
        preflight = record.get("last_preflight")
        self.assertIsNotNone(preflight, record)
        budget_ref = preflight.get("budget_ref")
        self.assertIsNotNone(budget_ref, preflight)
        self.assertEqual("isolation-probe", budget_ref["call_id"])
        ledger = json.loads(ToolArtifactStore(
            Path(self.data_dir) / "tool_artifacts").read(preflight["run_id"], budget_ref["sha256"]))
        self.assertTrue(ledger["run_id"].startswith("star-preflight-"))
        self.assertEqual(1, ledger["summary"]["limits"]["max_tool_calls"])
        self.assertGreaterEqual(ledger["summary"]["tool_calls"], 1)
        self.assertEqual("tool", ledger["actions"][0]["kind"])
        self.assertEqual("success", ledger["actions"][0]["status"])

    def test_full_best_effort_selects_after_one_call_and_replays_without_dispatch(self):
        self.open_full([SOLVED], SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(
            max_model_calls=1, max_http_attempts=1, max_tool_calls=1))
        response = self.submit("star_best_effort")
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        result = self.terminal(job_id)["result"]
        self.assertEqual("2", result["final_response"])
        self.assertEqual("candidate_selected", result["solver"]["best_effort"]["status"])
        self.assertEqual(1, len(self.outbound))
        self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
        first = self.client.get(f"/api/agent/jobs/{job_id}/candidate-replay")
        self.assertEqual(200, first.status_code, first.get_json())
        self.assertEqual(first.get_json(), self.client.get(
            f"/api/agent/jobs/{job_id}/candidate-replay").get_json())
        self.assertEqual(1, len(self.outbound))

    def test_each_core_feature_missing_or_disabled_rejects_before_enqueue(self):
        for feature in sorted(CORE):
            for missing in (False, True):
                with self.subTest(feature=feature, missing=missing):
                    features = dict.fromkeys(CORE, True)
                    if missing:
                        features.pop(feature)
                    else:
                        features[feature] = False
                    self.open_full([], SHOWCASE_STAR_FULL_FEATURES=features)
                    response = self.submit()
                    self.assertEqual(503, response.status_code, response.get_json())
                    self.assertEqual([], self.outbound)
                    self.assertEqual([], self.client.get("/api/agent/jobs/active").get_json()["jobs"])
                    modes = self.client.get("/api/capabilities").get_json()["solver_modes"]
                    reference = next(m for m in modes if m["solver_mode"] == "star_reference")
                    self.assertFalse(reference["enabled"])
                    self.assertIn(f"feature:{feature}", reference["missing_capabilities"])

    def test_runtime_isolation_failure_after_startup_rejects_without_model_or_job(self):
        self.open_full([])
        for failure in (
            {"status": "unavailable", "executed": False, "cleanup_verified": True},
            {"status": "unknown_outcome", "executed": True, "cleanup_verified": False},
        ):
            with self.subTest(failure=failure), patch(
                "showcase.python_executor.DockerPythonExecutor.execute", return_value=failure,
            ):
                response = self.submit()
                self.assertEqual(503, response.status_code, response.get_json())
                self.assertEqual([], self.outbound)
                modes = self.client.get("/api/capabilities").get_json()["solver_modes"]
                reference = next(m for m in modes if m["solver_mode"] == "star_reference")
                self.assertFalse(reference["enabled"])
                self.assertIn("isolated_python_preflight_failed", reference["missing_capabilities"])
        self.assertEqual([], self.client.get("/api/agent/jobs/active").get_json()["jobs"])

    def test_full_options_and_disabled_review_reject_before_model(self):
        self.open_full([])
        for body in ({"solver_options": {"skills": False}}, {"verification_mode": "off"}):
            response = self.submit(**body)
            self.assertEqual(400, response.status_code, response.get_json())
        self.assertEqual([], self.outbound)

    def test_full_flag_does_not_upgrade_limited_mode_or_default_legacy(self):
        self.open_full([SOLVED, POLISH, ACCEPT])
        response = self.submit("star_limited")
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_limited", job["result"]["execution_mode"])
        self.assertIn("feature:skills", job["result"]["missing_capabilities"])
        capabilities = self.client.get("/api/capabilities").get_json()["solver_modes"]
        self.assertTrue(next(m for m in capabilities if m["solver_mode"] == "legacy")["enabled"])
        legacy = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session,
        }, headers=self.headers())
        self.assertEqual(202, legacy.status_code)
        self.assertEqual("succeeded", self.terminal(legacy.get_json()["job_id"])["status"])
        self.assertEqual(3, len(self.outbound))

    def test_full_unknown_call_requires_new_identity_and_preserves_shared_deadline(self):
        self.open_full([requests.Timeout(), SOLVED, POLISH, ACCEPT])
        response = self.submit()
        job_id = response.get_json()["job_id"]
        first = self.terminal(job_id)
        old = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={
            "retry_call": {"call_id": old, "new_call_id": str(uuid.uuid4())},
        }, headers=self.headers())
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        result = self.terminal(job_id)["result"]
        self.assertEqual("completed_llm_reviewed", result["solver"]["status"])
        self.assertEqual(first["result"]["budget"]["deadline_at"], result["budget"]["deadline_at"])
        self.assertEqual(4, len(self.outbound))
        self.assertEqual(1, result["budget"]["unresolved_attempts"])
        bypass = self.client.post(f"/api/runs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, bypass.status_code)

    def test_full_best_effort_deadline_selects_only_previously_committed_candidate(self):
        def late_polish(_request):
            time.sleep(1.1)
            return {"solution_candidate": "late answer"}

        self.open_full([SOLVED, late_polish], SHOWCASE_STAR_FULL_BUDGET=RunBudgetLimits(
            max_model_calls=8, max_http_attempts=8, max_tool_calls=1, max_runtime_seconds=1))
        response = self.submit("star_best_effort")
        result = self.terminal(response.get_json()["job_id"])["result"]
        self.assertIn("final_response", result, result)
        self.assertEqual("2", result["final_response"])
        self.assertEqual("candidate_selected", result["solver"]["best_effort"]["status"])
        self.assertEqual(2, len(self.outbound))
        self.assertEqual(0, result["budget"]["tool_calls"])
        self.assertFalse(any(item["role"] == "whole_solution_verifier" for item in self.outbound))


class StarFullUnavailableTest(StarJobFixture, unittest.TestCase):
    def test_no_isolated_registry_keeps_full_closed_and_default_legacy_available(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        registry.register_python_math()
        self.open_star([], SHOWCASE_STAR_FULL_ENABLED=True, SHOWCASE_STAR_REGISTRY=registry)
        modes = self.client.get("/api/capabilities").get_json()["solver_modes"]
        for mode in ("star_reference", "star_best_effort"):
            record = next(m for m in modes if m["solver_mode"] == mode)
            self.assertFalse(record["enabled"])
            self.assertIn("isolated_python_required", record["missing_capabilities"])
            response = self.client.post("/api/agent/jobs", json={
                "message": "1+1", "session_id": self.session, "solver_mode": mode,
            }, headers=self.headers())
            self.assertEqual(503, response.status_code)
        self.assertEqual([], self.outbound)
        legacy = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session,
        }, headers=self.headers())
        self.assertEqual(202, legacy.status_code)
        self.assertEqual("succeeded", self.terminal(legacy.get_json()["job_id"])["status"])
        self.assertEqual([], self.outbound)

    def test_default_server_flag_keeps_full_presets_closed(self):
        self.open_star([])
        modes = self.client.get("/api/capabilities").get_json()["solver_modes"]
        for mode in ("star_reference", "star_best_effort"):
            record = next(m for m in modes if m["solver_mode"] == mode)
            self.assertFalse(record["enabled"])
            self.assertIn("full_mode_not_enabled", record["missing_capabilities"])

    def test_capabilities_without_star_pipeline_do_not_enumerate_limited_feature_gaps(self):
        import tempfile

        from showcase.flask_app import create_app

        with tempfile.TemporaryDirectory() as folder:
            app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": folder})
            client = app.test_client()
            try:
                modes = client.get("/api/capabilities").get_json()["solver_modes"]
                for mode in ("star_limited", "star_limited_best_effort"):
                    record = next(m for m in modes if m["solver_mode"] == mode)
                    self.assertFalse(record["enabled"])
                    self.assertEqual(["star_not_enabled"], record["missing_capabilities"], record)
                    self.assertFalse(any(gap.startswith("feature:")
                                         or gap == "isolated_python_registry"
                                         for gap in record["missing_capabilities"]))
            finally:
                for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
                    app.extensions[name].close()


class StarContractAnchorTest(unittest.TestCase):
    def test_contract_python_image_id_is_pinned_in_code(self):
        from showcase.star_product_runtime import CONTRACT_PYTHON_IMAGE_ID

        self.assertEqual(
            "sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d",
            CONTRACT_PYTHON_IMAGE_ID,
        )


