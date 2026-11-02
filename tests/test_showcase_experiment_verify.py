from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from showcase.cli import build_parser, run
from showcase.experiment_manifest import canonical_json, manifest_digest
from showcase.run_budget import public_solver_call_id


class ReadOnlyShowcaseClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method != "GET":
            raise AssertionError(f"verification attempted {method} {path}")
        for suffix, value in self.responses.items():
            if path.endswith(suffix):
                return value
        raise AssertionError(f"unexpected verification read: {path}")


def manifest_fixture():
    return {
        "schema_version": 1,
        "manifest_id": "manifest-1",
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
            "verification_mode": "auto",
        },
        "transport": {
            "policy": "legacy",
            "transport": "nonstream",
            "profile_set_fingerprint": "c" * 64,
            "calls": [
                {
                    "call_id": "whole_solution_verifier",
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "capability_limit": "verified_stream_profiles_empty",
                }
            ],
        },
        "samples": [
            {
                "id": "sample-1",
                "source_ref": "fixture-1",
                "type": "simple",
                "input_sha256": "d" * 64,
                "text_sha256": "e" * 64,
            }
        ],
        "run_limits": {
            "max_model_calls": 2,
            "max_http_attempts": 2,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 60,
        },
        "batch_limits": {
            "runs": 1,
            "logical_calls": 2,
            "http_attempts": 2,
            "tool_calls": 1,
            "charged_tokens": 4096,
            "wall_seconds": 60,
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
        "authorization": {"scope": "offline-fixture", "execution_authorized": False},
    }


def successful_fixture():
    manifest = manifest_fixture()
    digest = manifest_digest(manifest)
    answer = "private answer text"
    answer_hash = hashlib.sha256(answer.encode("utf-8")).hexdigest()
    artifact = {
        "schema": "public-answer-nfc-lf-v1",
        "sha256": answer_hash,
        "id": f"answer:{answer_hash}",
    }
    review_source = {
        "run_id": "job-1",
        "call_id": "review-call-internal",
        "plan_version": 2,
        "attempt_index": 1,
        "state_revision": 9,
        "origin": "whole_solution_verifier",
        "candidate_version": 1,
    }
    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    attempt = {
        "attempt_id": "attempt-1",
        "logical_call_id": "logical-review-1",
        "solver_call_id": public_solver_call_id("job-1", "review-call-internal"),
        "run_id": "job-1",
        "role": "whole_solution_verifier",
        "attempt_index": 1,
        "dispatch_status": "transport_observed",
        "requested_model": "intern-s2",
        "status": "success",
        "finish_reason": "stop",
        "usage": usage,
        "usage_source": "provider",
        "metering_status": "known",
        "thinking_mode": True,
        "temperature": 0.2,
        "max_tokens": 512,
        "retry_limit": 0,
        "requests_timeout_seconds": 60,
        "effective_timeout_seconds": 60,
    }
    budget = {
        "limits": manifest["run_limits"],
        "logical_calls": 1,
        "http_attempts": 1,
        "tool_calls": 0,
        "provider_known": usage,
        "provider_unknown_fields": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "reserved_tokens": 0,
        "charged_tokens": 30,
        "unknown_attempts": 0,
        "unresolved_attempts": 0,
        "unknown_tool_calls": 0,
        "deadline_at": 9999999999,
        "wall_time_seconds": 1.0,
        "cost": None,
    }
    semantics = {
        "execution": "completed",
        "transport": "known",
        "whole_review": "accepted",
        "binding": "same_artifact",
        "formal_verification": "not_verified",
        "verification_requirement": "default",
    }
    review = {
        "status": "unknown",
        "checker": "whole_solution_verifier",
        "checker_version": "star-whole-review-v1",
        "scope": "whole_solution_llm_review",
        "findings": ["llm_whole_review_accepted"],
        "limitations": ["LLM review is not formal mathematical verification."],
        "artifact": artifact,
        "source": review_source,
        "versions": [{"artifact": artifact}],
        "fact_sources": [],
        "proof_sources": [],
    }
    verification = {
        **review,
        "acceptance": "needs_review",
        "binding": "same_artifact",
        "history": [review],
    }
    transport_identity = {
        "policy": "legacy",
        "profile_set_fingerprint": "c" * 64,
        "calls": [
            {
                "call_id": public_solver_call_id("job-1", "review-call-internal"),
                "role": "whole_solution_verifier",
                "policy": "legacy",
                "transport": "nonstream",
                "evidence_kind": "documented",
                "reason": "provider_profile_unverified",
                "capability_limit": "verified_stream_profiles_empty",
            }
        ],
    }
    job = {
        "success": True,
        "job_id": "job-1",
        "session_id": "session-1",
        "status": "succeeded",
        "verification_mode": "auto",
        "result": {
            "final_response": answer,
            "budget": budget,
            "request_attempts": [attempt],
            "solver_mode": "star_reference",
            "solver": {"semantics": semantics},
            "verification": verification,
        },
    }
    report = {
        "version": "report-v0.2",
        "evidence_id": "job-1",
        "status": "succeeded",
        "solver": {"solver_mode": "star_reference", "solver": {"semantics": semantics}},
        "report": {
            "answer": answer,
            "request_attempts": [attempt],
            "budget": budget,
            "checks": verification,
            "semantics": semantics,
        },
    }
    evidence = {
        "version": "evidence-v0.1",
        "evidence_id": "job-1",
        "run": {
            "run_id": "job-1",
            "status": "COMPLETED",
            "final_response": answer,
        },
        "request_attempts": [attempt],
        "budget": budget,
        "solver": {"solver_mode": "star_reference", "solver": {"semantics": semantics}},
        "semantics": semantics,
        "verification": verification,
    }
    lookup = {
        "job_id": "job-1",
        "request_digest": "f" * 64,
        "status": "succeeded",
        "transport_identity": transport_identity,
        "budget": budget,
    }
    return manifest, digest, attempt, budget, semantics, lookup, job, report, evidence


