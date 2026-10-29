"""Early timed waits must not cancel a late, metered response reader."""

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from showcase import processing_deadline
from tests import test_star_job_parse_deadline_98 as job_parse_tests
from tests.star_product_support import StarJobFixture


class ProcessingEarlyWakeTest(StarJobFixture, unittest.TestCase):
    def test_early_wait_keeps_late_stream_usage_reconciliation(self):
        early_returns = []

        class EarlyEvent(threading.Event):
            def wait(self, timeout=None):
                # Simulate a timed wait expiring before the monotonic deadline.
                # Only the processing handoff event is replaced, not the parser
                # release, HTTP transport, or the public observation timeout.
                if timeout is not None and timeout > .2:
                    result = super().wait(timeout - .2)
                    if not result:
                        early_returns.append(timeout)
                    return result
                return super().wait(timeout)

        isolated_threading = SimpleNamespace(
            Event=EarlyEvent, Lock=threading.Lock, Thread=threading.Thread,
        )
        with patch.object(processing_deadline, "threading", isolated_threading):
            job_parse_tests.JobParseDeadlineTest.test_blocked_stream_event_finishes_job_before_late_parser_release(self)
        self.assertTrue(early_returns, "the early timeout path was not exercised")
