"""#124 manifest and frozen profile allow-list seams."""

import unittest

from tests.test_showcase_experiment_cli import _manifest


class ExperimentProfileAllowlistTest(unittest.TestCase):
    def setUp(self):
        self.source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }

    def test_manifest_accepts_singular_or_nonempty_unique_profile_list_only(self):
        from showcase.experiment_manifest import validate_manifest

        singular = _manifest(self.source)
        plural = _manifest(self.source)
        plural["transport"]["calls"] = [
            {"call_id": "explore", "profile_fingerprints": ["d" * 64, "e" * 64]}
        ]
        self.assertEqual(singular, validate_manifest(singular))
        self.assertEqual(plural, validate_manifest(plural))

        for call in (
            {"call_id": "explore"},
            {
                "call_id": "explore",
                "profile_fingerprint": "d" * 64,
                "profile_fingerprints": ["e" * 64],
            },
            {"call_id": "explore", "profile_fingerprints": []},
            {"call_id": "explore", "profile_fingerprints": ["d" * 64, "d" * 64]},
            {"call_id": "explore", "profile_fingerprints": ["bad"]},
        ):
            with self.subTest(call=call):
                invalid = _manifest(self.source)
                invalid["transport"]["calls"] = [call]
                with self.assertRaisesRegex(ValueError, "experiment_manifest_invalid"):
                    validate_manifest(invalid)

    def test_transport_adapter_accepts_trusted_profile_lists_and_rejects_unknown_members(self):
        from showcase.experiment_transport import ExperimentTransportAdapter, profile_fingerprint
        from showcase.stream_preference import StreamProfile, profile_set_fingerprint

        first = StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(("user", ("content", "role")),),
            evidence_kind="controlled_test",
            status="controlled_test",
        )
        second = StreamProfile(
            endpoint=first.endpoint,
            model=first.model,
            temperature=first.temperature,
            max_tokens=first.max_tokens,
            thinking_mode=first.thinking_mode,
            messages_schema=(("system", ("content", "role")), ("user", ("content", "role"))),
            evidence_kind="controlled_test",
            status="controlled_test",
        )
        adapter = ExperimentTransportAdapter(profiles=(first, second))
        transport = {
            "policy": "stream_first",
            "profile_set_fingerprint": profile_set_fingerprint((first, second)),
            "calls": [{
                "call_id": "explore",
                "profile_fingerprints": [profile_fingerprint(first), profile_fingerprint(second)],
            }],
        }
        adapter.validate_manifest_transport(transport)

        unknown = {
            **transport,
            "calls": [{"call_id": "explore", "profile_fingerprints": ["f" * 64]}],
        }
        with self.assertRaisesRegex(ValueError, "experiment_transport_profile_invalid"):
            adapter.validate_manifest_transport(unknown)


if __name__ == "__main__":
    unittest.main()
