"""Black-box contracts for the v0.2 Flask Showcase entry point."""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from showcase.flask_app import create_app
from showcase.profile import ProfileBoundaryError


class FlaskShowcaseContractTest(unittest.TestCase):
    """Exercise the loopback seam through Flask's public HTTP client."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "showcase-v0.2"
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)})
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temp_dir.cleanup()

    def _csrf(self) -> str:
        response = self.client.get("/api/check_auth")
        self.assertEqual(200, response.status_code)
        return response.get_json()["csrf_token"]

    def test_health_keeps_v01_contract_without_model_call(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            {"status": "ok", "service": "showcase_run", "profile": "showcase_mvp"},
            response.get_json(),
        )
        self.assertTrue(response.headers["X-Request-ID"])

    def test_check_auth_creates_loopback_session_and_dashboard_access(self) -> None:
        response = self.client.get("/api/check_auth")

        body = response.get_json()
        self.assertEqual(200, response.status_code)
        self.assertTrue(body["isLoggedIn"])
        self.assertEqual("local", body["username"])
        self.assertIn("dashboard.access", body["permissions"])
        self.assertTrue(body["dashboard"]["access"])
        self.assertTrue(body["csrf_token"])
        cookie = response.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

        restored = self.client.get("/api/check_auth")
        self.assertEqual(body["csrf_token"], restored.get_json()["csrf_token"])
        self.assertNotIn("Set-Cookie", restored.headers)

    def test_logout_revokes_cookie_but_preserves_run_history(self) -> None:
        csrf = self._csrf()
        created = self.client.post(
            "/api/runs",
            json={"problem": "计算 1+1"},
            headers={"X-CSRF-Token": csrf},
        )
        self.assertEqual(201, created.status_code)
        run_id = created.get_json()["run_id"]

        logged_out = self.client.post("/api/logout", headers={"X-CSRF-Token": csrf})
        self.assertEqual({"success": True}, logged_out.get_json())
        self.assertIn("Max-Age=0", logged_out.headers["Set-Cookie"])

        new_auth = self.client.get("/api/check_auth")
        self.assertNotEqual(csrf, new_auth.get_json()["csrf_token"])
        self.assertEqual(200, self.client.get(f"/api/runs/{run_id}").status_code)

    def test_state_changes_require_server_issued_csrf(self) -> None:
        self.client.get("/api/check_auth")

        missing = self.client.post("/api/logout")
        self.assertEqual(403, missing.status_code)
        self.assertEqual("csrf_required", missing.get_json()["error"])

        invalid = self.client.post("/api/logout", headers={"X-CSRF-Token": "invalid"})
        self.assertEqual(403, invalid.status_code)
        self.assertEqual("csrf_invalid", invalid.get_json()["error"])

    def test_capabilities_and_file_compatibility_are_explicit(self) -> None:
        body = self.client.get("/api/capabilities").get_json()

        self.assertEqual("showcase_mvp", body["profile"])
        self.assertTrue(body["jobs"]["enabled"])
        self.assertTrue(body["sse"]["enabled"])
        self.assertEqual(["auto", "required", "off"], body["verification_mode"])
        self.assertFalse(body["files"]["upload"]["enabled"])
        self.assertEqual("unavailable", body["files"]["upload"]["status"])

        response = self.client.post(
            "/api/upload_file",
            data={},
            headers={"X-CSRF-Token": self._csrf()},
        )
        self.assertEqual(503, response.status_code)
        self.assertEqual("capability_unavailable", response.get_json()["error"])

    def test_storage_defaults_are_created_and_profile_boundary_is_explicit(self) -> None:
        self.client.get("/api/check_auth")
        self.assertTrue((self.root / "showcase.sqlite3").exists())
        self.assertTrue((self.root / "attachments").is_dir())
        self.assertTrue((self.root / "events").is_dir())

        with self.assertRaises(ProfileBoundaryError):
            create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root)}, profile="official")

    def test_png_upload_is_unavailable_by_default(self) -> None:
        body = self.client.get("/api/capabilities").get_json()
        self.assertFalse(body["files"]["upload"]["enabled"])

    def test_enabled_png_upload_validates_signature_and_lists_redacted_reference(self) -> None:
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root / "enabled"), "SHOWCASE_VISION_ENABLED": True})
        client = app.test_client()
        try:
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000004000101e2dd0000000049454e44ae426082")
            uploaded = client.post("/api/upload_file", data={"file": (io.BytesIO(png), "题图.png")}, headers={"X-CSRF-Token": csrf}, content_type="multipart/form-data")
            self.assertEqual(201, uploaded.status_code)
            reference = uploaded.get_json()["file"]
            self.assertEqual("image/png", reference["mime"])
            self.assertNotIn("content", reference)
            listed = client.get("/api/files").get_json()
            self.assertEqual(reference["file_id"], listed[0]["file_id"])
            bad = client.post("/api/upload_file", data={"file": (io.BytesIO(b"not png"), "fake.png")}, headers={"X-CSRF-Token": csrf}, content_type="multipart/form-data")
            self.assertEqual(400, bad.status_code)
            self.assertEqual("image_signature_invalid", bad.get_json()["error"])
            removed = client.post("/api/delete_file", json={"file_id": reference["file_id"]}, headers={"X-CSRF-Token": csrf})
            self.assertEqual(200, removed.status_code)
            self.assertEqual([], client.get("/api/files").get_json())
        finally:
            app.extensions["showcase_run_service"].close()
            app.extensions["loopback_store"].close()

    def test_png_reference_enters_job_report_without_binary(self) -> None:
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(self.root / "job"), "SHOWCASE_VISION_ENABLED": True})
        client = app.test_client()
        try:
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            session = client.post("/api/new_chat", json={}, headers={"X-CSRF-Token": csrf}).get_json()["new_session_id"]
            png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000004000101e2dd0000000049454e44ae426082")
            uploaded = client.post("/api/upload_file", data={"file": (io.BytesIO(png), "q.png")}, headers={"X-CSRF-Token": csrf}, content_type="multipart/form-data").get_json()["file"]
            import uuid
            created = client.post("/api/agent/jobs", json={"message": "看图", "session_id": session, "input_user_file_id": uploaded["file_id"]}, headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())})
            self.assertEqual(202, created.status_code)
            report = client.get(f"/api/agent/jobs/{created.get_json()['job_id']}/report")
            self.assertEqual(uploaded["file_id"], report.get_json()["report"].get("asset_refs", [{}])[0].get("file_id"))
        finally:
            app.extensions["showcase_run_service"].close()
            app.extensions["loopback_store"].close()


if __name__ == "__main__":
    unittest.main()
