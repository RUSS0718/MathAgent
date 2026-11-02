from __future__ import annotations

import json
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from showcase.experiment_job_adapter import PublicExperimentJobAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.workspace import workspace_job_request_digest


class ExperimentPublicJobApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.app = create_app(
            {
                "TESTING": True,
                "SHOWCASE_DATA_DIR": str(Path(self.temporary.name) / "showcase"),
                "SHOWCASE_WORKER_ENABLED": False,
            }
        )
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session_id = self.client.post(
            "/api/new_chat", headers={"X-CSRF-Token": self.csrf}
        ).get_json()["new_session_id"]

    def tearDown(self):
        self.app.extensions["showcase_workspace_service"].close()
        self.app.extensions["showcase_run_service"].close()
        self.app.extensions["loopback_store"].close()
        self.temporary.cleanup()

    def test_budgeted_job_lookup_returns_active_and_terminal_identity_without_prompt(self):
        limits = {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 60,
        }
        deadline_at = time.time() + 30
        key = str(uuid.uuid4())
        message = "private prompt must never appear in lookup"
        response = self.client.post(
            "/api/agent/jobs",
            json={
                "session_id": self.session_id,
                "message": message,
                "verification_mode": "auto",
                "solver_mode": "legacy",
                "budget_limits": limits,
                "deadline_at": deadline_at,
            },
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key},
        )
        self.assertIn(response.status_code, (200, 202))
        job_id = response.get_json()["job_id"]
        digest = workspace_job_request_digest(
            session_id=self.session_id,
            message=message,
            verification_mode="auto",
            solver_mode="legacy",
            budget_limits=RunBudgetLimits(**limits),
            deadline_at=deadline_at,
        )

        lookup = self.client.get(
            "/api/agent/jobs/by-idempotency",
            headers={"Idempotency-Key": key, "X-Request-Digest": digest},
        )
        self.assertEqual(200, lookup.status_code)
        body = lookup.get_json()
        self.assertEqual(job_id, body["job_id"])
        self.assertEqual(digest, body["request_digest"])
        self.assertEqual("queued", body["status"])
        self.assertEqual(limits, body["budget"]["limits"])
        self.assertEqual(deadline_at, body["budget"]["deadline_at"])
        self.assertNotIn(message, str(body))

        mismatch = self.client.get(
            "/api/agent/jobs/by-idempotency",
            headers={"Idempotency-Key": key, "X-Request-Digest": "0" * 64},
        )
        self.assertEqual(409, mismatch.status_code)

        self.app.extensions["showcase_workspace_service"].store.complete_job(
            job_id, "completed", "safe summary"
        )
        terminal = self.client.get(
            "/api/agent/jobs/by-idempotency",
            headers={"Idempotency-Key": key, "X-Request-Digest": digest},
        )
        self.assertEqual(200, terminal.status_code)
        self.assertEqual("succeeded", terminal.get_json()["status"])

    def test_lookup_rejects_missing_or_mismatched_digest(self):
        key = str(uuid.uuid4())
        for digest, expected_status in (("", 400), ("0" * 64, 404)):
            response = self.client.get(
                "/api/agent/jobs/by-idempotency",
                headers={"Idempotency-Key": key, "X-Request-Digest": digest},
            )
            self.assertEqual(expected_status, response.status_code)

    def test_resume_preflight_attaches_only_to_matching_observable_job(self):
        limits = {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 60,
        }
        deadline_at = time.time() + 30
        request_digest = "a" * 64
        idempotency_key = str(uuid.uuid4())

        class LookupClient:
            def __init__(self, record):
                self.record = record
                self.requests = []

            def bootstrap(self):
                pass

            def request(self, method, path, *, headers):
                self.requests.append((method, path, headers))
                return self.record

        def adapter_for(status, *, digest=request_digest, budget=None):
            record = {
                "job_id": "accepted-job",
                "request_digest": digest,
                "status": status,
                "budget": budget
                or {
                    "limits": limits,
                    "deadline_at": deadline_at,
                    "unknown_attempts": 0,
                    "unresolved_attempts": 0,
                    "unknown_tool_calls": 0,
                },
            }
            client = LookupClient(record)
            adapter = PublicExperimentJobAdapter(
                client,
                {"run_limits": limits},
                model_config=None,
                sample_resolver=None,
                transport_adapter=None,
            )
            intent = {
                "idempotency_key": idempotency_key,
                "request_digest": request_digest,
            }
            return adapter, client, intent

        for status in ("queued", "running", "succeeded"):
            adapter, client, intent = adapter_for(status)
            result = adapter.resume_preflight("accepted-job", deadline_at, intent=intent)
            self.assertTrue(result["safe_to_resume"], status)
            self.assertTrue(result["observer_only"], status)
            self.assertEqual("accepted-job", result["job_id"])
            self.assertEqual(request_digest, result["request_digest"])
            self.assertEqual(1, len(client.requests))
            method, path, headers = client.requests[0]
            self.assertEqual("GET", method)
            self.assertEqual("/api/agent/jobs/by-idempotency", path)
            self.assertEqual(idempotency_key, headers["Idempotency-Key"])
            self.assertEqual(request_digest, headers["X-Request-Digest"])

        for status in ("failed", "needs_review", "waiting_input", "unknown"):
            adapter, _client, intent = adapter_for(status)
            result = adapter.resume_preflight("accepted-job", deadline_at, intent=intent)
            self.assertFalse(result["safe_to_resume"], status)

        adapter, _client, intent = adapter_for("running", digest="b" * 64)
        self.assertFalse(
            adapter.resume_preflight("accepted-job", deadline_at, intent=intent)["safe_to_resume"]
        )
        wrong_deadline_budget = {
            "limits": limits,
            "deadline_at": deadline_at - 1,
            "unknown_attempts": 0,
            "unresolved_attempts": 0,
            "unknown_tool_calls": 0,
        }
        adapter, _client, intent = adapter_for("running", budget=wrong_deadline_budget)
        self.assertFalse(
            adapter.resume_preflight("accepted-job", deadline_at, intent=intent)["safe_to_resume"]
        )

    def test_lookup_projects_only_persisted_transport_identity_and_adapter_fails_closed(self):
        from showcase.experiment_transport import ExperimentTransportAdapter
        from showcase.stream_preference import profile_set_fingerprint

        limits = {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 60,
        }
        deadline_at = time.time() + 30
        key = str(uuid.uuid4())
        message = "raw prompt must never appear in the transport projection"
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "session_id": self.session_id,
                "message": message,
                "verification_mode": "auto",
                "solver_mode": "legacy",
                "budget_limits": limits,
                "deadline_at": deadline_at,
            },
            headers={"X-CSRF-Token": self.csrf, "Idempotency-Key": key},
        )
        self.assertIn(created.status_code, (200, 202))
        job_id = created.get_json()["job_id"]
        self.app.extensions["showcase_workspace_service"].store.complete_job(
            job_id, "completed", "safe summary"
        )
        digest = workspace_job_request_digest(
            session_id=self.session_id,
            message=message,
            verification_mode="auto",
            solver_mode="legacy",
            budget_limits=RunBudgetLimits(**limits),
            deadline_at=deadline_at,
        )
        profile_set = "c" * 64
        profile = "d" * 64
        state = {
            "run_id": job_id,
            "transport_policy": {
                "policy": "stream_first",
                "profile_set_fingerprint": profile_set,
            },
            "calls": {
                "internal-call-id": {
                    "role": "explore",
                    "request": {"messages": [{"content": message}]},
                    "response": message,
                    "transport_decision": {
                        "policy": "stream_first",
                        "transport": "stream",
                        "evidence_kind": "controlled_test",
                        "profile_fingerprint": profile,
                        "profile_set_fingerprint": profile_set,
                        "endpoint": "must-not-be-projected",
                    },
                },
                "second-internal-call-id": {
                    "role": "explore",
                    "request": {"messages": [{"content": message}]},
                    "response": message,
                    "transport_decision": {
                        "policy": "stream_first",
                        "transport": "stream",
                        "evidence_kind": "controlled_test",
                        "profile_fingerprint": profile,
                        "profile_set_fingerprint": profile_set,
                        "endpoint": "must-not-be-projected",
                    },
                },
            },
        }
        store = self.app.extensions["showcase_workspace_service"].store
        with store._lock:
            store._connection.execute(
                "INSERT INTO solver_states(run_id,state_json,problem_hash,config_hash,state_revision,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (job_id, json.dumps(state), "problem-hash", "config-hash", 1, "now", "now"),
            )
            store._connection.commit()

        expected_transport = {
            "policy": "stream_first",
            "profile_set_fingerprint": profile_set,
            "calls": [
                {"call_id": "explore", "profile_fingerprint": profile},
                {"call_id": "planner", "profile_fingerprint": profile},
            ],
        }
        manifest = {"run_limits": limits, "transport": expected_transport}

        class ApiClient:
            def bootstrap(self):
                pass

            def request(_self, method, path, *, headers):
                response = self.client.get(path, headers=headers)
                if response.status_code != 200:
                    raise AssertionError("unexpected lookup failure")
                return response.get_json()

        adapter = PublicExperimentJobAdapter(
            ApiClient(),
            manifest,
            model_config=None,
            sample_resolver=None,
            transport_adapter=ExperimentTransportAdapter(profiles=()),
        )
        record = adapter.find_by_idempotency_key(key, digest)[0]
        identity_calls = record["transport_identity"]["calls"]
        self.assertEqual(2, len(identity_calls))
        self.assertEqual({"explore"}, {call["role"] for call in identity_calls})
        self.assertTrue(all(call["call_id"].startswith("solver_call_") for call in identity_calls))
        self.assertTrue(all(call["profile_fingerprint"] == profile for call in identity_calls))
        self.assertNotIn(message, json.dumps(record))
        self.assertNotIn("endpoint", json.dumps(record))
        observation = adapter.wait_for_job(job_id, deadline_at)
        self.assertFalse(observation["transport_known"])
        self.assertIsNone(observation["transport"])

        # A matching profile must also be trusted by the same #124 adapter.
        from showcase.experiment_transport import profile_fingerprint
        from showcase.stream_preference import StreamProfile

        profile_record = StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(("system", ("content", "role")), ("user", ("content", "role"))),
            evidence_kind="controlled_test",
            status="controlled_test",
        )
        expected_profile = profile_fingerprint(profile_record)
        profile_set = profile_set_fingerprint((profile_record,))
        state["transport_policy"]["profile_set_fingerprint"] = profile_set
        state["calls"]["internal-call-id"]["transport_decision"]["profile_set_fingerprint"] = (
            profile_set
        )
        state["calls"]["internal-call-id"]["transport_decision"]["profile_fingerprint"] = (
            expected_profile
        )
        state["calls"]["second-internal-call-id"]["transport_decision"][
            "profile_set_fingerprint"
        ] = profile_set
        state["calls"]["second-internal-call-id"]["transport_decision"]["profile_fingerprint"] = (
            expected_profile
        )
        with store._lock:
            store._connection.execute(
                "UPDATE solver_states SET state_json=? WHERE run_id=?",
                (json.dumps(state), job_id),
            )
            store._connection.commit()
        adapter = PublicExperimentJobAdapter(
            ApiClient(),
            manifest={
                "run_limits": limits,
                "transport": {
                    "policy": "stream_first",
                    "profile_set_fingerprint": profile_set,
                    "calls": [
                        {"call_id": "explore", "profile_fingerprint": expected_profile},
                        {"call_id": "planner", "profile_fingerprint": expected_profile},
                    ],
                },
            },
            model_config=None,
            sample_resolver=None,
            transport_adapter=ExperimentTransportAdapter(profiles=(profile_record,)),
        )
        adapter.find_by_idempotency_key(key, digest)
        observation = adapter.wait_for_job(job_id, deadline_at)
        self.assertTrue(observation["transport_known"])
        self.assertEqual(adapter.manifest["transport"], observation["transport"])

        state["calls"]["internal-call-id"]["transport_decision"]["profile_fingerprint"] = "e" * 64
        with store._lock:
            store._connection.execute(
                "UPDATE solver_states SET state_json=? WHERE run_id=?",
                (json.dumps(state), job_id),
            )
            store._connection.commit()
        observation = adapter.wait_for_job(job_id, deadline_at)
        self.assertFalse(observation["transport_known"])

        with store._lock:
            store._connection.execute("DELETE FROM solver_states WHERE run_id=?", (job_id,))
            store._connection.commit()
        missing = adapter.find_by_idempotency_key(key, digest)[0]
        self.assertIsNone(missing["transport_identity"])
        observation = adapter.wait_for_job(job_id, deadline_at)
        self.assertFalse(observation["transport_known"])

    def test_legacy_transport_wait_requires_manifested_fallback_reason(self):
        from showcase.experiment_transport import ExperimentTransportAdapter
        from showcase.experiment_transport_projection import project_transport_identity
        from showcase.stream_preference import profile_set_fingerprint

        limits = {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 60,
        }
        deadline_at = time.time() + 30
        digest = "a" * 64
        key = str(uuid.uuid4())
        manifest_transport = {
            "policy": "legacy",
            "transport": "nonstream",
            "profile_set_fingerprint": profile_set_fingerprint(()),
            "calls": [
                {
                    "call_id": "explore",
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "capability_limit": "verified_stream_profiles_empty",
                }
            ],
        }
        state = {
            "run_id": "legacy-job",
            "transport_policy": {
                "policy": "legacy",
                "profile_set_fingerprint": manifest_transport["profile_set_fingerprint"],
            },
            "calls": {
                "private-internal-call": {
                    "role": "explore",
                    "transport_decision": {
                        "policy": "legacy",
                        "profile_set_fingerprint": manifest_transport["profile_set_fingerprint"],
                        "transport": "nonstream",
                        "evidence_kind": "documented",
                        "reason": "provider_native_tools_unsupported_with_stream",
                    },
                }
            },
        }
        record = {
            "job_id": "legacy-job",
            "request_digest": digest,
            "status": "succeeded",
            "budget": {
                "limits": limits,
                "deadline_at": deadline_at,
                "unknown_attempts": 0,
                "unresolved_attempts": 0,
                "unknown_tool_calls": 0,
            },
            "transport_identity": project_transport_identity(state, "legacy-job"),
        }

        class ApiClient:
            def bootstrap(self):
                pass

            def request(self, _method, _path, *, headers):
                self.asserted_headers = headers
                return record

        adapter = PublicExperimentJobAdapter(
            ApiClient(),
            {"run_limits": limits, "transport": manifest_transport},
            model_config=None,
            sample_resolver=None,
            transport_adapter=ExperimentTransportAdapter(profiles=()),
        )
        adapter.find_by_idempotency_key(key, digest)
        observation = adapter.wait_for_job("legacy-job", deadline_at)

        self.assertFalse(observation["transport_known"])
        self.assertIsNone(observation["transport"])

        manifest_transport["calls"][0].update(
            reason="provider_native_tools_unsupported_with_stream",
            capability_limit="native_tools_require_nonstream",
        )
        adapter.manifest["transport"] = manifest_transport
        observation = adapter.wait_for_job("legacy-job", deadline_at)

        self.assertTrue(observation["transport_known"])
        self.assertEqual(manifest_transport, observation["transport"])


if __name__ == "__main__":
    unittest.main()
