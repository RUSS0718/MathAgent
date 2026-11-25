"""Offline contract tests for the DeepSeek ModelPort adapter."""

import io
import json
import os
import traceback
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ricl_runtime.port import ModelReply
from ricl_runtime.providers.deepseek import (
    ALLOWED_GATEWAY_HOST,
    DeepSeekModelPort,
    DeepSeekReply,
    ProviderConfigurationError,
    ProviderHTTPError,
    ProviderOutcomeUnknownError,
    ProviderPreflightError,
    ProviderProtocolError,
    ProviderTimeoutError,
    _RejectRedirects,
)


class FakeResponse:
    """Provide a bounded, in-memory response without opening a socket."""

    def __init__(self, body: bytes) -> None:
        """Retain fixture bytes and record the requested read limit."""

        self.body = body
        self.read_limit: int | None = None

    def __enter__(self) -> "FakeResponse":
        """Support urllib-style response management."""

        return self

    def __exit__(self, *_: object) -> None:
        """Close the fixture response without external effects."""

    def read(self, limit: int) -> bytes:
        """Return fixture data while exposing the adapter's bound."""

        self.read_limit = limit
        return self.body[:limit]


class FakeOpener:
    """Provide a bounded opener fixture without opening a socket."""

    def __init__(self, response: object = None, error: BaseException | None = None) -> None:
        """Retain one response or one fixture error."""

        self.response = response
        self.error = error
        self.calls: list[tuple[object, float]] = []

    def open(self, request: object, *, timeout: float) -> object:
        """Record the single request and return or raise the fixture outcome."""

        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        return self.response


