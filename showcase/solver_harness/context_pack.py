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
    """Deduplicate history and add a bounded non-authoritative excerpt or source index."""
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
            "retained_history_refs": [],
            "archived_history_refs": [],
            "included_refs": [],
            "summary_status": "not_needed",
            "summary_kind": "none",
            "summary_source_refs": [],
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
    archived = [(index + 1, *item) for index, item in enumerate(unique)
                if index not in recent_indexes]
    recent = [(index + 1, *item) for index, item in enumerate(unique)
              if index in recent_indexes]
    refs = [f"history:{digest}" for _, digest in unique]
    retained_refs = [f"history:{digest}" for _, _, digest in recent]
    archived_refs = [f"history:{digest}" for _, _, digest in archived]
    prepared["session_history"] = [deepcopy(entry) for _, entry, _ in recent]
    summary_status = "not_needed"
    summary_kind = "none"
    summary_text = None
    summary_source_refs = []
    if archived:
        archive_items = [
            {"index": index, "ref": f"history:{digest}", "sha256": digest}
            for index, _, digest in archived
        ]
        archive_digest = _digest(archive_items)
        source_ref = {
            "source": f"session-history:{_digest(prepared.get('session_key', 'local'))}",
            "index_base": 1,
            "index_scope": "deduplicated_session_history",
            "ranges": _index_ranges([item["index"] for item in archive_items]),
            "items": archive_items,
            "count": len(archived),
            "sha256": archive_digest,
            "version": "session-history-v2",
        }
        summarizer_input = [(entry, digest) for _, entry, digest in archived]
        bounded_input = _canonical_bytes({
            "exchanges": summarizer_input,
            "source": source_ref,
        })
        index_ref = f"archive-index:{archive_digest}"
        index_details = (
            f"archive index {index_ref}; "
            f"1-based deduplicated session-history indexes "
            f"{','.join(str(item['index']) for item in archive_items)}."
        )
        summary_prefix = f"Non-authoritative original archived exchanges; {index_details}"
        if len(bounded_input) <= policy["history_input_limit_bytes"]:
            if summarizer is not None:
                try:
                    text = summarizer(
                        summarizer_input, source_ref
                    )
                    if not isinstance(text, str) or len(text.encode("utf-8")) > policy[
                        "history_summary_limit_bytes"
                    ]:
                        raise ValueError("context_summary_invalid")
                    candidate = f"Non-authoritative provided summary: {text}\n{index_details}"
                    if len(candidate.encode("utf-8")) > policy["history_summary_limit_bytes"]:
                        raise ValueError("context_summary_invalid")
                    summary_text = candidate
                    summary_source_refs = list(archived_refs)
                    summary_status = "created"
                    summary_kind = "provided_summarizer_output"
                except Exception:  # one bounded attempt, then index-only fallback
                    summary_status = "reference_only"
                    summary_kind = "index"
            else:
                summary_text, excerpt_refs = _original_history_excerpt(
                    archived, summary_prefix, policy["history_summary_limit_bytes"]
                )
                if summary_text:
                    summary_source_refs = excerpt_refs
                    summary_status = "created"
                    summary_kind = "original_excerpt"
                else:
                    summary_status = "reference_only"
                    summary_kind = "index"
        else:
            summary_status = "reference_only"
            summary_kind = "index"
        if summary_text:
            prepared["session_history_summary"] = summary_text
        summary_sha256 = _digest(summary_text) if summary_text else None
        included_history_refs = list(retained_refs)
        if summary_text:
            included_history_refs.append(f"history-summary:{summary_sha256}")
        prepared["_context_pack"] = {
            "history_refs": refs,
            "retained_history_refs": retained_refs,
            "archived_history_refs": archived_refs,
            "included_refs": included_history_refs,
            "archived_history": source_ref,
            "summary_status": summary_status,
            "summary_kind": summary_kind,
            "summary_source_refs": summary_source_refs,
            "summary_sha256": summary_sha256,
            "summary_version": ({
                "original_excerpt": "context-history-excerpt-v1",
                "provided_summarizer_output": "context-history-summary-v2",
                "index": "context-history-index-v1",
            }.get(summary_kind) if summary_text else None),
            **source_metadata,
        }
    else:
        prepared["_context_pack"] = {
            "history_refs": refs,
            "retained_history_refs": retained_refs,
            "archived_history_refs": [],
            "included_refs": retained_refs,
            "summary_status": summary_status,
            "summary_kind": summary_kind,
            "summary_source_refs": [],
            **source_metadata,
        }
    return prepared


def _index_ranges(indexes: list[int]) -> list[dict[str, int]]:
    """Compress sorted one-based history indexes without spanning retained rows."""
    ranges = []
    for index in indexes:
        if ranges and index == ranges[-1]["to"] + 1:
            ranges[-1]["to"] = index
        else:
            ranges.append({"from": index, "to": index})
    return ranges


def _original_history_excerpt(archived, prefix: str, output_limit: int):
    """Include only complete original exchanges that fit as whole UTF-8 records."""
    excerpt = prefix
    included_refs = []
    for index, entry, digest in archived:
        if not isinstance(entry, dict) or not isinstance(entry.get("request"), dict) or not isinstance(
            entry.get("response"), dict
        ):
            return None, []
        ref = f"history:{digest}"
        line = f"\n[{index}; {ref}] {_canonical_bytes(entry).decode('utf-8')}"
        candidate = excerpt + line
        if len(candidate.encode("utf-8")) > output_limit:
            return None, []
        excerpt = candidate
        included_refs.append(ref)
    if not included_refs:
        return None, []
    return excerpt, included_refs


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
        ), *(source or {}).get("included_refs", [])],
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
