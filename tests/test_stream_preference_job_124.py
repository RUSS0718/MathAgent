"""Public Job evidence for issue #124 transport selection; offline only."""

import hashlib
import json
import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.stream_preference import StreamProfile
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_star_product_streaming_recovery import ScriptedSSETransport, split_fragments


def _schema_fingerprint(role):
    from showcase.solver_harness.intern_schemas import response_schema

    schema = response_schema({"role": role})
    return hashlib.sha256(json.dumps(
        schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


class PublicStreamPreferenceJobTest(StarJobFixture, unittest.TestCase):
    def open_legacy_loopback(self, replies):
        from showcase.adapters import InternModelAdapter

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_dir = folder.name
        self.enterContext(patch.dict(os.environ, {
            "INTERN_API_KEY": "scripted-only",
            "INTERN_API_BASE": "http://127.0.0.1:5000/api/v1/chat/completions",
        }))
        self.replies = list(replies)
        self.outbound = []

        def respond(_url, **kwargs):
            self.outbound.append(json.loads(kwargs["data"]))
            value = self.replies.pop(0)
            if isinstance(value, BaseException):
                raise value
            content = json.dumps(value)
            body = json.dumps({
                "choices": [{"finish_reason": "stop", "message": {"content": content}}],
                "model": "intern-s2",
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }).encode()

            class Reply:
                status_code = 200

                def raise_for_status(self):
                    pass

                def close(self):
                    pass

                def iter_content(self, chunk_size=1):
                    yield body

            return Reply()

        self.enterContext(patch(
            "showcase.request_transport.strict_loopback_post", side_effect=respond
        ))
        self.app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": folder.name,
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                InternChatClient(retry=1, loopback_only=True), max_tokens=256,
                thinking_mode=True,
            ),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_TRANSPORT_POLICY": "legacy",
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
                max_model_calls=6, max_http_attempts=12,
            ),
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post(
            "/api/new_chat", headers=self.headers()
        ).get_json()["new_session_id"]

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
            "SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED": True,
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

    def test_legacy_public_job_persists_each_nonstream_choice_for_later_projection(self):
        from requests import Timeout

        from showcase.run_budget import RunBudgetLimits
        from showcase.workspace import workspace_job_request_digest

        self.open_legacy_loopback([Timeout("scripted disconnect"), SOLVED, POLISH, ACCEPT])
        limits = RunBudgetLimits(
            max_model_calls=6,
            max_http_attempts=12,
            max_tool_calls=2,
            max_tokens=262144,
            max_runtime_seconds=60,
        )
        deadline_at = time.time() + 30
        key = str(uuid.uuid4())
        message = "1+1"
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "message": message,
                "session_id": self.session,
                "solver_mode": "star_limited",
                "verification_mode": "auto",
                "budget_limits": {
                    "max_model_calls": limits.max_model_calls,
                    "max_http_attempts": limits.max_http_attempts,
                    "max_tool_calls": limits.max_tool_calls,
                    "max_tokens": limits.max_tokens,
                    "max_runtime_seconds": limits.max_runtime_seconds,
                },
                "deadline_at": deadline_at,
            },
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key},
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        digest = workspace_job_request_digest(
            session_id=self.session,
            message=message,
            verification_mode="auto",
            solver_mode="star_limited",
            budget_limits=limits,
            deadline_at=deadline_at,
        )

        failed = self.terminal(job_id)
        self.assertEqual("failed", failed["status"], failed)
        retry_call_id = failed["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        lookup = self.client.get(
            "/api/agent/jobs/by-idempotency",
            headers={"Idempotency-Key": key, "X-Request-Digest": digest},
        )
        self.assertEqual(200, lookup.status_code, lookup.get_json())
        failed_identity = lookup.get_json()["transport_identity"]
        self.assertEqual(1, len(failed_identity["calls"]))
        self.assertEqual("nonstream", failed_identity["calls"][0]["transport"])
        self.assertEqual("provider_profile_unverified", failed_identity["calls"][0]["reason"])

        resumed = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": retry_call_id, "new_call_id": str(uuid.uuid4())}},
            headers=self.headers(),
        )
        self.assertEqual(202, resumed.status_code, resumed.get_json())
        self.wait_for(lambda: (job if (job := self.job(job_id))["status"] in {
            "queued", "running"} else None))
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)

        lookup = self.client.get(
            "/api/agent/jobs/by-idempotency",
            headers={"Idempotency-Key": key, "X-Request-Digest": digest},
        )
        self.assertEqual(200, lookup.status_code, lookup.get_json())
        identity = lookup.get_json()["transport_identity"]
        self.assertEqual("legacy", identity["policy"])
        self.assertEqual(4, len(identity["calls"]))
        self.assertEqual(
            {"explore", "explore_polish", "whole_solution_verifier"},
            {call["role"] for call in identity["calls"]},
        )
        self.assertEqual({"nonstream"}, {call["transport"] for call in identity["calls"]})
        self.assertEqual(
            {"provider_profile_unverified"},
            {call["reason"] for call in identity["calls"]},
        )
        self.assertEqual(
            {"verified_stream_profiles_empty"},
            {call["capability_limit"] for call in identity["calls"]},
        )
        self.assertTrue(all(call["call_id"].startswith("solver_call_") for call in identity["calls"]))
        self.assertEqual(4, len({call["call_id"] for call in identity["calls"]}))
        self.assertNotIn(message, json.dumps(identity))

        from showcase.experiment_job_adapter import PublicExperimentJobAdapter
        from showcase.experiment_transport import ExperimentTransportAdapter
        from showcase.stream_preference import profile_set_fingerprint

        manifest_transport = {
            "policy": "legacy",
            "transport": "nonstream",
            "profile_set_fingerprint": profile_set_fingerprint(()),
            "calls": [
                {
                    "call_id": role,
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "capability_limit": "verified_stream_profiles_empty",
                }
                for role in ("explore", "explore_polish", "whole_solution_verifier")
            ],
        }

        class ReadClient:
            def bootstrap(self):
                pass

            def request(self, _method, _path, *, headers):
                self.last_headers = headers
                return lookup.get_json()

        adapter = PublicExperimentJobAdapter(
            ReadClient(),
            {"run_limits": {
                "max_model_calls": limits.max_model_calls,
                "max_http_attempts": limits.max_http_attempts,
                "max_tool_calls": limits.max_tool_calls,
                "max_tokens": limits.max_tokens,
                "max_runtime_seconds": limits.max_runtime_seconds,
            }, "transport": manifest_transport},
            model_config=None,
            sample_resolver=None,
            transport_adapter=ExperimentTransportAdapter(profiles=()),
        )
        adapter.find_by_idempotency_key(key, digest)
        observed = adapter.wait_for_job(job_id, deadline_at)
        self.assertTrue(observed["transport_known"])
        self.assertEqual(manifest_transport, observed["transport"])


if __name__ == "__main__":
    unittest.main()
