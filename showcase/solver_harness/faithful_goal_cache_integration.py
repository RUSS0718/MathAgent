"""Opt-in Goal Cache adapter for the trusted formal-verification path."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any


class GoalCacheAdmission:
    """Use one explicitly enabled, owner/session-scoped GlobalGoalCache."""

    def __init__(self, connection, cache, identity, *, actor_id, workspace_id, prover):
        self.connection = connection
        self.cache = cache
        self.identity = identity
        self.actor_id = actor_id
        self.workspace_id = workspace_id
        self.prover = prover

    def recheck(self, request: Mapping[str, Any], *, invoke_current=None) -> dict[str, Any] | None:
        """Return only a fresh current Lean result that passes the prover verifier."""
        if not _explicitly_enabled(self.connection, self.actor_id, self.workspace_id):
            return None
        try:
            current = self.cache.recheck(
                self.identity, request, prover=self.prover, actor_id=self.actor_id,
                invoke_current=invoke_current,
            )
        except Exception:  # noqa: BLE001 - cache errors cannot change the formal verdict
            _record_failure(self.connection, self.actor_id, self.workspace_id, "recheck_failed")
            return None
        if not _explicitly_enabled(self.connection, self.actor_id, self.workspace_id):
            return None
        if not isinstance(current, Mapping) or current.get("status") not in {"rechecked", "stale"}:
            return None
        result = current.get("result")
        if (
            not isinstance(result, Mapping)
            or result.get("status") != "solved"
            or result.get("grade") != "L2"
            or result.get("attempt_id") != request.get("attempt_id")
            or result.get("parent_attempt_id") != request.get("parent_attempt_id")
        ):
            _record_failure(self.connection, self.actor_id, self.workspace_id, "candidate_rejected")
            return None
        try:
            verified = self.prover.verify_result(request, result)
        except Exception:  # noqa: BLE001 - reject a cache result on verifier errors
            verified = None
        if verified not in {"L2", "L3"}:
            _record_failure(self.connection, self.actor_id, self.workspace_id, "candidate_rejected")
            return None
        return dict(result)

    def admit(self, request: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        """Best-effort admission after the normal formal verifier accepts Lean."""
        if (
            not _is_trusted_lean(self.prover)
            or result.get("status") != "solved"
            or result.get("grade") not in {"L2", "L3"}
            or not _explicitly_enabled(self.connection, self.actor_id, self.workspace_id)
        ):
            return
        try:
            self.cache.put_receipt(
                self.identity, request, result,
                prover=self.prover, actor_id=self.actor_id,
            )
        except Exception:  # noqa: BLE001 - admission must not alter a verified result
            _record_failure(self.connection, self.actor_id, self.workspace_id, "admission_failed")


def prepare_goal_cache(connection, request: Mapping[str, Any], prover: Any) -> GoalCacheAdmission | None:
    """Resolve exact job ownership and require an existing explicit enabled row."""
    if connection is None or not isinstance(request, Mapping) or not _is_trusted_lean(prover):
        return None
    try:
        job_id = request.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            return None
        job = connection.execute(
            "SELECT user_id,session_id FROM workspace_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if job is None:
            return None
        owner_id, workspace_id = job[0], job[1]
        if not _explicitly_enabled(connection, owner_id, workspace_id):
            return None
        from .faithful_goal_cache import GlobalGoalCache, GoalCacheIdentity

        cache = GlobalGoalCache(
            connection, owner_id=owner_id, workspace_id=workspace_id
        )
        identity = GoalCacheIdentity.from_request(request, prover=prover)
        return GoalCacheAdmission(
            connection, cache, identity, actor_id=owner_id,
            workspace_id=workspace_id, prover=prover,
        )
    except (AttributeError, IndexError, KeyError, sqlite3.Error, TypeError, ValueError):
        return None


def _is_trusted_lean(prover: Any) -> bool:
    from ..formal import LeanTacticProver
    from ..formal_docker import LeanDockerExecutor

    return isinstance(prover, LeanTacticProver) and isinstance(
        prover.executor, LeanDockerExecutor
    )


def _explicitly_enabled(connection, owner_id: str, workspace_id: str) -> bool:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        ("faithful_goal_cache_control",),
    ).fetchone()
    if table is None:
        return False
    row = connection.execute(
        """SELECT enabled FROM faithful_goal_cache_control
           WHERE owner_id=? AND workspace_id=?""",
        (owner_id, workspace_id),
    ).fetchone()
    return row is not None and row[0] == 1


def _record_failure(connection, owner_id: str, workspace_id: str, category: str) -> None:
    """Append a bounded failure category without taking over the caller transaction."""
    name = "goal_cache_failure_" + uuid.uuid4().hex
    try:
        if not _explicitly_enabled(connection, owner_id, workspace_id):
            return
        connection.execute(f"SAVEPOINT {name}")
        connection.execute(
            """INSERT INTO faithful_goal_cache_audit(
                   event_id, owner_id, workspace_id, cache_id, event, actor_id,
                   details_json, created_at
               ) VALUES (?, ?, ?, NULL, 'cache_integration_failed', ?, ?, ?)""",
            (
                uuid.uuid4().hex, owner_id, workspace_id, owner_id,
                '{"category":"' + category + '"}', datetime.now(UTC).isoformat(),
            ),
        )
        connection.execute(f"RELEASE {name}")
    except sqlite3.Error:
        try:
            connection.execute(f"ROLLBACK TO {name}")
            connection.execute(f"RELEASE {name}")
        except sqlite3.Error:
            pass
