"""Known pre-dispatch refusals retain successful transport evidence."""

import tempfile
import unittest

from showcase.experiment_execution import run_batch
from showcase.experiment_manifest import manifest_digest
from showcase.experiment_transport_projection import project_transport_identity
from tests.test_showcase_experiment_execution import _context_for_run, _JobAdapter, _manifest


def transport_state():
    policy = {"policy": "stream_first", "profile_set_fingerprint": "a" * 64}
    return {
        "run_id": "job-1", "transport_policy": policy,
        "calls": {
            "private-refused-call": {
                "role": "researcher", "status": "policy_rejected",
                "transport_decision": {
                    **policy, "transport": "reject", "reason": "provider_profile_unverified",
                    "evidence_kind": "not_verified", "new_run_required": True,
                },
            },
            "private-successful-call": {
                "role": "planner", "status": "completed",
                "transport_decision": {
                    **policy, "transport": "stream", "profile_fingerprint": "b" * 64,
                    "evidence_kind": "provider_live",
                },
            },
        },
    }


class TransportRejectionProjectionTest(unittest.TestCase):
    def test_rejection_preserves_other_calls_and_public_aliases(self):
        result = project_transport_identity(transport_state(), "job-1")
        self.assertIsNotNone(result)
        self.assertEqual(["planner"], [call["role"] for call in result["calls"]])
        self.assertEqual("researcher", result["rejection"]["role"])
        self.assertEqual("provider_profile_unverified", result["rejection"]["reason"])
        self.assertTrue(result["rejection"]["new_run_required"])
        self.assertRegex(result["rejection"]["call_id"], r"^solver_call_[0-9a-f]{32}$")
        self.assertNotIn("private-", str(result))

    def test_successful_projection_keeps_existing_root_schema(self):
        state = transport_state()
        del state["calls"]["private-refused-call"]
        result = project_transport_identity(state, "job-1")
        self.assertEqual({"policy", "profile_set_fingerprint", "calls"}, set(result))

    def test_unknown_or_malformed_refusal_is_not_a_known_rejection(self):
        for status, reason, required in (
            ("unknown", "provider_profile_unverified", True),
            ("policy_rejected", "private prompt text", True),
            ("policy_rejected", "provider_profile_unverified", False),
        ):
            with self.subTest(status=status, reason=reason):
                state = transport_state()
                call = state["calls"]["private-refused-call"]
                call["status"] = status
                call["transport_decision"].update(reason=reason, new_run_required=required)
                self.assertIsNone(project_transport_identity(state, "job-1"))

    def test_runner_stops_known_refusal_without_another_submission(self):
        manifest = _manifest({
            "revision": "a" * 40, "source_sha256": "b" * 64,
            "dirty_status": "clean", "dirty_paths": [],
        })
        adapter = _JobAdapter([{
            "status": "failed", "transport_known": False, "transport": None,
            "transport_rejected": True,
        }])
        run_id = "known-refusal"
        with tempfile.TemporaryDirectory() as folder:
            result = run_batch(
                manifest, expected_sha256=manifest_digest(manifest), run_id=run_id,
                output_root=folder, context=_context_for_run(manifest, adapter, run_id),
            )
        self.assertEqual("transport_policy_rejected", result["stop_reason"])
        self.assertEqual(0, result["completed"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(0, adapter.resume_submissions)


if __name__ == "__main__":
    unittest.main()
