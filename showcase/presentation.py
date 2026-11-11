"""Independent, conservative presentation bindings over a public Job snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy

from .final_evidence import artifact_identity, bind_verification
from .redaction import redact_text

SCHEMA_VERSION = "presentation-v1"
LEGACY_POLICY_VERSION = "faithful-output-v1"
POLICY_VERSION = "faithful-output-v2"
MODES = ("solve", "teach", "report")


def normalize_mode(value):
    if value is None:
        return "solve"
    if not isinstance(value, str) or value not in MODES:
        raise ValueError("presentation_mode_invalid")
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def presentation_snapshot(job, public_report=None):
    """Select public identities; never copy arbitrary solver or checker payloads."""
    result = dict(job.get("result") or {})
    report = public_report.get("report") if isinstance(public_report, Mapping) else None
    if isinstance(report, Mapping):
        result["final_response"] = report.get("answer", result.get("final_response"))
        result["verification"] = report.get("checks", result.get("verification"))
        result["budget"] = report.get("budget", result.get("budget"))
        result["request_attempts"] = report.get("request_attempts", result.get("request_attempts"))
        solver_report = public_report.get("solver")
        if isinstance(solver_report, Mapping):
            result["solver"] = solver_report.get("solver", solver_report)
    answer = redact_text(str(result.get("final_response") or ""))
    solver = result.get("solver") or {}
    semantics = solver.get("semantics") or {}
    progress = solver.get("progress") or {}
    roots = progress.get("root_obligations") or {}
    checked = bind_verification(answer, result.get("verification"))
    reviewed = (semantics.get("whole_review") == "accepted"
                and semantics.get("binding") == "same_artifact")
    sources = []
    for item in checked.get("history", []):
        if (item.get("artifact") != artifact_identity(answer)
                or item.get("scope") != "whole_solution_llm_review" or not reviewed):
            continue
        public = {"artifact": artifact_identity(answer), "scope": "whole_solution_llm_review",
                  "grade": "llm_reviewed", "status": "current"}
        public["id"] = "verification:" + _digest({**public, "check_id": item.get("check_id")})
        sources.append(public)
    items = [{"ordinal": item["ordinal"], "status": item.get("status", "unresolved")}
             for item in roots.get("items", [])
             if isinstance(item, Mapping) and type(item.get("ordinal")) is int]
    snapshot = {
        "job_id": job["job_id"], "answer": answer, "answer_artifact": artifact_identity(answer),
        "job_status": job.get("status"), "sources": sources,
        "versions": {"job_status": job.get("status"),
                     "job_updated_at": job.get("updated_at"),
                     "source_event_id": job.get("source_event_id"),
                     "state_revision": solver.get("state_revision"),
                     "specification_version": progress.get("specification_version"),
                     "graph_version": (progress.get("proof_graph") or {}).get("graph_version")},
        "scope": {"covered": roots.get("covered", 0), "total": roots.get("total", 0),
                  "unresolved": [item for item in items if item["status"] != "satisfied"]},
        "whole_review": semantics.get("whole_review", "not_reviewed"),
        "answer_binding": semantics.get("binding", "unbound"),
        "formal_verification": "not_verified",
        "budget": _public_budget(result.get("budget")),
        "request_attempts": _public_attempts(result.get("request_attempts")),
    }
    if result.get("presentation_policy_version") == POLICY_VERSION:
        snapshot["policy_version"] = POLICY_VERSION
        evidence = solver.get("presentation_evidence") or {}
        snapshot["versions"]["specification_version"] = evidence.get("specification_version")
        snapshot["versions"]["graph_version"] = evidence.get("graph_version")
        snapshot["sources"].extend(evidence.get("sources", []))
        snapshot["verified_claims"] = evidence.get("verified_claims", [])
        snapshot["selection"] = _selection(solver)
        formal = _formal_source(solver.get("formal_verification"), snapshot["versions"])
        if formal:
            snapshot["sources"].append(formal)
    snapshot["fingerprint"] = _digest(snapshot)
    return snapshot


def _selection(solver):
    decision = solver.get("best_effort")
    if not decision:
        return None
    result = {key: decision[key] for key in ("status", "reason_codes", "termination_reason",
              "selected_candidate_id", "selected_candidate_version", "selected_answer_artifact",
              "evidence_grade") if key in decision}
    candidate = next((item for item in solver.get("candidate_history", [])
                      if item.get("candidate_id") == decision.get("selected_candidate_id")
                      and item.get("version") == decision.get("selected_candidate_version")), None)
    result["completeness"] = candidate.get("completeness") if candidate else None
    result["eligible"] = candidate.get("eligible", False) if candidate else False
    return result


def _formal_source(formal, versions):
    """Project an existing accepted receipt, without copying its proof or logs."""
    if not isinstance(formal, Mapping) or formal.get("status") != "solved":
        return None
    current = formal.get("current") or {}
    grade = formal.get("grade")
    if (grade not in {"L2", "L3"} or current.get("status") != "solved"
            or current.get("grade") != grade
            or current.get("attempt_id") != formal.get("current_attempt_id")):
        return None
    proof = current.get("proof_artifact") or {}
    specs = current.get("specifications") or {}
    specification_version = (specs.get("original_to_spec") or {}).get("problem_spec_version")
    if (proof.get("accepted") is not True
            or (versions.get("specification_version") is not None
                and specification_version != versions["specification_version"])):
        return None
    correspondence = all((specs.get(key) or {}).get("review_status") == "reviewed"
                         for key in ("original_to_spec", "spec_to_target", "target_to_environment"))
    public = {
        "kind": "VerificationRecord", "status": "current",
        "grade": "L3" if grade == "L3" and correspondence else "L2",
        "scope": "original_problem" if grade == "L3" and correspondence else "formal_target",
        "attempt_id": current["attempt_id"], "specification_version": specification_version,
        **{key: proof.get(key) for key in ("target_hash", "proof_hash", "environment_hash")},
    }
    public["id"] = "verification:" + _digest(public)
    return public


def _public_budget(value):
    if not isinstance(value, Mapping):
        return None
    return {key: value[key] for key in value}


def _public_attempts(value):
    if not isinstance(value, list):
        return []
    allowed = ("attempt_id", "solver_call_id", "status", "role", "transport",
               "usage", "error_category")
    return [{key: item[key] for key in allowed if key in item}
            for item in value if isinstance(item, Mapping)]


def _default_paragraphs(snapshot, mode):
    paragraphs = []
    if mode == "teach":
        paragraphs.append({"kind": "editorial", "text": "先阅读原答案，再对照验证依据与尚未完成的义务。"})
    elif mode == "report":
        scope = snapshot["scope"]
        paragraphs.append({"kind": "editorial", "text":
                           f"根义务覆盖 {scope['covered']}/{scope['total']}。以下内容保留原答案及其验证范围。"})
    paragraphs.append({"kind": "mathematical", "text": snapshot["answer"],
                       "claim_refs": [item["id"] for item in snapshot["sources"]
                                      if item.get("artifact") == snapshot["answer_artifact"]]})
    if snapshot.get("policy_version") == POLICY_VERSION:
        scope = snapshot["scope"]
        paragraphs.append({"kind": "editorial", "text":
                           f"交付范围：已满足 {scope['covered']}/{scope['total']} 项根义务，"
                           f"仍有 {len(scope['unresolved'])} 项未完成。以下逐项列出当前可引用依据。"})
        paragraphs.extend({"kind": "mathematical", "text": claim["text"],
                           "claim_refs": claim["claim_refs"]}
                          for claim in snapshot.get("verified_claims", [])
                          if claim["text"] != snapshot["answer"])
    for source in snapshot["sources"]:
        if source["scope"] in {"formal_target", "original_problem"}:
            paragraphs.append({"kind": "editorial", "text":
                               f"形式化依据：{source['grade']}，核验范围为 {source['scope']}。"
                               "形式目标核验与原答案文字审查分别记录。",
                               "claim_refs": [source["id"]]})
    return paragraphs


def build_presentation(snapshot, mode, *, paragraphs=None):
    """Build an output artifact; a rewrite cannot inherit exact-text verification.

    Paragraphs are trusted renderer output, never a client-supplied assertion of
    verification. Only an exact quotation of the current answer can reuse its
    scoped review. Any other mathematical text stays a proposed proof attempt.
    """
    mode = normalize_mode(mode)
    sources = {item["id"]: item for item in snapshot["sources"]}
    output = []
    draft = (_default_paragraphs(snapshot, mode) if paragraphs is None else paragraphs)
    for index, paragraph in enumerate(draft if snapshot["answer"] else [], 1):
        text = redact_text(paragraph["text"])
        kind = paragraph.get("kind", "mathematical")
        if kind not in {"editorial", "mathematical"}:
            raise ValueError("presentation_paragraph_invalid")
        refs = [ref for ref in paragraph.get("claim_refs", []) if ref in sources]
        exact = text == snapshot["answer"]
        matching = [sources[ref] for ref in refs
                    if sources[ref].get("artifact") == artifact_identity(text)
                    and sources[ref].get("status") == "current"
                    and sources[ref].get("grade") in {"llm_reviewed", "tool_verified"}]
        supported = kind == "mathematical" and bool(matching)
        item = {
            "id": f"paragraph:{index}", "version": 1, "text": text, "kind": kind,
            "claim_refs": refs, "status": "current" if supported or kind == "editorial" else "pending_verification",
            "grade": ("llm_reviewed" if any(source["grade"] == "llm_reviewed" for source in matching)
                      else "tool_verified") if supported else "not_verified",
            "binding": "same_artifact" if exact or supported else "artifact_changed" if kind == "mathematical" else "unbound",
        }
        if kind == "mathematical" and not supported:
            item["proof_attempt"] = {"id": "presentation-proof:" + _digest({"text": text, "source": snapshot["fingerprint"]}),
                                     "status": "proposed", "grade": "not_verified"}
        output.append(item)
    scope = snapshot["scope"]
    complete = (snapshot["job_status"] == "succeeded" and scope["total"] > 0
                and scope["covered"] == scope["total"] and not scope["unresolved"])
    selection = snapshot.get("selection")
    no_candidate = bool(selection and (selection.get("status") != "selected"
                        or not selection.get("eligible")
                        or selection.get("selected_answer_artifact") != snapshot["answer_artifact"]))
    if snapshot.get("policy_version") == POLICY_VERSION:
        reviewed_answer = any(item["kind"] == "mathematical" and item["text"] == snapshot["answer"]
                              and item["status"] == "current" and item["grade"] == "llm_reviewed"
                              for item in output)
        complete = (complete and snapshot["whole_review"] == "accepted"
                    and snapshot["answer_binding"] == "same_artifact"
                    and reviewed_answer and not no_candidate
                    and (not selection or selection.get("completeness") == "complete"))
    artifact = {
        "schema_version": SCHEMA_VERSION, "policy_version": snapshot.get("policy_version", LEGACY_POLICY_VERSION),
        "job_id": snapshot["job_id"], "mode": mode, "status": "ready",
        "answer": snapshot["answer"], "answer_artifact": snapshot["answer_artifact"],
        "source_fingerprint": snapshot["fingerprint"], "source_versions": snapshot["versions"],
        "sources": snapshot["sources"], "paragraphs": output,
        "budget": snapshot["budget"], "request_attempts": snapshot["request_attempts"],
        "scope": scope, "completion": "incomplete" if no_candidate else "complete" if complete else "partial" if snapshot["answer"] else "incomplete",
        "formal_verification": "not_verified", "revalidation_reason": None,
        "renderer": "deterministic-public-template-v1",
    }
    if snapshot.get("policy_version") == POLICY_VERSION:
        artifact["renderer"] = "evidence-walkthrough-v2"
        artifact["output_request"] = {
            "id": "output:" + _digest({"job_id": snapshot["job_id"], "mode": mode,
                                        "source": snapshot["fingerprint"], "policy": POLICY_VERSION}),
            "kind": "presentation_only", "model_calls": 0, "solver_resumed": False,
        }
        artifact["delivery"] = {
            "source_fingerprint": snapshot["fingerprint"], "source_versions": snapshot["versions"],
            "verified_claims": [] if no_candidate else [deepcopy(item) for item in output
                if item["kind"] == "mathematical" and item["status"] == "current"],
            "unresolved_goals": scope["unresolved"], "selection": selection,
            "grade": "llm_reviewed" if reviewed_answer and snapshot["whole_review"] == "accepted"
                     and snapshot["answer_binding"] == "same_artifact" and not no_candidate else "not_verified",
            "budget": snapshot["budget"], "request_attempts": snapshot["request_attempts"],
        }
    digest = _digest(artifact)
    artifact["artifact"] = {"schema": SCHEMA_VERSION, "sha256": digest, "id": "presentation:" + digest}
    return deepcopy(artifact)


def failed_presentation(snapshot, mode, reason):
    artifact = build_presentation(snapshot, mode, paragraphs=[])
    artifact["status"] = "failed"
    artifact["failure_reason"] = reason
    artifact["fallback"] = {
        "answer": snapshot["answer"], "artifact": snapshot["answer_artifact"],
        "binding": "same_artifact", "available": bool(snapshot["answer"]),
    }
    payload = {key: value for key, value in artifact.items() if key != "artifact"}
    digest = _digest(payload)
    artifact["artifact"] = {"schema": SCHEMA_VERSION, "sha256": digest, "id": "presentation:" + digest}
    return artifact


def revalidate(artifact, snapshot):
    """Project staleness without mutating a historical output or reviving evidence."""
    current = deepcopy(artifact)
    if artifact["source_fingerprint"] != snapshot["fingerprint"]:
        current["status"] = "needs_review"
        current["revalidation_reason"] = "source_changed"
        for paragraph in current["paragraphs"]:
            if paragraph["kind"] == "mathematical":
                paragraph["status"] = "needs_review"
                paragraph["grade"] = "not_verified"
        if "delivery" in current:
            current["delivery"]["verified_claims"] = []
            current["delivery"]["grade"] = "not_verified"
            current["formal_verification"] = "not_verified"
            current["completion"] = "partial" if current["answer"] else "incomplete"
            for source in current["sources"]:
                source["status"] = "needs_review"
    return current
