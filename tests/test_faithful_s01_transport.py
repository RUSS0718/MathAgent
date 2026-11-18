"""Public response transport behavior for the Faithful S01 stream policy."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

import requests

from showcase.request_transport import response_events


class VirtualClock:
    def __init__(self, initial: float):
        self.value = initial

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FaithfulTransportTimeoutTest(unittest.TestCase):
    def test_idle_expires_before_a_queued_heartbeat_backlog_is_drained(self):
        clock = VirtualClock(initial=100)
        start_flood = threading.Event()
        reader_started = threading.Event()
        backlog_queued = threading.Event()
        stop_reader = threading.Event()
        response_closed = threading.Event()
        self.addCleanup(stop_reader.set)

        class HeartbeatResponse:
            status_code = 200

            def iter_content(self, chunk_size=1):
                yield b"data: first effective delta\n\n"
                reader_started.set()
                start_flood.wait()
                frames = (
                    b": heartbeat\n\n",
                    b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n',
                    b'data: {"choices":[],"usage":{"total_tokens":1}}\n\n',
                    b'id: duplicate\ndata: {"choices":[{"delta":{"content":"repeat"}}]}\n\n',
                ) * 4
                for frame in frames:
                    clock.advance(2)
                    yield frame
                backlog_queued.set()
                stop_reader.wait()

            def close(self):
                response_closed.set()

        response = HeartbeatResponse()
        events = response_events(
            "http://127.0.0.1:1/chat/completions",
            deadline=clock() + 1000,
            clock=clock,
            timeout=(1, 1000),
            effective_idle_deadline=lambda: 130,
        )
        with patch("showcase.request_transport.requests.post", return_value=response):
            self.assertEqual("headers", next(events)[0])
            first_data = next(events)
            self.assertEqual(("bytes", b"data: first effective delta\n\n"), first_data)
            self.assertTrue(reader_started.wait(1))
            start_flood.set()
            self.assertTrue(backlog_queued.wait(1))
            self.assertGreaterEqual(clock(), 130)
            with self.assertRaises(requests.ReadTimeout) as caught:
                next(events)
            stop_reader.set()
            self.assertTrue(response_closed.wait(1))

        self.assertIn("effective_idle_deadline_exceeded", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
