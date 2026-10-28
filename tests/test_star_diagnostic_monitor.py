import tempfile
import unittest
from pathlib import Path

from showcase.star_diagnostic_monitor import monitor


class MonitorTest(unittest.TestCase):
    def test_missing_database_is_unavailable_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent"
            result = monitor(path)
            self.assertEqual("unavailable", result["status"])
            self.assertIsNone(result["charged_tokens"])
            self.assertFalse(path.exists())
