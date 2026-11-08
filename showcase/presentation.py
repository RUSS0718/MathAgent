"""Independent, conservative presentation bindings over a public Job snapshot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy

from .final_evidence import artifact_identity, bind_verification
from .redaction import redact_text

SCHEMA_VERSION = "presentation-v1"
POLICY_VERSION = "faithful-output-v1"
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
    snapshot["fingerprint"] = _digest(snapshot)
    return snapshot


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
                       "claim_refs": [item["id"] for item in snapshot["sources"]]})
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
        supported = kind == "mathematical" and exact and bool(refs)
        item = {
            "id": f"paragraph:{index}", "version": 1, "text": text, "kind": kind,
            "claim_refs": refs, "status": "current" if supported or kind == "editorial" else "pending_verification",
            "grade": "llm_reviewed" if supported else "not_verified",
            "binding": "same_artifact" if exact else "artifact_changed" if kind == "mathematical" else "unbound",
        }
        if kind == "mathematical" and not supported:
            item["proof_attempt"] = {"id": "presentation-proof:" + _digest({"text": text, "source": snapshot["fingerprint"]}),
                                     "status": "proposed", "grade": "not_verified"}
        output.append(item)
    scope = snapshot["scope"]
    complete = (snapshot["job_status"] == "succeeded" and scope["total"] > 0
                and scope["covered"] == scope["total"] and not scope["unresolved"])
    artifact = {
        "schema_version": SCHEMA_VERSION, "policy_version": POLICY_VERSION,
        "job_id": snapshot["job_id"], "mode": mode, "status": "ready",
        "answer": snapshot["answer"], "answer_artifact": snapshot["answer_artifact"],
        "source_fingerprint": snapshot["fingerprint"], "source_versions": snapshot["versions"],
        "sources": snapshot["sources"], "paragraphs": output,
        "budget": snapshot["budget"], "request_attempts": snapshot["request_attempts"],
        "scope": scope, "completion": "complete" if complete else "partial" if snapshot["answer"] else "incomplete",
        "formal_verification": "not_verified", "revalidation_reason": None,
        "renderer": "deterministic-public-template-v1",
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
    return current
