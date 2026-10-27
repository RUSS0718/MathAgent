"""Live Intern requests stay pinned to the documented HTTPS origin."""

import os
import unittest
from unittest.mock import patch

import requests

from showcase.request_transport import response_events, strict_provider_post


class Response:
    def __init__(self, status_code):
        self.status_code = status_code
        self.closed = False

    def close(self):
        self.closed = True


class Session:
    def __init__(self, response):
        self.response = response
        self.trust_env = True
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class StrictProviderPostTest(unittest.TestCase):
    def test_uses_direct_tls_session_and_disables_redirects(self):
        response = Response(200)
        session = Session(response)
        with patch("requests.Session", return_value=session):
            result = strict_provider_post(
                "https://chat.intern-ai.org.cn/api/v1/chat/completions",
                timeout=10,
                headers={"Authorization": "Bearer redacted"},
            )

        self.assertIs(response, result)
        self.assertFalse(session.trust_env)
        self.assertEqual(
            {"allow_redirects": False, "timeout": 10,
             "headers": {"Authorization": "Bearer redacted"}},
            session.calls[0][1],
        )

    def test_rejects_redirect_without_following_it(self):
        response = Response(307)
        session = Session(response)
        with patch("requests.Session", return_value=session):
            with self.assertRaises(requests.HTTPError) as caught:
                strict_provider_post(
                    "https://chat.intern-ai.org.cn/api/v1/chat/completions"
                )

        self.assertIs(response, caught.exception.response)
        self.assertTrue(response.closed)
        self.assertEqual(1, len(session.calls))

    def test_rejects_noncanonical_endpoint_before_opening_a_session(self):
        with patch("requests.Session") as make_session:
            for url in (
                "http://chat.intern-ai.org.cn/api/v1/chat/completions",
                "https://attacker.example/api/v1/chat/completions",
                "https://chat.intern-ai.org.cn/other",
                "https://user@chat.intern-ai.org.cn/api/v1/chat/completions",
                "https://chat.intern-ai.org.cn/api/v1/chat/completions?redirect=1",
            ):
                with self.subTest(url=url), self.assertRaises(ValueError):
                    strict_provider_post(url)

        make_session.assert_not_called()

    def test_response_reader_uses_strict_provider_policy(self):
        response = Response(200)
        response.iter_content = lambda chunk_size: iter((b"{}",))
        session = Session(response)
        with patch("requests.Session", return_value=session):
            events = list(response_events(
                "https://chat.intern-ai.org.cn/api/v1/chat/completions",
                deadline=10**10,
                timeout=5,
                provider_endpoint_only=True,
            ))

        self.assertEqual(["headers", "bytes", "complete"], [kind for kind, _ in events])
        self.assertFalse(session.trust_env)
        self.assertFalse(session.calls[0][1]["allow_redirects"])

    def test_response_reader_rejects_conflicting_transport_policies(self):
        events = response_events(
            "https://chat.intern-ai.org.cn/api/v1/chat/completions",
            deadline=10**10,
            timeout=5,
            loopback_only=True,
            provider_endpoint_only=True,
        )
        with self.assertRaisesRegex(ValueError, "conflicting_transport_policy"):
            list(events)

    def test_unmetered_client_path_uses_the_strict_provider_transport(self):
        from llm_client import InternChatClient

        environment = {
            "INTERN_API_KEY": "test-only-not-a-real-key",
            "INTERN_API_BASE": "https://chat.intern-ai.org.cn/api/v1/chat/completions",
            "INTERN_MODEL": "intern-s2",
        }
        response = Response(200)
        response.raise_for_status = lambda: None
        response.json = lambda: {
            "choices": [{"message": {"content": "safe response"}, "finish_reason": "stop"}],
            "model": "intern-s2",
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }
        with patch.dict(os.environ, environment), patch(
            "showcase.request_transport.strict_provider_post", return_value=response
        ) as post:
            client = InternChatClient(
                timeout=180, retry=3, thinking_mode=True, provider_endpoint_only=True
            )
            result = client.chat([{"role": "user", "content": "fixture"}], max_tokens=8)

        self.assertEqual("safe response", result)
        post.assert_called_once()
        self.assertEqual(environment["INTERN_API_BASE"], post.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
