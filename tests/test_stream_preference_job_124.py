"""Public Job evidence for issue #124 transport selection; offline only."""

import hashlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.stream_preference import StreamProfile
from tests.star_product_support import StarJobFixture, SOLVED, POLISH, ACCEPT
from tests.test_star_product_streaming_recovery import ScriptedSSETransport, split_fragments


def _schema_fingerprint(role):
    from showcase.solver_harness.intern_schemas import response_schema

    schema = response_schema({"role": role})
    return hashlib.sha256(json.dumps(
        schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


class PublicStreamPreferenceJobTest(StarJobFixture, unittest.TestCase):
    def open_stream_first(self, *, profiles=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_dir = folder.name
        self.enterContext(patch.dict(os.environ, {
            "INTERN_API_KEY": "scripted-only",
            "INTERN_API_BASE": "http://127.0.0.1:5000/api/v1/chat/completions",
        }))
        self.transport = ScriptedSSETransport(self, [
            [*split_fragments(SOLVED), {"type": "result"}],
            [*split_fragments(POLISH), {"type": "result"}],
            [*split_fragments(ACCEPT), {"type": "result"}],
        ])
        self.wire_payloads = []

        def capture_payload(url, **kwargs):
            self.wire_payloads.append(json.loads(kwargs["data"]))
            return self.transport(url, **kwargs)

        self.enterContext(patch(
            "showcase.request_transport.strict_loopback_post", side_effect=capture_payload
        ))
        shape = (("system", ("content", "role")), ("user", ("content", "role")))
        default_profiles = tuple(StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2", temperature=0.2, max_tokens=256,
            thinking_mode=True, messages_schema=shape,
            evidence_kind="controlled_test", status="controlled_test",
            schema_fingerprint=_schema_fingerprint(role),
        ) for role in ("explore", "explore_polish", "whole_solution_verifier"))
        self.app = create_app({
            "TESTING": True, "SHOWCASE_DATA_DIR": folder.name,
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternStreamAdapter(
                InternChatClient(retry=1, thinking_mode=True, loopback_only=True),
                max_tokens=256,
            ),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_TRANSPORT_POLICY": "stream_first",
            "SHOWCASE_STAR_TRANSPORT_PROFILES": default_profiles if profiles is None else profiles,
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=4, max_http_attempts=4),
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post(
            "/api/new_chat", headers=self.headers()
        ).get_json()["new_session_id"]

    def test_stream_first_public_job_records_wire_sse_and_policy_evidence(self):
        self.open_stream_first()
        job_id = self.create_job()
        final = self.terminal(job_id)

        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(3, len(self.transport.outbound))
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        dumps = json.dumps(evidence, ensure_ascii=False)
        self.assertTrue(all(payload["stream"] is True for payload in self.wire_payloads))
        self.assertTrue(all(payload["thinking_mode"] is True for payload in self.wire_payloads))
        self.assertIn("stream_metrics", stream)
        self.assertIn("usage", dumps)
        self.assertEqual(3, final["result"]["budget"]["logical_calls"])
        selected = [event for event in evidence["timeline"]
                    if event.get("solver_event_type") == "transport_selected"]
        self.assertEqual(3, len(selected), evidence["timeline"])
        self.assertTrue(all(event["transport"] == "stream" for event in selected))
        self.assertTrue(all(event["transport_evidence_kind"] == "controlled_test"
                            for event in selected))
        profile_fingerprints = {event["transport_profile_fingerprint"] for event in selected}
        self.assertEqual(3, len(profile_fingerprints))
        profile_set_fingerprints = {
            event["transport_profile_set_fingerprint"] for event in selected
        }
        self.assertEqual(1, len(profile_set_fingerprints))
        self.assertEqual(3, len([item for item in final["result"]["request_attempts"]
                                 if item.get("provider_stream") is True]))

    def test_unknown_profile_is_a_persisted_pre_dispatch_job_rejection(self):
        self.open_stream_first(profiles=())
        job_id = self.create_job()
        final = self.terminal(job_id)

        self.assertEqual("failed", final["status"], final)
        self.assertEqual([], self.wire_payloads)
        self.assertEqual([], self.transport.outbound)
        self.assertEqual([], final["result"]["request_attempts"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        rejected = [event for event in evidence["timeline"]
                    if event.get("solver_event_type") == "transport_rejected"]
        self.assertTrue(rejected, evidence["timeline"])
        self.assertEqual("unknown_endpoint", rejected[0]["transport_reason"])
        self.assertTrue(rejected[0]["new_run_required"])
        self.assertEqual("stream_first", rejected[0]["transport_policy"])


if __name__ == "__main__":
    unittest.main()
