from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import time
import unittest
import uuid
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from requests import HTTPError, Timeout

from scripts.run_s2_live_gate import main as run_g2_cli
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.g2_campaign import run_g2_campaign
from showcase.g2_live_gate import (
    G2_CASES,
    G2_CLIENT_TIMEOUT_SECONDS,
    G2_DATASET_VERSION,
    G2_MAX_GENERATIONS_PER_RUN,
    G2_MAX_HTTP_ATTEMPTS,
    G2_MAX_TOKENS_PER_ATTEMPT,
    G2_MODEL,
    G2_PROMPT_ARGUMENT_EXAMPLE,
    G2_PROTOCOL_PROMPT_VERSION,
    G2_REPEATS,
    G2LivePipeline,
    g2_protocol_schema_sha256,
)
from showcase.run_service import RunService
from showcase.tool_schemas import schema_error
from showcase.tools import ToolRegistry


class FakeResponse:
    def __init__(self, message, *, finish_reason="stop", status_code=200):
        self.message = message
        self.finish_reason = finish_reason
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise HTTPError("fake provider failure", response=self)

    def json(self):
        return {
            "id": f"response-{uuid.uuid4().hex}",
            "model": G2_MODEL,
            "choices": [{"finish_reason": self.finish_reason, "message": self.message}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 9, "total_tokens": 20},
        }


class FakeHTTPProvider:
    def __init__(self, outcomes, *, delay_seconds=0):
        self.outcomes = iter(outcomes)
        self.requests = []
        self.delay_seconds = delay_seconds

    def post(self, _url, *, data, **_kwargs):
        payload = json.loads(data)
        self.requests.append(payload)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


ARGUMENTS = (
    {
        "schema_version": 1,
        "variable": "x",
        "coefficients": ["1", "-1"],
        "domain": {"kind": "real"},
        "candidates": ["1", "2"],
    },
    {
        "schema_version": 1,
        "variable": "x",
        "coefficients": ["1", "0", "-1"],
        "domain": {"kind": "real"},
        "candidates": ["-1", "1", "2"],
    },
    {
        "schema_version": 1,
        "variable": "x",
        "coefficients": ["1", "-3", "2"],
        "domain": {"kind": "real"},
        "candidates": ["1", "2", "3"],
    },
)


def _tool_response(call_id, arguments, *, finish_reason="tool_calls"):
    return FakeResponse(
        {
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "polynomial_check",
                    "arguments": json.dumps(arguments),
                },
            }],
        },
        finish_reason=finish_reason,
    )