class DeepSeekModelPortTests(unittest.TestCase):
    """Exercise the public ModelPort behavior against a mocked HTTP boundary."""

    def test_complete_maps_chat_reply_and_provider_metadata(self) -> None:
        body = json.dumps(
            {
                "id": "request-fixture-42",
                "model": "deepseek-flash-revision",
                "choices": [{"message": {"content": "The answer is 4."}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5},
            }
        ).encode()
        response = FakeResponse(body)
        prompt = "fixture prompt that must not appear in diagnostics"
        port = DeepSeekModelPort(
            api_key="inert-test-credential",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
            thinking="enabled",
        )
        opener = FakeOpener(response=response)

        with (
            patch(
                "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
                return_value=opener,
            ) as build_opener,
            patch("ricl_runtime.providers.deepseek.DEFAULT_TIMEOUT_SECONDS", 0.25),
            patch("ricl_runtime.providers.deepseek.MAX_RESPONSE_BYTES", 2048),
        ):
            reply = port.complete(prompt)

        self.assertIsInstance(reply, ModelReply)
        self.assertIsInstance(reply, DeepSeekReply)
        self.assertEqual(reply.text, "The answer is 4.")
        self.assertEqual(reply.model, "deepseek-flash-revision")
        self.assertEqual(reply.input_tokens, 11)
        self.assertEqual(reply.output_tokens, 5)
        self.assertEqual(reply.usage_source, "provider")
        self.assertEqual(reply.request_id, "request-fixture-42")
        self.assertEqual(build_opener.call_count, 1)
        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer inert-test-credential")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "thinking": {"type": "enabled"},
            },
        )
        self.assertNotIn("tools", json.loads(request.data))
        self.assertEqual(timeout, 0.25)
        self.assertEqual(response.read_limit, 2049)

    def test_environment_factory_reads_only_named_configuration(self) -> None:
        with patch.dict(
            os.environ,
            {
                "API_KEY": "inert-environment-credential",
                "BASE_URL": "https://api.deepseek.com/v1",
                "MODEL": "deepseek-flash",
            },
        ):
            port = DeepSeekModelPort.from_environment()

        self.assertEqual(port.name, "deepseek-flash")

    def test_missing_environment_configuration_is_sanitized(self) -> None:
        with patch.dict(os.environ, {"API_KEY": "", "BASE_URL": "", "MODEL": ""}):
            with self.assertRaises(ProviderConfigurationError) as raised:
                DeepSeekModelPort.from_environment()

        self.assertNotIn("inert-environment-credential", str(raised.exception))

    def test_http_error_is_distinct_redacted_and_not_retried(self) -> None:
        prompt = "fixture prompt redaction sentinel"
        credential = "inert-test-credential"
        response_error = HTTPError(
            "https://api.deepseek.com/v1/chat/completions",
            429,
            f"provider body mentions {prompt} and {credential}",
            hdrs=None,
            fp=io.BytesIO(b"sensitive fixture body"),
        )
        port = DeepSeekModelPort(
            api_key=credential,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        opener = FakeOpener(error=response_error)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ProviderHTTPError) as raised:
                port.complete(prompt)

        self.assertEqual(raised.exception.status_code, 429)
        self.assertEqual(raised.exception.failure_status, "protocol_failed")
        self.assertNotIn(prompt, str(raised.exception))
        self.assertNotIn(credential, str(raised.exception))
        self.assertNotIn("sensitive fixture body", str(raised.exception))
        formatted = "".join(traceback.format_exception(raised.exception))
        self.assertNotIn(prompt, formatted)
        self.assertNotIn(credential, formatted)
        self.assertNotIn("sensitive fixture body", formatted)
        self.assertEqual(len(opener.calls), 1)

    def test_timeout_is_distinct_redacted_and_not_retried(self) -> None:
        prompt = "fixture prompt timeout sentinel"
        credential = "inert-test-credential"
        port = DeepSeekModelPort(
            api_key=credential,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        opener = FakeOpener(error=TimeoutError(f"{prompt} {credential}"))

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ProviderTimeoutError) as raised:
                port.complete(prompt)

        self.assertNotIn(prompt, str(raised.exception))
        self.assertNotIn(credential, str(raised.exception))
        self.assertEqual(len(opener.calls), 1)

    def test_transport_failure_is_unknown_outcome_and_not_retried(self) -> None:
        prompt = "fixture prompt unknown-outcome sentinel"
        credential = "inert-test-credential"
        port = DeepSeekModelPort(
            api_key=credential,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        opener = FakeOpener(error=URLError(f"{prompt} {credential}"))

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ProviderOutcomeUnknownError) as raised:
                port.complete(prompt)

        self.assertNotIn(prompt, str(raised.exception))
        self.assertNotIn(credential, str(raised.exception))
        self.assertEqual(raised.exception.failure_status, "unknown_outcome")
        self.assertEqual(len(opener.calls), 1)

    def test_redirect_is_rejected_before_a_follow_up_request(self) -> None:
        with self.assertRaises(ProviderHTTPError) as raised:
            _RejectRedirects().redirect_request(
                None, None, 307, "redirect", {}, "https://example.invalid/next"
            )

        self.assertEqual(raised.exception.status_code, 307)

    def test_request_preflight_allows_only_priced_host_and_models(self) -> None:
        opener_builder = patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener"
        )
        with opener_builder as build_opener:
            for base_url, model in (
                ("https://api.deepseek.example/v1", "deepseek-flash"),
                ("https://api.deepseek.com/v1", "unpriced-model"),
            ):
                with self.subTest(base_url=base_url, model=model):
                    port = DeepSeekModelPort(
                        api_key="inert-test-credential",
                        base_url=base_url,
                        model=model,
                    )
                    with self.assertRaises(ProviderPreflightError):
                        port.complete("fixture prompt")
            build_opener.assert_not_called()

    def test_request_preflight_accepts_legacy_flash_alias(self) -> None:
        port = DeepSeekModelPort(
            api_key="inert-test-credential",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-v4-flash-vision-exp",
        )
        response = FakeResponse(
            json.dumps(
                {
                    "id": "legacy-alias-request",
                    "model": "DeepSeek-V4.1-Flash-1017",
                    "choices": [{"message": {"content": "4"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ).encode()
        )
        opener = FakeOpener(response=response)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            reply = port.complete("fixture prompt")

        self.assertEqual(reply.model, "DeepSeek-V4.1-Flash-1017")
        self.assertEqual(len(opener.calls), 1)
        request, _ = opener.calls[0]
        self.assertEqual(json.loads(request.data)["model"], "deepseek-v4-flash-vision-exp")

    def test_request_preflight_accepts_configured_gateway_and_model(self) -> None:
        port = DeepSeekModelPort(
            api_key="inert-test-credential",
            base_url=f"https://{ALLOWED_GATEWAY_HOST}/v1",
            model="deepseek-v4.1-flash",
        )
        response = FakeResponse(
            json.dumps(
                {
                    "id": "gateway-request",
                    "model": "deepseek-v4.1-flash",
                    "choices": [{"message": {"content": "4"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }
            ).encode()
        )
        opener = FakeOpener(response=response)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            reply = port.complete("fixture prompt")

        self.assertEqual(reply.request_id, "gateway-request")
        request, _ = opener.calls[0]
        self.assertEqual(request.full_url, f"https://{ALLOWED_GATEWAY_HOST}/v1/chat/completions")
        self.assertEqual(json.loads(request.data)["model"], "deepseek-v4.1-flash")

    def test_request_preflight_rejects_oversized_prompt_without_opening(self) -> None:
        port = DeepSeekModelPort(
            api_key="inert-test-credential",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        prompt = "x" * (16 * 1024 + 1)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener"
        ) as build_opener:
            with self.assertRaises(ProviderPreflightError) as raised:
                port.complete(prompt)

        self.assertNotIn(prompt, str(raised.exception))
        build_opener.assert_not_called()
        self.assertEqual(port.cost_limit_usd, 0.05)
        self.assertEqual(port.preflight_cost_upper_bound_usd, "0.0055296")

    def test_malformed_json_is_a_redacted_protocol_error(self) -> None:
        prompt = "fixture prompt malformed response sentinel"
        credential = "inert-test-credential"
        port = DeepSeekModelPort(
            api_key=credential,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        malformed = FakeResponse(b"provider body is not JSON")
        opener = FakeOpener(response=malformed)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=opener,
        ):
            with self.assertRaises(ProviderProtocolError) as raised:
                port.complete(prompt)

        self.assertNotIn(prompt, str(raised.exception))
        self.assertNotIn(credential, str(raised.exception))
        self.assertNotIn("provider body", str(raised.exception))
        self.assertEqual(len(opener.calls), 1)

    def test_malformed_or_oversized_response_is_redacted_protocol_error(self) -> None:
        prompt = "fixture prompt protocol sentinel"
        credential = "inert-test-credential"
        port = DeepSeekModelPort(
            api_key=credential,
            base_url="https://api.deepseek.com/v1",
            model="deepseek-flash",
        )
        oversized = FakeResponse(b"provider body exceeds the configured limit")
        opener = FakeOpener(response=oversized)

        with (
            patch(
                "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
                return_value=opener,
            ),
            patch("ricl_runtime.providers.deepseek.MAX_RESPONSE_BYTES", 8),
        ):
            with self.assertRaises(ProviderProtocolError) as raised:
                port.complete(prompt)

        self.assertNotIn(prompt, str(raised.exception))
        self.assertNotIn(credential, str(raised.exception))
        self.assertNotIn("provider body", str(raised.exception))
        self.assertEqual(oversized.read_limit, 9)
        self.assertEqual(len(opener.calls), 1)


if __name__ == "__main__":
    unittest.main()
