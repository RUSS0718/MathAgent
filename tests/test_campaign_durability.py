"""Cross-instance public queries and interrupted local archive publication."""

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from showcase.flask_app import create_app
from tests.test_campaigns import CampaignFixture


class CampaignDurabilityTest(CampaignFixture):
    def test_stale_query_in_second_instance_cannot_remove_new_child_links(self):
        self.app.extensions["showcase_workspace_service"].worker_enabled = False
        reader = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "fake",
                "SHOWCASE_DATA_DIR": str(self.root / "artifacts" / "workspace"),
                "SHOWCASE_WORKER_ENABLED": False,
            }
        )
        client = reader.test_client()
        client.get("/api/check_auth")
        creator_workspace = self.app.extensions["showcase_workspace_service"]
        reader_workspace = reader.extensions["showcase_workspace_service"]
        original_create = creator_workspace.create_job
        original_read = reader_workspace.get_job
        first_link_saved, allow_creation = threading.Event(), threading.Event()
        old_query_loaded, allow_query = threading.Event(), threading.Event()
        created_count = 0

        def pause_second_job(**kwargs):
            nonlocal created_count
            created_count += 1
            if created_count == 2:
                first_link_saved.set()
                if not allow_creation.wait(5):
                    raise TimeoutError("test creation barrier")
            return original_create(**kwargs)

        def pause_old_query(job_id, user_id):
            job = original_read(job_id, user_id)
            old_query_loaded.set()
            if not allow_query.wait(5):
                raise TimeoutError("test query barrier")
            return job

        try:
            with (
                ThreadPoolExecutor(max_workers=2) as executor,
                patch.object(creator_workspace, "create_job", side_effect=pause_second_job),
            ):
                creation = executor.submit(self.submit)
                self.assertTrue(first_link_saved.wait(5))
                listing = client.get("/api/experiments/campaigns").get_json()
                campaign_id = listing["campaigns"][0]["campaign_id"]
                with patch.object(reader_workspace, "get_job", side_effect=pause_old_query):
                    query = executor.submit(client.get, f"/api/experiments/campaigns/{campaign_id}")
                    self.assertTrue(old_query_loaded.wait(5))
                    allow_creation.set()
                    accepted = creation.result(5)
                    self.assertEqual(202, accepted.status_code)
                    expected = accepted.get_json()["pairs"][0]["arms"]
                    allow_query.set()
                    self.assertEqual(200, query.result(5).status_code)
                restored = client.get(f"/api/experiments/campaigns/{campaign_id}").get_json()
                for name, arm in restored["pairs"][0]["arms"].items():
                    self.assertEqual(expected[name]["job_id"], arm["job_id"])
                    self.assertIsNotNone(arm["job_id"])
        finally:
            allow_creation.set()
            allow_query.set()
            reader.extensions["showcase_workspace_service"].close()
            reader.extensions["showcase_run_service"].close()
            reader.extensions["loopback_store"].close()

    def test_query_repairs_corrupt_content_addressed_report_and_evidence(self):
        report = self.finished(self.submit().get_json()["campaign_id"])
        archive_root = self.root / "artifacts" / "workspace" / "campaigns"
        artifacts = [report["archive"]]
        for arm in report["pairs"][0]["arms"].values():
            artifacts.extend(arm["artifacts"])
        for artifact in artifacts:
            (archive_root / artifact["path"]).write_bytes(b'{"partial":')
        restored = self.detail(report["campaign_id"])
        self.assertEqual(report["archive"], restored["archive"])
        for artifact in artifacts:
            self.assertEqual(
                artifact["sha256"],
                hashlib.sha256((archive_root / artifact["path"]).read_bytes()).hexdigest(),
            )

    def test_failed_publication_leaves_no_partial_final_report_and_retry_recovers(self):
        report = self.finished(self.submit().get_json()["campaign_id"])
        archive_root = self.root / "artifacts" / "workspace" / "campaigns"
        target = archive_root / report["archive"]["path"]
        target.unlink()
        with patch("os.replace", side_effect=OSError("test interrupted publication")):
            with self.assertRaises(OSError):
                self.detail(report["campaign_id"])
        self.assertFalse(target.exists())
        restored = self.detail(report["campaign_id"])
        self.assertEqual(report["archive"], restored["archive"])
        self.assertEqual(
            report["archive"]["sha256"], hashlib.sha256(target.read_bytes()).hexdigest()
        )
