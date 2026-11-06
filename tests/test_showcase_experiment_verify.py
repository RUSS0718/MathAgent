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
from showcase.experiment_verification_process import (
    _check_process_path,
    _safe_process_path,
)
from showcase.experiment_verification_state import (
    _overall_status,
    _process_coverage_summary,
)
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
    def test_natural_multistep_requires_live_mode_and_verified_transport(self):
        sample = {"type": "multistep"}
        evidence = {
            "execution_mode": "live",
            "process_path": {
                "evidence_kind": "provider_live",
                "plan_version": 1,
                "attempt_index": 1,
                "planned_steps": 1,
                "reported_steps": 1,
                "accepted_steps": 1,
                "successful_roles": ["planner", "reasoner", "step_verifier", "final_generator"],
                "tool_calls": 0,
                "verified_tool_calls": 0,
                "review_origin": "final_generator",
                "review_plan_version": 1,
                "review_attempt_index": 1,
            },
        }

        result = _check_process_path(
            sample, evidence, {"status": "PASS"}, {"status": "PASS"}
        )

        self.assertEqual("PASS", result["status"])
        self.assertEqual("natural_multistep_path_observed", result["reason"])

    def test_missing_progress_uses_complete_call_roles_without_guessing_a_path(self):
        attempts = [
            {"status": "success", "dispatch_status": "transport_observed", "role": "explore"},
            {
                "status": "success",
                "dispatch_status": "transport_observed",
                "role": "whole_solution_verifier",
            },
        ]
        process = _safe_process_path(
            {"solver": {"solver": {}}, "verification": {"history": []}},
            attempts,
            {"explore", "whole_solution_verifier", "planner"},
            "provider_live",
        )
        evidence = {
            "process_path": process,
            "request_attempts": [
                {
                    "status": item["status"],
                    "dispatch_status": item["dispatch_status"],
                    "role": item["role"],
                }
                for item in attempts
            ],
        }

        result = _check_process_path(
            {"type": "multistep"},
            evidence,
            {"status": "PASS"},
            {"status": "PASS"},
        )

        self.assertEqual("NOT_RUN", result["status"])
        self.assertEqual("natural_multistep_path_not_observed", result["reason"])

        attempts.append(
            {"status": "success", "dispatch_status": "transport_observed", "role": "planner"}
        )
        evidence["process_path"] = _safe_process_path(
            {"solver": {"solver": {}}, "verification": {"history": []}},
            attempts,
            {"explore", "whole_solution_verifier", "planner"},
            "provider_live",
        )
        evidence["request_attempts"].append(
            {"status": "success", "dispatch_status": "transport_observed", "role": "planner"}
        )
        result = _check_process_path(
            {"type": "multistep"},
            evidence,
            {"status": "PASS"},
            {"status": "PASS"},
        )
        self.assertEqual("UNKNOWN", result["status"])
        self.assertEqual("solver_progress_unavailable", result["reason"])

    def test_failed_delivery_is_counted_as_failed_after_multistep_path_started(self):
        evidence = {
            "process_path": {
                "evidence_kind": "provider_live",
                "plan_version": 1,
                "attempt_index": 1,
                "execution_started": True,
                "planned_steps": 2,
                "reported_steps": 1,
                "accepted_steps": 1,
                "tool_calls": 0,
                "successful_roles": ["planner", "reasoner", "step_verifier"],
                "review_plan_version": 1,
                "review_attempt_index": 1,
                "review_origin": "final_generator",
            }
        }

        result = _check_process_path(
            {"type": "multistep"},
            {"execution_mode": "live", **evidence},
            {"status": "FAIL"},
            {"status": "PASS"},
        )

        self.assertEqual("FAIL", result["status"])
        self.assertEqual("natural_multistep_trace_incomplete", result["reason"])

    def test_process_counts_keep_incomplete_distinct_from_failed_and_not_run(self):
        summary = _process_coverage_summary(
            {"samples": [
                {"id": "s1", "type": "multistep"},
                {"id": "s2", "type": "multistep"},
                {"id": "s3", "type": "multistep"},
            ]},
            [{
                "coverage": {"status": "PASS"},
                "process_path": {
                    "status": "FAIL",
                    "reason": "natural_multistep_trace_incomplete",
                },
            }, {
                "coverage": {"status": "UNKNOWN"},
                "task": {"status": "FAIL"},
                "process_path": {"status": "FAIL", "reason": "delivery_failed"},
            }, {
                "coverage": {"status": "PASS"},
                "task": {"status": "PASS"},
                "process_path": {
                    "status": "NOT_RUN",
                    "reason": "natural_multistep_path_not_observed",
                },
            }],
            [
                {"sample_id": "s1", "process_path": {"execution_started": True}},
                {"sample_id": "s2", "process_path": {"plan_version": 1}},
                {"sample_id": "s3", "process_path": {"plan_version": None}},
            ],
        )

        self.assertEqual(3, summary["registered"])
        self.assertEqual(2, summary["audited"])
        self.assertEqual(1, summary["not_observed"])
        self.assertEqual(1, summary["incomplete"])
        self.assertEqual(1, summary["failed"])
        self.assertEqual(0, summary["not_run"])

    def test_started_plan_with_missing_progress_is_incomplete_not_unknown(self):
        evidence = {
            "evidence_id": "job-1",
            "timeline": [{
                "run_id": "job-1",
                "solver_event_type": "initial_plan_generated",
                "solver_revision": 4,
                "plan_version": 1,
                "attempt_index": 1,
            }],
            "solver": {"solver": {}},
            "budget": {"tool_calls": 0},
        }

        process = _safe_process_path(evidence, [], {"planner"}, "provider_live")
        result = _check_process_path(
            {"type": "multistep"},
            {"execution_mode": "live", "process_path": process},
            {"status": "FAIL"},
            {"status": "PASS"},
        )

        self.assertEqual("FAIL", result["status"])
        self.assertEqual("natural_multistep_trace_incomplete", result["reason"])

    def test_roles_are_bound_to_current_plan_attempt_and_successful_public_call(self):
        attempts = []
        timeline = []
        for role, plan, plan_attempt, call_id, revision in (
            ("planner", 2, 1, "solver_call_" + "1" * 32, 2),
            ("reasoner", 1, 1, "solver_call_" + "2" * 32, 3),
            ("reasoner", 2, 2, "solver_call_" + "3" * 32, 4),
            ("step_verifier", 2, 1, "solver_call_" + "4" * 32, 5),
            ("final_generator", 2, 1, "solver_call_" + "5" * 32, 6),
        ):
            attempts.append({
                "run_id": "job-1",
                "role": role,
                "status": "success",
                "dispatch_status": "transport_observed",
                "solver_call_id": call_id,
            })
            timeline.append({
                "run_id": "job-1",
                "solver_event_type": "call_audit",
                "solver_revision": revision,
                "plan_version": plan,
                "attempt_index": plan_attempt,
                "solver_call_id": call_id,
                "call_status": "completed",
                "role": role,
            })
        evidence = {
            "evidence_id": "job-1",
            "timeline": timeline,
            "solver": {"solver": {"progress": {
                "plan_version": 2,
                "attempt_index": 1,
                "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}],
            }}},
            "budget": {"tool_calls": 0},
            "verification": {"history": []},
        }

        process = _safe_process_path(evidence, attempts, {"planner", "reasoner", "step_verifier", "final_generator"}, "provider_live")

        self.assertEqual(["final_generator", "planner", "step_verifier"], process["successful_roles"])

    def test_initial_planner_call_is_bound_to_the_plan_it_created(self):
        planner_call = "solver_call_" + "a" * 32
        timeline = [
            {
                "run_id": "job-1", "solver_event_type": "call_audit",
                "solver_revision": 2, "plan_version": 0, "attempt_index": 0,
                "solver_call_id": planner_call, "call_status": "completed", "role": "planner",
            },
            {
                "run_id": "job-1", "solver_event_type": "initial_plan_generated",
                "solver_revision": 3, "plan_version": 1, "attempt_index": 1, "role": "planner",
            },
            {
                "run_id": "job-1", "solver_event_type": "call_audit",
                "solver_revision": 4, "plan_version": 1, "attempt_index": 1,
                "solver_call_id": "solver_call_" + "b" * 32,
                "call_status": "completed", "role": "reasoner",
            },
            {
                "run_id": "job-1", "solver_event_type": "call_audit",
                "solver_revision": 5, "plan_version": 1, "attempt_index": 1,
                "solver_call_id": "solver_call_" + "c" * 32,
                "call_status": "completed", "role": "step_verifier",
            },
            {
                "run_id": "job-1", "solver_event_type": "call_audit",
                "solver_revision": 6, "plan_version": 1, "attempt_index": 1,
                "solver_call_id": "solver_call_" + "d" * 32,
                "call_status": "completed", "role": "final_generator",
            },
        ]
        attempts = [
            {
                "run_id": "job-1", "solver_call_id": event["solver_call_id"],
                "role": event["role"], "status": "success",
                "dispatch_status": "transport_observed",
            }
            for event in timeline if event["solver_event_type"] == "call_audit"
        ]
        evidence = {
            "evidence_id": "job-1", "timeline": timeline,
            "solver": {"solver": {"progress": {
                "plan_version": 1, "attempt_index": 1,
                "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}],
            }}},
            "budget": {"tool_calls": 0},
            "verification": {"history": [{"source": {
                "origin": "final_generator", "plan_version": 1, "attempt_index": 1,
            }}]},
        }

        process = _safe_process_path(
            evidence, attempts, {"planner", "reasoner", "step_verifier", "final_generator"},
            "provider_live",
        )
        result = _check_process_path(
            {"type": "multistep"},
            {"execution_mode": "live", "process_path": process},
            {"status": "PASS"}, {"status": "PASS"},
        )

        self.assertIn("planner", process["successful_roles"])
        self.assertEqual("PASS", result["status"])

    def test_tool_receipt_requires_matching_later_successful_same_run_call(self):
        receipt_id = "receipt_public_1"
        call_id = "solver_call_" + "a" * 32
        timeline = [
            {
                "run_id": "job-1", "solver_event_type": "tool_receipt",
                "solver_revision": 5, "plan_version": 2, "attempt_index": 1,
                "receipt_id": receipt_id, "receipt_status": "success",
                "receipt_executed": True,
            },
            {
                "run_id": "job-1", "solver_event_type": "call_audit",
                "solver_revision": 6, "plan_version": 2, "attempt_index": 1,
                "solver_call_id": call_id, "call_status": "completed",
                "role": "reasoner", "consumed_receipt_ids": [receipt_id],
            },
        ]
        attempts = [{
            "run_id": "job-1", "solver_call_id": call_id, "role": "reasoner",
            "status": "success", "dispatch_status": "transport_observed",
        }]
        evidence = {
            "evidence_id": "job-1", "timeline": timeline,
            "solver": {"solver": {"progress": {
                "plan_version": 2, "attempt_index": 1,
                "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}],
            }}},
            "budget": {"tool_calls": 1},
            "verification": {"history": []},
        }

        process = _safe_process_path(evidence, attempts, {"reasoner"}, "provider_live")

        self.assertEqual(1, process["verified_tool_calls"])
        timeline[1]["consumed_receipt_ids"] = ["different_receipt"]
        process = _safe_process_path(evidence, attempts, {"reasoner"}, "provider_live")
        self.assertIsNone(process["verified_tool_calls"])

    def test_tool_receipts_from_completed_plan_attempts_remain_auditable(self):
        receipts = [
            ("receipt_public_1", 1, 1, 3, "solver_call_" + "1" * 32, 4),
            ("receipt_public_2", 2, 2, 8, "solver_call_" + "2" * 32, 9),
        ]
        timeline = []
        attempts = []
        for receipt_id, plan, plan_attempt, receipt_revision, call_id, call_revision in receipts:
            timeline.extend([
                {
                    "run_id": "job-1", "solver_event_type": "tool_receipt",
                    "solver_revision": receipt_revision, "plan_version": plan,
                    "attempt_index": plan_attempt, "receipt_id": receipt_id,
                    "receipt_status": "success", "receipt_executed": True,
                },
                {
                    "run_id": "job-1", "solver_event_type": "call_audit",
                    "solver_revision": call_revision, "plan_version": plan,
                    "attempt_index": plan_attempt, "solver_call_id": call_id,
                    "call_status": "completed", "role": "reasoner",
                    "consumed_receipt_ids": [receipt_id],
                },
            ])
            attempts.append({
                "run_id": "job-1", "solver_call_id": call_id, "role": "reasoner",
                "status": "success", "dispatch_status": "transport_observed",
            })
        evidence = {
            "evidence_id": "job-1", "timeline": timeline,
            "solver": {"solver": {"progress": {
                "plan_version": 2, "attempt_index": 2,
                "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}],
            }}},
            "budget": {"tool_calls": 2},
            "verification": {"history": []},
        }

        process = _safe_process_path(evidence, attempts, {"reasoner"}, "provider_live")

        self.assertEqual(2, process["verified_tool_calls"])

    def test_explore_and_whole_reviewer_can_consume_run_tool_receipts(self):
        timeline = []
        attempts = []
        for index, role in enumerate(("explore", "whole_solution_verifier"), start=1):
            receipt_id = f"receipt_public_{index}"
            call_id = "solver_call_" + str(index) * 32
            timeline.extend([
                {
                    "run_id": "job-1", "solver_event_type": "tool_receipt",
                    "solver_revision": index * 2, "plan_version": 1, "attempt_index": 1,
                    "receipt_id": receipt_id, "receipt_status": "success",
                    "receipt_executed": True,
                },
                {
                    "run_id": "job-1", "solver_event_type": "call_audit",
                    "solver_revision": index * 2 + 1, "plan_version": 1,
                    "attempt_index": 1, "solver_call_id": call_id,
                    "call_status": "completed", "role": role,
                    "consumed_receipt_ids": [receipt_id],
                },
            ])
            attempts.append({
                "run_id": "job-1", "solver_call_id": call_id, "role": role,
                "status": "success", "dispatch_status": "transport_observed",
            })
        evidence = {
            "evidence_id": "job-1", "timeline": timeline,
            "solver": {"solver": {"progress": {
                "plan_version": 1, "attempt_index": 1,
                "steps": [{"reported": True, "verdict": "ACCEPT", "valid": True}],
            }}},
            "budget": {"tool_calls": 2},
            "verification": {"history": []},
        }

        process = _safe_process_path(
            evidence, attempts,
            {"explore", "whole_solution_verifier"},
            "provider_live",
        )

        self.assertEqual(2, process["verified_tool_calls"])

    def test_overall_status_keeps_usage_required_by_default(self):
        checks = {
            "transport": {"status": "PASS"},
            "task": {"status": "PASS"},
            "usage": {"status": "UNKNOWN"},
            "coverage": {"status": "PASS"},
        }

        self.assertEqual("UNKNOWN", _overall_status(checks))
        self.assertEqual("PASS", _overall_status(checks, usage_policy="observe_only"))
        checks["usage"]["status"] = "FAIL"
        self.assertEqual("FAIL", _overall_status(checks, usage_policy="observe_only"))

    def test_verify_observe_only_ignores_usage_unknown_for_overall_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, _, _, manifest, responses = prepare_run(root)
            manifest["evidence_kind"] = "provider_live"
            manifest["usage_policy"] = "observe_only"
            attempt = responses["/api/agent/jobs/job-1"]["result"]["request_attempts"][0]
            attempt["usage"] = None
            budget = responses["/api/agent/jobs/job-1"]["result"]["budget"]
            budget["provider_known"] = {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            }
            budget["provider_unknown_fields"] = {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 1,
            }
            budget["unknown_attempts"] = 1
            responses["/api/agent/jobs/job-1/report"]["report"]["request_attempts"] = [attempt]
            responses["/api/runs/job-1/evidence"]["request_attempts"] = [attempt]
            digest = manifest_digest(manifest)
            run_dir = output_root / "batch-1"
            (run_dir / "manifest.json").write_bytes(canonical_json(manifest))
            (run_dir / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            status["manifest_sha256"] = digest
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(0, result)
            self.assertEqual("PASS", report["status"])
            self.assertEqual("UNKNOWN", report["checks"]["usage"]["status"])

            export_path = root / "observe-only-report.json"
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
                export_result = run(export_args, experiment_context={})
            self.assertEqual(0, export_result)
            self.assertEqual("PASS", json.loads(export_path.read_text(encoding="utf-8"))["status"])

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

    def test_verify_reports_terminal_failed_job_as_coverage_failure_with_preserved_intent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(root)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            record = status["run_records"][0]
            status.update(
                phase="stopped",
                completed=0,
                completed_samples=[],
                stop_reason="job_failed_or_canceled",
                current_index=0,
                current_job_id="job-1",
            )
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            responses["/api/agent/jobs/job-1"]["status"] = "failed"
            responses["/api/agent/jobs/job-1/report"]["status"] = "failed"
            (run_dir / "dispatch_intent.json").write_text(
                json.dumps({
                    "index": 0,
                    "sample_id": record["sample_id"],
                    "session_id": record["session_id"],
                    "idempotency_key": record["idempotency_key"],
                    "request_digest": record["request_digest"],
                    "deadline_at": record["deadline_at"],
                }),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient(responses)},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("FAIL", report["checks"]["task"]["status"])
            self.assertEqual("FAIL", report["checks"]["coverage"]["status"])
            self.assertEqual("batch_stopped_before_completion", report["checks"]["coverage"]["reason"])

    def test_nonterminal_job_with_other_task_failure_keeps_dispatch_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, responses = prepare_run(
                root, mismatch="status_snapshot"
            )
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            record = status["run_records"][0]
            status.update(
                phase="stopped",
                completed=0,
                completed_samples=[],
                stop_reason="job_failed_or_canceled",
                current_index=0,
                current_job_id="job-1",
            )
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            responses["/api/agent/jobs/job-1/report"]["evidence_id"] = "job-other"
            (run_dir / "dispatch_intent.json").write_text(
                json.dumps({
                    "index": 0,
                    "sample_id": record["sample_id"],
                    "session_id": record["session_id"],
                    "idempotency_key": record["idempotency_key"],
                    "request_digest": record["request_digest"],
                    "deadline_at": record["deadline_at"],
                }),
                encoding="utf-8",
            )

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient(responses)},
                )

            report = json.loads(output.getvalue())

        self.assertEqual(1, result)
        self.assertEqual("FAIL", report["checks"]["task"]["status"])
        self.assertEqual("UNKNOWN", report["checks"]["coverage"]["status"])
        self.assertEqual("dispatch_intent_unresolved", report["checks"]["coverage"]["reason"])

    def test_unmatched_dispatch_intent_remains_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, _, _ = prepare_run(root, not_run=True)
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            status.update(phase="stopped", stop_reason="unknown_dispatch")
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            (run_dir / "dispatch_intent.json").write_text(
                json.dumps({
                    "index": 0,
                    "sample_id": "sample-1",
                    "session_id": "session-unknown",
                    "idempotency_key": "12345678-1234-4234-8234-123456789012",
                    "request_digest": "f" * 64,
                    "deadline_at": 9999999999,
                }),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient({})},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("UNKNOWN", report["checks"]["coverage"]["status"])
            self.assertEqual("dispatch_intent_unresolved", report["checks"]["coverage"]["reason"])

    def test_multistep_without_progress_is_audited_but_not_counted_as_path_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, manifest, responses = prepare_run(root)
            manifest["samples"][0]["type"] = "multistep"
            digest = manifest_digest(manifest)
            (run_dir / "manifest.json").write_bytes(canonical_json(manifest))
            (run_dir / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            status["manifest_sha256"] = digest
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            client = ReadOnlyShowcaseClient(responses)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": client},
                )

            report = json.loads(output.getvalue())
            self.assertEqual(1, result)
            self.assertEqual("PASS", report["checks"]["task"]["status"])
            self.assertEqual("PASS", report["checks"]["coverage"]["status"])
            self.assertEqual("NOT_RUN", report["checks"]["process_path"]["status"])
            self.assertEqual(
                "natural_multistep_path_not_observed",
                report["checks"]["process_path"]["reason"],
            )
            self.assertEqual(
                {
                    "registered": 1,
                    "audited": 1,
                    "completed_without_plan": 1,
                    "planned": 0,
                    "path_completed": 0,
                    "not_observed": 1,
                    "incomplete": 0,
                    "not_provider_live": 0,
                    "unknown": 0,
                    "not_run": 0,
                    "failed": 0,
                },
                report["process_coverage"],
            )

    def test_scripted_multistep_trace_is_not_counted_as_natural_path_coverage(self):
        evidence = {
            "execution_mode": "experimental",
            "process_path": {
                "evidence_kind": "scripted",
                "plan_version": 1,
                "planned_steps": 1,
                "reported_steps": 1,
                "accepted_steps": 1,
                "successful_roles": ["planner", "reasoner", "step_verifier", "final_generator"],
                "tool_calls": 0,
                "review_origin": "final_generator",
                "review_plan_version": 1,
            },
        }

        result = _check_process_path(
            {"type": "multistep"},
            evidence,
            {"status": "PASS"},
            {"status": "PASS"},
        )

        self.assertEqual("NOT_RUN", result["status"])
        self.assertEqual("provider_live_trace_required", result["reason"])

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
                    "process_path": "PASS",
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

    def test_legacy_multistep_report_cannot_export_without_path_evidence(self):
        from showcase.experiment_verification import export_experiment_report

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, manifest, responses = prepare_run(root)
            manifest["samples"][0]["type"] = "multistep"
            digest = manifest_digest(manifest)
            (run_dir / "manifest.json").write_bytes(canonical_json(manifest))
            (run_dir / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            status["manifest_sha256"] = digest
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient(responses)},
                )

            report_path = run_dir / "verification.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["schema_version"] = 1
            report.pop("process_coverage")
            report["checks"].pop("process_path")
            report["samples"][0]["type"] = "multistep"
            report["manifest_sha256"] = digest
            report["status"] = _overall_status(report["checks"])
            content = canonical_json(report)
            report_path.write_bytes(content)
            (run_dir / "verification.sha256").write_text(
                hashlib.sha256(content).hexdigest(), encoding="ascii"
            )

            with self.assertRaisesRegex(ValueError, "experiment_verification_invalid"):
                export_experiment_report(
                    "batch-1", output_root=output_root, output=root / "report.json"
                )

    def test_export_rejects_process_counts_that_disagree_with_registered_samples(self):
        from showcase.experiment_verification import export_experiment_report

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output_root, run_dir, _, manifest, responses = prepare_run(root)
            manifest["samples"][0]["type"] = "multistep"
            digest = manifest_digest(manifest)
            (run_dir / "manifest.json").write_bytes(canonical_json(manifest))
            (run_dir / "manifest.sha256").write_text(digest + "\n", encoding="ascii")
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            status["manifest_sha256"] = digest
            (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                run(
                    verify_args(root, output_root),
                    experiment_context={"read_client": ReadOnlyShowcaseClient(responses)},
                )

            report_path = run_dir / "verification.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["process_coverage"]["registered"] = 2
            report["process_coverage"]["not_observed"] = 2
            content = canonical_json(report)
            report_path.write_bytes(content)
            (run_dir / "verification.sha256").write_text(
                hashlib.sha256(content).hexdigest(), encoding="ascii"
            )

            with self.assertRaisesRegex(ValueError, "experiment_verification_invalid"):
                export_experiment_report(
                    "batch-1", output_root=output_root, output=root / "report.json"
                )

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
                {
                    "transport": "PASS",
                    "task": "PASS",
                    "usage": "PASS",
                    "coverage": "PASS",
                    "process_path": "PASS",
                },
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
