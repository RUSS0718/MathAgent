"""Versioned, opt-in context history projection and final-payload admission."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from math import ceil
from typing import Any

_DERIVED_PROJECTION_FIELDS = {
    "session_history_summary", "_context_pack", "context_pack", "_context_policy",
}
_CONTEXT_CAPACITY_VERSION = "context-capacity-v1"
_TOKEN_ESTIMATOR_VERSION = "utf8-bytes-per-three-v1"


class ContextCapacityExceeded(RuntimeError):
    """A known context policy rejected a request before provider dispatch."""

    no_dispatch = True

    def __init__(self, category: str, pack: dict[str, Any]) -> None:
        self.category = category
        self.pack = pack
        super().__init__(category)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def frozen_policy(config: dict[str, Any]) -> dict[str, Any]:
    enabled = config.get("features", {}).get("context_pack") is True
    if not enabled:
        policy = {"enabled": False, "version": "context-pack-v1"}
        policy["policy_sha256"] = _digest(policy)
        return policy
    policy = deepcopy(config.get("context_capacity"))
    required = {
        "version", "profile_version", "provider", "model", "endpoint", "cap_source",
        "cap_source_date", "input_cap_tokens", "output_reserve_tokens",
        "safety_margin_tokens", "token_estimator_version",
    }
    if not isinstance(policy, dict) or required - policy.keys():
        raise ValueError("context_capacity_policy_incomplete")
    for key in ("provider", "model", "endpoint", "profile_version", "version",
                "cap_source", "token_estimator_version"):
        if not isinstance(policy[key], str) or not policy[key].strip():
            raise ValueError(f"context_capacity_{key}_invalid")
    if policy["version"] != _CONTEXT_CAPACITY_VERSION:
        raise ValueError("context_capacity_version_unsupported")
    if policy["token_estimator_version"] != _TOKEN_ESTIMATOR_VERSION:
        raise ValueError("context_capacity_token_estimator_unsupported")
    for key in ("output_reserve_tokens", "safety_margin_tokens"):
        if type(policy[key]) is not int or policy[key] < 0:
            raise ValueError(f"context_capacity_{key}_invalid")
    cap = policy["input_cap_tokens"]
    if cap is not None and (type(cap) is not int or cap < 1):
        raise ValueError("context_capacity_input_cap_tokens_invalid")
    if cap is not None and not policy.get("cap_source_date"):
        raise ValueError("context_capacity_source_date_required")
    policy.update(enabled=True, history_input_limit_bytes=policy.get("history_input_limit_bytes", 32_768),
                  history_summary_limit_bytes=policy.get("history_summary_limit_bytes", 2_048),
                  recent_history_exchanges=policy.get("recent_history_exchanges", 1))
    if (type(policy["history_input_limit_bytes"]) is not int
            or policy["history_input_limit_bytes"] < 0
            or type(policy["history_summary_limit_bytes"]) is not int
            or policy["history_summary_limit_bytes"] < 0
            or type(policy["recent_history_exchanges"]) is not int
            or policy["recent_history_exchanges"] < 1):
        raise ValueError("context_capacity_history_limits_invalid")
    policy["policy_sha256"] = _digest(policy)
    return policy


def prepare_context_request(request: dict[str, Any], policy: dict[str, Any], *, run_id: str,
                            state_revision: int, problem_hash: str,
                            config_hash: str | None = None,
                            summarizer=None) -> dict[str, Any]:
    """Deduplicate exact history and retain a bounded, non-authoritative archive summary."""
    prepared = deepcopy(request)
    if not policy.get("enabled"):
        return prepared
    keep_count = policy.get("recent_history_exchanges", 1)
    if type(keep_count) is not int or keep_count < 1:
        raise ValueError("context_capacity_history_limits_invalid")
    # These fields are derived from a prior projection. Never accept them as source
    # material when rebuilding from a restored or rolled-back request.
    for field in _DERIVED_PROJECTION_FIELDS:
        prepared.pop(field, None)
    specification_version = prepared.get("problem_spec_version")
    if specification_version is None:
        specification_version = prepared.get("specification_version")
    source_metadata = {
        "problem_hash": problem_hash,
        "specification_version": specification_version,
        "config_hash": config_hash,
        "source_state_revision": state_revision,
        "run_id": run_id,
        "role": prepared.get("role"),
    }
    history = prepared.get("session_history")
    if not isinstance(history, list) or not history:
        prepared["_context_pack"] = {
            "history_refs": [],
            "summary_status": "not_needed",
            **source_metadata,
        }
        return prepared

    history = [_without_derived_history_fields(entry) for entry in history]
    unique, seen = [], set()
    for entry in history:
        digest = _digest(entry)
        if digest not in seen:
            unique.append((entry, digest))
            seen.add(digest)
    recent_indexes = set(range(max(0, len(unique) - keep_count), len(unique))) if keep_count else set()
    report = prepared.get("report")
    current_receipts = report.get("tool_receipts", []) if isinstance(report, dict) else []
    recent_indexes = _add_tool_pair_closure(unique, recent_indexes, current_receipts)
    archived = [item for index, item in enumerate(unique) if index not in recent_indexes]
    recent = [item for index, item in enumerate(unique) if index in recent_indexes]
    refs = [f"history:{digest}" for _, digest in unique]
    prepared["session_history"] = [deepcopy(entry) for entry, _ in recent]
    summary_status = "not_needed"
    summary_text = None
    if archived:
        archive_digest = _digest([digest for _, digest in archived])
        source_ref = {
            "source": f"session-history:{_digest(prepared.get('session_key', 'local'))}",
            "from": 1,
            "to": len(archived),
            "count": len(archived),
            "sha256": archive_digest,
            "version": "session-history-v1",
        }
        bounded_input = _canonical_bytes([entry for entry, _ in archived])
        if len(bounded_input) <= policy["history_input_limit_bytes"]:
            try:
                text = (summarizer(archived, source_ref) if summarizer else
                        f"Archived {len(archived)} historical exchanges; non-authoritative; "
                        f"source sha256={archive_digest}.")
                if not isinstance(text, str) or len(text.encode("utf-8")) > policy["history_summary_limit_bytes"]:
                    raise ValueError("context_summary_invalid")
                summary_text = text
                summary_status = "created"
            except Exception:  # deterministic reference fallback; never retry the summary
                summary_text = (f"Historical exchanges archived; non-authoritative; "
                                f"source sha256={archive_digest}.")
                if len(summary_text.encode("utf-8")) > policy["history_summary_limit_bytes"]:
                    summary_text = None
                summary_status = "fallback"
        else:
            summary_text = f"Historical exchanges archived; non-authoritative; source sha256={archive_digest}."
            if len(summary_text.encode("utf-8")) > policy["history_summary_limit_bytes"]:
                summary_text = None
            summary_status = "input_limit_fallback"
        if summary_text:
            prepared["session_history_summary"] = summary_text
        prepared["_context_pack"] = {
            "history_refs": refs,
            "archived_history": source_ref,
            "summary_status": summary_status,
            "summary_sha256": _digest(summary_text) if summary_text else None,
            "summary_version": "context-history-summary-v1" if summary_text else None,
            **source_metadata,
        }
    else:
        prepared["_context_pack"] = {
            "history_refs": refs,
            "summary_status": summary_status,
            **source_metadata,
        }
    return prepared


def _without_derived_history_fields(entry: Any) -> Any:
    """Remove prior pack summaries so they cannot recursively survive history replay."""
    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items()
                    if key not in _DERIVED_PROJECTION_FIELDS}
        if isinstance(value, list):
            return [strip(item) for item in value]
        return deepcopy(value)

    return strip(entry)


def _add_tool_pair_closure(unique: list[tuple[Any, str]], selected: set[int],
                           current_receipts: Any) -> set[int]:
    """Keep a source tool request with any retained exchange that reports its receipt."""
    if not selected and not current_receipts:
        return selected

    request_indexes: dict[str, list[int]] = {}
    for index, (entry, _digest_value) in enumerate(unique):
        request = entry.get("request") if isinstance(entry, dict) else None
        if not isinstance(request, dict):
            continue
        for key in ("call_id", "request_id"):
            value = request.get(key)
            if isinstance(value, str) and value:
                request_indexes.setdefault(value, []).append(index)

    pending = list(current_receipts) if isinstance(current_receipts, list) else []
    for index in tuple(selected):
        pending.extend(_exchange_tool_receipts(unique[index][0]))
    while pending:
        receipt = pending.pop()
        if not isinstance(receipt, dict):
            continue
        source_id = receipt.get("review_call_id")
        if not isinstance(source_id, str) or not source_id:
            continue
        for source_index in request_indexes.get(source_id, ()):
            source_entry = unique[source_index][0]
            source_response = source_entry.get("response", {}) \
                if isinstance(source_entry, dict) else {}
            if (isinstance(source_response, dict)
                    and isinstance(source_response.get("tool_request"), dict)
                    and source_index not in selected):
                selected.add(source_index)
                pending.extend(_exchange_tool_receipts(source_entry))
    return selected


def _exchange_tool_receipts(entry: Any) -> list[Any]:
    request = entry.get("request") if isinstance(entry, dict) else None
    report = request.get("report") if isinstance(request, dict) else None
    receipts = report.get("tool_receipts", []) if isinstance(report, dict) else []
    return receipts if isinstance(receipts, list) else []


def finalize_context_pack(serialized_payload: bytes, policy: dict[str, Any], *, role: str,
                          run_id: str, state_revision: int, problem_hash: str,
                          endpoint: str, source: dict[str, Any] | None = None,
                          provider: str | None = None) -> dict[str, Any]:
    """Measure the exact final serialized request body and enforce a frozen known cap."""
    if not isinstance(serialized_payload, bytes):
        raise TypeError("serialized_payload_must_be_bytes")
    try:
        payload = json.loads(serialized_payload)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError("context_payload_invalid_json") from exc
    model = payload.get("model") if isinstance(payload, dict) else None
    profile_matches = (
        (provider or policy["provider"]) == policy["provider"]
        and model == policy["model"]
        and endpoint == policy["endpoint"]
    )
    byte_count = len(serialized_payload)
    estimated = ceil(byte_count / 3)
    cap = policy["input_cap_tokens"]
    actual_output_reserve = max(
        policy["output_reserve_tokens"],
        payload.get("max_tokens", 0) if isinstance(payload.get("max_tokens", 0), int) else 0,
    )
    reserved = actual_output_reserve + policy["safety_margin_tokens"]
    available = max(0, cap - reserved) if cap is not None else None
    pack = {
        **(source or {}),
        "version": policy["version"],
        "policy_sha256": policy.get("policy_sha256"),
        "role": role,
        "run_id": run_id,
        "problem_hash": problem_hash,
        "specification_version": (source or {}).get("specification_version"),
        "config_hash": (source or {}).get("config_hash"),
        "source_state_revision": state_revision,
        "profile": {
            "provider": provider or policy["provider"],
            "model": model,
            "endpoint": endpoint,
            "version": policy["profile_version"],
            "cap_source": policy["cap_source"],
            "cap_source_date": policy["cap_source_date"],
        },
        "serialized_utf8_bytes": byte_count,
        "token_estimate": estimated,
        "token_estimator_version": policy["token_estimator_version"],
        "token_estimate_error": "Heuristic estimate from complete serialized UTF-8 bytes; tokenizer-specific error is uncalibrated and this is not a hard token bound.",
        "capacity_is_hard_guarantee": False,
        "input_cap_tokens": cap,
        "output_reserve_tokens": actual_output_reserve,
        "reserved_tokens": reserved,
        "available_input_tokens": available,
        "capacity_status": "uncalibrated" if cap is None else "admitted_estimate",
        "payload_sha256": hashlib.sha256(serialized_payload).hexdigest(),
        "included_refs": ["serialized_payload", *(
            f"payload.{key}" for key in payload if key in {"messages", "tools", "model", "max_tokens"}
        ), *(source or {}).get("history_refs", [])],
        "profile_match": profile_matches,
    }
    pack["pack_sha256"] = _digest(pack)
    if not profile_matches:
        pack["capacity_status"] = "profile_mismatch"
        pack["pack_sha256"] = _digest({key: value for key, value in pack.items()
                                        if key != "pack_sha256"})
        raise ContextCapacityExceeded("context_profile_mismatch", pack)
    if cap is not None and estimated > available:
        pack["capacity_status"] = "context_capacity_exceeded"
        pack["pack_sha256"] = _digest({key: value for key, value in pack.items() if key != "pack_sha256"})
        raise ContextCapacityExceeded("context_capacity_exceeded", pack)
    return pack