def prepare_run(root: Path, *, mismatch: str | None = None, not_run: bool = False):
    """Persist a sanitized batch fixture and return its remote GET responses."""
    output_root = root / "runs"
    run_dir = output_root / "batch-1"
    run_dir.mkdir(parents=True)
    manifest, digest, attempt, budget, semantics, lookup, job, report, evidence = (
        successful_fixture()
    )
    status_usage = {
        "logical_calls": 0 if not_run else 1,
        "http_attempts": 0 if not_run else 1,
        "tool_calls": 0,
        "charged_tokens": 0 if not_run else 30,
        "wall_seconds": 0.0 if not_run else 1.0,
    }
    if mismatch == "budget_attempts":
        budget["http_attempts"] = 2
    if mismatch == "binding":
        semantics["binding"] = "artifact_changed"
        report["report"]["checks"]["binding"] = "artifact_changed"
        evidence["verification"]["binding"] = "artifact_changed"
    if mismatch == "session":
        job["session_id"] = "session-other"
    if mismatch == "job_id":
        job["job_id"] = "job-other"
    if mismatch == "report_answer":
        report["report"]["answer"] = "different answer text"
    if mismatch == "evidence_id":
        evidence["evidence_id"] = "job-other"
    if mismatch == "review_attempt_status":
        attempt["status"] = "error"
    if mismatch == "invalid_usage":
        attempt["usage"]["prompt_tokens"] = -1
    if mismatch == "invalid_wall_time":
        budget["wall_time_seconds"] = float("nan")
    if mismatch == "duplicate_attempt":
        duplicate = dict(attempt)
        duplicate.update(attempt_id="attempt-2", attempt_index=2)
        job["result"]["request_attempts"] = [attempt, duplicate]
        report["report"]["request_attempts"] = [attempt, duplicate]
        evidence["request_attempts"] = [attempt, duplicate]
        budget.update(
            logical_calls=1,
            http_attempts=2,
            provider_known={"prompt_tokens": 20, "completion_tokens": 40, "total_tokens": 60},
            charged_tokens=60,
        )
        status_usage.update(http_attempts=2, charged_tokens=60)
    if mismatch == "lookup_status":
        lookup["status"] = "running"
    if mismatch == "status_snapshot":
        job["status"] = "running"
        lookup["status"] = "running"
    if mismatch == "transport_call_id":
        lookup["transport_identity"]["calls"][0]["call_id"] = "solver_call_unrelated"
        evidence["solver"]["transport_identity"] = lookup["transport_identity"]
    if mismatch == "transport_text":
        lookup["transport_identity"]["calls"][0]["reason"] = "private prompt text"
        evidence["solver"]["transport_identity"] = lookup["transport_identity"]
    if mismatch == "attempt_solver_call_id":
        attempt["solver_call_id"] = "private prompt text"
    if mismatch == "evidence_transport_identity":
        evidence["solver"]["transport_identity"] = {
            **lookup["transport_identity"],
            "calls": [{**lookup["transport_identity"]["calls"][0], "transport": "stream"}],
        }
    if mismatch == "unconfirmed_dispatch":
        attempt["dispatch_status"] = "reserved_dispatch_unconfirmed"
    if mismatch == "secret_finish_reason":
        attempt["finish_reason"] = "private credential text"
    if mismatch == "malformed_review_findings":
        evidence["verification"]["history"][-1]["findings"] = None
    (run_dir / "manifest.json").write_bytes(canonical_json(manifest))
    (run_dir / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
    status = {
        "run_id": "batch-1",
        "manifest_sha256": digest,
        "phase": "registered" if not_run else "completed",
        "completed": 0 if not_run else 1,
        "total": 1,
        "completed_samples": [] if not_run else [0],
        "usage": status_usage,
        "run_records": []
        if not_run
        else [
            {
                "sample_id": "sample-1",
                "job_id": "job-1",
                "session_id": "session-1",
                "idempotency_key": "12345678-1234-4234-8234-123456789012",
                "request_digest": lookup["request_digest"],
                "deadline_at": 9999999999,
            }
        ],
        "stop_reason": {"private": "invalid"} if mismatch == "invalid_stop_reason" else None,
    }
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    responses = {
        "/api/agent/jobs/job-1": job,
        "/api/agent/jobs/by-idempotency": lookup,
        "/api/agent/jobs/job-1/report": report,
        "/api/runs/job-1/evidence": evidence,
    }
    return output_root, run_dir, digest, manifest, responses


def verify_args(root: Path, output_root: Path):
    """Build the read-only verify command arguments for one persisted run."""
    return build_parser().parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8090",
            "--cookie-file",
            str(root / "cookies.txt"),
            "experiment",
            "verify",
            "--run-id",
            "batch-1",
            "--output-root",
            str(output_root),
        ]
    )


