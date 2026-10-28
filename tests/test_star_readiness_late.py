"""Late usage reconciliation through the #97 coordinator's public Job path."""

import hashlib
import json
import tempfile
import time
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from showcase.run_budget import RunBudgetLedger
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_coordinator import StarReadinessCoordinator
from showcase.star_readiness_registration import digest
from tests.star_experiment_support import LoopbackProvider
from tests.test_star_readiness_coordinator import QUESTION_SPECS, SOURCE, frozen_manifest


class StarReadinessLateUsageTest(unittest.TestCase):
    """Verify a late loopback response updates S3 after #97 archives an unknown Job."""

    def test_late_usage_updates_original_attempt_after_terminal_archive_is_frozen(self):
        """Keep terminal files immutable while recording post-terminal usage separately."""
        provider = LoopbackProvider("late")
        self.addCleanup(provider.close)
        provider.respond = lambda _context: {"late": True}
        adapters = provider.adapters()
        adapters["nonstream"]._get_client().loopback_only = True

        class ShortPolicy(ExperimentRunPolicy):
            def prepare(self, limits):
                super().prepare(limits)
                self.run_deadline_at = time.time() + 2

        preflight_ids = iter(("probe-0", "probe-1", "probe-2"))
        runtime_paths = []
        make_temporary_directory = tempfile.TemporaryDirectory

        def capture_runtime_directory(*args, **kwargs):
            directory = make_temporary_directory(*args, **kwargs)
            if kwargs.get("prefix") == "star-readiness-97-":
                runtime_paths.append(Path(directory.name))
            return directory

        def scripted_preflight(_server):
            return {
                "available": True,
                "identity": {"run_id": next(preflight_ids)},
                "budget": {"tool_calls": 1, "http_attempts": 0},
            }

        with (
            patch("showcase.star_readiness_registration.QUESTION_SPECS", QUESTION_SPECS),
            patch("showcase.star_readiness_registration.V4_QUESTION_SPECS", QUESTION_SPECS),
            patch("showcase.star_readiness_coordinator.current_source_identity", return_value=SOURCE),
            patch("showcase.star_readiness_coordinator.ExperimentRunPolicy", ShortPolicy),
            patch("showcase.star_product_readiness.isolated_readiness", return_value={"available": True}),
            patch.object(ExperimentServer, "preflight", scripted_preflight),
        ):
            manifest = frozen_manifest()
            with tempfile.TemporaryDirectory() as temporary, ExitStack() as resources:
                root = Path(temporary) / "round"
                coordinator = StarReadinessCoordinator(
                    root,
                    adapters={"nonstream": adapters["nonstream"]},
                    manifest=manifest,
                    manifest_sha256=digest(manifest),
                )
                with patch(
                    "showcase.star_readiness_coordinator.tempfile.TemporaryDirectory",
                    side_effect=capture_runtime_directory,
                ):
                    result = coordinator.run()

                self.assertEqual("unknown_transport", result["stop_reason"], result)
                self.assertEqual(1, result["executed_runs"])
                self.assertEqual(1, len(provider.requests))
                self.assertEqual("retained", result["runtime_storage_cleanup"])
                runtime_path, = runtime_paths
                self.assertFalse(runtime_path.is_relative_to(root))
                self.assertTrue(runtime_path.exists(), "pending response must retain its ledger")
                terminal_at = time.time()

                hashes_before = json.loads((root / "hashes.json").read_text(encoding="utf-8"))
                archive_names = set(hashes_before) | {"hashes.json"}
                archive_before = {
                    name: (root / name).read_bytes() for name in archive_names
                }
                bundle = json.loads((root / "run-00.json").read_text(encoding="utf-8"))
                self.assertTrue(bundle["bundle_invariants"]["verification_match"])
                self.assertEqual(1, bundle["budget"]["unresolved_attempts"])
                self.assertIsNone(bundle["budget"]["provider_known"]["total_tokens"])
                attempts = bundle["request_attempts"]
                self.assertEqual(1, len(attempts))
                attempt_id = attempts[0]["attempt_id"]
                run_id = bundle["job"]["job_id"]

                ledger = RunBudgetLedger(
                    database_path=runtime_path / "nonstream/showcase.sqlite3"
                )
                resources.callback(ledger.close)
                self.assertEqual(1, ledger.snapshot(run_id)["unresolved_attempts"])

                provider.release.set()
                deadline = time.monotonic() + 5
                supplements = root / "supplemental-usage"
                while time.monotonic() < deadline:
                    files = list(supplements.glob("*.json")) if supplements.exists() else []
                    if files and ledger.snapshot(run_id)["unresolved_attempts"] == 0:
                        break
                    time.sleep(0.01)

                self.assertEqual(0, ledger.snapshot(run_id)["unresolved_attempts"])
                self.assertEqual(10, ledger.snapshot(run_id)["provider_known"]["total_tokens"])
                settled, = [item for item in ledger.attempts(run_id)
                            if item["attempt_id"] == attempt_id]
                self.assertEqual(10, settled["usage"]["total_tokens"])
                supplement_files = list(supplements.glob("*.json"))
                self.assertEqual(1, len(supplement_files))
                evidence = json.loads(supplement_files[0].read_text(encoding="utf-8"))
                self.assertEqual({"run_id", "attempt_id", "observed_at", "usage"}, set(evidence))
                self.assertEqual(run_id, evidence["run_id"])
                self.assertEqual(attempt_id, evidence["attempt_id"])
                self.assertEqual(10, evidence["usage"]["total_tokens"])
                self.assertGreaterEqual(evidence["observed_at"], terminal_at)
                ledger.close()

                for name, data in archive_before.items():
                    self.assertEqual(data, (root / name).read_bytes(), name)
                self.assertEqual(hashes_before, json.loads(
                    (root / "hashes.json").read_text(encoding="utf-8")
                ))
                for name, expected in hashes_before.items():
                    self.assertEqual(expected, hashlib.sha256((root / name).read_bytes()).hexdigest())
                self.assertNotIn("supplemental-usage", hashes_before)

    def test_collection_retains_terminal_job_when_cancel_loses_the_race(self):
        """A terminal worker commit between GET and cancel does not lose its bundle."""
        server = Mock()
        server.get.side_effect = [
            {"status": "running"}, {"status": "failed"}, {"status": "failed"},
            {"report": {}}, {}, {},
        ]
        server.post.side_effect = ValueError("experiment_public_admission_failed")

        bundle = ExperimentServer.collect(server, "job-1", time.time() - 1)

        self.assertEqual("failed", bundle["job"]["status"])
        server.post.assert_called_once_with("/api/agent/jobs/job-1/cancel", {})

    def test_collection_does_not_hide_cancel_failure_for_a_running_job(self):
        """Only a proven terminal state can explain a failed cancellation."""
        server = Mock()
        server.get.return_value = {"status": "running"}
        server.post.side_effect = ValueError("experiment_public_admission_failed")

        with self.assertRaises(ValueError):
            ExperimentServer.collect(server, "job-1", time.time() - 1)


if __name__ == "__main__":
    unittest.main()
