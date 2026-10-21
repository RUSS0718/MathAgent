"""Exact public artifact identity and append-only verification observations."""
from __future__ import annotations

import hashlib
import json
import platform
import unicodedata
from collections.abc import Mapping
from typing import Any

from .redaction import redact_text


def artifact_identity(answer: str) -> dict[str, str]:
    canonical = unicodedata.normalize("NFC", redact_text(answer).replace("\r\n", "\n").replace("\r", "\n"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {"schema": "public-answer-nfc-lf-v1", "sha256": digest, "id": f"answer:{digest}"}


def bind_verification(answer: str, check: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Keep observations immutable and only accept evidence for this exact artifact."""
    current = artifact_identity(answer)
    source = dict(check or {"status": "unknown", "findings": ["verification_not_run"]})
    if source.get("checker") == "polynomial_check":
        source.setdefault("scope", "polynomial_candidates")
        source.setdefault("checker_version", "polynomial-check-v1")
        for finding in source.get("findings", []):
            if finding.startswith("polynomial_") and ":" in finding:
                key, value = finding.removeprefix("polynomial_").split(":", 1)
                source.setdefault(key, value)
    history = list(source.get("history", []))
    if not history:
        observation = {key: value for key, value in source.items() if key not in {"artifact", "acceptance"}}
        observation.update({
            "artifact": source.get("artifact", current),
            "checker_version": source.get("checker_version", "lightweight_v0"),
            "environment": source.get("environment", {"python": platform.python_version()}),
            "scope": source.get("scope", "shape_and_tool_consistency"),
            "limitations": source.get("limitations", ["不证明数学正确性或完整解集。"]),
        })
        encoded = json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        observation["check_id"] = hashlib.sha256(encoded.encode()).hexdigest()
        history.append(observation)
    latest = history[-1]
    same = latest.get("artifact") == current
    status = latest.get("status", "unknown") if same else "unknown"
    if latest.get("scope") in {"polynomial_candidates", "shape_and_tool_consistency"} and status == "pass":
        status = "unknown"  # Scoped consistency/candidate checks cannot accept a final mathematical claim.
    return {**source, "status": status, "artifact": current, "history": history,
            "acceptance": "accepted" if same and status == "pass" else "needs_review",
            "binding": "same_artifact" if same else "artifact_changed"}


def append_verification(answer: str, stored: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    previous = bind_verification(answer, stored)
    observation = bind_verification(answer, {
        "status": "unknown", "checker": "polynomial_check",
        "checker_version": "polynomial-check-v1", "scope": "polynomial_candidates",
        "candidate_status": result.get("candidate_status", "unknown"),
        "coverage_status": result.get("coverage_status", "unknown"),
        "limitations": result.get("limitations", []), "evidence": dict(result),
    })["history"][0]
    history = [*previous["history"], observation]
    return bind_verification(answer, {**observation, "history": history})


def checked_verification(answer: str, checked: Any, tools: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind a checker invocation, retaining the actual structured candidate evidence."""
    payload = {"status": checked.status, "checker": checked.checker, "findings": list(checked.findings)}
    if checked.checker == "polynomial_check":
        for tool in reversed(tools):
            if tool.get("name") != "polynomial_check":
                continue
            value = tool.get("value")
            if not isinstance(value, Mapping):
                try:
                    value = json.loads(tool.get("result_summary", "{}"))
                except (TypeError, ValueError):
                    value = {}
            if isinstance(value, Mapping):
                payload.update({"evidence": dict(value), "limitations": value.get("limitations", []),
                                "checker_version": value.get("checker_version", "polynomial-check-v1")})
                break
    return bind_verification(answer, payload)
