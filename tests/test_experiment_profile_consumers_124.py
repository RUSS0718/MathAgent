"""Actual profile choices and known refusals cross the public read boundaries."""

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from showcase.experiment_job_adapter import PublicExperimentJobAdapter
from showcase.experiment_manifest import canonical_json, manifest_digest
from showcase.experiment_transport import ExperimentTransportAdapter, profile_fingerprint
from showcase.experiment_verification import verify_experiment_run
from showcase.stream_preference import StreamProfile, profile_set_fingerprint
from tests.test_showcase_experiment_verify import ReadOnlyShowcaseClient, prepare_run


class LookupClient:
    def __init__(self, record):
        self.record = record
        self.methods = []

    def bootstrap(self):
        pass

    def request(self, method, _path, **_kwargs):
        self.methods.append(method)
        return self.record


class ExperimentProfileConsumersTest(unittest.TestCase):
    def _observation(self, *, listed=True, refusal=False):
        first = StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions", model="intern-s2",
            temperature=0.2, max_tokens=256, thinking_mode=False,
            messages_schema=(("system", ("content", "role")), ("user", ("content", "role"))),
            evidence_kind="controlled_test", status="controlled_test", schema_fingerprint="a" * 64,
        )
        second = replace(first, schema_fingerprint="b" * 64)
        fingerprints = [profile_fingerprint(first), profile_fingerprint(second)]
        expected = {
            "policy": "stream_first", "profile_set_fingerprint": profile_set_fingerprint((first, second)),
            "calls": [{"call_id": "researcher", "profile_fingerprints": fingerprints if listed else fingerprints[:1]}],
        }
        public_id = "solver_call_0123456789abcdef0123456789abcdef"
        observed = {
            "policy": expected["policy"], "profile_set_fingerprint": expected["profile_set_fingerprint"],
            "calls": [{"call_id": public_id, "role": "researcher", "policy": "stream_first",
                       "transport": "stream", "evidence_kind": "controlled_test",
                       "profile_fingerprint": fingerprints[1]}],
        }
        if refusal:
            observed["calls"] = []
            observed["rejection"] = {
                "call_id": public_id, "role": "researcher",
                "reason": "provider_profile_unverified", "new_run_required": True,
            }
        limits = {"max_model_calls": 2}
        deadline = 9999999999
        record = {"job_id": "job-1", "request_digest": "digest", "status": "failed" if refusal else "succeeded",
                  "transport_identity": observed, "budget": {"limits": limits, "deadline_at": deadline}}
        client = LookupClient(record)
        adapter = PublicExperimentJobAdapter(
            client, {"transport": expected, "run_limits": limits}, None, None,
            ExperimentTransportAdapter(profiles=(first, second)),
        )
        adapter.find_by_idempotency_key("key", "digest")
        return adapter.wait_for_job("job-1", deadline), client.methods

    def test_adapter_accepts_second_allowed_profile_and_rejects_unlisted_choice(self):
        self.assertTrue(self._observation()[0]["transport_known"])
        self.assertFalse(self._observation(listed=False)[0]["transport_known"])

    def test_adapter_identifies_known_refusal_using_only_gets(self):
        observation, methods = self._observation(refusal=True)
        self.assertTrue(observation.get("transport_rejected"))
        self.assertFalse(observation["transport_known"])
        self.assertEqual(["GET", "GET"], methods)

    def _verify(self, root, *, listed=True, refusal=False):
        output, directory, _digest, manifest, responses = prepare_run(root)
        manifest["transport"] = {
            "policy": "stream_first", "profile_set_fingerprint": "c" * 64,
            "calls": [{"call_id": "whole_solution_verifier",
                       "profile_fingerprints": ["d" * 64, "e" * 64] if listed else ["d" * 64]}],
        }
        lookup = responses["/api/agent/jobs/by-idempotency"]
        observed = lookup["transport_identity"]
        observed["policy"] = "stream_first"
        call = observed["calls"][0]
        call.pop("reason")
        call.pop("capability_limit")
        call.update(transport="stream", evidence_kind="controlled_test", profile_fingerprint="e" * 64)
        if refusal:
            observed["rejection"] = {
                "call_id": "solver_call_0123456789abcdef0123456789abcdef", "role": "whole_solution_verifier",
                "reason": "provider_profile_unverified", "new_run_required": True,
            }
        (directory / "manifest.json").write_bytes(canonical_json(manifest))
        digest = manifest_digest(manifest)
        (directory / "manifest.sha256").write_text(digest, encoding="ascii")
        status_path = directory / "status.json"
        status = json.loads(status_path.read_text())
        status["manifest_sha256"] = digest
        status_path.write_text(json.dumps(status), encoding="utf-8")
        return verify_experiment_run("batch-1", output_root=output, read_client=ReadOnlyShowcaseClient(responses))

    def test_independent_verifier_checks_chosen_profile_and_known_refusal(self):
        for listed, refusal, expected in ((True, False, "PASS"), (False, False, "FAIL"), (True, True, "FAIL")):
            with self.subTest(listed=listed, refusal=refusal), tempfile.TemporaryDirectory() as folder:
                report = self._verify(Path(folder), listed=listed, refusal=refusal)
                self.assertEqual(expected, report["checks"]["transport"]["status"])
                if refusal:
                    self.assertEqual("transport_policy_rejected", report["checks"]["transport"]["reason"])


if __name__ == "__main__":
    unittest.main()
