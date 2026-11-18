"""Load domain-matched population observations as advisory run guidance."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping

_SCHEMA = "population-memory-injection-v1"
_MAX_OBSERVATIONS = 25
_MAX_CONTEXT_BYTES = 16_384


def has_population_memory(request: Mapping) -> bool:
    """Recognize an advisory whether it arrives directly, in role context, or layers."""
    memory = request.get("population_memory_advisory")
    if isinstance(memory, Mapping) and memory.get("authority") == "advisory_only":
        return True
    role_context = request.get("role_context")
    state = role_context.get("state") if isinstance(role_context, Mapping) else None
    memory = state.get("population_memory_advisory") if isinstance(state, Mapping) else None
    if isinstance(memory, Mapping) and memory.get("authority") == "advisory_only":
        return True
    layers = request.get("prompt_layers")
    return isinstance(layers, list) and any(
        isinstance(layer, Mapping)
        and isinstance(layer.get("state"), Mapping)
        and isinstance(layer["state"].get("population_memory_advisory"), Mapping)
        and layer["state"]["population_memory_advisory"].get("authority") == "advisory_only"
        for layer in layers
    )


def _envelope(domain: str | None, observations: list[dict] | None = None) -> dict:
    items = observations or []
    return {
        "schema": _SCHEMA,
        "status": "available" if items else "unavailable",
        "source": "faithful_memory_entries",
        "domain": domain,
        "authority": "advisory_only",
        "review_status": "requires_current_run_review",
        "observations": items,
    }


def _load_json(value):
    def reject_constant(constant):
        raise ValueError(f"invalid JSON constant: {constant}")

    try:
        return json.loads(value, parse_constant=reject_constant)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _owned_run(connection, run_id, session_id, owner_id, *, require_terminal=True) -> bool:
    if not isinstance(run_id, str) or not run_id:
        return False
    return connection.execute(
        "SELECT 1 FROM workspace_jobs j "
        "JOIN chat_sessions s ON s.session_id=j.session_id "
        "WHERE j.job_id=? AND j.session_id=? AND j.user_id=? AND s.user_id=? "
        "AND (?=0 OR j.status IN ('succeeded','failed','canceled'))",
        (run_id, session_id, owner_id, owner_id, int(require_terminal)),
    ).fetchone() is not None


def _safe_provenance(value, *, depth=0):
    if not isinstance(value, dict) or depth > 2:
        return {}
    result = {
        key: value[key]
        for key in ("source_run_id", "source_state_revision", "imported_by")
        if isinstance(value.get(key), (str, int)) and not isinstance(value.get(key), bool)
    }
    imported = value.get("imported_from")
    if isinstance(imported, dict) and isinstance(imported.get("record_id"), str):
        scope = imported.get("scope")
        result["imported_from"] = {
            "record_id": imported["record_id"],
            "scope": {
                key: scope[key]
                for key in ("kind", "scope_id", "owner_id", "workspace_id")
                if isinstance(scope, dict) and isinstance(scope.get(key), str)
            },
        }
    original = value.get("original_provenance")
    if isinstance(original, dict) and depth < 2:
        result["original_provenance"] = _safe_provenance(original, depth=depth + 1)
    return result


def _import_source(connection, provenance, observation, owner_id):
    """Validate one import edge and return its source provenance and workspace."""
    imported_from = provenance.get("imported_from")
    source_scope = imported_from.get("scope") if isinstance(imported_from, dict) else None
    record_id = imported_from.get("record_id") if isinstance(imported_from, dict) else None
    if (
        not isinstance(source_scope, dict)
        or provenance.get("imported_by") != owner_id
        or not isinstance(record_id, str)
    ):
        return None

    source = connection.execute(
        "SELECT owner_id,workspace_id,scope_kind,scope_id,entry_type,state,payload_json "
        "FROM faithful_memory_entries WHERE record_id=?",
        (record_id,),
    ).fetchone()
    if source is None:
        return None
    source_owner, source_session, scope_kind, scope_id, entry_type, state, payload_json = source
    if (
        source_owner != owner_id
        or entry_type != "observation"
        or state != "active"
        or source_scope
        != {
            "kind": scope_kind,
            "scope_id": scope_id,
            "owner_id": source_owner,
            "workspace_id": source_session,
        }
    ):
        return None

    source_session_owner = connection.execute(
        "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
        (source_session, owner_id),
    ).fetchone()
    source_scope_control = connection.execute(
        "SELECT enabled FROM faithful_memory_scope_controls "
        "WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?",
        (source_owner, source_session, scope_kind, scope_id),
    ).fetchone()
    source_payload = _load_json(payload_json)
    original = provenance.get("original_provenance")
    if (
        source_session_owner is None
        or (source_scope_control is not None and not bool(source_scope_control[0]))
        or not isinstance(source_payload, dict)
        or not isinstance(original, dict)
        or source_payload.get("provenance") != original
        or source_payload.get("observation") != observation
        or provenance.get("source_run_id") != original.get("source_run_id")
    ):
        return None
    source_run_id = original.get("source_run_id")
    if scope_kind == "run":
        if not _owned_run(connection, scope_id, source_session, owner_id, require_terminal=False):
            return None
        if "imported_from" not in original and scope_id != source_run_id:
            return None
    if scope_kind == "population" and scope_id != source_session:
        return None
    if scope_kind not in {"run", "population"}:
        return None
    return original, source_session


def _valid_provenance(connection, provenance, observation, owner_id, session_id) -> bool:
    """Walk every explicit import back to an owned terminal Run without cycles."""
    seen = set()
    while isinstance(provenance, dict) and "imported_from" in provenance:
        imported = provenance["imported_from"]
        record_id = imported.get("record_id") if isinstance(imported, dict) else None
        if not isinstance(record_id, str) or record_id in seen:
            return False
        seen.add(record_id)
        source = _import_source(connection, provenance, observation, owner_id)
        if source is None:
            return False
        provenance, session_id = source
    if not isinstance(provenance, dict):
        return False
    return _owned_run(
        connection, provenance.get("source_run_id"), session_id, owner_id
    )


def load_population_memory(
    connection, *, run_id: str, problem_spec: Mapping | None
) -> dict:
    """Return enabled, owned, same-domain memory with advisory-only authority."""
    raw_domain = problem_spec.get("domain") if isinstance(problem_spec, Mapping) else None
    if not isinstance(raw_domain, str) or not raw_domain.strip():
        return _envelope(None)
    domain = raw_domain.strip()
    try:
        job = connection.execute(
            "SELECT j.user_id,j.session_id,s.user_id "
            "FROM workspace_jobs j LEFT JOIN chat_sessions s ON s.session_id=j.session_id "
            "WHERE j.job_id=?",
            (run_id,),
        ).fetchone()
        if job is None or job[2] != job[0]:
            return _envelope(domain)
        owner_id, session_id = job[0], job[1]
        enabled = connection.execute(
            "SELECT 1 FROM faithful_memory_injection_controls "
            "WHERE owner_id=? AND workspace_id=? AND scope_kind='population' "
            "AND scope_id=? AND enabled=1",
            (owner_id, session_id, session_id),
        ).fetchone()
        if enabled is None:
            return _envelope(domain)
        memory_scope = connection.execute(
            "SELECT enabled FROM faithful_memory_scope_controls "
            "WHERE owner_id=? AND workspace_id=? AND scope_kind='population' AND scope_id=?",
            (owner_id, session_id, session_id),
        ).fetchone()
        if memory_scope is not None and not bool(memory_scope[0]):
            return _envelope(domain)

        rows = connection.execute(
            "SELECT record_id,entry_type,state,payload_json FROM faithful_memory_entries "
            "WHERE owner_id=? AND workspace_id=? AND scope_kind='population' AND scope_id=? "
            "ORDER BY created_at DESC,record_id DESC LIMIT 25",
            (owner_id, session_id, session_id),
        ).fetchall()
        observations = []
        total_size = 0
        for row in rows:
            if row[1] != "observation" or row[2] != "active":
                continue
            payload = _load_json(row[3])
            if not isinstance(payload, dict):
                continue
            observation = payload.get("observation")
            provenance = payload.get("provenance")
            applicability = observation.get("applicability") if isinstance(observation, dict) else None
            observed_domain = applicability.get("domain") if isinstance(applicability, dict) else None
            if (
                not isinstance(observed_domain, str)
                or observed_domain.strip().casefold() != domain.casefold()
                or not isinstance(observation, dict)
                or observation.get("outcome") not in {"success", "failure", "unknown"}
                or any(not isinstance(observation.get(key), dict)
                       for key in ("applicability", "versions", "cost", "content"))
                or not _valid_provenance(
                    connection, provenance, observation, owner_id, session_id
                )
            ):
                continue
            outcome = observation.get("outcome")
            use = (
                "candidate_guidance"
                if isinstance(outcome, str) and outcome.strip().casefold() in {"success", "succeeded"}
                else "diagnostic_only"
            )
            item = {
                "record_id": row[0],
                "outcome": outcome,
                "applicability": applicability,
                "versions": observation.get("versions"),
                "cost": observation.get("cost"),
                "content": observation.get("content"),
                "provenance": _safe_provenance(provenance),
                "authority": "advisory_only",
                "review_status": "requires_current_run_review",
                "use": use,
            }
            try:
                encoded_size = len(
                    json.dumps(item, ensure_ascii=False, allow_nan=False).encode("utf-8")
                )
            except (TypeError, ValueError):
                continue
            if total_size + encoded_size <= _MAX_CONTEXT_BYTES:
                observations.append(item)
                total_size += encoded_size
            if len(observations) >= _MAX_OBSERVATIONS:
                break
        return _envelope(domain, observations)
    except sqlite3.Error:
        return _envelope(domain)
