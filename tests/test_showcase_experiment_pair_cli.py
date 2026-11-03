from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from showcase import cli
from showcase.experiment_cli import InvocationAuthorization
from showcase.experiment_manifest import canonical_json
from showcase.experiment_pair import pair_manifest_digest, validate_pair_manifest


def _manifest(manifest_id: str) -> dict:
    sample_hash = hashlib.sha256(b"x+1=2\n").hexdigest()
    return {
        "schema_version": 1,
        "manifest_id": manifest_id,
        "evidence_kind": "scripted",
        "source_identity": {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        },
        "model": {
            "name": "intern-s2",
            "thinking_mode": True,
            "temperature": 0.2,
            "max_output_tokens": 512,
            "request_timeout_seconds": 60,
            "retry": 0,
            "solver_mode": "star_reference",
            "verification_mode": "required",
        },
        "transport": {
            "policy": "stream_first",
            "profile_set_fingerprint": "c" * 64,
            "calls": [{"call_id": "explore", "profile_fingerprint": "d" * 64}],
        },
        "samples": [
            {
                "id": "sample-01",
                "source_ref": "sample-01",
                "type": "simple",
                "input_sha256": sample_hash,
                "text_sha256": sample_hash,
            }
        ],
        "run_limits": {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 120,
        },
        "batch_limits": {
            "runs": 1,
            "logical_calls": 2,
            "http_attempts": 3,
            "tool_calls": 1,
            "charged_tokens": 4096,
            "wall_seconds": 120,
        },
        "stop_on": [
            "unknown_transport",
            "incomplete_or_unresolved_usage",
            "failure",
            "cancel",
            "hard_limit",
            "source_or_config_change",
            "ledger_or_binding_defect",
        ],
        "authorization": {"scope": manifest_id, "execution_authorized": False},
    }


def _pair(pair_id: str, report: dict | None = None) -> dict:
    features = {
        "skills": False,
        "reexplore_after_replan": False,
        "candidate_registry": False,
        "best_effort": False,
    }
    variant_features = dict(features, skills=True)
    report_hash = hashlib.sha256(canonical_json(report or {})).hexdigest()
    return {
        "schema_version": 1,
        "pair_id": pair_id,
        "readiness_report_sha256": report_hash,
        "factor": "skills",
        "baseline": {
            "run_id": f"{pair_id}-base",
            "manifest": _manifest(f"{pair_id}-base-manifest"),
            "features": features,
        },
        "variant": {
            "run_id": f"{pair_id}-variant",
            "manifest": _manifest(f"{pair_id}-variant-manifest"),
            "features": variant_features,
        },
    }


