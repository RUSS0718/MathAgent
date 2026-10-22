"""Append-only, opt-in answer candidates derived from committed phase transitions."""

import hashlib
from copy import deepcopy

from ..redaction import redact
from .confidence import grade_candidate


def enabled(config):
    features = config.get("features", {})
    return features.get("candidate_registry") is True or features.get("best_effort") is True


def latest_records(registry):
    """Expose the latest version per immutable candidate identity in source order."""
    latest = {}
    for record in registry or []:
        latest[record["candidate_id"]] = record
    return list(latest.values())


def prepare_candidates(run, event, updates):
    """Return a registry patch committed atomically with its source transition."""
    state = {**run["state"], **updates}
    registry = deepcopy(run["state"].get("candidate_registry") or [])
    if event["type"].startswith("candidate_") or any(
        event["event_id"] in record["source_event_refs"] for record in registry
    ):
        return {}, []
    actions = []
    kind = event["type"]
    if kind in {"explore_assessed", "exploration_polished"}:
        finding = state["exploration_findings"][-1]
        _add(
            registry,
            actions,
            state,
            event,
            finding.get("solution_candidate"),
            "EXPLORE",
            "complete" if finding["assessment"] == "SOLVED" else "partial",
            [],
            [],
        )
    elif kind == "step_reported":
        step_id = event["step_id"]
        report = state["steps"][step_id]["report"]
        _add(
            registry,
            actions,
            state,
            event,
            report.get("solution_candidate"),
            "STEP_EXECUTE",
            report.get("answer_completeness", "partial"),
            [step_id],
            [],
        )
    elif kind == "final_candidate_generated":
        attempt = state["final_solution_attempts"][-1]
        facts = attempt["accepted_results"]
        refs = list(dict.fromkeys(fact["source"] for fact in facts if fact.get("source")))
        evidence = [ref for fact in facts for ref in fact.get("evidence_refs", [])]
        _add(
            registry,
            actions,
            state,
            event,
            attempt["candidate"],
            "FINAL_GENERATE",
            "complete",
            refs,
            evidence,
        )
        if actions:
            registry[-1]["dependency_refs"] = list(
                dict.fromkeys(
                    [
                        *refs,
                        *[fact["result_id"] for fact in facts if fact.get("result_id")],
                        *[dep for fact in facts for dep in fact.get("dependencies", [])],
                    ]
                )
            )
    elif kind in {"solution_review_assessed", "final_candidate_reviewed", "step_reviewed"}:
        source = {
            "solution_review_assessed": "EXPLORE",
            "final_candidate_reviewed": "FINAL_GENERATE",
            "step_reviewed": "STEP_EXECUTE",
        }[kind]
        targets = [
            record
            for record in latest_records(registry)
            if record["source_phase"] == source
            and record["plan_version"] == state["plan_version"]
            and record["attempt_index"] == state["attempt_index"]
        ]
        if kind == "step_reviewed":
            targets = [record for record in targets if event["step_id"] in record["step_refs"]]
            review = state["steps"][event["step_id"]]["verification"]
        elif kind == "final_candidate_reviewed":
            review = state["final_solution_attempts"][-1]["review"]
            targets = targets[-1:]
        else:
            review = event
            reviewed_text = state["exploration_findings"][-1].get("solution_candidate", "")
            reviewed_hash = hashlib.sha256(redact(reviewed_text).encode("utf-8")).hexdigest()
            targets = [record for record in targets if record["answer_hash"] == reviewed_hash][-1:]
        for record in targets:
            _review(registry, actions, record, event, review, source == "STEP_EXECUTE")
    elif kind in {"trace_back_applied", "plan_archived"}:
        failure = state["failure_records"][-1]
        invalid_steps = set(failure.get("archived_steps", {}))
        if kind == "plan_archived":
            invalid_steps.update(
                step["step_id"] for step in (failure.get("archived_plan") or {}).get("steps", [])
            )
        invalid_results = {
            r["result_id"] for r in failure.get("invalidated_results", []) if r.get("result_id")
        }
        invalid = invalid_steps | invalid_results
        plan_steps = state.get("plan", {}).get("steps", [])
        changed = True
        while changed:
            before = set(invalid)
            for step in plan_steps:
                if invalid.intersection(step.get("depends_on", [])):
                    invalid.add(step["step_id"])
            changed = before != invalid
        latest = latest_records(registry)
        changed = True
        while changed:
            changed = False
            for record in latest:
                if record["candidate_id"] in invalid or record["review_state"] == "invalidated":
                    continue
                if invalid.intersection(record["dependency_refs"]):
                    invalid.add(record["candidate_id"])
                    changed = True
        for record in latest:
            if record["candidate_id"] in invalid:
                _version(
                    registry,
                    actions,
                    record,
                    event,
                    "candidate_invalidated",
                    review_state="invalidated",
                    selection_eligible=False,
                    invalidated_by=[*record["invalidated_by"], event["event_id"]],
                )
    for record in registry[len(run["state"].get("candidate_registry") or []):]:
        record["evidence_grade"] = grade_candidate(record, state, events=[*run["events"], {**event, "run_id": state["run_id"]}])
        if record["evidence_grade"]["confidence_level"] == "rejected":
            record["selection_eligible"] = False
    return ({"candidate_registry": registry} if actions else {}), actions


