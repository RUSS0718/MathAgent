"""Persist scoped, advisory Run and Population observations."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_LOCK = threading.RLock()
_FORBIDDEN_OBSERVATION_KEYS = frozenset({
    "evidence_level", "grade", "is_proof", "policy_change",
    "proof", "proof_status", "proven", "verified", "verified_gain", "verification",
})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _contains_authority_claim(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            key in _FORBIDDEN_OBSERVATION_KEYS or _contains_authority_claim(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_authority_claim(item) for item in value)
    return False


@dataclass(frozen=True)
class MemoryScope:
    """Identify one owner- and workspace-bound memory scope."""

    kind: str
    scope_id: str
    owner_id: str
    workspace_id: str

    def __post_init__(self) -> None:
        if self.kind not in {"run", "population", "goal_cache"}:
            raise ValueError("memory_scope_kind_invalid")
        for name in ("scope_id", "owner_id", "workspace_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"memory_{name}_required")
            object.__setattr__(self, name, value.strip())


class FaithfulMemoryStore:
    """Own sidecar memory tables on the caller's existing SQLite connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        with _LOCK:
            schema = """
                CREATE TABLE IF NOT EXISTS faithful_memory_entries (
                    record_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS faithful_memory_scope_idx
                    ON faithful_memory_entries(owner_id, workspace_id, scope_kind, scope_id, state);
                CREATE TABLE IF NOT EXISTS faithful_memory_scope_controls (
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner_id, workspace_id, scope_kind, scope_id)
                );
                CREATE TABLE IF NOT EXISTS faithful_memory_injection_controls (
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner_id, workspace_id, scope_kind, scope_id)
                );
                CREATE TABLE IF NOT EXISTS faithful_memory_audit (
                    event_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    record_id TEXT,
                    event TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS faithful_memory_audit_scope_idx
                    ON faithful_memory_audit(owner_id, workspace_id, scope_kind, scope_id, created_at);
                """
            for statement in schema.split(";"):
                if statement.strip():
                    self._connection.execute(statement)

    def record_observation(
        self,
        scope: MemoryScope,
        observation: Mapping[str, Any],
        *,
        provenance: Mapping[str, Any],
    ) -> str:
        """Persist a historical observation without proof or policy authority."""
        payload = self._validate_observation(observation, provenance)
        record_id = uuid.uuid4().hex
        created_at = _utc_now()
        with _LOCK, self._savepoint():
            if not self._enabled(scope):
                raise ValueError("memory_scope_disabled")
            self._connection.execute(
                """INSERT INTO faithful_memory_entries(
                       record_id, owner_id, workspace_id, scope_kind, scope_id,
                       entry_type, state, payload_json, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, 'observation', 'active', ?, ?, ?)""",
                (record_id, *self._scope_values(scope), _json(payload), created_at, created_at),
            )
            self._audit(scope, "observation_recorded", scope.owner_id, record_id, {})
        return record_id

    def list_observations(self, scope: MemoryScope) -> list[dict[str, Any]]:
        """Return active observations from exactly one enabled scope."""
        with _LOCK:
            if not self._enabled(scope):
                return []
            rows = self._connection.execute(
                """SELECT record_id, payload_json FROM faithful_memory_entries
                   WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?
                     AND entry_type='observation' AND state='active'
                   ORDER BY created_at, record_id""",
                self._scope_values(scope),
            ).fetchall()
        return [
            {
                "record_id": row[0],
                **json.loads(row[1]),
                "authority": "historical_observation",
                "trust": "advisory",
            }
            for row in rows
        ]

    def import_observation(
        self,
        record_id: str,
        destination: MemoryScope,
        *,
        actor_id: str,
        allow_cross_workspace: bool = False,
    ) -> str:
        """Copy an observation with explicit provenance and same-owner controls."""
        if not isinstance(actor_id, str) or actor_id != destination.owner_id:
            raise ValueError("memory_import_actor_mismatch")
        if type(allow_cross_workspace) is not bool:
            raise ValueError("memory_import_scope_mismatch")
        with _LOCK, self._savepoint():
            row = self._connection.execute(
                """SELECT owner_id, workspace_id, scope_kind, scope_id, payload_json
                   FROM faithful_memory_entries WHERE record_id=? AND entry_type='observation'
                     AND state='active'""",
                (record_id,),
            ).fetchone()
            if row is None:
                raise ValueError("memory_observation_unavailable")
            source_scope = MemoryScope(row[2], row[3], row[0], row[1])
            if (source_scope.owner_id != destination.owner_id
                    or (source_scope.workspace_id != destination.workspace_id
                        and not allow_cross_workspace)
                    or source_scope == destination):
                raise ValueError("memory_import_scope_mismatch")
            if not self._enabled(source_scope) or not self._enabled(destination):
                raise ValueError("memory_scope_disabled")
            original = json.loads(row[4])
            provenance = dict(original["provenance"])
            provenance.update(
                imported_by=actor_id,
                imported_from={"record_id": record_id, "scope": self._scope_dict(source_scope)},
                original_provenance=dict(original["provenance"]),
            )
            copied = {"observation": original["observation"], "provenance": provenance}
            imported_id = uuid.uuid4().hex
            created_at = _utc_now()
            self._connection.execute(
                """INSERT INTO faithful_memory_entries(
                       record_id, owner_id, workspace_id, scope_kind, scope_id,
                       entry_type, state, payload_json, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, 'observation', 'active', ?, ?, ?)""",
                (imported_id, *self._scope_values(destination), _json(copied), created_at, created_at),
            )
            self._audit(
                destination,
                "observation_imported",
                actor_id,
                imported_id,
                {"source_record_id": record_id, "source_scope": self._scope_dict(source_scope)},
            )
        return imported_id

    def disable_scope(self, scope: MemoryScope, *, actor_id: str) -> None:
        """Hide a scope while retaining its records and an audit event."""
        self._check_actor(scope, actor_id)
        self._set_enabled(scope, False, actor_id)

    def enable_scope(self, scope: MemoryScope, *, actor_id: str) -> None:
        """Re-enable a previously disabled scope."""
        self._check_actor(scope, actor_id)
        self._set_enabled(scope, True, actor_id)

    def clear_scope(self, scope: MemoryScope, *, actor_id: str) -> None:
        """Invalidate current records and append durable scope and entry tombstones."""
        self._check_actor(scope, actor_id)
        now = _utc_now()
        with _LOCK, self._savepoint():
            rows = self._connection.execute(
                """SELECT record_id FROM faithful_memory_entries
                   WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?
                     AND state='active'""",
                self._scope_values(scope),
            ).fetchall()
            for row in rows:
                self._connection.execute(
                    "UPDATE faithful_memory_entries SET state='invalidated', updated_at=? WHERE record_id=?",
                    (now, row[0]),
                )
                self._audit(scope, "entry_cleared", actor_id, row[0], {"tombstone": True})
            self._audit(scope, "scope_cleared", actor_id, None, {"tombstone": True})

    def list_audit_events(self, scope: MemoryScope) -> list[dict[str, Any]]:
        """Return this scope's append-only audit events, including tombstones."""
        with _LOCK:
            rows = self._connection.execute(
                """SELECT record_id, event, actor_id, details_json, created_at
                   FROM faithful_memory_audit
                   WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?
                   ORDER BY created_at, event_id""",
                self._scope_values(scope),
            ).fetchall()
        return [
            {
                "record_id": row[0], "event": row[1], "actor_id": row[2],
                "details": json.loads(row[3]), "created_at": row[4],
            }
            for row in rows
        ]

    @staticmethod
    def _validate_observation(
        observation: Mapping[str, Any], provenance: Mapping[str, Any]
    ) -> dict[str, Any]:
        if not isinstance(observation, Mapping) or not isinstance(provenance, Mapping):
            raise ValueError("memory_observation_invalid")
        if not isinstance(provenance.get("source_run_id"), str) or not provenance["source_run_id"].strip():
            raise ValueError("memory_observation_source_required")
        if observation.get("outcome") not in {"success", "failure", "unknown"}:
            raise ValueError("memory_observation_outcome_invalid")
        if any(not isinstance(observation.get(key), Mapping)
               for key in ("applicability", "versions", "cost", "content")):
            raise ValueError("memory_observation_shape_invalid")
        if _contains_authority_claim(observation):
            raise ValueError("memory_observation_authority_claim")
        try:
            data = json.loads(_json(dict(observation)))
            source = json.loads(_json(dict(provenance)))
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_observation_not_json") from exc
        return {"observation": data, "provenance": source}

    def _set_enabled(self, scope: MemoryScope, enabled: bool, actor_id: str) -> None:
        now = _utc_now()
        with _LOCK, self._savepoint():
            self._connection.execute(
                """INSERT INTO faithful_memory_scope_controls(
                       owner_id, workspace_id, scope_kind, scope_id, enabled, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(owner_id, workspace_id, scope_kind, scope_id)
                   DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at""",
                (*self._scope_values(scope), int(enabled), now),
            )
            self._audit(scope, "scope_enabled" if enabled else "scope_disabled", actor_id, None, {})

    def _enabled(self, scope: MemoryScope) -> bool:
        row = self._connection.execute(
            """SELECT enabled FROM faithful_memory_scope_controls
               WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?""",
            self._scope_values(scope),
        ).fetchone()
        return row is None or bool(row[0])

    def injection_enabled(self, scope: MemoryScope) -> bool:
        """Require an explicit user enablement before injecting memory into a Run."""
        row = self._connection.execute(
            """SELECT enabled FROM faithful_memory_injection_controls
               WHERE owner_id=? AND workspace_id=? AND scope_kind=? AND scope_id=?""",
            self._scope_values(scope),
        ).fetchone()
        return row is not None and bool(row[0])

    def set_injection_enabled(self, scope: MemoryScope, enabled: bool, *, actor_id: str) -> None:
        """Set Run-injection consent without hiding or disabling stored observations."""
        self._check_actor(scope, actor_id)
        if type(enabled) is not bool:
            raise ValueError("memory_control_enabled_invalid")
        now = _utc_now()
        with _LOCK, self._savepoint():
            self._connection.execute(
                """INSERT INTO faithful_memory_injection_controls(
                       owner_id, workspace_id, scope_kind, scope_id, enabled, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(owner_id, workspace_id, scope_kind, scope_id)
                   DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at""",
                (*self._scope_values(scope), int(enabled), now),
            )
            self._audit(
                scope,
                "injection_enabled" if enabled else "injection_disabled",
                actor_id,
                None,
                {"injection_only": True},
            )

    def _audit(
        self,
        scope: MemoryScope,
        event: str,
        actor_id: str,
        record_id: str | None,
        details: Mapping[str, Any],
    ) -> None:
        self._connection.execute(
            """INSERT INTO faithful_memory_audit(
                   event_id, owner_id, workspace_id, scope_kind, scope_id,
                   record_id, event, actor_id, details_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, *self._scope_values(scope), record_id, event, actor_id,
             _json(dict(details)), _utc_now()),
        )

    @staticmethod
    def _scope_values(scope: MemoryScope) -> tuple[str, str, str, str]:
        return scope.owner_id, scope.workspace_id, scope.kind, scope.scope_id

    @staticmethod
    def _scope_dict(scope: MemoryScope) -> dict[str, str]:
        return {
            "kind": scope.kind,
            "scope_id": scope.scope_id,
            "owner_id": scope.owner_id,
            "workspace_id": scope.workspace_id,
        }

    @staticmethod
    def _check_actor(scope: MemoryScope, actor_id: str) -> None:
        if not isinstance(actor_id, str) or actor_id != scope.owner_id:
            raise ValueError("memory_control_actor_mismatch")

    def _savepoint(self):
        """Isolate sidecar writes without committing a caller's transaction."""
        return _Savepoint(self._connection)


class _Savepoint:
    """Commit or roll back one namespaced sequence on the shared connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.name = "faithful_memory_" + uuid.uuid4().hex

    def __enter__(self):
        self.connection.execute(f"SAVEPOINT {self.name}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.connection.execute(f"ROLLBACK TO {self.name}")
        self.connection.execute(f"RELEASE {self.name}")
        return False
