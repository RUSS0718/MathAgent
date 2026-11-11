"""Read-only public Run, evidence graph, and persisted F6 presentation views."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from flask import Blueprint, g, jsonify, request

from .solver_harness.proof_graph_projection import proof_graph_summary

SCHEME = "f7-deeplink-v1"
MODES = {"solve", "teach", "report"}


def register_faithful_system_api(app, *, workspace_service):
    """Expose F7 read routes without creating presentations or invoking solvers."""
    blueprint = Blueprint("faithful_system", __name__)

    @blueprint.get("/api/faithful/runs")
    def list_runs():
        user_id = _user_id()
        if user_id is None:
            return _error("auth_required", 401)
        try:
            limit = _integer_arg("limit", 50, minimum=1, maximum=100)
            offset = _integer_arg("offset", 0, minimum=0, maximum=1_000_000)
        except ValueError:
            return _error("pagination_invalid", 400)

        with _readonly_connection(workspace_service.store.database_path) as connection:
            connection.execute("BEGIN")
            total = connection.execute(
                "SELECT COUNT(*) FROM workspace_jobs WHERE user_id=?", (user_id,),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT job_id,status,created_at,updated_at,result_json FROM workspace_jobs "
                "WHERE user_id=? ORDER BY created_at DESC,job_id DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        items = [_run_summary(row) for row in rows]
        next_offset = offset + len(items) if offset + len(items) < total else None
        response = jsonify({"items": items, "total": total, "next_offset": next_offset})
        response.headers["Cache-Control"] = "no-store"
        return response

    @blueprint.get("/api/faithful/runs/<run_id>")
    def read_run(run_id: str):
        user_id = _user_id()
        if user_id is None:
            return _error("auth_required", 401)
        if request.args.get("scheme") != SCHEME:
            return _error("scheme_unsupported", 400)
        mode = request.args.get("mode")
        requested_mode = mode
        if mode is not None and mode not in MODES:
            return _error("presentation_mode_invalid", 400)
        output_id = request.args.get("output")
        artifact_id = request.args.get("artifact")
        paragraph_id = request.args.get("paragraph")
        try:
            graph_version = _integer_arg("graph", 0, minimum=0, maximum=2_147_483_647) \
                if request.args.get("graph") is not None else None
        except ValueError:
            return _error("graph_version_invalid", 400)
        node_id = request.args.get("node")
        if bool(output_id) != bool(artifact_id):
            return _error("presentation_identity_incomplete", 400)
        if paragraph_id and (not output_id or not paragraph_id.startswith("paragraph:")):
            return _error("paragraph_identity_incomplete", 400)
        if node_id and graph_version is None:
            return _error("graph_identity_incomplete", 400)

        with _readonly_connection(workspace_service.store.database_path) as connection:
            connection.execute("BEGIN")
            row = connection.execute(
                "SELECT job_id,status,created_at,updated_at,result_json FROM workspace_jobs "
                "WHERE job_id=? AND user_id=?", (run_id, user_id),
            ).fetchone()
            if row is None:
                return _error("job_not_found", 404)
            result = _load_result(row["result_json"])
            solver_row = connection.execute(
                "SELECT state_revision,state_json FROM solver_states WHERE run_id=?", (run_id,),
            ).fetchone()
            state = _load_result(solver_row["state_json"]) if solver_row is not None else {}
            source_event = connection.execute(
                "SELECT COALESCE(MAX(event_id),0) FROM workspace_events "
                "WHERE job_id=? AND event_type!='presentation_artifact_saved'",
                (run_id,),
            ).fetchone()[0]
            if mode is None:
                frozen_mode = result.get("presentation_mode")
                mode = frozen_mode if frozen_mode in MODES else "solve"
            stored_rows = connection.execute(
                "SELECT artifact_json FROM presentation_artifacts "
                "WHERE job_id=? AND user_id=? ORDER BY created_at",
                (run_id, user_id),
            ).fetchall()
        job = {
            "job_id": row["job_id"], "status": row["status"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "source_event_id": int(source_event), "result": result,
        }
        stored = [_load_json(item["artifact_json"]) for item in stored_rows]

        current_versions = _current_versions(job, state,
                                             solver_row["state_revision"] if solver_row else None)
        matching = [item for item in stored if requested_mode is None or item.get("mode") == requested_mode]
        presentation = _select_presentation(matching, output_id, artifact_id, current_versions)
        if presentation is not None:
            mode = presentation["mode"]
        graph = _public_graph(state, graph_version)
        graph_target_status = "not_requested"
        if graph_version is not None or node_id is not None:
            graph_target_status = "available"
            if graph is None or graph_version != graph["graph_version"]:
                graph_target_status = "unavailable"
            elif node_id is not None and node_id not in {
                item["id"] for item in [*graph["propositions"], *graph["attempts"]]
            }:
                graph_target_status = "unavailable"

        paragraph = None
        paragraph_status = "not_requested"
        if paragraph_id:
            paragraph_status = "unavailable"
            if presentation is not None:
                paragraph = next((item for item in presentation["paragraphs"]
                                  if item["id"] == paragraph_id), None)
                if paragraph is not None:
                    paragraph_status = "available"

        selection_status = "available" if presentation is not None else "unavailable"
        response = jsonify({
            "scheme": SCHEME,
            "run": _job_detail(job),
            "presentations": [{"mode": item.get("mode"),
                               "output_id": (item.get("output_request") or {}).get("id"),
                               "artifact_id": (item.get("artifact") or {}).get("id")}
                              for item in stored if (item.get("output_request") or {}).get("id")
                              and (item.get("artifact") or {}).get("id")],
            "graph": graph if graph_target_status != "unavailable" else None,
            "graph_target": {"status": graph_target_status, "version": graph_version,
                             "node_id": node_id if graph_target_status == "available" else None},
            "selection": {"status": selection_status, "mode": mode,
                          "presentation": presentation,
                          "paragraph_status": paragraph_status, "paragraph": paragraph},
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    app.register_blueprint(blueprint)


def _user_id() -> str | None:
    session = getattr(g, "auth_session", None)
    user_id = getattr(session, "user_id", None)
    return user_id if isinstance(user_id, str) and user_id else None


def _readonly_connection(database_path):
    """Open a query-only SQLite connection without calling workspace readers."""
    if str(database_path) == ":memory:":
        raise ValueError("f7_requires_file_database")
    uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return closing(connection)


def _load_json(value: object) -> object:
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return {}


def _load_result(value: object) -> dict[str, object]:
    result = _load_json(value)
    return dict(result) if isinstance(result, Mapping) else {}


def _integer_arg(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    value = int(raw)
    if value < minimum or value > maximum:
        raise ValueError(name)
    return value


def _run_summary(row: Mapping[str, object]) -> dict[str, object]:
    result = _load_result(row["result_json"])
    return {
        "run_id": row["job_id"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "execution_mode": result.get("execution_mode"),
        "solver_mode": result.get("solver_mode"),
        "presentation_mode": result.get("presentation_mode"),
    }


def _job_detail(job: Mapping[str, object]) -> dict[str, object]:
    result = job.get("result") if isinstance(job.get("result"), Mapping) else {}
    return {
        "run_id": job.get("job_id"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "execution_mode": result.get("execution_mode"),
        "solver_mode": result.get("solver_mode"),
        "presentation_mode": result.get("presentation_mode"),
    }


def _select_presentation(
    stored: list[dict[str, object]], output_id: str | None, artifact_id: str | None,
    current_versions: Mapping[str, object],
) -> dict[str, object] | None:
    if output_id is not None and artifact_id is not None:
        stored = [item for item in stored if
                  (item.get("output_request") or {}).get("id") == output_id
                  and (item.get("artifact") or {}).get("id") == artifact_id]
    else:
        return None
    if not stored:
        return None
    return _public_presentation(stored[-1], current_versions)


def _current_versions(job: Mapping[str, object], state: Mapping, revision: int | None) -> dict[str, object]:
    """Match F6's CAS identity using the authoritative persisted solver state."""
    return {
        "job_status": job.get("status"),
        "job_updated_at": job.get("updated_at"),
        "source_event_id": job.get("source_event_id"),
        "state_revision": revision,
        "specification_version": state.get("specification_version"),
        "graph_version": (state.get("proof_graph") or {}).get("current_version"),
    }


