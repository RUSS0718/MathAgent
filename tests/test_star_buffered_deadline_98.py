"""Issue #98: an already-buffered transport result must settle exactly once."""

import threading
import time
import unittest
from unittest.mock import patch

import requests

from showcase.request_transport import response_events


class BufferedDeadlineRaceTest(unittest.TestCase):
    def test_buffered_slow_late_callback_does_not_delay_deadline(self):
        reader_finished = threading.Event()
        callback_started = threading.Event()
        callback_finished = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        calls = []

        class Reply:
            def iter_content(self, chunk_size=1):
                yield b"x"

            def close(self):
                reader_finished.set()

        def slow_callback(_response, body, _headers, _elapsed, complete):
            calls.append((body, complete))
            callback_started.set()
            release.wait(1)
            callback_finished.set()

        deadline = time.monotonic() + .12
        with patch("showcase.request_transport.requests.post", return_value=Reply()):
            events = response_events("http://127.0.0.1", deadline=deadline, timeout=2,
                                     on_late_response=slow_callback)
            self.assertEqual("headers", next(events)[0])
            self.assertTrue(reader_finished.wait(1))
            time.sleep(max(0, deadline - time.monotonic()) + .02)
            started = time.monotonic()
            with self.assertRaises(requests.ReadTimeout):
                next(events)
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, .3, "slow settlement must never delay timeout")
            self.assertTrue(callback_started.wait(1))
            self.assertFalse(callback_finished.is_set())
            release.set()
            self.assertTrue(callback_finished.wait(1))
            with self.assertRaises(StopIteration):
                next(events)
        self.assertEqual([(b"x", True)], calls)

    def test_late_callback_exception_does_not_repeat_or_escape(self):
        reader_waiting, release, reader_finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        calls = []

        class Reply:
            def iter_content(self, chunk_size=1):
                reader_waiting.set()
                if not release.wait(2):
                    raise AssertionError("reader not released")
                yield b"x"

            def close(self):
                reader_finished.set()

        def failing_callback(_response, body, _headers, _elapsed, complete):
            calls.append((body, complete))
            raise RuntimeError("simulated settlement failure")

        deadline = time.monotonic() + .1
        with patch("showcase.request_transport.requests.post", return_value=Reply()):
            events = response_events("http://127.0.0.1", deadline=deadline, timeout=2,
                                     on_late_response=failing_callback)
            self.assertEqual("headers", next(events)[0])
            self.assertTrue(reader_waiting.wait(1))
            with self.assertRaises(requests.ReadTimeout):
                next(events)
            release.set()
            self.assertTrue(reader_finished.wait(1))
            with self.assertRaises(StopIteration):
                next(events)
        self.assertEqual([(b"x", True)], calls)
    def test_finished_reader_is_settled_when_consumer_crosses_deadline(self):
        reader_finished = threading.Event()
        callback_finished = threading.Event()
        callbacks = []

        class Reply:
            status_code = 200

            def iter_content(self, chunk_size=1):
                yield b"x"

            def close(self):
                reader_finished.set()

        def callback(_response, body, _headers, _elapsed, complete):
            callbacks.append((body, complete))
            callback_finished.set()

        deadline = time.monotonic() + .15
        with patch("showcase.request_transport.requests.post", return_value=Reply()):
            events = response_events("http://127.0.0.1", deadline=deadline, timeout=2,
                on_late_response=callback)
            self.assertEqual("headers", next(events)[0])
            self.assertTrue(reader_finished.wait(1))
            time.sleep(max(0, deadline - time.monotonic()) + .03)
            with self.assertRaises(requests.ReadTimeout):
                next(events)
        self.assertTrue(callback_finished.wait(1))
        self.assertEqual([(b"x", True)], callbacks)


if __name__ == "__main__":
    unittest.main()
