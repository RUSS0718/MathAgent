"""Paired campaigns through the public Flask contract, using public toy problems."""

import hashlib
import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app


def campaign_input():
    return {
        "schema_version": 1,
        "dataset_version": "public-toy-v1",
        "problems": [{"id": "addition", "problem": "Compute 1+1."}],
        "model": "intern-s2",
        "allow_network": False,
        "budget": {
            "max_model_calls": 0,
            "max_http_attempts": 0,
            "max_tool_calls": 0,
            "max_tokens": 0,
            "max_runtime_seconds": 30,
        },
        "conditions": {"thinking_mode": True, "max_tokens": 256},
        "strategies": {
            "baseline": {"verification_mode": "auto"},
            "candidate": {"verification_mode": "auto"},
        },
    }


class CampaignFixture(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(
            os.environ, {"INTERN_API_KEY": "deterministic-test-key", "INTERN_MODEL": "intern-s2"}
        )
        self.env.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "fake",
                "SHOWCASE_DATA_DIR": str(self.root / "artifacts" / "workspace"),
                "SHOWCASE_JOB_DELAY_SECONDS": 0,
            }
        )
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]

    def tearDown(self):
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.tmp.cleanup()
        self.env.stop()

    def submit(self, payload=None, key=None):
        return self.client.post(
            "/api/experiments/campaigns",
            json=payload or campaign_input(),
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key or str(uuid.uuid4())},
        )

    def detail(self, campaign_id):
        return self.client.get(f"/api/experiments/campaigns/{campaign_id}").get_json()

    def finished(self, campaign_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            report = self.detail(campaign_id)
            if report["status"] == "completed":
                return report
            time.sleep(0.01)
        self.fail(str(report))


class CampaignContractTest(CampaignFixture):
    def test_closing_fake_workspace_keeps_borrowed_run_connection_available(self):
        report = self.finished(self.submit().get_json()["campaign_id"])
        job_id = report["pairs"][0]["arms"]["baseline"]["job_id"]
        self.app.extensions["showcase_workspace_service"].close()
        self.assertEqual(200, self.client.get(f"/api/runs/{job_id}").status_code)

    def test_fake_pair_is_durable_and_links_existing_runs_and_evidence(self):
        key = str(uuid.uuid4())
        response = self.submit(key=key)
        self.assertEqual(202, response.status_code)
        campaign_id = response.get_json()["campaign_id"]
        self.assertEqual(campaign_id, self.submit(key=key).get_json()["campaign_id"])
        report = self.finished(campaign_id)
        self.assertEqual("fake", report["mode"])
        self.assertEqual(1, len(report["pairs"]))
        self.assertEqual(report["common_hash"], report["pairs"][0]["common_hash"])
        for arm in report["pairs"][0]["arms"].values():
            self.assertEqual("succeeded", arm["status"])
            self.assertEqual(0, arm["usage"]["http_attempts"])
            self.assertIsNone(arm["cost"])
            self.assertEqual(200, self.client.get(arm["evidence_url"]).status_code)
            self.assertEqual('fake', self.client.get(arm['report_url']).get_json()['mode'])
            self.assertEqual(report["common"]["budget"], arm["budget"]["limits"])
        listed = self.client.get("/api/experiments/campaigns").get_json()
        self.assertEqual(campaign_id, listed["campaigns"][0]["campaign_id"])

    def test_failed_pair_and_unknown_quality_are_retained_with_archive_hashes(self):
        payload = campaign_input()
        payload["strategies"]["candidate"]["verification_mode"] = "required"
        campaign_id = self.submit(payload).get_json()["campaign_id"]
        report = self.finished(campaign_id)
        pair = report["pairs"][0]
        self.assertEqual("succeeded", pair["arms"]["baseline"]["status"])
        self.assertEqual("failed", pair["arms"]["candidate"]["status"])
        self.assertEqual("unknown", pair["arms"]["candidate"]["quality"]["status"])
        self.assertEqual(0, report["summary"]["successful_pairs"])
        archive_root = self.root / "artifacts" / "workspace" / "campaigns"
        artifact = report["archive"]
        data = (archive_root / artifact["path"]).read_bytes()
        self.assertEqual(artifact["sha256"], hashlib.sha256(data).hexdigest())
        self.assertNotIn("archive", json.loads(data))
        self.assertEqual(report, self.detail(campaign_id))

    def test_common_config_and_strategy_boundary_reject_mismatches(self):
        for field, value in (
            ("model", "intern-latest"),
            ("allow_network", True),
            ("strategies", {"baseline": {}, "candidate": {"budget": {}}}),
        ):
            with self.subTest(field=field):
                payload = campaign_input()
                payload[field] = value
                self.assertIn(self.submit(payload).status_code, (400, 409, 503))
        key = str(uuid.uuid4())
        self.assertEqual(202, self.submit(key=key).status_code)
        payload = campaign_input()
        payload["dataset_version"] = "v2"
        self.assertEqual(409, self.submit(payload, key).status_code)

    def test_deadline_failures_are_preserved_for_both_arms(self):
        payload = campaign_input()
        payload["budget"]["max_runtime_seconds"] = 0
        report = self.finished(self.submit(payload).get_json()["campaign_id"])
        for arm in report["pairs"][0]["arms"].values():
            self.assertEqual("failed", arm["status"])
            self.assertEqual("run_deadline_exhausted", arm["error"])

    def test_public_child_report_reads_committed_budget_while_writer_is_reserved(self):
        import sqlite3

        report = self.finished(self.submit().get_json()["campaign_id"])
        arm = report["pairs"][0]["arms"]["baseline"]
        writer = sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])
        try:
            writer.execute("BEGIN IMMEDIATE")
            started = time.monotonic()
            response = self.client.get(arm["report_url"])
            self.assertEqual(200, response.status_code)
            self.assertLess(time.monotonic() - started, 1)
        finally:
            writer.rollback()
            writer.close()

    def test_cli_creates_and_reads_campaign_using_shared_http_contract(self):
        import subprocess
        import sys
        import threading

        from werkzeug.serving import make_server

        server = make_server("127.0.0.1", 0, self.app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        payload_path = self.root / "runtime-input.json"
        payload_path.write_text(json.dumps(campaign_input()), encoding="utf-8")
        command = [
            sys.executable,
            "showcase_cli.py",
            "--base-url",
            f"http://127.0.0.1:{server.server_port}",
            "--cookie-file",
            str(self.root / "cli.cookies"),
            "campaign",
        ]
        try:
            created = subprocess.run(
                [*command, "create", str(payload_path), "--idempotency-key", str(uuid.uuid4())],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, created.returncode, created.stderr)
            campaign_id = json.loads(created.stdout)["campaign_id"]
            detail = subprocess.run(
                [*command, "detail", campaign_id],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, detail.returncode, detail.stderr)
            self.assertEqual(campaign_id, json.loads(detail.stdout)["campaign_id"])
        finally:
            server.shutdown()
            thread.join(2)
            server.server_close()

    def test_incomplete_and_canceled_pairs_survive_restart_without_dispatch(self):
        self.app.extensions["showcase_workspace_service"].worker_enabled = False
        campaign_id = self.submit().get_json()["campaign_id"]
        before = self.detail(campaign_id)
        job_id = before["pairs"][0]["arms"]["baseline"]["job_id"]
        canceled = self.client.post(
            f"/api/agent/jobs/{job_id}/cancel",
            json={},
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())},
        )
        self.assertEqual(200, canceled.status_code)
        second = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "fake",
                "SHOWCASE_DATA_DIR": str(self.root / "artifacts" / "workspace"),
                "SHOWCASE_WORKER_ENABLED": False,
            }
        )
        try:
            client = second.test_client()
            client.get("/api/check_auth")
            report = client.get(f"/api/experiments/campaigns/{campaign_id}").get_json()
            self.assertEqual("canceled", report["pairs"][0]["arms"]["baseline"]["status"])
            self.assertEqual("failed", report["pairs"][0]["arms"]["candidate"]["status"])
            self.assertEqual("needs_review", report["pairs"][0]["arms"]["candidate"]["error"])
            self.assertEqual(before["common_hash"], report["common_hash"])
        finally:
            second.extensions["showcase_workspace_service"].close()
            second.extensions["showcase_run_service"].close()
            second.extensions["loopback_store"].close()


if __name__ == "__main__":
    unittest.main()