def _add(registry, actions, state, event, text, phase, completeness, steps, evidence):
    if not isinstance(text, str) or not text.strip():
        return
    text = redact(text)
    complete = completeness == "complete"
    candidate_id = f"{state['run_id']}:candidate:{event['event_id']}"
    audit_id = f"candidate-added:{candidate_id}"
    record = {
        "candidate_id": candidate_id,
        "version": 1,
        "run_id": state["run_id"],
        "problem_hash": state["problem_hash"],
        "answer_text": text,
        "answer_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_phase": phase,
        "plan_version": state["plan_version"],
        "attempt_index": state["attempt_index"],
        "step_refs": steps,
        "dependency_refs": [*steps],
        "created_event_id": audit_id,
        "source_event_refs": [event["event_id"]],
        "answer_completeness": "complete" if complete else "partial",
        "review_state": "eligible_unreviewed" if complete else "draft",
        "evidence_refs": evidence,
        "known_objections": [],
        "invalidated_by": [],
        "selection_eligible": complete,
    }
    registry.append(record)
    actions.append(_audit(audit_id, "candidate_added", record))


def _review(registry, actions, record, event, review, local):
    if record["review_state"] in {"invalidated", "refuted"}:
        return
    verdict = review.get("verdict")
    if not isinstance(verdict, str):
        return
    if verdict == "ACCEPT" and (not local or review.get("valid") is True):
        _version(
            registry,
            actions,
            record,
            event,
            "candidate_reviewed",
            review_state="locally_reviewed" if local else "whole_reviewed",
            evidence_refs=[*record["evidence_refs"], event["event_id"]],
        )
    elif verdict in {"REJECT", "CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN"}:
        # A missing proof obligation is an objection, not decisive disproof.
        counterexample = review.get("counterexample")
        refuted = isinstance(counterexample, str) and bool(counterexample.strip())
        objection = (
            counterexample
            if refuted
            else review.get("reason")
            or review.get("objection")
            or "review_rejected_without_decisive_evidence"
        )
        _version(
            registry,
            actions,
            record,
            event,
            "candidate_refuted" if refuted else "candidate_reviewed",
            review_state="refuted" if refuted else record["review_state"],
            selection_eligible=False if refuted else record["selection_eligible"],
            known_objections=[*record["known_objections"], objection],
            evidence_refs=[*record["evidence_refs"], event["event_id"]],
        )


def _version(registry, actions, record, event, kind, **changes):
    updated = {
        **deepcopy(record),
        **changes,
        "version": record["version"] + 1,
        "source_event_refs": [*record["source_event_refs"], event["event_id"]],
    }
    registry.append(updated)
    actions.append(_audit(f"{kind}:{record['candidate_id']}:{updated['version']}", kind, updated))


def _audit(event_id, kind, record):
    return {
        "event_id": event_id,
        "type": kind,
        "candidate_id": record["candidate_id"],
        "candidate_version": record["version"],
        "evidence_refs": record["evidence_refs"],
        "usage_source": "no_additional_calls",
    }
