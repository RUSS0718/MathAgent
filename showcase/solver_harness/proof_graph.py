"""Versioned proof graph derived from the existing verified-results ledger."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping

from .proof_graph_sources import recorded_call

PROPOSITION_STATES = frozenset({"unresolved", "supported", "invalidated", "refuted"})
ATTEMPT_STATES = frozenset({"proposed", "accepted", "rejected", "invalidated", "unknown"})
EVIDENCE_GRADES = frozenset({"llm_reviewed", "tool_verified"})


class ProofGraphValidationError(ValueError):
    """An attempted graph transition has an invalid identity or reference."""


def initial_proof_graph() -> dict:
    """Create the empty immutable graph snapshot for one explicitly enabled Run."""
    return {"current_version": 0, "snapshots": [_empty_snapshot(0)]}


def _empty_snapshot(version: int) -> dict:
    return {
        "graph_version": version,
        "propositions": {},
        "derivations": {},
        "attempts": {},
        "sources": {},
        "not_imported_records": [],
        "bootstrap_complete": False,
        "conflict_resolutions": {},
    }


def _digest(*parts: str) -> str:
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def proposition_id(state: Mapping, statement: str, scope: str) -> str:
    """Assign a stable, Run-scoped identity from normalized claim semantics."""
    specification = state.get("specification_version", 0)
    return "prop_" + _digest(
        state["problem_hash"], str(specification), _clean(statement), _clean(scope)
    )[:32]


def _source_id(kind: str, identity: str) -> str:
    return f"{kind}:{identity}"


def _attempt_id(run_id: str, call_id: str, prop_id: str) -> str:
    return "attempt_" + _digest(run_id, call_id, prop_id)[:32]


def _source_refs(sources: dict, refs: list[tuple[str, str, str]]) -> list[str]:
    result = []
    for kind, identity, grade in refs:
        source_id = _source_id(kind, identity)
        sources[source_id] = {"kind": kind, "grade": grade}
        result.append(source_id)
    return sorted(set(result))


def _resolution_valid(state: Mapping, prop_id: str, resolution: Mapping) -> bool:
    call = recorded_call(state, resolution.get("review_call_id"), "step_verifier")
    if call is None or call.get("status") != "completed":
        return False
    response = call.get("response")
    request = call.get("request")
    snapshot = state["proof_graph"]["snapshots"][-1]
    since = snapshot.get("propositions", {}).get(prop_id, {}).get("conflict_since_revision")
    revision = call.get("request_revision")
    if (type(since) is not int or type(revision) is not int
            or not since < revision <= state["state_revision"]):
        return False
    return (
        isinstance(response, Mapping)
        and response.get("proof_graph_resolution") == resolution.get("ruling")
        and response.get("proof_graph_proposition_id") == prop_id
        and isinstance(request, Mapping)
        and prop_id in request.get("proof_graph_conflict_ids", [])
    )


def evolve_proof_graph(state: Mapping, event: Mapping,
                      persisted_receipts: Mapping[str, Mapping] | None = None) -> tuple[dict | None, dict | None]:
    """Derive one proof-graph snapshot through the storage transaction boundary."""
    from .proof_graph_evolution import evolve_proof_graph as evolve

    return evolve(state, event, persisted_receipts)
