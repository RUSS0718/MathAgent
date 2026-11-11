"""Authenticated controls for scoped, advisory Faithful Memory records."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from flask import g, jsonify, request

from .solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from .workspace import WorkspaceError

_SCHEMA_LOCK = RLock()


def register_memory_control_api(app, database_path: str | Path) -> None:
    """Register session-bound memory listing and explicit management routes."""

    @contextmanager
    def connection(*, write=False):
        db = sqlite3.connect(str(database_path), timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def authenticated_session(session_id: str, db: sqlite3.Connection):
        auth = g.auth_session
        if auth is None:
            raise WorkspaceError("auth_required", status=401)
        row = db.execute(
            "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
            (session_id, auth.user_id),
        ).fetchone()
        if row is None:
            raise WorkspaceError("session_not_found", status=404)
        return auth

    def owned_scope(session_id: str, kind: str, scope_id: str, db: sqlite3.Connection):
        auth = authenticated_session(session_id, db)
        if kind == "population":
            if scope_id != session_id:
                raise WorkspaceError("memory_scope_not_found", status=404)
        elif kind == "run":
            row = db.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=? AND session_id=?",
                (scope_id, auth.user_id, session_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError("memory_scope_not_found", status=404)
        else:
            raise WorkspaceError("memory_scope_invalid")
        try:
            return auth, MemoryScope(kind, scope_id, auth.user_id, session_id)
        except ValueError as error:
            raise WorkspaceError("memory_scope_invalid") from error

    def payload_object():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise WorkspaceError("memory_request_invalid")
        return body

    def store_call(operation):
        try:
            return operation()
        except ValueError as error:
            code = str(error)
            if code == "memory_observation_unavailable":
                raise WorkspaceError("memory_observation_not_found", status=404) from error
            if code == "memory_import_scope_mismatch":
                raise WorkspaceError("memory_scope_not_found", status=404) from error
            if code == "memory_scope_disabled":
                raise WorkspaceError("memory_scope_disabled", status=409) from error
            if code in {"memory_import_actor_mismatch", "memory_control_actor_mismatch"}:
                raise WorkspaceError("memory_control_forbidden", status=403) from error
            raise WorkspaceError("memory_request_invalid") from error

    def session_observations(
        store: FaithfulMemoryStore, scope: MemoryScope, db: sqlite3.Connection
    ):
        """Keep only records with a verifiable same-owner Run provenance chain."""
        observations = store.list_observations(scope)
        if not observations:
            return []

        def owned_run(run_id: str, workspace_id: str) -> bool:
            return db.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=? AND session_id=?",
                (run_id, scope.owner_id, workspace_id),
            ).fetchone() is not None

        def run_owned_by_user(run_id: str) -> bool:
            return db.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (run_id, scope.owner_id),
            ).fetchone() is not None

        visible = []
        for item in observations:
            provenance = item.get("provenance")
            if not isinstance(provenance, Mapping):
                continue
            source_run_id = provenance.get("source_run_id")
            if not isinstance(source_run_id, str):
                continue
            imported_from = provenance.get("imported_from")
            original = provenance.get("original_provenance")
            if imported_from is None and original is None:
                if (
                    owned_run(source_run_id, scope.workspace_id)
                    and (scope.kind != "run" or source_run_id == scope.scope_id)
                ):
                    visible.append(item)
                continue
            if not isinstance(imported_from, Mapping) or not isinstance(original, Mapping):
                continue
            source_scope = imported_from.get("scope")
            if (
                provenance.get("imported_by") != scope.owner_id
                or original.get("source_run_id") != source_run_id
                or not isinstance(imported_from.get("record_id"), str)
                or not isinstance(source_scope, Mapping)
                or source_scope.get("owner_id") != scope.owner_id
                or not isinstance(source_scope.get("workspace_id"), str)
                or not run_owned_by_user(source_run_id)
            ):
                continue
            source_workspace = source_scope["workspace_id"]
            source_session = db.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
                (source_workspace, scope.owner_id),
            ).fetchone()
            if source_session is None:
                continue
            source_kind = source_scope.get("kind")
            source_scope_id = source_scope.get("scope_id")
            if source_kind == "run":
                valid_source_scope = (
                    isinstance(source_scope_id, str)
                    and owned_run(source_scope_id, source_workspace)
                )
            elif source_kind == "population":
                valid_source_scope = source_scope_id == source_workspace
            else:
                valid_source_scope = False
            if valid_source_scope:
                visible.append(item)
        return visible

    @app.get("/api/sessions/<session_id>/memory/<kind>/<scope_id>")
    def list_memory(session_id: str, kind: str, scope_id: str):
        with connection() as db:
            with _SCHEMA_LOCK:
                auth, scope = owned_scope(session_id, kind, scope_id, db)
                store = FaithfulMemoryStore(db)
            observations = session_observations(store, scope, db)
            injection_enabled = store.injection_enabled(scope)
        response = jsonify(
            {
                "success": True,
                "authority": "observations_only",
                "scope": {"kind": kind, "scope_id": scope_id},
                "injection_enabled": injection_enabled,
                "observations": observations,
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/sessions/<session_id>/memory/<kind>/<scope_id>/imports")
    def import_memory(session_id: str, kind: str, scope_id: str):
        body = payload_object()
        record_id = body.get("record_id")
        source_kind = body.get("source_kind")
        source_scope_id = body.get("source_scope_id")
        source_session_id = body.get("source_session_id", session_id)
        if set(body) - {
            "record_id", "source_kind", "source_scope_id", "source_session_id"
        }:
            raise WorkspaceError("memory_request_invalid")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (record_id, source_kind, source_scope_id, source_session_id)
        ):
            raise WorkspaceError("memory_request_invalid")
        with connection(write=True) as db:
            with _SCHEMA_LOCK:
                auth, destination = owned_scope(session_id, kind, scope_id, db)
                _, source = owned_scope(
                    source_session_id, source_kind, source_scope_id, db
                )
                store = FaithfulMemoryStore(db)
            available = store_call(lambda: session_observations(store, source, db))
            selected = next((item for item in available if item["record_id"] == record_id), None)
            if selected is None:
                raise WorkspaceError("memory_observation_not_found", status=404)
            imported_id = store_call(
                lambda: store.import_observation(
                    record_id, destination, actor_id=auth.user_id,
                    allow_cross_workspace=source_session_id != session_id,
                )
            )
        return jsonify({
            "success": True, "record_id": imported_id, "authority": "advisory",
            "source_session_id": source_session_id,
            "destination_session_id": session_id,
        }), 201

    @app.put("/api/sessions/<session_id>/memory/<kind>/<scope_id>")
    def control_memory(session_id: str, kind: str, scope_id: str):
        body = payload_object()
        if set(body) != {"enabled"} or type(body.get("enabled")) is not bool:
            raise WorkspaceError("memory_request_invalid")
        with connection(write=True) as db:
            with _SCHEMA_LOCK:
                auth, scope = owned_scope(session_id, kind, scope_id, db)
                store = FaithfulMemoryStore(db)
            action = store.enable_scope if body["enabled"] else store.disable_scope
            store_call(lambda: action(scope, actor_id=auth.user_id))
            injection_enabled = store.injection_enabled(scope)
        return jsonify({
            "success": True,
            "enabled": body["enabled"],
            "injection_enabled": injection_enabled,
        })

    @app.put("/api/sessions/<session_id>/memory/<kind>/<scope_id>/injection")
    def control_memory_injection(session_id: str, kind: str, scope_id: str):
        body = payload_object()
        if set(body) != {"enabled"} or type(body.get("enabled")) is not bool:
            raise WorkspaceError("memory_request_invalid")
        if kind != "population":
            raise WorkspaceError("memory_scope_invalid")
        with connection(write=True) as db:
            with _SCHEMA_LOCK:
                auth, scope = owned_scope(session_id, kind, scope_id, db)
                store = FaithfulMemoryStore(db)
            store_call(lambda: store.set_injection_enabled(
                scope, body["enabled"], actor_id=auth.user_id
            ))
            injection_enabled = store.injection_enabled(scope)
        return jsonify({
            "success": True,
            "enabled": body["enabled"],
            "injection_enabled": injection_enabled,
        })

    @app.delete("/api/sessions/<session_id>/memory/<kind>/<scope_id>")
    def clear_memory(session_id: str, kind: str, scope_id: str):
        with connection(write=True) as db:
            with _SCHEMA_LOCK:
                auth, scope = owned_scope(session_id, kind, scope_id, db)
                store = FaithfulMemoryStore(db)
            store_call(lambda: store.clear_scope(scope, actor_id=auth.user_id))
        return jsonify({"success": True, "cleared": True})

    @app.get("/api/sessions/<session_id>/memory/<kind>/<scope_id>/audit")
    def memory_audit(session_id: str, kind: str, scope_id: str):
        with connection() as db:
            with _SCHEMA_LOCK:
                _, scope = owned_scope(session_id, kind, scope_id, db)
                store = FaithfulMemoryStore(db)
            events = store.list_audit_events(scope)
        response = jsonify({"success": True, "events": events})
        response.headers["Cache-Control"] = "no-store"
        return response
