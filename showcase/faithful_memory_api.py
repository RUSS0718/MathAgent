"""Opt-in, read-only Run Memory view over the authoritative Solver snapshot."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from flask import g, jsonify

from .run_budget import _summary


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
        "graph_version": (state.get("proof_graph") or {}).get("graph_version"),
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
            return jsonify({"success": False, "code": "auth_required"}), 401
        uri = Path(database_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=1)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN")
            owner = connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (job_id, session.user_id),
            ).fetchone()
            if owner is None:
                return jsonify({"success": False, "code": "job_not_found"}), 404
            row = connection.execute(
                "SELECT state_json,state_revision FROM solver_states WHERE run_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return jsonify({"success": False, "code": "run_memory_unavailable"}), 404
            state = json.loads(row["state_json"])
            ledger = connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)
            ).fetchone()
            budget = _summary(json.loads(ledger[0])) if ledger is not None else None
            memory = project_run_memory(job_id, row["state_revision"], state, budget)
        return jsonify({"success": True, "run_memory": memory})
