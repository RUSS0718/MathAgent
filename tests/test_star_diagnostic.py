import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from showcase.star_diagnostic import DiagnosticJob, socket_free
from showcase.star_diagnostic_registration import freeze
from tests.star_diagnostic_support import plan


class DiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(tempfile.TemporaryDirectory())
        self.root = Path(self.directory)
        self.registration = self.root / "registration"
        self.manifest = freeze(plan(), self.registration)
        self.job = DiagnosticJob(self.registration, self.root / "archive", self.root / "registry.db")

    def test_socket_free_order_and_duplicate_across_directories(self):
        with patch("socket.socket", side_effect=AssertionError("socket forbidden")):
            result = self.job.run()
        self.assertEqual("completed", result["status"])
        self.assertEqual([r["run_id"] for r in self.manifest["requests"]],
                         [r["run_id"] for r in result["results"]])
        self.assertEqual(2, result["dispatched"])
        self.assertEqual(20, result["charged_tokens"])
        for row in result["results"]:
            self.assertEqual((1, 1, 0), tuple(row["budget"][k] for k in ("logical_calls", "http_attempts", "tool_calls")))
        other = DiagnosticJob(self.registration, self.root / "other", self.root / "registry.db")
        with self.assertRaisesRegex(ValueError, "consumed"):
            other.run()

    def test_unknown_stops_batch_and_late_original_usage_is_idempotent(self):
        result = self.job.run(outcomes=["unknown", "success"])
        self.assertEqual("unknown", result["status"])
        self.assertEqual(1, result["dispatched"])
        original = result["results"][0]
        self.assertGreater(result["reserved_tokens"], 16384)
        self.assertIsNone(result["provider_known"]["total_tokens"])
        args = (original["run_id"], original["attempt_id"])
        self.assertTrue(self.job.reconcile(*args, prompt_tokens=7, completion_tokens=3, total_tokens=10))
        self.assertFalse(self.job.reconcile(*args, prompt_tokens=7, completion_tokens=3, total_tokens=10))
        after = self.job.snapshot()
        self.assertEqual("unknown", after["status"])
        self.assertEqual(10, after["charged_tokens"])
        self.assertEqual(original["deadline_at"], after["results"][0]["deadline_at"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.job.run()

    def test_intent_crash_reserves_full_envelope_and_restart_never_resends(self):
        result = self.job.run(outcomes=["intent_crash", "success"])
        self.assertEqual("interrupted", result["status"])
        self.assertEqual(65536, result["unconfirmed_reserved_tokens"])
        self.assertIsNone(result["charged_tokens"])
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.job.run()

    def test_p_control_continuation_reuses_prior_results_and_total_ledger(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = freeze(plan("P", 36), root / "registration")
            job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
            first = job.run(limit=3)
            self.assertEqual("control_complete", first["status"])
            self.assertEqual(3, first["dispatched"])
            after = job.continue_remaining()
            self.assertEqual("completed", after["status"])
            self.assertEqual(36, after["dispatched"])
            self.assertEqual(360, after["charged_tokens"])
            self.assertEqual(0, after["remaining_requests"])
            self.assertEqual(first["results"], after["results"][:3])
            self.assertEqual(manifest["sha256"], after["manifest_sha256"])

    def test_all_socket_entry_points_are_blocked_including_loopback(self):
        import socket
        with socket_free():
            for call in (lambda: socket.socket(), lambda: socket.create_connection(("127.0.0.1", 80)),
                         lambda: socket.getaddrinfo("localhost", 80), lambda: socket.socketpair()):
                with self.assertRaisesRegex(RuntimeError, "socket_forbidden"):
                    call()

    def test_cancel_stops_before_next_dispatch_and_restart_is_rejected(self):
        result = self.job.run(cancel_after=1)
        self.assertEqual("cancelled", result["status"])
        self.assertEqual(1, result["dispatched"])
        self.assertEqual(10, result["charged_tokens"])
        with self.assertRaises(ValueError):
            self.job.continue_remaining()

    def test_crash_after_reservation_preserves_original_and_blocks_new_registration(self):
        result = self.job.run(outcomes=["crash", "success"])
        self.assertEqual("interrupted", result["status"])
        self.assertGreater(result["reserved_tokens"], 16384)
        next_plan = plan()
        next_plan["registration_id"] = "new-name"
        freeze(next_plan, self.root / "new-registration")
        other = DiagnosticJob(self.root / "new-registration", self.root / "new-archive", self.root / "registry.db")
        with self.assertRaisesRegex(ValueError, "unresolved"):
            other.run()
        self.assertFalse((self.root / "new-archive").exists())

    def test_disconnect_and_missing_usage_pause_with_unknown_cost(self):
        for outcome in ("disconnect", "missing_usage"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                freeze(plan(), root / "registration")
                job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
                result = job.run(outcomes=[outcome, "success"])
                self.assertEqual("unknown", result["status"])
                self.assertEqual(1, result["dispatched"])
                self.assertIsNone(result["cost"])
                self.assertEqual("unknown", result["remote_concurrency"])

    def test_archive_failure_keeps_known_usage_without_next_dispatch(self):
        result = self.job.run(outcomes=["archive_failure", "success"])
        self.assertEqual("archive_failed", result["status"])
        self.assertEqual(1, result["dispatched"])
        self.assertEqual(10, result["charged_tokens"])

    def test_concurrent_launch_across_archives_has_exactly_one_owner(self):
        other = DiagnosticJob(self.registration, self.root / "other", self.root / "registry.db")
        def run(job):
            try:
                return job.run()["status"]
            except ValueError:
                return "rejected"
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(run, (self.job, other)))
        self.assertCountEqual(["completed", "rejected"], results)

    def test_concurrent_late_reconciliation_changes_original_once(self):
        result = self.job.run(outcomes=["unknown", "success"])
        original = result["results"][0]
        def reconcile(_):
            return self.job.reconcile(original["run_id"], original["attempt_id"],
                                      prompt_tokens=7, completion_tokens=3, total_tokens=10)
        with ThreadPoolExecutor(2) as pool:
            changed = list(pool.map(reconcile, range(2)))
        self.assertCountEqual([True, False], changed)
        self.assertEqual("unknown", self.job.snapshot()["status"])
        self.assertEqual(1, self.job.snapshot()["dispatched"])

    def test_public_cancel_is_preserved_across_p_control_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            freeze(plan("P", 4), root / "registration")
            job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
            job.run(limit=3)
            job.cancel()
            result = job.continue_remaining()
            self.assertEqual("cancelled", result["status"])
            self.assertEqual(3, result["dispatched"])

    def test_p_continuation_rejects_corrupted_control_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = freeze(plan("P", 4), root / "registration")
            job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
            job.run(limit=3)
            visible = job.archive / "private" / manifest["requests"][0]["workspace_id"] / "visible.json"
            visible.write_text('{"visible_response":"changed"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "control_result"):
                job.continue_remaining()
            self.assertEqual(3, job.snapshot()["dispatched"])

    def test_monitor_shows_running_during_p_continuation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = freeze(plan("P", 4), root / "registration")
            job = DiagnosticJob(root / "registration", root / "archive", root / "registry.db")
            job.run(limit=3)
            waiting, release = threading.Event(), threading.Event()
            mkdir = Path.mkdir
            def slow_filesystem(path, *args, **kwargs):
                if path.name == manifest["requests"][3]["workspace_id"]:
                    waiting.set()
                    if not release.wait(5):
                        raise TimeoutError("fake filesystem stalled")
                return mkdir(path, *args, **kwargs)
            with patch.object(Path, "mkdir", slow_filesystem), ThreadPoolExecutor(1) as pool:
                result = pool.submit(job.continue_remaining)
                try:
                    self.assertTrue(waiting.wait(5))
                    self.assertEqual("running", job.snapshot()["status"])
                finally:
                    release.set()
                self.assertEqual("completed", result.result()["status"])
