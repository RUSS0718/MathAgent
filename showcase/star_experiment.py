"""Bounded spec #87 coordinator over authenticated public Job/Run products."""

import threading
import time
from copy import deepcopy
from pathlib import Path

from .star_experiment_archive import ExperimentArchive, source_identity
from .star_experiment_gates import Qualification
from .star_experiment_policy import ExperimentRunPolicy
from .star_experiment_registration import digest, oracle, registration
from .star_experiment_review import await_review
from .star_experiment_scoring import admit, aggregate, score
from .star_experiment_server import ExperimentServer


class ExperimentCoordinator:
    """One call creates one immutable round; stopped rounds cannot be resumed.

    `reviewer(question_id, question, public_bundle)` supplies a separate human
    mathematical assessment bound to both hashes. It never modifies solver input.
    Scripted runs require loopback provider URLs; RB08 alone enables live.
    """

    def __init__(self, path, *, adapters, qualification, evidence_kind="scripted"):
        if evidence_kind not in {"scripted", "live"}:
            raise ValueError("experiment_evidence_kind_invalid")
        if not isinstance(qualification, Qualification):
            raise ValueError("experiment_prerequisites_unverified")
        self.path, self.adapters = Path(path), adapters
        self.qualification, self.evidence_kind = qualification, evidence_kind
        self._canceled = threading.Event()

    def cancel(self):
        self._canceled.set()

    def run(self, reviewer):
        archive = ExperimentArchive(self.path)
        started = time.monotonic()
        policy = ExperimentRunPolicy(time.time() + 4800)
        frozen = registration()
        archive.put("registration.json", dict(registration=frozen, sha256=digest(frozen),
                                             source=source_identity(), evidence_kind=self.evidence_kind))
        archive.put("prerequisites.json", self.qualification.report)
        archive.put("independent-oracles.json", {key: oracle(key) for key in frozen["questions"]})
        servers, records, probes, dispatched = {}, [], [], []
        stop = None

        def capture_probe(server):
            observed = server.preflight()
            identity = observed.get("identity") or {}
            if identity and all((p.get("identity") or {}).get("run_id") != identity["run_id"] for p in probes):
                probes.append(observed)
                archive.put(f"preflight-{len(probes):02d}.json", observed)
            if not observed["available"]:
                raise ValueError("experiment_preflight_evidence_invalid")

        try:
            self.qualification.require(self.evidence_kind)
            for transport in ("nonstream", "stream"):
                if self._canceled.is_set():
                    break
                servers[transport] = ExperimentServer(self.path / transport, transport,
                    self.adapters[transport], policy, self.evidence_kind)
                capture_probe(servers[transport])
            for entry in frozen["schedule"]:
                if self._canceled.is_set():
                    stop = "canceled"
                    break
                used = aggregate(records)
                stop = admit(used, entry["limits"], time.monotonic() - started, len(probes))
                if stop:
                    break
                if source_identity() != self.qualification.report["source"]:
                    stop = "source_changed"
                    break
                policy.prepare(entry["limits"])
                server = servers[entry["transport"]]
                question = frozen["questions"][entry["question"]]
                # Persist dispatch intent first. A crash cannot silently reset the round.
                archive.put(f"intent-{entry['index']:02d}.json", entry)
                dispatched_at = time.monotonic()
                job_id = server.dispatch(question)
                dispatched.append(dict(index=entry["index"], job_id=job_id))
                archive.put(f"dispatch-{entry['index']:02d}.json", dict(job_id=job_id))
                capture_probe(server)
                bundle = server.collect(job_id, policy.deadline_at, canceled=self._canceled.is_set)
                bundle["delivery_wall_time_seconds"] = time.monotonic() - dispatched_at
                # Persist failures before independent review (which may be unavailable).
                archive.put(f"run-{entry['index']:02d}.json", bundle)
                scored = score(entry["question"], question, bundle, None)
                record = dict(entry=entry, job_id=job_id, bundle=bundle, score=scored)
                records.append(record)
                budget = bundle["report"].get("budget") or {}
                if not (scored["unknown"] or scored["protocol_defect"] or self._canceled.is_set()
                        or self._hard_limit(budget, entry["limits"])):
                    review = await_review(reviewer, (entry["question"], deepcopy(question), deepcopy(bundle)),
                        remaining=lambda: 4800 - (time.monotonic() - started), canceled=self._canceled.is_set)
                    scored = score(entry["question"], question, bundle, review)
                    record["score"] = scored
                archive.put(f"score-{entry['index']:02d}.json", scored)
                status = bundle["job"]["status"]
                if self._canceled.is_set() or status == "canceled":
                    stop = "canceled"
                elif scored["unknown"]:
                    stop = "unknown_outcome"
                elif scored["protocol_defect"]:
                    stop = "product_protocol_defect"
                elif time.monotonic() - started >= 4800:
                    stop = "round_deadline_exhausted"
                elif self._hard_limit(budget, entry["limits"]):
                    stop = "run_hard_limit"
                elif not scored["state_consistent"]:
                    stop = "product_evidence_defect"
                elif entry["stage"] == "E1" and not scored["e1_gate"]:
                    stop = "e1_gate_failed"
                elif status != "succeeded" and not self._honest_unsolved(bundle):
                    stop = "product_failure"
                elif status == "succeeded" and not scored["evidence_complete"]:
                    stop = "product_evidence_defect"
                elif entry["stage"] == "E2" and not any(
                    e["question"] == entry["question"] for e in frozen["schedule"][entry["index"] + 1:]
                ) and not any(r["entry"]["question"] == entry["question"]
                              and r["score"]["mathematics"] == "pass" and r["score"]["flow_complete"]
                              for r in records):
                    stop = "e2_gate_failed"
                if stop:
                    break
            if stop is None:
                e2 = [r for r in records if r["entry"]["stage"] == "E2"]
                passed = all(any(r["entry"]["question"] == q and r["score"]["mathematics"] == "pass"
                                 and r["score"]["flow_complete"] for r in e2)
                             for q in ("digit_cancel", "sharp", "partitions"))
                stop = "completed" if passed else "e2_gate_failed"
        except Exception as exc:  # Stop and preserve evidence on reviewer/configuration failure.
            stop = "experiment_defect:" + type(exc).__name__
            archive.put("failure.json", dict(category=stop))
        finally:
            for server in servers.values():
                try:
                    capture_probe(server)
                except ValueError:
                    pass  # The failed probe itself remains in the immutable evidence list.
                server.close()
        uncollected = [item for item in dispatched if not any(r["job_id"] == item["job_id"] for r in records)]
        usage = aggregate(records)
        if uncollected:
            usage = dict(accounting_complete=False, observed_s3_subtotal=usage,
                         uncollected=uncollected, cost=None)
        return archive.finish(dict(stop_reason=stop, executed_runs=len(dispatched),
            evidence_kind=self.evidence_kind,
            unexecuted=[e["index"] for e in frozen["schedule"][len(dispatched):]],
            uncollected=uncollected, usage=usage, preflights=len(probes),
            tools_including_environment=None if uncollected else aggregate(records)["tool_calls"] + len(probes),
            wall_time_seconds=time.monotonic() - started, cost=None,
            runs=[dict(entry=r["entry"], job_id=r["job_id"], score=r["score"]) for r in records],
            natural_nonfastpath=any(r["score"]["nonfastpath"] for r in records),
            mechanisms={name: ("observed" if self.evidence_kind == "live" and any(
                event.get("solver_event_type") == event_type for r in records
                for event in r["bundle"]["evidence"].get("timeline", [])) else "not_covered")
                for name, event_type in (("live_challenge", "challenge_replied"),
                                         ("live_traceback", "trace_back_applied"),
                                         ("live_replan", "plan_replaced"))},
            limitations=["Scripted results are not live mathematical capability.",
                         "Independent reviewer identity is an operator attestation, not authentication.",
                         "No automatic resend or continuation of this round is supported."]))

    @staticmethod
    def _hard_limit(budget, limits):
        return (any(budget.get(key, 0) >= limits[field] for key, field in (
            ("logical_calls", "max_model_calls"), ("http_attempts", "max_http_attempts"),
            ("tool_calls", "max_tool_calls"), ("charged_tokens", "max_tokens")))
            or budget.get("wall_time_seconds", 0) >= limits["max_runtime_seconds"])

    @staticmethod
    def _honest_unsolved(bundle):
        result = bundle["job"].get("result") or {}
        review = (bundle["report"].get("semantics") or {}).get("whole_review")
        if review == "invalid_source":
            return False
        steps = (result.get("solver") or {}).get("progress", {}).get("steps", [])
        history = (bundle["report"].get("checks") or {}).get("history", [])
        return (review == "rejected" or any(
            "llm_whole_review_rejected" in item.get("findings", []) for item in history)
            or any(s.get("verdict") in {"REJECT", "CHALLENGE"} for s in steps))
