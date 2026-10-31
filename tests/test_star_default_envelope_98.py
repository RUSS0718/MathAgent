"""The unmetered client envelope retains the pre-#98 public key set."""

import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from llm_response import public_attempt
from showcase.g2_campaign import run_g2_campaign


class DefaultEnvelopeContractTest(unittest.TestCase):
    def test_unmetered_success_keeps_baseline_attempt_keys(self):
        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
                        "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

        with (patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}),
              patch("llm_client.requests.post", return_value=Reply())):
            response = InternChatClient(timeout=2, retry=1).chat_response(
                [{"role": "user", "content": "offline"}])
        self.assertEqual({"attempts", "content", "finish_reason", "model", "usage"}, set(response))
        self.assertEqual({
            "api_host", "attempt_id", "attempt_index", "attempts_configured", "cached_tokens",
            "completion_seconds", "completion_tokens", "content_bytes", "content_chars",
            "duration_seconds", "effective_timeout_seconds", "event_count", "finish_reason",
            "first_byte_seconds", "first_content_seconds", "first_event_seconds",
            "first_reasoning_seconds", "has_reasoning_content", "http_status", "logical_call_id",
            "logical_call_index", "max_tokens", "message_count", "message_roles", "messages_sha256",
            "prompt_tokens", "provider_stream", "reasoning_chars", "reasoning_content_chars",
            "reasoning_mode", "reasoning_tokens", "request_model_id", "request_purpose",
            "request_sequence", "requests_stream", "requests_timeout_seconds",
            "response_content_chars", "response_headers_seconds", "response_id", "response_model_id",
            "retry_limit", "started_at_utc", "status", "temperature", "thinking_mode",
            "timeout_seconds", "total_tokens",
        }, set(response["attempts"][0]))


    def test_g2_campaign_counts_not_submitted_as_legacy_error(self):
        class Reply:
            status_code = 200

            def __init__(self, value):
                self.value = value

            def get_json(self, silent=False):
                return self.value

        class Workspace:
            def __init__(self):
                self.index = 0

            def post(self, path, **_kwargs):
                if path == "/api/new_chat":
                    return Reply({"new_session_id": "session"})
                self.index += 1
                return Reply({"job_id": f"run-{self.index}"})

            def get(self, path):
                if path == "/api/check_auth":
                    return Reply({"csrf_token": "offline"})
                run_id = f"run-{self.index}"
                if path.endswith("/report"):
                    attempt = public_attempt({"attempt_id": "attempt-1", "attempt_index": 1,
                        "requested_model": "offline-model", "max_tokens": 32,
                        "status": "not_submitted", "error_category": "timeout"},
                        run_id=run_id, role="explore")
                    return Reply({"report": {"request_attempts": [attempt], "tool_summaries": []}})
                if path.endswith("/evidence"):
                    return Reply({})
                if path.startswith("/api/runs/"):
                    return Reply({"status": "FAILED", "error": {"category": "timeout"}})
                return Reply({"status": "failed"})

        report = run_g2_campaign(Workspace(), poll_interval_seconds=.001)
        self.assertTrue(report["attempts_complete"])
        self.assertEqual(6, report["http_attempt_count"])
        for row in report["runs"]:
            self.assertEqual("timeout", row["error_category"])
            self.assertEqual("error", row["attempts"][0]["status"])
            self.assertEqual("not_submitted", row["attempts"][0]["dispatch_status"])

if __name__ == "__main__":
    unittest.main()