class ExperimentVerifyCliTest(unittest.TestCase):
    def test_verify_accepts_legacy_transport_without_evidence_kind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root)
            identity = responses["/api/agent/jobs/by-idempotency"]["transport_identity"]
            identity["calls"][0]["evidence_kind"] = None
            responses["/api/runs/job-1/evidence"]["solver"]["transport_identity"] = identity
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(0, result)
            self.assertEqual("PASS", report["checks"]["transport"]["status"])
            archived = next((output_root / "batch-1" / "evidence").glob("*.json"))
            saved = json.loads(archived.read_text(encoding="utf-8"))
            self.assertIsNone(saved["transport_identity"]["calls"][0]["evidence_kind"])

    def test_verify_keeps_coverage_unknown_when_persisted_job_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, _ = prepare_run(root)
            client = ReadOnlyShowcaseClient({})
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("UNKNOWN", report["status"])
            self.assertEqual("UNKNOWN", report["checks"]["coverage"]["status"])
            self.assertEqual(1, len(client.calls))
            self.assertTrue(all(method == "GET" for method, _, _ in client.calls))

            export_path = root / "unknown-report.json"
            export_args = build_parser().parse_args(
                [
                    "--base-url",
                    "http://127.0.0.1:8090",
                    "--cookie-file",
                    str(root / "cookies.txt"),
                    "experiment",
                    "export",
                    "--run-id",
                    "batch-1",
                    "--output-root",
                    str(output_root),
                    "--output",
                    str(export_path),
                ]
            )
            with contextlib.redirect_stdout(io.StringIO()):
                export_result = run(export_args, experiment_context={"read_client": client})
            self.assertEqual(1, export_result)
            self.assertEqual(
                "UNKNOWN", json.loads(export_path.read_text(encoding="utf-8"))["status"]
            )

    def test_verify_reports_not_run_without_dispatching_any_sample(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, _ = prepare_run(root, not_run=True)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(verify_args(root, output_root), experiment_context={})

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("NOT_RUN", report["status"])
            self.assertEqual(
                {
                    "transport": "NOT_RUN",
                    "task": "NOT_RUN",
                    "usage": "NOT_RUN",
                    "coverage": "NOT_RUN",
                },
                {key: value["status"] for key, value in report["checks"].items()},
            )

    def test_verify_does_not_hide_attempt_and_usage_disagreement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root, mismatch="budget_attempts")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("FAIL", report["checks"]["usage"]["status"])

    def test_verify_reports_non_finite_budget_time_without_crashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root, mismatch="invalid_wall_time")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["checks"]["usage"]["status"])
            self.assertEqual(0.0, report["budget"]["observed"]["wall_seconds"])
            archive = next((output_root / "batch-1" / "evidence").glob("*.json"))
            saved = json.loads(archive.read_text(encoding="utf-8"))
            self.assertIsNone(saved["budget"]["wall_time_seconds"])

    def test_verify_rejects_duplicate_or_unconfirmed_attempt_records(self):
        for mismatch in ("duplicate_attempt", "unconfirmed_dispatch"):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output_root, _, _, _, responses = prepare_run(root, mismatch=mismatch)
                client = ReadOnlyShowcaseClient(responses)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": client},
                    )

                report = json.loads(output.getvalue())
                self.assertEqual(1, result)
                self.assertEqual("FAIL", report["status"])
                self.assertEqual("FAIL", report["checks"]["usage"]["status"])

    def test_verify_rejects_conflicting_transport_projection_in_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(
                root, mismatch="evidence_transport_identity"
            )
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["checks"]["transport"]["status"])

    def test_verify_redacts_untrusted_finish_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root, mismatch="secret_finish_reason")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            archive = next((output_root / "batch-1" / "evidence").glob("*.json"))
            self.assertNotIn("private credential text", archive.read_text(encoding="utf-8"))

    def test_verify_handles_malformed_review_findings_without_crashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(
                root, mismatch="malformed_review_findings"
            )
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertIn(report["checks"]["task"]["status"], {"FAIL", "UNKNOWN"})

    def test_verify_sanitizes_malformed_stop_reason(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root, mismatch="invalid_stop_reason")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertIsNone(report["stop_reason"])
            self.assertEqual("FAIL", report["status"])

    def test_verify_does_not_replace_a_modified_evidence_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(root)
            client = ReadOnlyShowcaseClient(responses)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": client},
                    ),
                )

            archive = next((run_dir / "evidence").glob("*.json"))
            archive.write_text('{"tampered":true}', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            self.assertEqual(1, result)
            self.assertEqual('{"tampered":true}', archive.read_text(encoding="utf-8"))
            self.assertEqual(
                "FAIL", json.loads(output.getvalue())["checks"]["coverage"]["status"]
            )

    def test_verify_does_not_recreate_a_removed_evidence_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(root)
            client = ReadOnlyShowcaseClient(responses)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": client},
                    ),
                )

            evidence_dir = run_dir / "evidence"
            for archive in evidence_dir.iterdir():
                archive.unlink()
            evidence_dir.rmdir()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            self.assertEqual(1, result)
            self.assertFalse(evidence_dir.exists())
            self.assertEqual(
                "FAIL", json.loads(output.getvalue())["checks"]["coverage"]["status"]
            )

    def test_verify_detects_removed_archive_when_remote_evidence_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(root)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    0,
                    run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": ReadOnlyShowcaseClient(responses)},
                    ),
                )

            evidence_dir = run_dir / "evidence"
            for archive in evidence_dir.iterdir():
                archive.unlink()
            evidence_dir.rmdir()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient({})},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["checks"]["coverage"]["status"])

    def test_verify_does_not_export_untrusted_job_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(root)
            responses["/api/agent/jobs/job-1"]["status"] = {"private": "credential text"}
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            self.assertEqual(1, result)
            archive = next((run_dir / "evidence").glob("*.json"))
            archived = archive.read_text(encoding="utf-8")
            self.assertNotIn("credential text", archived)
            self.assertIn('"job_status":"unknown"', archived)

    def test_export_rejects_unallowlisted_persisted_fields(self):
        from showcase.experiment_verification import export_experiment_report

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, _ = prepare_run(root)
            report = {
                "run_id": "batch-1",
                "checks": {name: {"status": "PASS", "reason": "ok"}
                           for name in ("transport", "task", "usage", "coverage")},
                "status": "PASS",
                "unexpected_secret": "must not export",
            }
            content = canonical_json(report)
            (run_dir / "verification.json").write_bytes(content)
            (run_dir / "verification.sha256").write_text(
                hashlib.sha256(content).hexdigest(), encoding="ascii"
            )
            export_path = root / "report.json"
            with self.assertRaisesRegex(ValueError, "experiment_verification_invalid"):
                export_experiment_report(
                    "batch-1", output_root=output_root, output=export_path
                )
            self.assertFalse(export_path.exists())

    def test_verify_reports_changed_final_artifact_binding_as_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, responses = prepare_run(root, mismatch="binding")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["status"])
            self.assertEqual("FAIL", report["checks"]["task"]["status"])

    def test_verify_rejects_job_identity_and_final_answer_disagreements(self):
        for mismatch in (
            "session",
            "job_id",
            "report_answer",
            "evidence_id",
            "review_attempt_status",
            "invalid_usage",
            "lookup_status",
            "status_snapshot",
            "transport_call_id",
            "transport_text",
            "attempt_solver_call_id",
        ):
            with self.subTest(mismatch=mismatch), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output_root, _, _, _, responses = prepare_run(root, mismatch=mismatch)
                client = ReadOnlyShowcaseClient(responses)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": client},
                    )

                report = json.loads(output.getvalue())
                expected_check = {
                    "transport_call_id": "transport",
                    "transport_text": "transport",
                    "attempt_solver_call_id": "transport",
                    "invalid_usage": "usage",
                }.get(mismatch, "task")
                expected_check_status = (
                    "UNKNOWN"
                    if mismatch in {"lookup_status", "status_snapshot"}
                    else "FAIL"
                )
                expected_status = (
                    "UNKNOWN" if mismatch in {"lookup_status", "status_snapshot"} else "FAIL"
                )
                self.assertEqual(1, result)
                self.assertEqual(expected_status, report["status"])
                self.assertEqual(
                    expected_check_status, report["checks"][expected_check]["status"]
                )
                if mismatch in {"transport_call_id", "transport_text", "attempt_solver_call_id"}:
                    archive = next((output_root / "batch-1" / "evidence").glob("*.json"))
                    self.assertNotIn("solver_call_unrelated", archive.read_text(encoding="utf-8"))
                    self.assertNotIn("private prompt text", archive.read_text(encoding="utf-8"))

    def test_verify_rejects_malformed_job_route_identity_before_http(self):
        for field, value in (
            ("job_id", "../sessions"),
            ("idempotency_key", "invalid\r\nheader"),
            ("request_digest", "g" * 64),
            ("deadline_at", -1),
            ("deadline_at", 0),
            ("deadline_at", float("nan")),
            ("deadline_at", float("inf")),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                output_root, run_dir, _, _, responses = prepare_run(root)
                status_path = run_dir / "status.json"
                status = json.loads(status_path.read_text(encoding="utf-8"))
                status["run_records"][0][field] = value
                status_path.write_text(json.dumps(status), encoding="utf-8")
                client = ReadOnlyShowcaseClient(responses)
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    result = run(
                        verify_args(root, output_root),
                        experiment_context={"read_client": client},
                    )

                report = json.loads(output.getvalue())
                self.assertEqual(1, result)
                self.assertEqual("FAIL", report["status"])
                self.assertEqual([], client.calls)

    def test_export_refuses_environment_file_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, _, _ = prepare_run(root, not_run=True)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(1, run(verify_args(root, output_root), experiment_context={}))

            with self.assertRaisesRegex(ValueError, "experiment_export_path_invalid"):
                run(
                    build_parser().parse_args(
                        [
                            "--base-url", "http://127.0.0.1:8090",
                            "--cookie-file", str(root / "cookies.txt"),
                            "experiment", "export", "--run-id", "batch-1",
                            "--output-root", str(output_root), "--output", str(root / ".env"),
                        ]
                    ),
                    experiment_context={},
                )
            self.assertFalse((root / ".env").exists())

    def test_verify_reconciles_persisted_job_and_exports_only_redacted_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, digest, manifest, responses = prepare_run(root)
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root), experiment_context={"read_client": client}
                )

            self.assertEqual(0, result)
            report_json = json.loads(output.getvalue())
            self.assertEqual("PASS", report_json["status"])
            self.assertEqual(
                {"transport": "PASS", "task": "PASS", "usage": "PASS", "coverage": "PASS"},
                {key: value["status"] for key, value in report_json["checks"].items()},
            )
            self.assertEqual("batch-1", report_json["run_id"])
            self.assertEqual(digest, report_json["manifest_sha256"])
            self.assertEqual(["sample-1"], report_json["sample_ids"])
            self.assertEqual(
                [
                    {
                        "id": "sample-1",
                        "type": "simple",
                        "input_sha256": "d" * 64,
                        "text_sha256": "e" * 64,
                    }
                ],
                report_json["samples"],
            )
            self.assertEqual(manifest["model"], report_json["applied_config"])
            self.assertEqual("PASS", report_json["checks"]["task"]["status"])
            self.assertNotIn("private answer text", output.getvalue())
            self.assertTrue(client.calls)
            self.assertTrue(all(method == "GET" for method, _, _ in client.calls))
            self.assertNotIn("POST", str(client.calls))
            self.assertTrue((run_dir / "verification.json").is_file())
            archive_paths = list((run_dir / "evidence").glob("*.json"))
            self.assertEqual(1, len(archive_paths))
            self.assertNotIn("private answer text", archive_paths[0].read_text(encoding="utf-8"))

            export_path = root / "report.json"
            export_args = build_parser().parse_args(
                [
                    "--base-url",
                    "http://127.0.0.1:8090",
                    "--cookie-file",
                    str(root / "cookies.txt"),
                    "experiment",
                    "export",
                    "--run-id",
                    "batch-1",
                    "--output-root",
                    str(output_root),
                    "--output",
                    str(export_path),
                ]
            )
            calls_before_export = len(client.calls)
            with contextlib.redirect_stdout(io.StringIO()):
                export_result = run(export_args, experiment_context={"read_client": client})
            self.assertEqual(0, export_result)
            self.assertEqual(calls_before_export, len(client.calls))
            self.assertEqual("PASS", json.loads(export_path.read_text(encoding="utf-8"))["status"])


if __name__ == "__main__":
    unittest.main()
