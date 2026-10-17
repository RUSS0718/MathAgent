from __future__ import annotations

import subprocess
import sys
import unittest


class ShowcaseCliContractTest(unittest.TestCase):
    def test_help_exposes_frontend_contract_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "showcase_cli.py", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode)
        for command in ("capabilities", "session", "job", "probe"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
