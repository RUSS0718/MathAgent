"""An explicit live batch can defer usage acceptance without replaying unknown work."""

import tempfile
import unittest

from showcase.experiment_execution import run_batch
from showcase.experiment_manifest import manifest_digest, validate_manifest
from tests.test_showcase_experiment_execution import _context_for_run, _JobAdapter, _manifest


class ExperimentUsageObservationPolicyTest(unittest.TestCase):
    def _run(self, *, policy=None, unresolved=0, unknown_tools=0):
        manifest = _manifest({
            "revision": "a" * 40, "source_sha256": "b" * 64,
            "dirty_status": "clean", "dirty_paths": [],
        })
        manifest["evidence_kind"] = "provider_live"
        manifest["authorization"]["execution_authorized"] = True
        if policy is not None:
            manifest["usage_policy"] = policy
        adapter = _JobAdapter([{"budget": {
            "logical_calls": 1, "http_attempts": 1, "tool_calls": 0,
            "charged_tokens": 2048, "wall_time_seconds": 1.0,
            "unknown_attempts": 1, "unresolved_attempts": unresolved,
            "unknown_tool_calls": unknown_tools,
        }}])
        run_id = "usage-policy-run"
        with tempfile.TemporaryDirectory() as folder:
            result = run_batch(
                manifest, expected_sha256=manifest_digest(manifest), run_id=run_id,
                output_root=folder, context=_context_for_run(manifest, adapter, run_id),
            )
        return result, adapter.submissions

    def test_observe_only_completes_known_success_with_full_reservation(self):
        result, submissions = self._run(policy="observe_only")
        self.assertEqual("completed", result["phase"])
        self.assertEqual(1, result["completed"])
        self.assertEqual(2048, result["usage"]["charged_tokens"])
        self.assertEqual(1, submissions)

    def test_default_and_explicit_required_keep_missing_usage_stop(self):
        for policy in (None, "required"):
            with self.subTest(policy=policy):
                result, submissions = self._run(policy=policy)
                self.assertEqual("incomplete_or_unresolved_usage", result["stop_reason"])
                self.assertEqual(0, result["completed"])
                self.assertEqual(1, submissions)

    def test_observe_only_still_stops_unresolved_requests_or_tools(self):
        for unresolved, unknown_tools in ((1, 0), (0, 1)):
            with self.subTest(unresolved=unresolved, unknown_tools=unknown_tools):
                result, submissions = self._run(
                    policy="observe_only", unresolved=unresolved, unknown_tools=unknown_tools,
                )
                self.assertEqual("incomplete_or_unresolved_usage", result["stop_reason"])
                self.assertEqual(0, result["completed"])
                self.assertEqual(1, submissions)

    def test_unknown_policy_is_rejected(self):
        manifest = _manifest({
            "revision": "a" * 40, "source_sha256": "b" * 64,
            "dirty_status": "clean", "dirty_paths": [],
        })
        manifest["usage_policy"] = "ignore_every_failure"
        with self.assertRaisesRegex(ValueError, "experiment_manifest_invalid"):
            validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
