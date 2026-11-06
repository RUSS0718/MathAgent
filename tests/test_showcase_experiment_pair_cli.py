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
        model_path = root / "applied-model.json"
        model_path.write_text(json.dumps({"schema_version": 1, "model": pair["baseline"]["manifest"]["model"]}), encoding="utf-8")
        sample_root = root / "samples"
        sample_root.mkdir()
        (sample_root / "sample.txt").write_text("x+1=2\n", encoding="utf-8")
        (sample_root / "input.txt").write_text("x+1=2\n", encoding="utf-8")
        sample_map = root / "sample-map.json"
        sample_map.write_text(json.dumps({"sample-01": {"input": "input.txt", "text": "sample.txt"}}), encoding="utf-8")
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
            "--applied-config",
            str(model_path),
            "--sample-root",
            str(sample_root),
            "--sample-map",
            str(sample_map),
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
                "experiment_readiness_not_verified",
            ),
            (
                "wrong-issue",
                {
                    "schema_version": 1,
                    "issue_number": 126,
                    "status": "PASS",
                    "run_id": "one-run",
                    "manifest_sha256": "a" * 64,
                    "verification_sha256": "b" * 64,
                },
                "experiment_readiness_mismatch",
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
                    [expected_reason],
                    result["execution_blockers"],
                )
                self.assertEqual("not_started", result["arms"]["baseline"]["status"])
                self.assertTrue((root / "runs" / "pairs" / pair["pair_id"] / "status.json").is_file())

                verify_output = StringIO()
                with (
                    redirect_stdout(verify_output),
                    patch("showcase.experiment_cli._create_read_client", return_value=Mock()),
                ):
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
                "--applied-config",
                str(root / "applied-model.json"),
                "--sample-root",
                str(root / "samples"),
                "--sample-map",
                str(root / "sample-map.json"),
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
                "readiness": {
                    "issue_number": 127,
                    "status": "PASS",
                    "report_sha256": pair["readiness_report_sha256"],
                },
                "arms": {},
            }
            (pair_dir / "status.json").write_text(json.dumps(forged), encoding="utf-8")
            args = cli.build_parser().parse_args(
                ["experiment", "pair-verify", "--pair-id", pair["pair_id"], "--output-root", str(root)]
            )
            output = StringIO()
            with redirect_stdout(output), patch(
                "showcase.experiment_cli._create_read_client", return_value=Mock()
            ):
                code = cli.run(args)

            self.assertEqual(1, code)
            self.assertEqual("UNKNOWN", json.loads(output.getvalue())["status"])

    def test_pair_verify_reconciles_each_saved_arm_and_rejects_tampered_sample_rows(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_pair_verification import _sample_outcome, verify_experiment_pair

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
            pair = _pair("pair-independent-verify", report)
            pair_dir = root / "pairs" / pair["pair_id"]
            pair_dir.mkdir(parents=True)
            (pair_dir / "registration.json").write_bytes(canonical_json(pair))
            arms = {}
            for name in ("baseline", "variant"):
                arm = pair[name]
                run_id = arm["run_id"]
                run_dir = root / run_id
                (run_dir / "evidence").mkdir(parents=True)
                job_id = f"job-{name}"
                evidence = {
                    "sample_id": "sample-01",
                    "job_id": job_id,
                    "job_status": "succeeded",
                    "transport_identity": {"policy": "stream_first", "calls": []},
                    "budget": {"tool_calls": 0, "logical_calls": 1},
                    "whole_review": {"accepted": True, "binding": "same_artifact"},
                    "semantics": {"binding": "same_artifact"},
                    "request_attempts": [],
                }
                (run_dir / "evidence" / "sample.json").write_bytes(canonical_json(evidence))
                run_status = {
                    "run_id": run_id,
                    "manifest_sha256": manifest_digest(arm["manifest"]),
                    "phase": "completed",
                    "completed": 1,
                    "completed_samples": [0],
                    "total": 1,
                    "run_records": [{"sample_id": "sample-01", "job_id": job_id}],
                }
                (run_dir / "status.json").write_bytes(canonical_json(run_status))
                (run_dir / "manifest.json").write_bytes(canonical_json(arm["manifest"]))
                (run_dir / "manifest.sha256").write_text(
                    manifest_digest(arm["manifest"]), encoding="ascii"
                )
                arms[name] = {
                    "run_id": run_id,
                    "manifest_sha256": manifest_digest(arm["manifest"]),
                    "status": "completed",
                    "execution_phase": "completed",
                    "verification_status": "PASS",
                    "job_ids": [job_id],
                    "applied_component_config": arm["features"],
                    "sample_outcomes": [_sample_outcome(evidence, "PASS")],
                }
            state = {
                "pair_id": pair["pair_id"],
                "pair_sha256": pair_manifest_digest(pair),
                "factor": pair["factor"],
                "status": "PASS",
                "phase": "completed",
                "execution_order": ["baseline", "variant"],
                "dispatch_count": 2,
                "completed": 2,
                "readiness": {
                    "issue_number": 127,
                    "status": "PASS",
                    "report_sha256": pair["readiness_report_sha256"],
                },
                "arms": arms,
            }
            (pair_dir / "status.json").write_bytes(canonical_json(state))
            reader = Mock()
            reader.request.return_value = {}
            with (
                patch("showcase.experiment_verification.verify_experiment_run",
                      return_value={"status": "PASS"}),
                patch("showcase.experiment_pair_verification.verify_pair_arm_component_config",
                      side_effect=lambda _reader, _job, pair_value, arm_name: {
                          "status": "PASS",
                          "applied_component_config": pair_value[arm_name]["features"],
                      }),
            ):
                verified = verify_experiment_pair(
                    pair["pair_id"], output_root=root, read_client=reader
                )
                self.assertEqual("PASS", verified["status"], verified)
                self.assertEqual(
                    {"factor": "skills", "baseline": False, "variant": True},
                    verified["config_difference"],
                )
                state["arms"]["variant"]["sample_outcomes"][0]["job_status"] = "failed"
                (pair_dir / "status.json").write_bytes(canonical_json(state))
                tampered = verify_experiment_pair(
                    pair["pair_id"], output_root=root, read_client=reader
                )
                state["arms"]["variant"]["sample_outcomes"][0]["job_status"] = "succeeded"
                state["arms"]["variant"]["status"] = "stopped"
                (pair_dir / "status.json").write_bytes(canonical_json(state))
                inconsistent = verify_experiment_pair(
                    pair["pair_id"], output_root=root, read_client=reader
                )
            self.assertEqual("FAIL", tampered["status"])
            self.assertEqual("paired_arm_record_mismatch", tampered["reason"])
            self.assertEqual("FAIL", inconsistent["status"])
            self.assertEqual("paired_arm_record_mismatch", inconsistent["reason"])

    def test_pair_dispatches_arms_serially_only_with_independent_readiness(self) -> None:
        from showcase.experiment_pair import run_pair

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {
                "schema_version": 1,
                "issue_number": 127,
                "status": "PASS",
                "independent_verifier": "PASS",
                "manifest_sha256": "a" * 64,
                "verification_sha256": "b" * 64,
            }
            pair = _pair("pair-dispatch", report)
            order: list[str] = []

            def run_arm(manifest, *, expected_sha256, run_id, output_root, context):
                del manifest, expected_sha256, output_root, context
                order.append(run_id)
                return {
                    "run_id": run_id,
                    "phase": "completed",
                    "status": "COMPLETED",
                    "completed": 1,
                    "total": 1,
                    "stop_reason": None,
                    "run_records": [{"job_id": f"job-{run_id}"}],
                }

            with patch("showcase.experiment_pair.run_batch", side_effect=run_arm):
                result = run_pair(
                    pair,
                    expected_sha256=pair_manifest_digest(pair),
                    readiness_report=report,
                    output_root=root / "runs",
                    context={
                        "authorization": InvocationAuthorization(
                            pair_manifest_digest(pair), "scripted", pair["pair_id"]
                        ),
                        "readiness_verifier": lambda _report: {"status": "PASS"},
                        "pair_job_adapter_factory": lambda *_args: object(),
                        "pair_arm_verifier": lambda run_id, **_kwargs: {
                            "status": "PASS",
                            "applied_component_config": pair[
                                "baseline" if run_id == pair["baseline"]["run_id"] else "variant"
                            ]["features"],
                            "sample_outcomes": [{
                                "sample_id": "sample-01",
                                "job_id": f"job-{run_id}",
                                "status": "PASS",
                                "usage": {"logical_calls": 1, "tool_calls": 0},
                            }],
                        },
                    },
                )

            self.assertEqual([pair["baseline"]["run_id"], pair["variant"]["run_id"]], order)
            self.assertEqual("PASS", result["status"])
            self.assertEqual(["baseline", "variant"], result["execution_order"])
            self.assertEqual(2, result["dispatch_count"])
            self.assertEqual("completed", result["arms"]["baseline"]["status"])
            self.assertEqual("completed", result["arms"]["variant"]["status"])
            for name in ("baseline", "variant"):
                self.assertEqual(
                    [{
                        "sample_id": "sample-01",
                        "job_id": f"job-{pair[name]['run_id']}",
                        "status": "PASS",
                        "usage": {"logical_calls": 1, "tool_calls": 0},
                    }],
                    result["arms"][name]["sample_outcomes"],
                )

    def test_pair_cli_dispatches_frozen_arms_separately_and_persists_outcomes(self) -> None:
        from showcase.experiment_cli import execute_experiment_command

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
            pair = _pair("pair-cli-dispatch", report)
            pair_path = root / "pair.json"
            pair_path.write_bytes(canonical_json(pair))
            report_path = root / "readiness.json"
            report_path.write_bytes(canonical_json(report))
            adapter_order = []
            verifier_order = []
            outcome = {
                "sample_id": "sample-01",
                "job_id": "job-public",
                "status": "PASS",
                "usage": {"logical_calls": 1, "tool_calls": 0},
            }

            def adapter_factory(_pair, arm_name, _arm):
                adapter_order.append(arm_name)
                return object()

            def run_arm(_manifest, *, expected_sha256, run_id, output_root, context):
                del expected_sha256, output_root
                adapter = context["job_adapter_factory"]()
                self.assertIsNotNone(adapter)
                arm_name = "baseline" if run_id == pair["baseline"]["run_id"] else "variant"
                return {
                    "run_id": run_id,
                    "phase": "completed",
                    "completed": 1,
                    "total": 1,
                    "run_records": [{"sample_id": "sample-01", "job_id": f"job-{arm_name}"}],
                }

            def verify_arm(run_id, **_kwargs):
                arm_name = "baseline" if run_id == pair["baseline"]["run_id"] else "variant"
                verifier_order.append(arm_name)
                return {
                    "status": "PASS",
                    "applied_component_config": pair[arm_name]["features"],
                    "sample_outcomes": [dict(outcome, job_id=f"job-{arm_name}")],
                }

            args = cli.build_parser().parse_args([
                "experiment", "pair", "--manifest", str(pair_path),
                "--sha256", pair_manifest_digest(pair),
                "--authorize-sha256", pair_manifest_digest(pair),
                "--authorize-evidence-kind", "scripted",
                "--readiness-report", str(report_path),
                "--output-root", str(root / "runs"),
                "--applied-config", str(root / "unused-model.json"),
                "--sample-root", str(root / "unused-samples"),
                "--sample-map", str(root / "unused-map.json"),
            ])
            with patch("showcase.experiment_pair.run_batch", side_effect=run_arm):
                result, exit_code = execute_experiment_command(
                    args,
                    context={
                        "authorization": InvocationAuthorization(
                            pair_manifest_digest(pair), "scripted", pair["pair_id"]
                        ),
                        "readiness_verifier": lambda _report: {"status": "PASS"},
                        "pair_runtime_preparer": lambda: None,
                        "pair_job_adapter_factory": adapter_factory,
                        "pair_arm_verifier": verify_arm,
                    },
                )

            self.assertEqual(0, exit_code)
            self.assertEqual(["baseline", "variant"], adapter_order)
            self.assertEqual(["baseline", "variant"], verifier_order)
            persisted = json.loads(
                (root / "runs" / "pairs" / pair["pair_id"] / "status.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual("PASS", persisted["status"])
            self.assertEqual(
                [dict(outcome, job_id="job-baseline")],
                persisted["arms"]["baseline"]["sample_outcomes"],
            )
            self.assertEqual(
                [dict(outcome, job_id="job-variant")],
                persisted["arms"]["variant"]["sample_outcomes"],
            )

    def test_cli_readiness_verifier_uses_service_preflight_without_job_dispatch(self) -> None:
        from showcase.experiment_cli import _verify_pair_readiness

        report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
        pair = _pair("pair-cli-readiness", report)

        class Client:
            def bootstrap(self):
                return {"csrf_token": "fixture"}

            def request(self, method, path, *, payload):
                self.assertion = (method, path, payload)
                return {"status": "PASS"}

        client = Client()
        args = type("Args", (), {
            "base_url": "http://127.0.0.1:8090",
            "cookie_file": Path("fixture.cookies"),
            "timeout": 10,
        })()
        result = _verify_pair_readiness(args, {"showcase_client": client}, pair, report)

        self.assertEqual({"status": "PASS"}, result)
        method, path, payload = client.assertion
        self.assertEqual("POST", method)
        self.assertEqual(
            f"/api/experiments/pairs/{pair['pair_id']}/readiness", path
        )
        self.assertEqual(pair_manifest_digest(pair), payload["pair_sha256"])
        self.assertEqual(report, payload["readiness_report"])
    def test_pair_does_not_complete_when_execution_stops_even_if_arm_verifier_claims_pass(self) -> None:
        from showcase.experiment_pair import run_pair

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
            pair = _pair("pair-stopped", report)
            order: list[str] = []

            def run_arm(_manifest, *, run_id, **_kwargs):
                order.append(run_id)
                return {"phase": "stopped", "stop_reason": "hard_limit", "run_records": []}

            with patch("showcase.experiment_pair.run_batch", side_effect=run_arm):
                result = run_pair(
                    pair,
                    expected_sha256=pair_manifest_digest(pair),
                    readiness_report=report,
                    output_root=root / "runs",
                    context={
                        "authorization": InvocationAuthorization(
                            pair_manifest_digest(pair), "scripted", pair["pair_id"]
                        ),
                        "readiness_verifier": lambda _report: {"status": "PASS"},
                        "pair_job_adapter_factory": lambda *_args: object(),
                        "pair_arm_verifier": lambda _run_id, **_kwargs: {
                            "status": "PASS",
                            "applied_component_config": pair["baseline"]["features"],
                        },
                    },
                )

            self.assertEqual([pair["baseline"]["run_id"]], order)
            self.assertNotEqual("PASS", result["status"])
            self.assertEqual("NOT_RUN", result["arms"]["variant"]["verification_status"])

    def test_second_arm_exception_does_not_reuse_baseline_result(self) -> None:
        from showcase.experiment_pair import run_pair

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
            pair = _pair("pair-variant-error", report)
            baseline_result = {
                "run_id": pair["baseline"]["run_id"],
                "phase": "completed",
                "completed": 1,
                "total": 1,
                "run_records": [{"job_id": "baseline-job"}],
            }
            with patch(
                "showcase.experiment_pair.run_batch",
                side_effect=[baseline_result, RuntimeError("variant failed")],
            ):
                result = run_pair(
                    pair,
                    expected_sha256=pair_manifest_digest(pair),
                    readiness_report=report,
                    output_root=root / "runs",
                    context={
                        "authorization": InvocationAuthorization(
                            pair_manifest_digest(pair), "scripted", pair["pair_id"]
                        ),
                        "readiness_verifier": lambda _report: {"status": "PASS"},
                        "pair_job_adapter_factory": lambda *_args: object(),
                        "pair_arm_verifier": lambda _run_id, **_kwargs: {
                            "status": "PASS",
                            "applied_component_config": pair["baseline"]["features"],
                        },
                    },
                )

            variant = result["arms"]["variant"]
            self.assertEqual("unknown", variant["execution_phase"])
            self.assertEqual([], variant["job_ids"])
            self.assertEqual("UNKNOWN", variant["verification_status"])


if __name__ == "__main__":
    unittest.main()
