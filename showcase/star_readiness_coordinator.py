"""Run the frozen two-question #97 batch through bounded STAR public Jobs."""

import re
import subprocess
import tempfile
import time
import uuid
from copy import deepcopy
from pathlib import Path

from .star_acceptance import evaluate_delivery
from .star_experiment_archive import ExperimentArchive, source_identity
from .star_experiment_policy import ExperimentRunPolicy
from .star_experiment_server import ExperimentServer
from .star_readiness_admission import admit_next_run
from .star_readiness_archive import (
    delivery_record,
    preflight_record,
    registration_record,
    run_record,
)
from .star_readiness_configuration import validate_server_configuration
from .star_readiness_profile import validate_execution_profile
from .star_readiness_registration import (
    V2_DRAFT_VERSION,
    V2_LIVE_MANIFEST_SHA256,
    V3_DRAFT_VERSION,
    V4_DRAFT_VERSION,
    V5_DRAFT_VERSION,
    digest,
    registration,
)
from .star_readiness_runtime import cleanup_runtime_storage

ARTIFACTS = Path(__file__).resolve().parents[1] / "artifacts"


def _claim_live_registration(manifest_sha256, draft_version):
    """Consume the enabled batch version once, retaining the historical v2 hash key."""
    if not isinstance(manifest_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise ValueError("star_readiness_registration_identity_mismatch")
    if draft_version == V4_DRAFT_VERSION:
        batch_key = V4_DRAFT_VERSION
    elif draft_version == V5_DRAFT_VERSION:
        batch_key = V5_DRAFT_VERSION
    elif draft_version == V3_DRAFT_VERSION:
        batch_key = V3_DRAFT_VERSION
    elif draft_version == V2_DRAFT_VERSION and manifest_sha256 == V2_LIVE_MANIFEST_SHA256:
        batch_key = V2_LIVE_MANIFEST_SHA256
    else:
        raise ValueError("star_readiness_live_draft_version_invalid")
    marker = ARTIFACTS / "issue-97-prereg" / f"{batch_key}.consumed"
    marker.parent.mkdir(parents=True, exist_ok=True)
    if (marker.parent / f"{manifest_sha256}.consumed").exists():
        raise ValueError("star_readiness_live_registration_already_consumed")
    try:
        with marker.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(manifest_sha256 + "\n")
    except FileExistsError:
        raise ValueError("star_readiness_live_registration_already_consumed") from None


def current_source_identity():
    """Return the registered source hash and whether the checkout has local changes."""
    root = Path(__file__).resolve().parents[1]
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=normal"], cwd=root
    )
    return {**source_identity(), "dirty_status": bool(status)}