def _successful_outcomes(start_index=0):
    outcomes = []
    for index in range(start_index, G2_REPEATS * len(G2_CASES)):
        outcomes.extend([
            _tool_response(f"g2-call-{index}", ARGUMENTS[index // G2_REPEATS]),
            FakeResponse({"content": "候选代回结果已返回。"}),
        ])
    return outcomes


class G2LiveGateContractTest(unittest.TestCase):
    def _run_campaign(self, provider, *, run_timeout_seconds=5):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "g2"
        root.mkdir()
        database = root / "workspace.sqlite3"
        with (
            patch.dict(os.environ, {
                "INTERN_API_KEY": "deterministic-test-key",
                "INTERN_MODEL": G2_MODEL,
                "INTERN_THINKING_MODE": "false",
                "INTERN_RETRY_COUNT": "8",
            }),
            patch("llm_client.requests.post", side_effect=provider.post),
            ExitStack() as cleanup,
        ):
            model = InternModelAdapter(
                model_id=G2_MODEL,
                max_tokens=G2_MAX_TOKENS_PER_ATTEMPT,
                client_retry=1,
                client_timeout=G2_CLIENT_TIMEOUT_SECONDS,
                thinking_mode=True,
            )
            app = create_app(
                {
                    "TESTING": True,
                    "SHOWCASE_MODE": "live",
                    "SHOWCASE_DATA_DIR": str(root),
                    "SHOWCASE_JOB_DELAY_SECONDS": 0,
                    "SHOWCASE_LIVE_PIPELINE": G2LivePipeline(model),
                },
                database_path=database,
                service=RunService(database_path=database),
            )
            cleanup.callback(app.extensions["showcase_workspace_service"].close)
            cleanup.callback(app.extensions["showcase_run_service"].close)
            cleanup.callback(app.extensions["loopback_store"].close)
            report = run_g2_campaign(
                app.test_client(),
                poll_interval_seconds=0.005,
                run_timeout_seconds=run_timeout_seconds,
            )
        return report

    def test_six_live_runs_record_native_tool_execution_and_matching_continuation(self):
        provider = FakeHTTPProvider(_successful_outcomes())
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("pass", report["contract_result"])
        self.assertEqual("fake", report["mode"])
        self.assertEqual("fake_http", report["execution_source"])
        self.assertEqual(G2_PROTOCOL_PROMPT_VERSION, report["protocol_prompt_version"])
        self.assertEqual(g2_protocol_schema_sha256(), report["protocol_schema_sha256"])
        registry = ToolRegistry(max_calls=1)
        registry.register_polynomial_check()
        parameters = registry.allowed_schemas()[0]["parameters"]
        self.assertIsNone(schema_error(G2_PROMPT_ARGUMENT_EXAMPLE, parameters))
        self.assertEqual("object", parameters["properties"]["domain"]["type"])
        self.assertEqual(2, len(parameters["properties"]["domain"]["oneOf"]))
        transmitted_parameters = provider.requests[0]["tools"][0]["function"]["parameters"]
        self.assertEqual(
            report["protocol_schema_sha256"],
            hashlib.sha256(
                json.dumps(
                    transmitted_parameters,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(G2_MAX_HTTP_ATTEMPTS, report["http_attempt_count"])
        self.assertEqual(G2_REPEATS * len(G2_CASES), len(report["runs"]))
        self.assertEqual(G2_MAX_HTTP_ATTEMPTS, len(provider.requests))
        self.assertTrue(all(item["protocol_evidence"] == "simulated" for item in report["runs"]))
        for index, row in enumerate(report["runs"]):
            with self.subTest(run=index):
                case = G2_CASES[index // G2_REPEATS]
                self.assertEqual(G2_DATASET_VERSION, row["input_version"])
                self.assertEqual(
                    hashlib.sha256(case.problem.encode("utf-8")).hexdigest(),
                    row["input_sha256"],
                )
                self.assertEqual(row["run_id"], row["evidence_id"])
                self.assertEqual(row["run_id"], row["run_evidence_id"])
                self.assertEqual("fake", row["mode"])
                self.assertEqual("live", row["workspace_mode"])
                self.assertEqual("fake_http", row["execution_source"])
                self.assertEqual(G2_PROTOCOL_PROMPT_VERSION, row["protocol_prompt_version"])
                self.assertEqual(report["protocol_schema_sha256"], row["protocol_schema_sha256"])
                self.assertEqual(2, len(row["attempts"]))
                self.assertEqual(["tool_calls", "stop"], row["finish_reasons"])
                for attempt in row["attempts"]:
                    self.assertEqual(G2_MODEL, attempt["requested_model"])
                    self.assertEqual(G2_MODEL, attempt["returned_model"])
                    self.assertTrue(attempt["thinking_mode"])
                    self.assertLessEqual(attempt["max_tokens"], 512)
                    self.assertEqual("success", attempt["status"])
                self.assertEqual("native", row["tool_protocol"])
                self.assertEqual("polynomial_check", row["tool_name"])
                self.assertEqual("success", row["tool_execution_status"])
                self.assertEqual(row["tool_call_id"], row["continuation_tool_call_id"])
                self.assertTrue(row["continuation_response_received"])

        for index, request in enumerate(provider.requests):
            self.assertEqual(G2_MODEL, request["model"])
            self.assertEqual(512, request["max_tokens"])
            self.assertIs(request["thinking_mode"], True)
            self.assertIn(
                G2_PROTOCOL_PROMPT_VERSION,
                request["messages"][0]["content"],
            )
            if index % 2 == 0:
                self.assertEqual("polynomial_check", request["tools"][0]["function"]["name"])
            else:
                self.assertEqual("tool", request["messages"][-1]["role"])
                self.assertEqual(
                    f"g2-call-{index // 2}", request["messages"][-1]["tool_call_id"]
                )
        serialized = json.dumps(report, ensure_ascii=False)
        for case in G2_CASES:
            self.assertNotIn(case.problem, serialized)
        self.assertNotIn("reasoning_content", serialized)

    def test_registry_accepts_both_domain_objects_and_rejects_domain_string(self):
        registry = ToolRegistry(max_calls=2)
        registry.register_polynomial_check()
        base = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "-1"],
            "candidates": ["1"],
        }
        real = registry.invoke(
            "polynomial_check", {**base, "domain": {"kind": "real"}}, tool_call_id="real"
        )
        interval = registry.invoke(
            "polynomial_check",
            {**base, "domain": {"kind": "interval", "left": "0", "right": "2"}},
            tool_call_id="interval",
        )
        invalid = registry.invoke(
            "polynomial_check", {**base, "domain": "real"}, tool_call_id="invalid"
        )

        self.assertEqual("success", real.status)
        self.assertEqual("success", interval.status)
        self.assertEqual("rejected", invalid.status)
        self.assertEqual("tool_schema_invalid", invalid.error_category)
        tool_parameters = registry.provider_schemas()[0]["function"]["parameters"]
        self.assertEqual("object", tool_parameters["properties"]["domain"]["type"])
        self.assertEqual(2, len(tool_parameters["properties"]["domain"]["oneOf"]))

    def test_truncated_first_generation_is_retained_without_retry_or_tool_execution(self):
        provider = FakeHTTPProvider([
            _tool_response("g2-truncated", ARGUMENTS[0], finish_reason="length"),
            *_successful_outcomes(start_index=1),
        ])
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("needs_review", report["contract_result"])
        self.assertEqual(1 + G2_MAX_HTTP_ATTEMPTS - 2, report["http_attempt_count"])
        first = report["runs"][0]
        self.assertEqual("needs_review", first["protocol_evidence"])
        self.assertEqual(["length"], first["finish_reasons"])
        self.assertEqual("output_truncated", first["error_category"])
        self.assertEqual([], first["tool_call_ids"])
        self.assertEqual(1 + G2_MAX_HTTP_ATTEMPTS - 2, len(provider.requests))

    def test_no_native_tool_request_is_retained_and_not_replaced(self):
        provider = FakeHTTPProvider([
            FakeResponse({"content": "直接答案。"}),
            *_successful_outcomes(start_index=1),
        ])
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("needs_review", report["contract_result"])
        first = report["runs"][0]
        self.assertEqual("needs_review", first["protocol_evidence"])
        self.assertEqual("tool_request_missing", first["error_category"])
        self.assertEqual(1, len(first["attempts"]))
        self.assertEqual("stop", first["finish_reasons"][0])
        self.assertEqual([], first["tool_call_ids"])
        self.assertEqual(1 + G2_MAX_HTTP_ATTEMPTS - 2, len(provider.requests))

    def test_truncated_continuation_retains_execution_and_attempt_without_retry(self):
        provider = FakeHTTPProvider([
            _tool_response("g2-cont-truncated", ARGUMENTS[0]),
            FakeResponse({"content": "部分答案"}, finish_reason="length"),
            *_successful_outcomes(start_index=1),
        ])
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("needs_review", report["contract_result"])
        first = report["runs"][0]
        self.assertEqual("needs_review", first["protocol_evidence"])
        self.assertEqual(["tool_calls", "length"], first["finish_reasons"])
        self.assertEqual("output_truncated", first["error_category"])
        self.assertEqual("success", first["tool_execution_status"])
        self.assertTrue(first["continuation_response_received"])
        self.assertEqual(first["tool_call_id"], first["continuation_tool_call_id"])
        self.assertEqual(G2_MAX_HTTP_ATTEMPTS, len(provider.requests))

    def test_timeout_is_recorded_as_one_attempt_and_later_fixed_runs_continue(self):
        provider = FakeHTTPProvider([
            Timeout("fake timeout"),
            *_successful_outcomes(start_index=1),
        ])
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("needs_review", report["contract_result"])
        first = report["runs"][0]
        self.assertEqual("needs_review", first["protocol_evidence"])
        self.assertEqual(1, len(first["attempts"]))
        self.assertEqual("error", first["attempts"][0]["status"])
        self.assertEqual("timeout", first["attempts"][0]["error_category"])
        self.assertEqual(1 + G2_MAX_HTTP_ATTEMPTS - 2, len(provider.requests))

    def test_unresolved_workspace_run_blocks_rest_of_batch(self):
        provider = FakeHTTPProvider(_successful_outcomes(), delay_seconds=0.25)
        report = self._run_campaign(provider, run_timeout_seconds=0.02)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("needs_review", report["contract_result"])
        self.assertFalse(report["attempts_complete"])
        self.assertIsNone(report["http_attempt_count"])
        self.assertEqual("unknown", report["runs"][0]["status"])
        self.assertFalse(report["runs"][0]["attempts_complete"])
        self.assertTrue(all(row["protocol_evidence"] == "blocked" for row in report["runs"][1:]))
        self.assertTrue(all(row["run_id"] is None for row in report["runs"][1:]))
        self.assertLessEqual(len(provider.requests), G2_MAX_GENERATIONS_PER_RUN)

    def test_auth_failure_stops_requests_and_retains_blocked_rows(self):
        provider = FakeHTTPProvider([FakeResponse({"content": "denied"}, status_code=401)])
        report = self._run_campaign(provider)

        self.assertEqual("simulated", report["status"])
        self.assertEqual("blocked", report["contract_result"])
        self.assertEqual(1, len(provider.requests))
        self.assertEqual(6, len(report["runs"]))
        self.assertEqual("needs_review", report["runs"][0]["protocol_evidence"])
        self.assertEqual(401, report["runs"][0]["attempts"][0]["http_status"])
        self.assertTrue(all(row["protocol_evidence"] == "blocked" for row in report["runs"][1:]))
        self.assertTrue(all(row["run_id"] is None for row in report["runs"][1:]))

    def test_cli_defaults_to_offline_without_an_http_request(self):
        output = io.StringIO()
        with patch("llm_client.requests.post", side_effect=AssertionError("unexpected request")) as post:
            with redirect_stdout(output):
                status = run_g2_cli([])

        self.assertEqual(0, status)
        post.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertEqual("offline", payload["mode"])
        self.assertEqual(0, payload["http_attempt_count"])


if __name__ == "__main__":
    unittest.main()
