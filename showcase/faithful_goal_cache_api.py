"""Authenticated, session-scoped metadata controls for Global Goal Cache."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from threading import RLock

from flask import g, jsonify, request

from .solver_harness.faithful_goal_cache import GlobalGoalCache
from .workspace import WorkspaceError

_SCHEMA_LOCK = RLock()


def register_goal_cache_api(app, database_path: str | Path) -> None:
    """Register metadata-only cache views and explicit per-session controls."""

    def open_connection():
        connection = sqlite3.connect(str(database_path), timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN IMMEDIATE" if request.method != "GET" else "BEGIN")
        return connection

    def authenticated_scope(session_id: str, connection: sqlite3.Connection):
        auth = g.auth_session
        if auth is None:
            raise WorkspaceError("auth_required", status=401)
        owned = connection.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
            (session_id, auth.user_id),
        ).fetchone()
        if owned is None:
            raise WorkspaceError("session_not_found", status=404)
        return auth

    def cache_enabled(connection: sqlite3.Connection, owner_id: str, session_id: str) -> bool:
        row = connection.execute(
            """SELECT enabled FROM faithful_goal_cache_control
               WHERE owner_id=? AND workspace_id=?""",
            (owner_id, session_id),
        ).fetchone()
        return row is not None and row[0] == 1

    def store_error(error: ValueError) -> WorkspaceError:
        code = str(error)
        if code == "goal_cache_actor_mismatch":
            return WorkspaceError("goal_cache_control_forbidden", status=403)
        if code == "goal_cache_disabled":
            return WorkspaceError("goal_cache_disabled", status=409)
        return WorkspaceError("goal_cache_request_invalid")

    @app.get("/api/sessions/<session_id>/goal-cache")
    def get_goal_cache(session_id: str):
        with closing(open_connection()) as connection:
            auth = authenticated_scope(session_id, connection)
            with _SCHEMA_LOCK:
                cache = GlobalGoalCache(
                    connection, owner_id=auth.user_id, workspace_id=session_id
                )
            enabled = cache_enabled(connection, auth.user_id, session_id)
            entries = cache.list_entries() if enabled else []
            events = cache.list_audit_events()
            connection.commit()
        response = jsonify({
            "success": True,
            "authority": "metadata_only",
            "enabled": enabled,
            "entries": [
                {
                    key: item[key]
                    for key in (
                        "cache_id", "state", "reason", "source_run_id",
                        "source_attempt_id", "source_grade", "grade_ceiling",
                        "created_at", "updated_at",
                    )
                    if key in item
                }
                for item in entries
            ],
            "events": [
                {
                    key: item[key]
                    for key in ("cache_id", "event", "details", "created_at")
                    if key in item
                }
                for item in events
            ],
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.put("/api/sessions/<session_id>/goal-cache")
    def set_goal_cache(session_id: str):
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"enabled"} or type(
            body.get("enabled")
        ) is not bool:
            raise WorkspaceError("goal_cache_request_invalid")
        with closing(open_connection()) as connection:
            auth = authenticated_scope(session_id, connection)
            with _SCHEMA_LOCK:
                cache = GlobalGoalCache(
                    connection, owner_id=auth.user_id, workspace_id=session_id
                )
            try:
                action = cache.enable if body["enabled"] else cache.disable
                action(actor_id=auth.user_id)
            except ValueError as error:
                raise store_error(error) from error
            connection.commit()
        return jsonify({"success": True, "enabled": body["enabled"]})

    @app.delete("/api/sessions/<session_id>/goal-cache")
    def clear_goal_cache(session_id: str):
        with closing(open_connection()) as connection:
            auth = authenticated_scope(session_id, connection)
            with _SCHEMA_LOCK:
                cache = GlobalGoalCache(
                    connection, owner_id=auth.user_id, workspace_id=session_id
                )
            try:
                cache.clear(actor_id=auth.user_id)
            except ValueError as error:
                raise store_error(error) from error
            connection.commit()
        return jsonify({"success": True, "cleared": True})
