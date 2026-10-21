"""JSON Evidence Pack export with product trace redaction."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from llm_response import public_attempt

from .final_evidence import bind_verification
from .redaction import redact
from .verification import VerificationResult


class EvidencePackExporter:
    """Export observable summaries while excluding sensitive request bodies."""

    version = "evidence-v0.1"
    report_version = "report-v0.2"

    def export(
        self,
        snapshot: Mapping[str, Any],
        *,
        events: Sequence[Mapping[str, Any]] = (),
        tool_results: Sequence[Mapping[str, Any]] = (),
        verification: VerificationResult | Mapping[str, Any] | None = None,
        artifacts: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        """Return a JSON-compatible, redacted Evidence Pack."""

        if not tool_results:
            result = snapshot.get("result") if isinstance(snapshot.get("result"), Mapping) else {}
            stored_tools = result.get("tool_results", [])
            tool_results = [item for item in stored_tools if isinstance(item, Mapping)]
        verification_data = bind_verification(str(snapshot.get("final_response") or ""), _verification_dict(verification))
        pack = {
            "version": self.version,
            # A Run's update timestamp makes repeated reads byte-stable.
            "exported_at": snapshot.get("updated_at") or datetime.now(UTC).isoformat(),
            "run": {
                "run_id": snapshot.get("run_id"),
                "profile": snapshot.get("profile"),
                "status": snapshot.get("status"),
                "stage": snapshot.get("stage"),
                "input_ref": snapshot.get("input_ref"),
                "asset_refs": snapshot.get("asset_refs", []),
                "final_response": snapshot.get("final_response"),
                "error": snapshot.get("error"),
            },
            "timeline": [_event_summary(event, index) for index, event in enumerate(events, 1)],
            "agent": {"summary": snapshot.get("agent_summary", "")},
            "tools": [_tool_summary(result) for result in tool_results],
            "request_attempts": _attempts(snapshot),
            "budget": (snapshot.get("result") or {}).get("budget"),
            "verification": verification_data,
            "artifacts": [redact(artifact) for artifact in artifacts],
            "feature_status": {
                "execution": "implemented",
                "python_math": "experimental",
                "multimodal": _multimodal_status(snapshot),
                "verification": "implemented",
            },
        }
        safe = redact(pack)
        safe["evidence_id"] = str(snapshot.get("run_id") or "unknown")
        safe["mode"] = _mode(snapshot)
        safe["report"] = self.report(snapshot, tool_results=tool_results, verification=verification_data)
        return safe

    def report(
        self,
        snapshot: Mapping[str, Any],
        *,
        tool_results: Sequence[Mapping[str, Any]] = (),
        verification: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the public report DTO without exposing prompts or hidden reasoning."""

        result = snapshot.get("result") if isinstance(snapshot.get("result"), Mapping) else {}
        answer = snapshot.get("final_response") or result.get("final_response") or ""
        summary = snapshot.get("agent_summary") or result.get("summary") or ""
        check = bind_verification(str(answer), verification)
        return redact({
            "answer": answer,
            "request_attempts": _attempts(snapshot),
            "budget": (snapshot.get("result") or {}).get("budget"),
            "public_summary": summary,
            "stage": snapshot.get("stage"),
            "asset_refs": snapshot.get("asset_refs", []),
            "vision_status": snapshot.get("vision_status"),
            "tool_summaries": [_tool_summary(item) for item in tool_results],
            "checks": check,
            "limitations": ["公开报告省略完整提示、隐藏推理、凭证和原始图片。"],
        })

    def to_json(self, pack: Mapping[str, Any]) -> str:
        """Serialize an Evidence Pack with stable UTF-8 JSON."""

        return json.dumps(pack, ensure_ascii=False, sort_keys=True, indent=2)


def _verification_dict(value: VerificationResult | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, VerificationResult):
        return {
            "status": value.status,
            "findings": list(value.findings),
            "checker": value.checker,
        }
    if isinstance(value, Mapping):
        return dict(value)
    return {"status": "unknown", "findings": ["verification_not_run"]}


def _event_summary(event: Mapping[str, Any], index: int) -> dict[str, Any]:
    summary = {
        "evidence_id": f"event_{index}",
        "type": event.get("type", "unknown"),
        "sequence": event.get("sequence", index),
        "status": event.get("status"),
        "stage": event.get("stage"),
        "summary": event.get("summary", ""),
        "error_category": event.get("error_category"),
    }
    for key in ("tool_call_id", "protocol", "tool_name"):
        if event.get(key) is not None:
            summary[key] = event[key]
    return summary


def _tool_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = {
        "evidence_id": result.get("evidence_id", result.get("name", "tool")),
        "request_id": result.get("request_id"),
        "tool_call_id": result.get("tool_call_id"),
        "protocol": result.get("protocol"),
        "continuation_tool_call_id": result.get("continuation_tool_call_id"),
        "continuation_status": result.get("continuation_status"),
        "continuation_response_received": result.get("continuation_response_received"),
        "continuation_finish_reason": result.get("continuation_finish_reason"),
        "continuation_request_id": result.get("continuation_request_id"),
        "transport_mode": result.get("transport_mode", "unavailable"),
        "name": result.get("name"),
        "status": result.get("status"),
        "duration_seconds": result.get("duration_seconds"),
        "parameter_summary": result.get("parameter_summary", ""),
        "result_summary": result.get("result_summary", ""),
        "error_category": result.get("error_category"),
    }
    value = result.get("value")
    if result.get("name") == "polynomial_check" and isinstance(value, Mapping):
        candidates = value.get('candidates', [])
        observations = [item.get('in_domain') for item in candidates if isinstance(item, Mapping)]
        summary['domain_status'] = 'out_of_domain' if any(item is False for item in observations) else ('in_domain' if observations and all(item is True for item in observations) else 'unknown')
        summary["candidate_status"] = value.get("candidate_status", "unknown")
        summary["coverage_status"] = value.get("coverage_status", "unknown")
        summary["limitations"] = value.get("limitations", [])
        summary["checker_evidence_id"] = value.get("evidence_id")
    return summary


def _multimodal_status(snapshot: Mapping[str, Any]) -> str:
    vision_status = snapshot.get("vision_status")
    if vision_status == "implemented":
        return "implemented"
    if vision_status == "unavailable":
        return "unavailable"
    return "planned"


def _mode(snapshot: Mapping[str, Any]) -> str:
    value = snapshot.get("run_mode") or snapshot.get("execution_mode") or snapshot.get("mode")
    return value if value in {"live", "fake", "replay", "experimental", "unavailable", "planned"} else "unavailable"


def replay_evidence(pack: Mapping[str, Any]) -> dict[str, Any]:
    """Replay a previously saved public Evidence Pack without executing anything."""

    if not isinstance(pack, Mapping) or not pack.get("evidence_id"):
        raise ValueError("replay_invalid")
    result = json.loads(json.dumps(pack, ensure_ascii=False))
    result["mode"] = "replay"
    result.setdefault("limitations", ["回放仅读取已保存 Evidence Pack。"])
    return redact(result)


__all__ = ["EvidencePackExporter", "replay_evidence"]


def _attempts(snapshot):
    result = snapshot.get("result") if isinstance(snapshot.get("result"), Mapping) else {}
    records = snapshot.get("request_attempts", result.get("request_attempts", []))
    return [public_attempt(item, run_id=item.get("run_id"), role=item.get("role")) for item in records if isinstance(item, Mapping)]
