"""Opt-in, read-only Run Memory view over the authoritative Solver snapshot."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from flask import g, jsonify, request

from .run_budget import _summary
from .workspace import WorkspaceError


def project_run_memory(run_id, revision, state, budget=None):
    """Keep conjectures and invalid results out of the effective evidence view."""
    ledger = state.get("verified_results_ledger", [])
    evidence = [
        {
            key: item[key]
            for key in ("result_id", "category", "evidence_level", "source", "obligation_id")
            if key in item
        }
        for item in ledger
        if isinstance(item, dict)
        and item.get("proven") is True
        and item.get("valid", True) is True
        and item.get("invalidated") is not True
        and item.get("status") not in {"INVALIDATED", "invalidated"}
    ]
    return {
        "run_id": run_id,
        "source": "authoritative_run_snapshot",
        "state_revision": revision,
        "phase": state.get("phase"),
        "status": state.get("status"),
        "plan_version": state.get("plan_version"),
        "graph_version": (state.get("proof_graph") or {}).get("current_version"),
        "budget": budget,
        "valid_evidence": evidence,
        "invalidated_count": sum(
            isinstance(item, dict)
            and (
                item.get("valid") is False
                or item.get("invalidated") is True
                or item.get("status") in {"INVALIDATED", "invalidated"}
            )
            for item in ledger
        ),
    }


def register_run_memory(app, database_path):
    """Expose scoped Run recovery facts without creating a second state ledger."""

    @app.get("/api/agent/jobs/<job_id>/memory")
    def run_memory(job_id):
        session = g.auth_session
        if session is None:
            raise WorkspaceError("auth_required", status=401)
        uri = Path(database_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            owner = connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (job_id, session.user_id),
            ).fetchone()
            if owner is None:
                raise WorkspaceError("job_not_found", status=404)
            row = connection.execute(
                "SELECT state_json,state_revision FROM solver_states WHERE run_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise WorkspaceError("run_memory_unavailable", status=404)
            state = json.loads(row["state_json"])
            ledger = connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)
            ).fetchone()
            budget = _summary(json.loads(ledger[0])) if ledger is not None else None
            memory = project_run_memory(job_id, row["state_revision"], state, budget)
        response = jsonify({"success": True, "run_memory": memory})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/sessions/<session_id>/population-memory")
    def population_memory(session_id):
        """Read historical route observations within one owned chat session."""
        session = g.auth_session
        if session is None:
            raise WorkspaceError("auth_required", status=401)
        try:
            limit = int(request.args.get("limit", "25"))
            offset = int(request.args.get("offset", "0"))
        except ValueError as exc:
            raise WorkspaceError("memory_page_invalid") from exc
        if not 1 <= limit <= 100 or offset < 0:
            raise WorkspaceError("memory_page_invalid")
        uri = Path(database_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            owned = connection.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
                (session_id, session.user_id),
            ).fetchone()
            if owned is None:
                raise WorkspaceError("session_not_found", status=404)
            total_jobs = connection.execute(
                "SELECT COUNT(*) FROM workspace_jobs j "
                "JOIN solver_states s ON s.run_id=j.job_id "
                "WHERE j.session_id=? AND j.user_id=?",
                (session_id, session.user_id),
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT j.job_id,s.state_json,s.state_revision FROM workspace_jobs j "
                "JOIN solver_states s ON s.run_id=j.job_id "
                "WHERE j.session_id=? AND j.user_id=? "
                "ORDER BY j.created_at DESC,j.job_id DESC LIMIT ? OFFSET ?",
                (session_id, session.user_id, limit, offset),
            ).fetchall()
            observations = []
            for row in rows:
                state = json.loads(row["state_json"])
                for route in state.get("route_registry", []):
                    if not isinstance(route, dict):
                        continue
                    observations.append(
                        {
                            "source_run_id": row["job_id"],
                            "source_state_revision": row["state_revision"],
                            "route_id": route.get("route_id"),
                            "parent_route_id": route.get("parent_route_id"),
                            "status": route.get("status"),
                            "stop_reason": route.get("stop_reason"),
                            "graph_version": route.get("graph_version"),
                            "plan_version": route.get("plan_version"),
                            "policy_version": route.get("policy_version"),
                            "unknown_observation_count": len(
                                route.get("unknown_observations") or []
                            ),
                        }
                    )
        response = jsonify(
            {
                "success": True,
                "authority": "observations_only",
                "observations": observations,
                "total_jobs": total_jobs,
                "limit": limit,
                "offset": offset,
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response
