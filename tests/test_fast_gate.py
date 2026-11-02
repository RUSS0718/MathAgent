"""Fast gate stops at the first failed public check."""

import unittest
from unittest.mock import Mock, patch

from scripts import check_fast


class FastGateTest(unittest.TestCase):
    def test_failed_baseline_prevents_following_checks(self):
        with patch.object(
            check_fast.subprocess,
            "run",
            side_effect=[
                Mock(returncode=0),
                Mock(returncode=7),
            ],
        ) as run:
            self.assertEqual(7, check_fast.main())
        self.assertEqual(2, run.call_count)

    def test_success_runs_entry_and_demo_cli_contracts(self):
        with patch.object(check_fast.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(0, check_fast.main())
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn([check_fast.sys.executable, "demo_server.py", "--help"], commands)
        self.assertIn([check_fast.sys.executable, "showcase_server.py", "--help"], commands)
