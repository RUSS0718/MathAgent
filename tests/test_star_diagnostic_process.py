import os
import unittest

from showcase.star_diagnostic_process import observe_process, process_identity


class ProcessTest(unittest.TestCase):
    def test_creation_time_distinguishes_reused_pid_and_missing_process(self):
        identity = process_identity()
        self.assertEqual(os.getpid(), identity["pid"])
        self.assertEqual("running", observe_process(identity))
        self.assertEqual("reused", observe_process({**identity, "process_created_at": "wrong"}))
        self.assertEqual("exited", observe_process(dict(pid=2147483647, process_created_at=0)))
