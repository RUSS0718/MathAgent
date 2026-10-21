from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from requests import HTTPError

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry


class ProviderResponse:
    status_code = 200

    def __init__(self, message, finish_reason="stop", status_code=200):
        self.message = message
        self.finish_reason = finish_reason
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError("fake provider failure", response=self)

    def json(self):
        return {
            "id": "fake-provider-response",
            "model": "intern-s2-test",
            "choices": [{"finish_reason": self.finish_reason, "message": self.message}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }


class DeterministicHTTPProvider:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def post(self, _url, *, data, **_kwargs):
        self.requests.append(json.loads(data))
        return next(self.responses)


def _native_tool_response(call_id, name, arguments, *, call_type="function"):
    raw_arguments = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return ProviderResponse(
        {
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": call_type,
                "function": {"name": name, "arguments": raw_arguments},
            }],
        },
        finish_reason="tool_calls",
    )


class LiveToolWorkspaceContractTest(unittest.TestCase):
    def _run_job(self, provider, registry, *, tool_protocol="native", verification_mode="auto"):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"INTERN_API_KEY": "deterministic-test-key", "INTERN_MODEL": "intern-s2"}),
            patch("llm_client.requests.post", side_effect=provider.post),
            ExitStack() as cleanup,
        ):
            model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256)
            pipeline = LiveAgentPipeline(
                model,
                registry,
                tool_protocol=tool_protocol,
                execution_mode="fake",
            )
            app = create_app({
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": str(Path(directory) / "showcase"),
                "SHOWCASE_JOB_DELAY_SECONDS": 0,
                "SHOWCASE_LIVE_PIPELINE": pipeline,
            })
            cleanup.callback(app.extensions["showcase_workspace_service"].close)
            cleanup.callback(app.extensions["showcase_run_service"].close)
            cleanup.callback(app.extensions["loopback_store"].close)
            client = app.test_client()
            csrf = client.get("/api/check_auth").get_json()["csrf_token"]
            session_id = client.post(
                "/api/new_chat", headers={"X-CSRF-Token": csrf}
            ).get_json()["new_session_id"]
            created = client.post(
                "/api/agent/jobs",
                json={
                    "message": "求解 x-1=0",
                    "session_id": session_id,
                    "verification_mode": verification_mode,
                },
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())},
            )
            job_id = created.get_json()["job_id"]
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                job = client.get(f"/api/agent/jobs/{job_id}").get_json()
                if job["status"] in {"succeeded", "failed", "canceled"}:
                    break
                time.sleep(0.01)
            return {
                "job": job,
                "run": client.get(f"/api/runs/{job_id}").get_json(),
                "run_events": client.get(f"/api/runs/{job_id}/events").get_json()["events"],
                "run_report": client.get(f"/api/runs/{job_id}/report").get_json(),
                "workspace_events": client.get(
                    f"/api/agent/jobs/{job_id}/events?last_event_id=0"
                ).data.decode(),
                "evidence": client.get(f"/api/runs/{job_id}/evidence").get_json(),
                "job_report": client.get(f"/api/agent/jobs/{job_id}/report").get_json(),
                "provider_requests": list(provider.requests),
            }

    def test_text_action_is_explicit_and_returns_result_with_the_same_call_id(self):
        tool_call_id = "text_call_24"
        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        text_action = json.dumps({
            "protocol": "text_action",
            "tool_call": {
                "id": tool_call_id,
                "name": "polynomial_check",
                "arguments": arguments,
            },
        })
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            ProviderResponse({"content": text_action}),
            ProviderResponse({"content": "Candidate checked."}),
            ProviderResponse({"content": "Answer."}),
        ])
        registry = ToolRegistry()
        registry.register_polynomial_check()

        result = self._run_job(provider, registry, tool_protocol="text_action")

        self.assertEqual("succeeded", result["job"]["status"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual("text_action", tool["protocol"])
        self.assertEqual(tool_call_id, tool["tool_call_id"])
        self.assertEqual(tool_call_id, tool["continuation_tool_call_id"])
        self.assertNotIn("tools", result["provider_requests"][1])
        continuation = result["provider_requests"][2]["messages"]
        self.assertEqual(text_action, continuation[-2]["content"])
        returned = json.loads(continuation[-1]["content"])["tool_result"]
        self.assertEqual(tool_call_id, returned["tool_call_id"])
        self.assertEqual(tool_call_id, result["evidence"]["tools"][0]["tool_call_id"])

    def test_native_type_arguments_and_missing_id_errors_are_reviewed_with_evidence(self):
        valid_arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        cases = [
            ("bad_type", "call_bad_type", "other", valid_arguments, "tool_request_invalid"),
            ("bad_arguments", "call_bad_args", "function", "{broken", "tool_arguments_invalid"),
            ("missing_id", None, "function", valid_arguments, "tool_call_id_missing"),
        ]
        for label, call_id, call_type, arguments, expected_error in cases:
            with self.subTest(label=label):
                registry = ToolRegistry()
                registry.register_polynomial_check()
                provider = DeterministicHTTPProvider([
                    ProviderResponse({"content": "Plan."}),
                    _native_tool_response(call_id, "polynomial_check", arguments, call_type=call_type),
                ])

                result = self._run_job(provider, registry)

                self.assertEqual("failed", result["job"]["status"])
                self.assertEqual("NEEDS_REVIEW", result["run"]["status"])
                tool = result["job"]["result"]["tool_results"][0]
                self.assertEqual(expected_error, tool["error_category"])
                self.assertEqual(call_id or "", tool["tool_call_id"])
                self.assertEqual(2, len(result["provider_requests"]))
                self.assertEqual(call_id or "", result["evidence"]["tools"][0]["tool_call_id"])
                self.assertEqual(
                    result["job_report"]["report"]["tool_summaries"],
                    result["run_report"]["report"]["tool_summaries"],
                )
                self.assertEqual(
                    result["job_report"]["report"]["tool_summaries"][0]["tool_call_id"],
                    result["run_report"]["report"]["tool_summaries"][0]["tool_call_id"],
                )
                self.assertEqual(
                    result["job_report"]["report"]["checks"],
                    result["run_report"]["report"]["checks"],
                )
                self.assertEqual(result["job"]["job_id"], result["run_report"]["evidence_id"])
                self.assertEqual(
                    result["job_report"]["report"]["checks"],
                    result["evidence"]["verification"],
                )

    def test_multiple_native_calls_are_rejected_without_executing_either(self):
        handler_calls = []
        registry = ToolRegistry()
        registry.register(
            "double",
            lambda arguments: handler_calls.append(arguments["value"]),
            parameters_schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
        )
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            ProviderResponse(
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_first",
                            "type": "function",
                            "function": {"name": "double", "arguments": '{"value":1}'},
                        },
                        {
                            "id": "call_second",
                            "type": "function",
                            "function": {"name": "double", "arguments": '{"value":2}'},
                        },
                    ],
                },
                finish_reason="tool_calls",
            ),
        ])

        result = self._run_job(provider, registry, verification_mode="required")

        self.assertEqual("failed", result["job"]["status"])
        self.assertEqual("multiple_tool_requests", result["run"]["error"]["category"])
        self.assertEqual([], handler_calls)
        self.assertEqual(
            ["call_first", "call_second"],
            [item["tool_call_id"] for item in result["job"]["result"]["tool_results"]],
        )
        self.assertEqual(2, len(result["provider_requests"]))
        self.assertIn("call_first", result["workspace_events"])
        self.assertIn("call_second", result["workspace_events"])

    def test_unknown_invalid_schema_and_profile_denied_tools_are_recorded(self):
        valid_arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        cases = [
            ("unknown", "unregistered_tool", {}, ToolRegistry(), "tool_not_registered"),
            (
                "invalid_schema",
                "polynomial_check",
                {"schema_version": 1},
                ToolRegistry(),
                "tool_schema_invalid",
            ),
            (
                "profile_denied",
                "polynomial_check",
                valid_arguments,
                ToolRegistry(profile="official"),
                "tool_not_permitted_for_profile",
            ),
        ]
        for label, name, arguments, registry, expected_error in cases:
            if name == "polynomial_check":
                registry.register_polynomial_check()
            call_id = f"call_{label}"
            provider = DeterministicHTTPProvider([
                ProviderResponse({"content": "Plan."}),
                _native_tool_response(call_id, name, arguments),
            ])
            with self.subTest(label=label):
                result = self._run_job(provider, registry)
                self.assertEqual("failed", result["job"]["status"])
                self.assertEqual("NEEDS_REVIEW", result["run"]["status"])
                tool = result["job"]["result"]["tool_results"][0]
                self.assertEqual(expected_error, tool["error_category"])
                self.assertEqual(call_id, tool["tool_call_id"])
                self.assertEqual(call_id, result["evidence"]["tools"][0]["tool_call_id"])
                self.assertEqual(2, len(result["provider_requests"]))
                if label == "profile_denied":
                    self.assertNotIn("tools", result["provider_requests"][1])

    def test_tool_exception_is_recorded_without_continuation(self):
        handler_calls = []

        def fail(_arguments):
            handler_calls.append(True)
            raise RuntimeError("private detail")

        registry = ToolRegistry()
        registry.register(
            "explode",
            fail,
            parameters_schema={"type": "object", "properties": {}, "additionalProperties": False},
        )
        call_id = "call_explode"
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            _native_tool_response(call_id, "explode", {}),
        ])

        result = self._run_job(provider, registry)

        self.assertEqual("failed", result["job"]["status"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual("error", tool["status"])
        self.assertEqual("tool_execution_error", tool["error_category"])
        self.assertEqual(call_id, tool["tool_call_id"])
        self.assertEqual([True], handler_calls)
        self.assertEqual(2, len(result["provider_requests"]))
        self.assertNotIn("private detail", json.dumps(result["evidence"], ensure_ascii=False))

    def test_missing_continuation_is_reviewed_and_keeps_tool_evidence(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        call_id = "call_missing_continuation"
        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            _native_tool_response(call_id, "polynomial_check", arguments),
            ProviderResponse({"error": "unavailable"}, status_code=503),
        ])

        result = self._run_job(provider, registry)

        self.assertEqual("failed", result["job"]["status"])
        self.assertEqual("NEEDS_REVIEW", result["run"]["status"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual("success", tool["status"])
        self.assertEqual(call_id, tool["tool_call_id"])
        self.assertEqual("missing", tool["continuation_status"])
        self.assertEqual("tool_continuation_missing", tool["continuation_error_category"])
        self.assertFalse(tool["continuation_response_received"])
        self.assertEqual(call_id, tool["continuation_tool_call_id"])
        self.assertEqual(call_id, result["provider_requests"][2]["messages"][-1]["tool_call_id"])
        self.assertEqual(call_id, result["evidence"]["tools"][0]["tool_call_id"])

    def test_empty_continuation_is_reported_without_claiming_non_consumption(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        call_id = "call_empty_continuation"
        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            _native_tool_response(call_id, "polynomial_check", arguments),
            ProviderResponse({"content": ""}),
        ])

        result = self._run_job(provider, registry)

        self.assertEqual("failed", result["job"]["status"])
        self.assertEqual("tool_continuation_incomplete", result["run"]["error"]["category"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual("empty_response", tool["continuation_status"])
        self.assertTrue(tool["continuation_response_received"])
        self.assertEqual(call_id, result["evidence"]["tools"][0]["tool_call_id"])

    def test_another_continuation_tool_request_is_reported_as_incomplete(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        call_id = "call_second_tool"
        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan."}),
            _native_tool_response(call_id, "polynomial_check", arguments),
            _native_tool_response("call_extra", "polynomial_check", arguments),
        ])

        result = self._run_job(provider, registry)

        self.assertEqual("failed", result["job"]["status"])
        self.assertEqual("tool_continuation_incomplete", result["run"]["error"]["category"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual("another_tool_requested", tool["continuation_status"])
        self.assertTrue(tool["continuation_response_received"])

    def test_native_tool_call_id_reaches_execution_continuation_events_and_evidence(self):
        tool_call_id = "call_poly_9f4a"
        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["1"],
        }
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Check the polynomial candidate."}),
            ProviderResponse(
                {
                    "content": None,
                    "tool_calls": [{
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "polynomial_check",
                            "arguments": json.dumps(arguments),
                        },
                    }],
                },
                finish_reason="tool_calls",
            ),
            ProviderResponse({"content": "The candidate is valid."}),
            ProviderResponse({"content": "答案：x=1。"}),
        ])

        registry = ToolRegistry()
        registry.register_polynomial_check()
        result = self._run_job(provider, registry)

        self.assertEqual("succeeded", result["job"]["status"])
        tool = result["job"]["result"]["tool_results"][0]
        self.assertEqual(tool_call_id, tool["tool_call_id"])
        self.assertEqual("native", tool["protocol"])
        self.assertEqual(tool_call_id, tool["continuation_tool_call_id"])
        self.assertTrue(tool["continuation_response_received"])
        self.assertEqual("pass", tool["value"]["candidate_status"])
        self.assertEqual("unknown", result["job"]["result"]["verification"]["status"])

        continuation_messages = result["provider_requests"][2]["messages"]
        self.assertEqual("assistant", continuation_messages[-2]["role"])
        assistant_tool_call = continuation_messages[-2]["tool_calls"][0]
        self.assertEqual(tool_call_id, assistant_tool_call["id"])
        self.assertEqual(arguments, json.loads(assistant_tool_call["function"]["arguments"]))
        continuation_tool_message = continuation_messages[-1]
        self.assertEqual("tool", continuation_tool_message["role"])
        self.assertEqual(tool_call_id, continuation_tool_message["tool_call_id"])
        self.assertEqual("polynomial_check", continuation_tool_message["name"])
        schema = result["provider_requests"][1]["tools"][0]
        self.assertEqual("function", schema["type"])
        self.assertEqual("polynomial_check", schema["function"]["name"])
        self.assertEqual(set(arguments), set(schema["function"]["parameters"]["properties"]))

        self.assertIn(tool_call_id, result["workspace_events"])
        self.assertTrue(any(event.get("tool_call_id") == tool_call_id for event in result["run_events"]))
        evidence = result["evidence"]
        self.assertEqual(tool_call_id, evidence["tools"][0]["tool_call_id"])
        self.assertEqual(tool_call_id, evidence["tools"][0]["continuation_tool_call_id"])
        self.assertEqual("native", evidence["tools"][0]["protocol"])
        self.assertEqual("fake", evidence["mode"])
        self.assertEqual("pass", evidence["tools"][0]["candidate_status"])
        self.assertTrue(evidence["tools"][0]["checker_evidence_id"])
        self.assertTrue(evidence["tools"][0]["continuation_response_received"])
        self.assertEqual("fake", result["job_report"]["mode"])
        self.assertEqual(
            result["job_report"]["report"]["tool_summaries"],
            result["run_report"]["report"]["tool_summaries"],
        )
        self.assertEqual(
            result["job_report"]["report"]["tool_summaries"][0]["tool_call_id"],
            result["run_report"]["report"]["tool_summaries"][0]["tool_call_id"],
        )
        self.assertEqual(
            result["job_report"]["report"]["checks"],
            result["run_report"]["report"]["checks"],
        )
        self.assertEqual(result["job"]["job_id"], result["run_report"]["evidence_id"])
        self.assertEqual(result["job"]["job_id"], result["evidence"]["evidence_id"])
        self.assertEqual(
            result["job_report"]["report"]["checks"],
            result["evidence"]["verification"],
        )


if __name__ == "__main__":
    unittest.main()
