"""Population identity binds the effective transport configuration."""

import unittest
from dataclasses import replace

from showcase.star_product_modes import mode_identity
from showcase.star_product_pipeline import StarProductPipeline
from showcase.stream_preference import VERIFIED_STREAM_PROFILES, profile_set_fingerprint
from showcase.workspace import workspace_job_request_digest

CAPACITY = {
    "service_id": "test-provider",
    "max_inflight": 2,
    "worker_slots": 2,
    "evidence_ref": "controlled-test-fixture",
    "status": "controlled",
}


class PopulationTransportIdentityTest(unittest.TestCase):
    def _identity_and_digest(self, transport_policy, stream_profiles):
        pipeline = StarProductPipeline(
            ":memory:", evidence_kind="fault_injection", population_capacity=CAPACITY,
            transport_policy=transport_policy, stream_profiles=stream_profiles,
        )
        identity = mode_identity("star_population", pipeline.preset_config("star_population"))
        digest = workspace_job_request_digest(
            session_id="session-1", message="problem", solver_mode="star_population",
            population_policy_hash=identity["population_policy_hash"],
        )
        return pipeline, identity, digest

    def test_transport_policy_and_profile_set_change_identity_and_request_digest(self):
        profile = VERIFIED_STREAM_PROFILES[0]
        changed_profile = replace(profile, max_tokens=profile.max_tokens - 1)
        _, legacy, legacy_digest = self._identity_and_digest("legacy", (profile,))
        _, stream, stream_digest = self._identity_and_digest("stream_first", (profile,))
        _, changed_profiles, changed_profiles_digest = self._identity_and_digest(
            "stream_first", (changed_profile,)
        )

        self.assertNotEqual(legacy["population_policy_hash"], stream["population_policy_hash"])
        self.assertNotEqual(stream["population_policy_hash"], changed_profiles["population_policy_hash"])
        self.assertNotEqual(legacy_digest, stream_digest)
        self.assertNotEqual(stream_digest, changed_profiles_digest)

    def test_population_transport_identity_is_frozen_for_the_run(self):
        profile = VERIFIED_STREAM_PROFILES[0]
        changed_profile = replace(profile, max_tokens=profile.max_tokens - 1)
        pipeline, identity, digest = self._identity_and_digest("stream_first", (profile,))

        transport_identity = pipeline.preset_config("star_population")["transport_identity"]
        self.assertEqual("stream_first", transport_identity["transport_policy"])
        self.assertEqual(profile_set_fingerprint((profile,)), transport_identity["stream_profiles_fingerprint"])

        pipeline.transport_policy = "legacy"
        pipeline.stream_profiles = (changed_profile,)

        resumed_identity = mode_identity("star_population", pipeline.preset_config("star_population"))
        resumed_digest = workspace_job_request_digest(
            session_id="session-1", message="problem", solver_mode="star_population",
            population_policy_hash=resumed_identity["population_policy_hash"],
        )
        self.assertEqual(identity["population_policy_hash"], resumed_identity["population_policy_hash"])
        self.assertEqual(digest, resumed_digest)


if __name__ == "__main__":
    unittest.main()