def _public_presentation(
    value: Mapping[str, object], current_versions: Mapping[str, object],
) -> dict[str, object]:
    sources = [source for source in value.get("sources", []) if isinstance(source, Mapping)]
    source_versions = value.get("source_versions") \
        if isinstance(value.get("source_versions"), Mapping) else {}
    current = all(
        key in source_versions and source_versions[key] == expected
        for key, expected in current_versions.items()
    )
    delivery = value.get("delivery") if isinstance(value.get("delivery"), Mapping) else {}
    selection = delivery.get("selection") if isinstance(delivery.get("selection"), Mapping) else None
    grade_labels = []
    for source in sources:
        if not current or source.get("status") != "current":
            continue
        grade, scope = source.get("grade"), source.get("scope")
        if grade == "L2" and scope == "formal_target":
            grade_labels.append("VERIFIED L2")
        elif grade == "L3" and scope == "original_problem":
            grade_labels.append("VERIFIED L3")
        elif grade == "llm_reviewed" and scope == "whole_solution_llm_review":
            grade_labels.append("REVIEWED")
    if (current and selection is not None and selection.get("status") == "candidate_selected"
            and selection.get("eligible") is True
            and selection.get("completeness") in {"complete", "partial"}):
        grade_labels.append("BEST-EFFORT")
    return {
        "schema_version": value.get("schema_version"),
        "policy_version": value.get("policy_version"),
        "job_id": value.get("job_id"),
        "mode": value.get("mode"),
        "status": value.get("status"),
        "answer": value.get("answer"),
        "answer_artifact": _pick(value.get("answer_artifact"), ("schema", "sha256", "id")),
        "source_fingerprint": value.get("source_fingerprint"),
        "source_versions": _pick(source_versions, tuple(current_versions)),
        "freshness": "current" if current else "needs_review",
        "output_request": _pick(value.get("output_request"),
                                 ("id", "kind", "model_calls", "solver_resumed")),
        "artifact": _pick(value.get("artifact"), ("schema", "sha256", "id")),
        "grade_labels": list(dict.fromkeys(grade_labels)),
        "paragraphs": [
            _pick(item, ("id", "version", "text", "kind", "claim_refs", "status", "grade", "binding"))
            for item in value.get("paragraphs", []) if isinstance(item, Mapping)
        ],
        "sources": [
            _pick(item, ("id", "kind", "scope", "grade", "status", "graph_version",
                         "specification_version", "node_id", "attempt_id", "target_hash",
                         "proof_hash", "environment_hash", "conclusion", "dependencies"))
            for item in sources
        ],
        "delivery": {
            "grade": delivery.get("grade"),
            "selection": _pick(selection, ("status", "reason_codes", "termination_reason",
                                            "selected_candidate_id", "eligible", "completeness")),
            "unresolved_goals": delivery.get("unresolved_goals", []),
            "verified_claims": [
                _pick(item, ("id", "text", "claim_refs", "status", "grade"))
                for item in delivery.get("verified_claims", []) if isinstance(item, Mapping)
            ],
        } if delivery else None,
    }


def _public_graph(state: Mapping, version: int | None) -> dict[str, object] | None:
    """Reuse F1's public projection for the exact immutable graph version."""
    projected = proof_graph_summary(state, version)
    if projected is not None and (state.get("proof_graph") or {}).get("data_origin") == "synthetic_f7_performance":
        projected["data_origin"] = "synthetic_f7_performance"
    return projected


def _pick(value: object, allowed: tuple[str, ...]) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {key: value[key] for key in allowed if key in value}


def _error(code: str, status: int):
    return jsonify({"code": code, "error": code, "success": False}), status