class ExperimentPairCliTest(unittest.TestCase):
    def _invoke(self, root: Path, pair: dict, report_path: Path) -> tuple[int, dict]:
        manifest_path = root / f"{pair['pair_id']}.json"
        manifest_path.write_text(json.dumps(pair), encoding="utf-8")
        argv = [
            "experiment",
            "pair",
            "--manifest",
            str(manifest_path),
            "--sha256",
            pair_manifest_digest(pair),
            "--authorize-sha256",
            pair_manifest_digest(pair),
            "--authorize-evidence-kind",
            "scripted",
            "--readiness-report",
            str(report_path),
            "--output-root",
            str(root / "runs"),
        ]
        factory = Mock(side_effect=AssertionError("Job adapter must not be created"))
        output = StringIO()
        with (
            redirect_stdout(output),
            patch(
                "showcase.cli.confirm_cli_invocation",
                return_value=InvocationAuthorization(
                    pair_manifest_digest(pair), "scripted", pair["pair_id"]
                ),
            ),
            patch("showcase.experiment_cli._create_public_job_adapter", factory),
        ):
            code = cli.main(argv)
        self.assertEqual(0, factory.call_count)
        return code, json.loads(output.getvalue())

    def test_cli_keeps_pair_not_run_for_missing_fail_unknown_and_single_run_pass(self) -> None:
        cases = (
            ("missing", None, "experiment_readiness_not_run"),
            ("failed", {"schema_version": 1, "issue_number": 127, "status": "FAIL"}, "experiment_readiness_not_passed"),
            ("unknown", {"schema_version": 1, "issue_number": 127, "status": "UNKNOWN"}, "experiment_readiness_not_passed"),
            ("not-run", {"schema_version": 1, "issue_number": 127, "status": "NOT_RUN"}, "experiment_readiness_not_passed"),
            (
                "mismatch",
                {"schema_version": 1, "issue_number": 127, "status": "PASS"},
                "experiment_readiness_mismatch",
            ),
            (
                "single-run-pass",
                {
                    "schema_version": 1,
                    "issue_number": 127,
                    "status": "PASS",
                    "run_id": "one-run",
                    "manifest_sha256": "a" * 64,
                    "verification_sha256": "b" * 64,
                },
                "experiment_readiness_aggregate_verifier_unavailable",
            ),
        )
        for label, report, expected_reason in cases:
            with self.subTest(readiness=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                pair = _pair(f"pair-{label}", report)
                if label == "mismatch":
                    pair["readiness_report_sha256"] = "e" * 64
                report_path = root / "readiness.json"
                if report is not None:
                    report_path.write_text(json.dumps(report), encoding="utf-8")
                code, result = self._invoke(root, pair, report_path)

                self.assertEqual(1, code)
                self.assertEqual("NOT_RUN", result["status"])
                self.assertEqual([], result["execution_order"])
                self.assertEqual("NOT_RUN", result["readiness"]["status"])
                self.assertEqual(expected_reason, result["stop_reason"])
                self.assertEqual(
                    ["aggregate_readiness_verifier_unavailable", "component_job_path_unavailable"],
                    result["execution_blockers"],
                )
                self.assertEqual("not_started", result["arms"]["baseline"]["status"])
                self.assertTrue((root / "runs" / "pairs" / pair["pair_id"] / "status.json").is_file())

                verify_output = StringIO()
                with redirect_stdout(verify_output):
                    verify_code = cli.main(
                        [
                            "experiment",
                            "pair-verify",
                            "--pair-id",
                            pair["pair_id"],
                            "--output-root",
                            str(root / "runs"),
                        ]
                    )
                self.assertEqual(1, verify_code)
                self.assertEqual("NOT_RUN", json.loads(verify_output.getvalue())["status"])

    def test_unregistered_model_factor_is_rejected(self) -> None:
        pair = _pair("pair-policy-factor")
        with self.assertRaisesRegex(ValueError, "experiment_pair_manifest_invalid"):
            validate_pair_manifest(dict(pair, factor="model.solver_mode"))

    def test_registered_feature_and_whole_review_invariant_are_enforced(self) -> None:
        pair = _pair("pair-valid")
        validated = validate_pair_manifest(pair)
        self.assertEqual("skills", validated["factor"])
        pair["variant"]["manifest"]["model"]["verification_mode"] = "off"
        with self.assertRaisesRegex(ValueError, "experiment_pair_manifest_invalid"):
            validate_pair_manifest(pair)
        pair = _pair("pair-model-difference")
        pair["variant"]["manifest"]["model"]["temperature"] = 0.7
        with self.assertRaisesRegex(ValueError, "experiment_pair_manifest_invalid"):
            validate_pair_manifest(pair)

    def test_public_cli_rejects_more_than_one_registered_feature_difference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair = _pair("pair-two-feature-diffs")
            pair["variant"]["features"]["candidate_registry"] = True
            digest = pair_manifest_digest(pair)
            manifest_path = root / "pair.json"
            manifest_path.write_text(json.dumps(pair), encoding="utf-8")
            readiness_path = root / "readiness.json"
            readiness_path.write_text("{}", encoding="utf-8")
            argv = [
                "experiment",
                "pair",
                "--manifest",
                str(manifest_path),
                "--sha256",
                digest,
                "--authorize-sha256",
                digest,
                "--authorize-evidence-kind",
                "scripted",
                "--readiness-report",
                str(readiness_path),
                "--output-root",
                str(root / "runs"),
            ]
            error_output = StringIO()
            adapter_factory = Mock(side_effect=AssertionError("Job adapter must not be created"))
            with (
                redirect_stderr(error_output),
                patch(
                    "showcase.cli.confirm_cli_invocation",
                    return_value=InvocationAuthorization(digest, "scripted", pair["pair_id"]),
                ),
                patch("showcase.experiment_cli._create_public_job_adapter", adapter_factory),
            ):
                code = cli.main(argv)

            self.assertEqual(1, code)
            self.assertEqual(
                "experiment_pair_manifest_invalid", json.loads(error_output.getvalue())["error"]
            )
            adapter_factory.assert_not_called()
            self.assertFalse((root / "runs" / "pairs" / pair["pair_id"]).exists())

    def test_pair_verify_demotes_runner_authored_pass_to_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pair = _pair("pair-verify")
            report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
            pair["readiness_report_sha256"] = hashlib.sha256(canonical_json(report)).hexdigest()
            pair_dir = root / "pairs" / pair["pair_id"]
            pair_dir.mkdir(parents=True)
            (pair_dir / "registration.json").write_bytes(canonical_json(pair))
            forged = {
                "schema_version": 1,
                "pair_id": pair["pair_id"],
                "pair_sha256": pair_manifest_digest(pair),
                "factor": pair["factor"],
                "status": "PASS",
                "phase": "completed",
                "execution_order": ["baseline", "variant"],
                "dispatch_count": 2,
                "readiness": {"status": "PASS"},
                "arms": {},
            }
            (pair_dir / "status.json").write_text(json.dumps(forged), encoding="utf-8")
            args = cli.build_parser().parse_args(
                ["experiment", "pair-verify", "--pair-id", pair["pair_id"], "--output-root", str(root)]
            )
            output = StringIO()
            with redirect_stdout(output):
                code = cli.run(args)

            self.assertEqual(1, code)
            self.assertEqual("UNKNOWN", json.loads(output.getvalue())["status"])


if __name__ == "__main__":
    unittest.main()
