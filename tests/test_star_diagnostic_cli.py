import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from showcase.star_diagnostic_registration import ROOT
from tests.star_diagnostic_support import plan


class DiagnosticCliTest(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/run_star_diagnostic_102.py"), *args],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_cli_freeze_dry_run_fake_monitor_are_explicit_and_redacted(self):
        root = ROOT / "artifacts"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            work = Path(directory)
            file = work / "plan.json"
            value = plan()
            value["registration_id"] = uuid4().hex
            file.write_text(json.dumps(value), encoding="utf-8")
            args = ("--registration", str(work / "registration"))
            frozen = self.call("freeze", "--plan", str(file), *args)
            self.assertEqual(0, frozen.returncode, frozen.stderr)
            sha = json.loads(frozen.stdout)["sha256"]
            dry = self.call("dry-run", *args)
            self.assertEqual(0, dry.returncode, dry.stderr)
            self.assertEqual(33, json.loads(dry.stdout)["p_inclusion"]["remaining_ceiling"])
            fake = self.call("fake-run", *args, "--archive", str(work / "archive"), "--sha256", sha)
            self.assertEqual(0, fake.returncode, fake.stderr)
            observed = self.call("monitor", "--archive", str(work / "archive"))
            self.assertEqual("completed", json.loads(observed.stdout)["status"])
            self.assertNotIn("Give a complete proof", frozen.stdout + fake.stdout + observed.stdout)
            self.assertNotIn("run-live", self.call("--help").stdout)

    def test_two_processes_cannot_consume_same_registration_in_different_archives(self):
        root = ROOT / "artifacts"
        root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as directory:
            work = Path(directory)
            value = plan()
            value["registration_id"] = uuid4().hex
            file = work / "plan.json"
            file.write_text(json.dumps(value), encoding="utf-8")
            args = ("--registration", str(work / "registration"))
            frozen = self.call("freeze", "--plan", str(file), *args)
            self.assertEqual(0, frozen.returncode, frozen.stderr)
            sha = json.loads(frozen.stdout)["sha256"]
            def start(index):
                return self.call("fake-run", *args, "--archive", str(work / f"archive-{index}"), "--sha256", sha)
            with ThreadPoolExecutor(2) as pool:
                results = list(pool.map(start, range(2)))
            self.assertCountEqual([0, 2], [r.returncode for r in results])
            statuses = [json.loads(r.stdout)["status"] for r in results]
            self.assertCountEqual(["completed", "rejected"], statuses)

    def test_paths_and_digest_fail_closed_without_echoing_private_input(self):
        bad = self.call("freeze", "--registration", str(ROOT / "unignored"), "--plan", "secret-credential")
        self.assertEqual(2, bad.returncode)
        self.assertNotIn("secret-credential", bad.stdout + bad.stderr)
