"""Real-loopback coverage for the opt-in restricted HTTP transport."""

from __future__ import annotations

import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import requests

from llm_client import ChatClientError, InternChatClient
from showcase.request_transport import response_events, strict_loopback_post

_COMPLETION = json.dumps(
    {
        "choices": [{"message": {"content": "local answer"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
).encode()


class _ReplyHandler(BaseHTTPRequestHandler):
    """Serve a configured response and record requests received by each test server."""

    def do_POST(self):
        self.server.requests.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        status, headers, body = self.server.reply
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        """Keep test server output quiet."""


class LoopbackTransportTest(unittest.TestCase):
    """Exercise the client opt-in against actual HTTP listeners on loopback."""

    def start_server(self, reply):
        """Start a test-only HTTP server bound to the IPv4 loopback address."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _ReplyHandler)
        server.daemon_threads = True
        server.requests = []
        server.reply = reply
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server, f"http://127.0.0.1:{server.server_port}/chat"

    def make_client(self, api_base, **kwargs):
        """Build a client with a placeholder credential and a local endpoint."""
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-test-key"}):
            client = InternChatClient(timeout=2, retry=1, **kwargs)
        client.api_base = api_base
        return client

    def test_loopback_opt_in_does_not_follow_redirect_to_another_loopback_server(self):
        """A redirect response cannot move the opt-in request to a second listener."""
        destination, destination_url = self.start_server((200, {}, _COMPLETION))
        redirect, redirect_url = self.start_server(
            (302, {"Location": destination_url}, b"redirect")
        )
        client = self.make_client(redirect_url, loopback_only=True)

        with self.assertRaises(ChatClientError):
            client.chat([{"role": "user", "content": "offline test"}], max_tokens=8)

        self.assertEqual(["/chat"], redirect.requests)
        self.assertEqual([], destination.requests)

    def test_loopback_opt_in_ignores_environment_proxy(self):
        """A configured environment proxy does not receive strict loopback traffic."""
        target, target_url = self.start_server((200, {}, _COMPLETION))
        proxy, proxy_url = self.start_server((200, {}, _COMPLETION))
        client = self.make_client(target_url, loopback_only=True)
        proxy_env = {
            "HTTP_PROXY": proxy_url,
            "http_proxy": proxy_url,
            "ALL_PROXY": proxy_url,
            "all_proxy": proxy_url,
            "NO_PROXY": "",
            "no_proxy": "",
        }

        with patch.dict(os.environ, proxy_env):
            answer = client.chat([{"role": "user", "content": "offline test"}], max_tokens=8)

        self.assertEqual("local answer", answer)
        self.assertEqual(["/chat"], target.requests)
        self.assertEqual([], proxy.requests)

    def test_deadline_reader_rejects_redirect_without_contacting_destination(self):
        destination, destination_url = self.start_server((200, {}, _COMPLETION))
        redirect, redirect_url = self.start_server((302, {"Location": destination_url}, b""))
        with self.assertRaises(requests.HTTPError):
            list(response_events(redirect_url, deadline=time.monotonic() + 3, timeout=2,
                                 loopback_only=True, data=b"{}"))
        self.assertEqual(["/chat"], redirect.requests)
        self.assertEqual([], destination.requests)

    def test_loopback_opt_in_rejects_other_hosts_before_network(self):
        with self.assertRaises(ValueError):
            strict_loopback_post("https://example.com", timeout=1)

    def test_strict_loopback_rejects_explicit_proxy_without_dispatch(self):
        target, target_url = self.start_server((200, {}, _COMPLETION))
        proxy, proxy_url = self.start_server((200, {}, _COMPLETION))
        with self.assertRaises(ValueError):
            strict_loopback_post(target_url, timeout=2, proxies={"http": proxy_url}, data=b"{}")
        self.assertEqual([], target.requests)
        self.assertEqual([], proxy.requests)

    def test_deadline_reader_consumes_complete_loopback_response(self):
        target, url = self.start_server((200, {}, _COMPLETION))
        events = list(response_events(url, deadline=time.monotonic() + 3, timeout=2,
                                      loopback_only=True, data=b"{}"))
        self.assertEqual(_COMPLETION, b"".join(v for k, v in events if k == "bytes"))
        self.assertEqual("complete", events[-1][0])
        self.assertEqual(["/chat"], target.requests)


if __name__ == "__main__":
    unittest.main()