class _StopBatch(Exception):
    """Carry a sanitized terminal reason out of the batch loop."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class StarReadinessCoordinator:
    """Execute each registered question at most once in an immutable archive."""

    def __init__(self, path, *, adapters, manifest, manifest_sha256, evidence_kind="scripted"):
        if evidence_kind not in {"scripted", "live"}:
            raise ValueError("star_readiness_evidence_kind_invalid")
        if not isinstance(adapters, dict) or "nonstream" not in adapters:
            raise ValueError("star_readiness_adapter_invalid")
        self.path = Path(path)
        self.adapters = adapters
        self.manifest = deepcopy(manifest)
        self.manifest_sha256 = manifest_sha256
        self.evidence_kind = evidence_kind
        self._check_execution_profile()

    def _check_execution_profile(self):
        """Keep the default loopback profile and the authorized live profile disjoint."""
        try:
            client = self.adapters["nonstream"]._get_client()
        except (AttributeError, KeyError, TypeError, ValueError):
            raise ValueError("star_readiness_provider_client_invalid") from None
        validate_execution_profile(self.evidence_kind, self.manifest, client)

    def _verified_registration(self):
        """Verify the frozen registration against the current repository source."""
        current = current_source_identity()
        if not isinstance(self.manifest, dict) or current != self.manifest.get("source_identity"):
            raise _StopBatch("source_identity_mismatch")
        try:
            return registration(
                self.manifest,
                expected_sha256=self.manifest_sha256,
                current_source=current,
            )
        except ValueError:
            raise _StopBatch("registration_invalid") from None

    def _verified_configuration(self, server):
        """Compare effective Reference settings with the independently frozen preset."""
        try:
            return validate_server_configuration(server, self.manifest["reference_configuration"])
        except (AttributeError, KeyError, TypeError, ValueError):
            raise _StopBatch("configuration_mismatch") from None

    @staticmethod
    def _run_limits(limits):
        """Translate the frozen #97 envelope to the S3 Run policy fields."""
        return {
            "max_model_calls": limits["logical_calls"],
            "max_http_attempts": limits["http_attempts"],
            "max_tool_calls": limits["problem_tool_calls"],
            "max_tokens": limits["charged_tokens"],
            "max_runtime_seconds": limits["wall_seconds"],
        }

    @staticmethod
    def _valid_preflight(observed):
        """Accept only a successful immutable preflight receipt and its S3 ledger."""
        if not isinstance(observed, dict) or observed.get("available") is not True:
            return False
        identity, budget = observed.get("identity"), observed.get("budget")
        return (
            isinstance(identity, dict)
            and isinstance(identity.get("run_id"), str)
            and bool(identity["run_id"])
            and isinstance(budget, dict)
            and type(budget.get("tool_calls")) is int
            and budget["tool_calls"] == 1
            and type(budget.get("http_attempts")) is int
            and budget["http_attempts"] == 0
        )

    @staticmethod
    def _bundle_consistent(bundle, job_id):
        """Check that public report, evidence and Run refer to one unchanged Job."""
        if not isinstance(bundle, dict) or not all(
            isinstance(bundle.get(key), dict) for key in ("job", "report", "evidence", "run")
        ):
            return False
        job, report, evidence, run = (bundle[key] for key in ("job", "report", "evidence", "run"))
        result = job.get("result") or {}
        return (
            job.get("job_id") == job_id
            and run.get("run_id") == job_id
            and (evidence.get("run") or {}).get("run_id") == job_id
            and report.get("semantics") == evidence.get("semantics")
            and report.get("checks") == evidence.get("verification")
            and report.get("budget") == evidence.get("budget")
            and report.get("request_attempts") == evidence.get("request_attempts")
            and report.get("answer") == result.get("final_response", "")
        )

    @staticmethod
    def _usage(budget):
        """Extract S3 counters, keeping charged tokens separate from reservations."""
        if not isinstance(budget, dict):
            return None
        fields = ("logical_calls", "http_attempts", "tool_calls", "charged_tokens", "reserved_tokens",
                  "unknown_attempts", "unresolved_attempts", "unknown_tool_calls")
        values = {field: budget.get(field) for field in fields}
        if any(type(value) is not int or value < 0 for value in values.values()):
            return None
        known = budget.get("provider_known")
        known_tokens = known.get("total_tokens") if isinstance(known, dict) else None
        if known_tokens is not None and (type(known_tokens) is not int or known_tokens < 0):
            return None
        return {**values, "known_tokens": known_tokens}

    @staticmethod
    def _add_usage(total, usage):
        """Accumulate observed S3 counters without adding reserved tokens twice."""
        for field in ("logical_calls", "http_attempts", "charged_tokens", "reserved_tokens",
                      "unknown_attempts", "unresolved_attempts", "unknown_tool_calls"):
            total[field] += usage[field]
        total["problem_tool_calls"] += usage["tool_calls"]
        if usage["known_tokens"] is None and usage["http_attempts"] > 0:
            total["usage_complete"] = False
        elif usage["known_tokens"] is not None:
            total["known_tokens"] += usage["known_tokens"]

    @staticmethod
    def _usage_unknown(budget, usage):
        """Identify missing or unresolved S3 usage independently of protocol failure."""
        unknown_fields = budget.get("provider_unknown_fields") or {}
        return (
            usage["unknown_attempts"] > 0
            or usage["unresolved_attempts"] > 0
            or usage["unknown_tool_calls"] > 0
            or (usage["http_attempts"] > 0 and usage["known_tokens"] is None)
            or any(value for value in unknown_fields.values())
        )

    @staticmethod
    def _protocol_failed(bundle):
        result = (bundle.get("job") or {}).get("result") or {}
        recovery = ((result.get("solver") or {}).get("recovery") or {})
        return bool(recovery.get("protocol_failures"))

    @staticmethod
    def _delivery_bound(delivery):
        return bool(
            isinstance(delivery, dict)
            and delivery.get("review_bound")
            and (
                delivery.get("reason") == "fastpath_no_step_proofs"
                or delivery.get("reason") == "proof_bound" and delivery.get("proof_delivered")
            )
        )

    @staticmethod
    def _semantics_complete(semantics):
        return (
            isinstance(semantics, dict)
            and semantics.get("execution") == "completed"
            and semantics.get("whole_review") == "accepted"
            and semantics.get("binding") == "same_artifact"
        )

    def run(self):
        """Run the registered batch once, archiving intent, every bundle and result."""
        started = time.monotonic()
        wall_started = time.time()
        archive = ExperimentArchive(self.path)
        policy = None
        server = None
        runtime_storage = None
        runtime_cleanup = "not_started"
        frozen = None
        stop = "completed"
        attempted = []
        dispatched = []
        unresolved_dispatches = []
        records = []
        retention_reason = None
        preflight_ids = set()
        preflight_count = 0
        usage = {
            "logical_calls": 0,
            "http_attempts": 0,
            "problem_tool_calls": 0,
            "charged_tokens": 0,
            "reserved_tokens": 0,
            "known_tokens": 0,
            "usage_complete": True,
            "unknown_attempts": 0,
            "unresolved_attempts": 0,
            "unknown_tool_calls": 0,
        }

        try:
            frozen = self._verified_registration()
            round_wall_seconds = frozen["round_limits"]["wall_seconds"]
            policy = ExperimentRunPolicy(wall_started + round_wall_seconds)
            archive.put("registration.json", {
                "registration": registration_record(frozen),
                "sha256": digest(frozen),
                "source": frozen["source_identity"],
                "evidence_kind": self.evidence_kind,
            })
            if self.evidence_kind == "live":
                _claim_live_registration(self.manifest_sha256, frozen["draft_version"])
            self._check_execution_profile()
            runtime_root = ARTIFACTS / "issue-97-runtime"
            runtime_root.mkdir(parents=True, exist_ok=True)
            runtime_storage = tempfile.TemporaryDirectory(prefix="star-readiness-97-", dir=runtime_root)
            server = ExperimentServer(
                Path(runtime_storage.name) / "nonstream",
                "nonstream",
                self.adapters["nonstream"],
                policy,
                self.evidence_kind,
                refresh_preflight_each_call=True,
                late_usage_evidence_dir=self.path / "supplemental-usage",
                request_timeout_seconds=frozen["model"]["request_timeout_seconds"],
            )
            server.check_conditions()
            archive.put("configuration-startup.json", self._verified_configuration(server))
            questions = {question["id"]: question for question in frozen["questions"]}
            first_entry = frozen["schedule"][0]
            first_admission = admit_next_run(
                {"logical_calls": 0, "http_attempts": 0, "problem_tool_calls": 0,
                 "charged_tokens": 0},
                first_entry["limits"],
                remaining_seconds=max(0, round_wall_seconds - (time.monotonic() - started)),
                preflights=0,
            )
            if first_admission:
                stop = first_admission
                raise _StopBatch(stop)

            preflight_count += 1
            try:
                observed = server.preflight()
            except Exception as exc:
                observed = {"available": False, "reason": "preflight_failed",
                            "failure_type": type(exc).__name__}
            archive.put("preflight-00.json", preflight_record(observed))
            if not self._valid_preflight(observed):
                stop = "preflight_evidence_mismatch"
                raise _StopBatch(stop)
            preflight_ids.add(observed["identity"]["run_id"])

            for index, entry in enumerate(frozen["schedule"]):
                remaining = max(0, round_wall_seconds - (time.monotonic() - started))
                used = {
                    "logical_calls": usage["logical_calls"],
                    "http_attempts": usage["http_attempts"],
                    "problem_tool_calls": usage["problem_tool_calls"],
                    "charged_tokens": usage["charged_tokens"],
                }
                stop_reason = admit_next_run(
                    used,
                    entry["limits"],
                    remaining_seconds=remaining,
                    preflights=preflight_count,
                )
                if stop_reason:
                    stop = stop_reason
                    break

                policy.prepare(self._run_limits(entry["limits"]))
                run_deadline = min(started + round_wall_seconds,
                                   time.monotonic() + entry["limits"]["wall_seconds"])

                self._verified_registration()
                self._check_execution_profile()
                server.check_conditions()
                archive.put(f"configuration-{index:02d}.json", self._verified_configuration(server))
                preflight_count += 1
                try:
                    observed = server.preflight()
                except Exception as exc:
                    observed = {"available": False, "reason": "preflight_failed",
                                "failure_type": type(exc).__name__}
                archive.put(f"preflight-{preflight_count - 1:02d}.json", preflight_record(observed))
                if not self._valid_preflight(observed):
                    stop = "preflight_evidence_mismatch"
                    break
                preflight_id = observed["identity"]["run_id"]
                if preflight_id in preflight_ids:
                    stop = "preflight_evidence_mismatch"
                    break
                preflight_ids.add(preflight_id)
                if time.monotonic() >= run_deadline:
                    stop = "run_deadline_exceeded"
                    break

                question = {"prompt": questions[entry["question"]]["text"]}
                registered_question = questions[entry["question"]]
                idempotency_key = str(uuid.uuid4())
                archive.put(f"intent-{index:02d}.json", {
                    "entry": entry,
                    "idempotency_key": idempotency_key,
                    "question": {
                        "id": registered_question["id"],
                        "source": registered_question["source"],
                        "text_sha256": registered_question["text_sha256"],
                    },
                })
                attempted.append(index)
                response_recovered = False
                try:
                    job_id = server.dispatch(question, idempotency_key=idempotency_key)
                except Exception as exc:
                    try:
                        job_id = server.resolve_dispatch(idempotency_key)
                    except Exception:
                        job_id = None  # Never resend when the local read is inconclusive.
                    unresolved_dispatches.append({
                        "index": index,
                        "question_id": entry["question"],
                        "idempotency_key": idempotency_key,
                        "job_id": job_id,
                        "status": "pending_settlement",
                        # Hold the whole Run envelope separately from observed S3 usage.
                        "reserved_budget": {**entry["limits"], "deadline_at": policy.deadline_at},
                    })
                    stop = "unknown_dispatch_outcome"
                    failure_type = type(exc).__name__
                    if job_id is None:
                        usage["usage_complete"] = False
                        break
                    # Collect the accepted Job only; never dispatch this or the next question.
                    response_recovered = True
                dispatched.append({"index": index, "job_id": job_id})
                retention_reason = "job_archive_incomplete"
                archive.put(f"dispatch-{index:02d}.json", {
                    "job_id": job_id,
                    **({"recovered_from_store": True, "status": "response_recovered"}
                       if response_recovered else {}),
                })

                bundle = server.collect(job_id, policy.deadline_at,
                                        canceled=lambda: time.monotonic() >= run_deadline)
                if not self._bundle_consistent(bundle, job_id):
                    stop = "evidence_mismatch"
                    break
                archive.put(f"run-{index:02d}.json", run_record(bundle, job_id=job_id))
                if response_recovered:
                    snapshot, contexts = server.provenance(job_id)
                    delivery = evaluate_delivery(bundle["job"], snapshot, contexts)
                    archive.put(f"delivery-{index:02d}.json", delivery_record(delivery))
                    record = {"index": index, "question": entry["question"], "job_id": job_id}
                    records.append(record)
                    retention_reason = None

                report = bundle.get("report") if isinstance(bundle, dict) else None
                budget = report.get("budget") if isinstance(report, dict) else None
                observed_usage = self._usage(budget)
                if observed_usage is None:
                    usage["usage_complete"] = False
                    stop = "usage_incomplete"
                    break
                self._add_usage(usage, observed_usage)
                if response_recovered:
                    if self._usage_unknown(budget, observed_usage):
                        usage["usage_complete"] = False
                    else:
                        # Release the reservation only after identity and both archives commit.
                        unresolved_dispatches.pop()
                semantics = report.get("semantics") or {}
                if semantics.get("transport") == "unknown":
                    stop = "unknown_transport"
                    break
                if self._protocol_failed(bundle):
                    stop = "protocol_failure"
                    break
                if bundle["job"].get("status") != "succeeded":
                    stop = "failure"
                    break
                if self._usage_unknown(budget, observed_usage):
                    usage["usage_complete"] = False
                    stop = "usage_unknown"
                    break
                if not self._semantics_complete(semantics):
                    stop = "evidence_mismatch"
                    break

                if not response_recovered:
                    snapshot, contexts = server.provenance(job_id)
                    delivery = evaluate_delivery(bundle["job"], snapshot, contexts)
                    archive.put(f"delivery-{index:02d}.json", delivery_record(delivery))
                    record = {"index": index, "question": entry["question"], "job_id": job_id}
                    records.append(record)
                    retention_reason = None
                if not self._delivery_bound(delivery):
                    stop = "evidence_mismatch"
                    break
                if self._hard_limit(budget, entry["limits"]):
                    stop = "hard_limit"
                    break
                if response_recovered:
                    stop = "dispatch_response_recovered"
                    break

        except _StopBatch as exc:
            stop = exc.reason
        except Exception as exc:  # Persist a sanitized terminal result after any failed step.
            stop = "failure"
            failure_type = type(exc).__name__
        finally:
            try:
                if server is not None:
                    try:
                        server.close()
                    except Exception as exc:
                        if stop == "completed":
                            stop = "failure"
                            failure_type = type(exc).__name__
            finally:
                if runtime_storage is not None:
                    try:
                        runtime_cleanup = cleanup_runtime_storage(
                            runtime_storage,
                            [item["job_id"] for item in dispatched],
                            grace_seconds=self.manifest["model"]["request_timeout_seconds"] + 1,
                            preserve=bool(unresolved_dispatches) or len(records) < len(dispatched),
                            retention_reason=(retention_reason or
                                              ("pending_settlement" if unresolved_dispatches else None)),
                        )
                    except Exception as exc:
                        runtime_cleanup = "failed"
                        if stop == "completed":
                            stop = "failure"
                            failure_type = type(exc).__name__

        if unresolved_dispatches or len(records) < len(dispatched):
            usage["usage_complete"] = False
        result = {
            "stop_reason": stop,
            "failure_type": failure_type if "failure_type" in locals() else None,
            "evidence_kind": self.evidence_kind,
            "executed_runs": len(dispatched),
            "attempted_runs": len(attempted),
            "unexecuted": [entry["question"] for entry in
                           frozen["schedule"][len(attempted):]] if frozen else [],
            "uncollected": [item for item in dispatched
                            if not any(record["job_id"] == item["job_id"] for record in records)],
            "unresolved_dispatches": unresolved_dispatches,
            "preflights": preflight_count,
            "usage": usage,
            "wall_time_seconds": time.monotonic() - started,
            "runtime_storage_cleanup": runtime_cleanup,
            "runtime_storage_path": (
                Path(runtime_storage.name).relative_to(ARTIFACTS).as_posix()
                if runtime_storage is not None and runtime_cleanup != "complete" else None
            ),
            "cost": None,
            "runs": records,
        }
        archive.finish(result)
        return result

    @staticmethod
    def _hard_limit(budget, limits):
        return any((
            budget.get("logical_calls", 0) >= limits["logical_calls"],
            budget.get("http_attempts", 0) >= limits["http_attempts"],
            budget.get("tool_calls", 0) >= limits["problem_tool_calls"],
            budget.get("charged_tokens", 0) >= limits["charged_tokens"],
            budget.get("wall_time_seconds", 0) >= limits["wall_seconds"],
        ))
