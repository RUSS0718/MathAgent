"""Wrapped SQLite failures retain safe codes, never exception message contents."""

import sqlite3
import unittest

from showcase.job_failure import record_job_failure


class JobFailureTest(unittest.TestCase):
    def test_sqlite_cause_code_is_logged_without_private_exception_message(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        try:
            try:
                connection.execute("SELECT * FROM private_answer_185")
            except sqlite3.Error as exc:
                raise RuntimeError("private_prompt_185") from exc
        except RuntimeError as error:
            with self.assertLogs("showcase.job_failure", level="ERROR") as captured:
                record_job_failure("job185", error)
        output = " ".join(captured.output)
        self.assertIn("sqlite_errorname=SQLITE_ERROR", output)
        self.assertNotIn("private_answer_185", output)
        self.assertNotIn("private_prompt_185", output)
