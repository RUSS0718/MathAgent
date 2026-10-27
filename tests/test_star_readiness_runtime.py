"""Runtime cleanup must keep late-settlement work alive until it is safe."""

import gc
import json
import sqlite3
import tempfile
import time
import unittest
import uuid
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from showcase.run_budget import RunBudgetLedger
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_runtime import cleanup_runtime_storage
from tests.star_experiment_support import LoopbackProvider


class StarReadinessRuntimeCleanupTest(unittest.TestCase):
    def test_deferred_cleanup_thread_keeps_process_alive_for_late_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = tempfile.TemporaryDirectory(dir=directory)
            self.addCleanup(storage.cleanup)
            with (
                patch("showcase.star_readiness_runtime._has_unresolved_attempts", return_value=True),
                patch("showcase.star_readiness_runtime.threading.Thread") as thread,
            ):
                self.assertEqual(
                    "deferred",
                    cleanup_runtime_storage(storage, ["run-1"], grace_seconds=2),
                )

            self.assertFalse(thread.call_args.kwargs["daemon"])

    def test_unidentified_dispatch_survives_directory_finalizer_and_leaves_retention_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = tempfile.TemporaryDirectory(dir=directory)
            path = Path(storage.name)
            self.assertEqual("retained", cleanup_runtime_storage(
                storage, [], grace_seconds=1, preserve=True,
            ))
            del storage
            gc.collect()
            self.assertTrue(path.is_dir())
            self.assertEqual(
                {"reason": "dispatch_identity_unresolved", "run_ids": []},
                json.loads((path / "retention.json").read_text(encoding="utf-8")),
            )

    def test_known_job_retention_reason_does_not_claim_dispatch_identity_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = tempfile.TemporaryDirectory(dir=directory)
            path = Path(storage.name)
            self.assertEqual("retained", cleanup_runtime_storage(
                storage, ["job-1"], grace_seconds=1, preserve=True,
            ))
            self.assertEqual(
                {"reason": "job_archive_incomplete", "run_ids": ["job-1"]},
                json.loads((path / "retention.json").read_text(encoding="utf-8")),
            )

    def test_lost_response_recovers_accepted_job_without_post_and_retains_original_ledger(self):
        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        for status in ("queued", "running", "failed"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                storage = tempfile.TemporaryDirectory(dir=directory)
                self.addCleanup(storage.cleanup)
                runtime = Path(storage.name)
                policy = ExperimentRunPolicy(time.time() + 900)
                policy.prepare({"max_model_calls": 6, "max_http_attempts": 8,
                                "max_tool_calls": 1, "max_tokens": 32768,
                                "max_runtime_seconds": 300})
                deadline = policy.deadline_at
                # This test covers public durable admission, not Docker readiness or solving.
                with patch("showcase.star_product_pipeline.StarProductPipeline.full_gaps",
                           return_value=[]):
                    server = ExperimentServer(runtime / "nonstream", "nonstream",
                                              provider.adapters()["nonstream"], policy, "scripted")
                    service = server.app.extensions["showcase_workspace_service"]
                    ledger = service.budget_ledger
                    ledger.late_usage_evidence_dir = Path(directory) / "late-usage"
                    post = server.client.post
                    accepted = []
                    requests = []

                    def hold_job(job_id):
                        if status != "queued":
                            service.store.start_job(job_id, execution_mode="star_reference")
                            ledger.ensure(job_id, policy.budget(), deadline_at=deadline)
                            ledger.reserve(job_id, "http", attempt_id="original-attempt",
                                           input_estimate=32, output_cap=8192)
                            if status == "failed":
                                service.store.fail_job(job_id, "fixture_transport_unknown",
                                                       execution_mode="star_reference")

                    def lose_response(path, **kwargs):
                        requests.append(path)
                        response = post(path, **kwargs)
                        if path == "/api/agent/jobs":
                            self.assertEqual(202, response.status_code, response.get_json())
                            accepted.append(response.get_json()["job_id"])
                            raise TimeoutError("fixture_response_lost_after_commit")
                        return response

                    key = str(uuid.uuid4())
                    try:
                        with (patch.object(service, "_submit", side_effect=hold_job),
                              patch.object(server.client, "post", side_effect=lose_response),
                              patch("llm_client.requests.post",
                                    side_effect=AssertionError("No provider call allowed"))):
                            with self.assertRaises(TimeoutError):
                                server.dispatch({"prompt": "Compute 2 + 2."}, idempotency_key=key)
                            job_id = server.resolve_dispatch(key)
                            self.assertEqual(accepted, [job_id])
                            self.assertEqual(status, server.get(f"/api/agent/jobs/{job_id}")["status"])
                            self.assertIsNone(server.resolve_dispatch(str(uuid.uuid4())))
                        self.assertEqual(1, requests.count("/api/agent/jobs"))
                    finally:
                        server.close()

                with (patch("showcase.star_readiness_runtime.time.monotonic", return_value=100),
                      patch("showcase.star_readiness_runtime.threading.Thread") as thread):
                    self.assertEqual("deferred", cleanup_runtime_storage(
                        storage, [job_id], grace_seconds=1,
                    ))
                # Expiring grace while the Job is queued/running must retain the database.
                with patch("showcase.star_readiness_runtime.time.monotonic", return_value=102):
                    thread.call_args.kwargs["target"]()
                database = runtime / "nonstream" / "showcase.sqlite3"
                self.assertTrue(database.is_file())
                self.assertEqual("settlement_grace_expired", json.loads(
                    (runtime / "retention.json").read_text(encoding="utf-8"))["reason"])
                with closing(sqlite3.connect(database)) as connection:
                    self.assertEqual((job_id, status), connection.execute(
                        "SELECT job_id,status FROM workspace_jobs WHERE idempotency_key=?", (key,)
                    ).fetchone())
                if status != "queued":
                    ledger.settle(job_id, "original-attempt", {
                        "status": "success", "prompt_tokens": 7,
                        "completion_tokens": 10, "total_tokens": 17,
                    })
                    reopened = RunBudgetLedger(database_path=database)
                    try:
                        budget = reopened.snapshot(job_id)
                        self.assertEqual(17, budget["charged_tokens"])
                        self.assertEqual(0, budget["reserved_tokens"])
                        self.assertEqual(1, budget["http_attempts"])
                        self.assertEqual(deadline, budget["deadline_at"])
                    finally:
                        reopened.close()
                    self.assertEqual(1, len(list(ledger.late_usage_evidence_dir.glob("*.json"))))
                    if status == "failed":
                        self.assertEqual("complete", cleanup_runtime_storage(
                            storage, [job_id], grace_seconds=1,
                        ))
                        self.assertFalse(database.exists(), "Only settled terminal Jobs can be released")
        self.assertEqual([], provider.requests)


if __name__ == "__main__":
    unittest.main()
