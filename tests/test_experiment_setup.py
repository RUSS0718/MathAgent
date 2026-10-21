"""Public seam: subprocess CLI stdout JSON and exit code, as agreed for this slice."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_experiment_setup.py"


class ExperimentSetupCLITests(unittest.TestCase):
    def campaign(self) -> dict:
        return json.loads((ROOT / "experiments" / "campaign.json").read_text(encoding="utf-8"))

    def check_campaign(
        self, config: dict, *, write_output: bool = False
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="setup-contract-", dir=artifacts) as temporary:
            path = Path(temporary) / "campaign.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "--offline", "--config", str(path)]
            if write_output:
                command.extend(["--output", str(Path(temporary) / "report.json")])
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        self.assertTrue(result.stdout.strip(), "CLI must emit a JSON result")
        return result, json.loads(result.stdout)

    def test_network_enablement_is_rejected(self) -> None:
        config = self.campaign()
        config["allow_network"] = True
        result, report = self.check_campaign(config)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report["category"], "network_not_allowed")
        self.assertEqual(report["network_requests"], 0)
        self.assertTrue(report["planned_not_implemented"])
        self.assertEqual(result.stderr, "")

    def test_experiments_require_the_fixed_profile_and_model(self) -> None:
        for field, value in (("profile", "official"), ("model", "intern-latest")):
            with self.subTest(field=field):
                config = self.campaign()
                config[field] = value
                result, report = self.check_campaign(config)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(report["category"], "experiment_identity_invalid")

    def test_caps_are_finite_positive_and_offline_stays_zero(self) -> None:
        cases = (
            ("calibration", "accounted_plus_reserved_tokens_limit", float("inf")),
            ("api_probe", "max_tokens_per_attempt", 0),
            ("api_probe", "max_tokens_per_attempt", 512.5),
            ("calibration", "independent_problems", 12.5),
            ("calibration", "max_generation_attempts", 0.5),
            ("offline", "max_generation_attempts", 1),
        )
        for stage, field, value in cases:
            with self.subTest(stage=stage, field=field):
                config = self.campaign()
                config["stages"][stage][field] = value
                result, report = self.check_campaign(config)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(report["category"], "budget_invalid")

    def test_direction_documents_must_exist_inside_the_repository(self) -> None:
        for path in ("../outside-secret-sentinel.md", "docs/prd/missing-contract.md"):
            with self.subTest(path=path):
                config = self.campaign()
                config["directions"][0]["prd"] = path
                result, report = self.check_campaign(config)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(report["category"], "direction_document_invalid")
                self.assertNotIn("outside-secret-sentinel", result.stdout + result.stderr)

    def test_baseline_requires_a_real_full_commit(self) -> None:
        for commit in ("HEAD", "0" * 40):
            with self.subTest(commit=commit):
                config = self.campaign()
                config["base_commit"] = commit
                result, report = self.check_campaign(config)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(report["category"], "baseline_invalid")

    def test_valid_setup_reports_verified_baseline_without_claiming_live_readiness(self) -> None:
        result, report = self.check_campaign(self.campaign(), write_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["base_commit"], "5b0e1912e1cc82d7ab1ecd3bcb8ea5ffc10933ae")
        self.assertRegex(report["current_commit"], r"^[0-9a-f]{40}$")
        if report["branch"] is not None:
            self.assertIsInstance(report["branch"], str)
            self.assertTrue(report["branch"])
        self.assertEqual(report["counts"], {
            "directions": 5, "direction_documents": 15,
            "disabled_features": 5, "protected_files": 11,
        })
        self.assertEqual(report["network_requests"], 0)
        self.assertTrue(report["planned_not_implemented"])
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
