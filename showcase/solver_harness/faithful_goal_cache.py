"""Persist Global Goal Cache fingerprints and recheck them with trusted Lean."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_LOCK = threading.RLock()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class GoalCacheIdentity:
    """The complete semantic and execution identity for one cached Lean proof."""

    goal: Mapping[str, Any]
    hypotheses: tuple[Any, ...]
    declarations: tuple[str, ...]
    imports: tuple[str, ...]
    environment: Mapping[str, Any]
    template_version: str
    axiom_policy: tuple[str, ...]
    specification_version: Any
    target_version: str
    proof_identity: str

    def __post_init__(self) -> None:
        if not isinstance(self.goal, Mapping) or not isinstance(self.environment, Mapping):
            raise ValueError("goal_cache_identity_invalid")
        try:
            goal = json.loads(_canonical_json(dict(self.goal)))
            environment = json.loads(_canonical_json(dict(self.environment)))
            hypotheses = tuple(json.loads(_canonical_json(list(self.hypotheses))))
        except (TypeError, ValueError) as exc:
            raise ValueError("goal_cache_identity_invalid") from exc
        for name in ("template_version", "target_version", "proof_identity"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"goal_cache_{name}_required")
        if not self.declarations or not self.imports or not self.axiom_policy:
            raise ValueError("goal_cache_identity_incomplete")
        if any(not isinstance(value, str) or not value for value in (
            *self.declarations, *self.imports, *self.axiom_policy
        )):
            raise ValueError("goal_cache_identity_invalid")
        object.__setattr__(self, "goal", goal)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "hypotheses", hypotheses)
        object.__setattr__(self, "declarations", tuple(self.declarations))
        object.__setattr__(self, "imports", tuple(self.imports))
        object.__setattr__(self, "axiom_policy", tuple(sorted(set(self.axiom_policy))))

    @classmethod
    def from_request(cls, request: Mapping[str, Any], *, prover: Any) -> GoalCacheIdentity:
        """Derive every key component from a normalized request and pinned Lean backend."""
        from ..formal import (
            RATIONAL_POLYNOMIAL_TARGET,
            LeanTacticProver,
            build_polynomial_identity_source,
            normalize_formal_request,
        )
        from ..formal_docker import LeanDockerExecutor, load_trusted_manifest
        from ..formal_specification import TEMPLATE_VERSION

        if not isinstance(prover, LeanTacticProver) or not isinstance(
            prover.executor, LeanDockerExecutor
        ):
            raise ValueError("goal_cache_requires_trusted_lean")
        normalized = normalize_formal_request(request)
        policy = normalized["policy"]
        if policy["enabled"] is not True or policy["backend"] != prover.name:
            raise ValueError("goal_cache_formal_policy_invalid")
        manifest = load_trusted_manifest(prover.executor.manifest)
        dependencies = manifest.get("dependency_audit", {})
        if (
            prover.executor.environment_hash != manifest.get("deployment_manifest_sha256")
            or dependencies.get("passed") is not True
            or not dependencies.get("packages")
        ):
            raise ValueError("goal_cache_lean_environment_untrusted")
        build = manifest.get("build_manifest", {})
        template_version = build.get("template_version")
        if template_version != TEMPLATE_VERSION:
            raise ValueError("goal_cache_template_unsupported")
        source = build_polynomial_identity_source(normalized["target"])
        imports = tuple(
            line.split(maxsplit=1)[1]
            for line in source.splitlines()
            if line.startswith("import ")
        )
        declarations = tuple(re.findall(r"^(?:theorem|lemma|def)\s+([A-Za-z_][\w']*)", source, re.M))
        if not imports or declarations != ("polynomial_identity",):
            raise ValueError("goal_cache_proof_source_invalid")
        specification = normalized["specification"]
        hypotheses = tuple(specification.get("assumptions", ())) + tuple(
            normalized["target"].get("assumptions", ())
        )
        return cls(
            goal={
                "target": normalized["target"],
                "specification_hash": specification["hash"],
            },
            hypotheses=hypotheses,
            declarations=declarations,
            imports=imports,
            environment=manifest,
            template_version=template_version,
            axiom_policy=tuple(policy["allowed_axioms"]),
            specification_version=specification.get("specification_version"),
            target_version=RATIONAL_POLYNOMIAL_TARGET,
            proof_identity="sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest(),
        )

    @property
    def key(self) -> str:
        """Return a stable digest over goal, context, environment, policy, and proof identity."""
        return _digest(self.to_dict())

    @property
    def lookup_key(self) -> str:
        """Locate the same logical goal when another key dimension has drifted."""
        return _digest({
            "goal": self.goal,
            "hypotheses": self.hypotheses,
            "specification_version": self.specification_version,
            "target_version": self.target_version,
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": dict(self.goal),
            "hypotheses": list(self.hypotheses),
            "declarations": list(self.declarations),
            "imports": list(self.imports),
            "environment": dict(self.environment),
            "template_version": self.template_version,
            "axiom_policy": list(self.axiom_policy),
            "specification_version": self.specification_version,
            "target_version": self.target_version,
            "proof_identity": self.proof_identity,
        }


class GlobalGoalCache:
    """Store per-workspace cache records and audit state on a shared SQLite connection."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        owner_id: str,
        workspace_id: str,
    ) -> None:
        self._connection = connection
        self.owner_id = self._required_identity(owner_id, "owner")
        self.workspace_id = self._required_identity(workspace_id, "workspace")
        with _LOCK, self._savepoint():
            statements = (
                """CREATE TABLE IF NOT EXISTS faithful_goal_cache_entries (
                    cache_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    lookup_key TEXT NOT NULL,
                    identity_json TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('active','stale','invalidated')),
                    state_reason TEXT,
                    proof_source_hash TEXT NOT NULL,
                    proof_hash TEXT NOT NULL,
                    target_hash TEXT NOT NULL,
                    environment_hash TEXT NOT NULL,
                    grade TEXT NOT NULL CHECK(grade IN ('L2','L3')),
                    source_run_id TEXT NOT NULL,
                    source_attempt_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""",
                """CREATE INDEX IF NOT EXISTS faithful_goal_cache_identity_idx
                    ON faithful_goal_cache_entries(owner_id, workspace_id, identity_key, created_at)""",
                """CREATE INDEX IF NOT EXISTS faithful_goal_cache_lookup_idx
                    ON faithful_goal_cache_entries(owner_id, workspace_id, lookup_key, created_at)""",
                """CREATE TABLE IF NOT EXISTS faithful_goal_cache_control (
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(owner_id, workspace_id)
                )""",
                """CREATE TABLE IF NOT EXISTS faithful_goal_cache_audit (
                    event_id TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    cache_id TEXT,
                    event TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""",
                """CREATE INDEX IF NOT EXISTS faithful_goal_cache_audit_idx
                    ON faithful_goal_cache_audit(owner_id, workspace_id, created_at)""",
            )
            for statement in statements:
                self._connection.execute(statement)

    def put_receipt(
        self,
        identity: GoalCacheIdentity,
        request: Mapping[str, Any],
        result: Mapping[str, Any],
        *,
        prover: Any,
        actor_id: str,
    ) -> str:
        """Admit only a current, genuinely verified L2+ Lean receipt."""
        self._check_actor(actor_id)
        try:
            self._check_identity(identity, request, prover)
            self._verified_grade(request, result, prover)
            grade = str(result.get("grade"))
            proof = result.get("proof_artifact") or {}
            if (
                identity.proof_identity != "sha256:" + str(proof.get("source_hash"))
                or proof.get("target_hash") != identity.goal["target"]["hash"]
                or proof.get("environment_hash")
                != identity.environment["deployment_manifest_sha256"]
                or proof.get("dependency_audit", {}).get("passed") is not True
                or proof.get("dependency_audit", {}).get("recursive") is not True
            ):
                raise ValueError("goal_cache_receipt_identity_invalid")
            run_id = request.get("run_id")
            attempt_id = request.get("attempt_id")
            if not isinstance(run_id, str) or not isinstance(attempt_id, str):
                raise ValueError("goal_cache_receipt_provenance_invalid")
        except Exception as error:
            self._audit_rejected_receipt(actor_id, error)
            raise
        now = _utc_now()
        with _LOCK, self._savepoint():
            self._require_enabled()
            existing = self._latest_by_key(identity.key)
            if existing is not None and existing[4] == "active":
                if existing[6] == proof["source_hash"] and existing[7] == proof["proof_hash"]:
                    self._audit(existing[0], "receipt_duplicate", actor_id, {"grade": grade})
                    return existing[0]
                self._transition(existing[0], "stale", "proof_identity_changed", actor_id)
            cache_id = uuid.uuid4().hex
            self._connection.execute(
                """INSERT INTO faithful_goal_cache_entries(
                       cache_id, owner_id, workspace_id, identity_key, lookup_key, identity_json,
                       state, state_reason, proof_source_hash, proof_hash, target_hash,
                       environment_hash, grade, source_run_id, source_attempt_id,
                       created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cache_id, self.owner_id, self.workspace_id, identity.key,
                    identity.lookup_key, _canonical_json(identity.to_dict()),
                    proof["source_hash"], proof["proof_hash"], proof["target_hash"],
                    proof["environment_hash"], grade, run_id, attempt_id, now, now,
                ),
            )
            self._audit(cache_id, "receipt_admitted", actor_id, {
                "grade": grade,
                "source_run_id": run_id,
                "source_attempt_id": attempt_id,
                "dependency_audit": "recursive_passed",
            })
        return cache_id

    def recheck(
        self,
        identity: GoalCacheIdentity,
        request: Mapping[str, Any],
        *,
        prover: Any,
        actor_id: str,
        invoke_current=None,
    ) -> dict[str, Any] | None:
        """Re-run current Lean through the supplied bounded path, never replay old evidence."""
        self._check_actor(actor_id)
        if invoke_current is not None and not callable(invoke_current):
            raise ValueError("goal_cache_invoker_invalid")
        with _LOCK:
            row = self._latest_by_key(identity.key)
            if not self._enabled():
                if row is not None:
                    with self._savepoint():
                        self._audit(
                            row[0], "receipt_check_suppressed", actor_id, {"tombstone": True}
                        )
                return None
            if row is None:
                drifted = self._latest_by_lookup(identity.lookup_key)
                if drifted is None:
                    return None
                reason = self._identity_drift_reason(drifted[3], identity)
                self._transition(drifted[0], "stale", reason, actor_id)
                return self._state_result(drifted[0], "stale", reason)
            if row[4] != "active":
                return self._state_result(row[0], row[4], row[5])

        try:
            self._check_identity(identity, request, prover)
        except Exception:
            self._transition(row[0], "stale", "current_lean_identity_untrusted", actor_id)
            return self._state_result(row[0], "stale", "current_lean_identity_untrusted")

        try:
            fresh_result = (
                invoke_current(request) if invoke_current is not None
                else prover.invoke(request)
            )
            self._verified_grade(request, fresh_result, prover)
        except Exception:
            self._transition(row[0], "stale", "lean_recheck_failed", actor_id)
            return self._state_result(row[0], "stale", "lean_recheck_failed")
        proof = fresh_result.get("proof_artifact") or {}
        if (
            proof.get("source_hash") != row[6]
            or proof.get("proof_hash") != row[7]
            or proof.get("target_hash") != row[8]
            or proof.get("environment_hash") != row[9]
        ):
            self._transition(row[0], "stale", "lean_proof_or_environment_drift", actor_id)
            safe_result = json.loads(_canonical_json(dict(fresh_result)))
            safe_result["grade"] = "L2"
            return {
                **self._state_result(row[0], "stale", "lean_proof_or_environment_drift"),
                "result": safe_result,
            }

        safe_result = json.loads(_canonical_json(dict(fresh_result)))
        safe_result["grade"] = "L2"
        with _LOCK, self._savepoint():
            # A clear/disable may finish while Lean is executing outside the lock.
            current = self._latest_by_key(identity.key)
            if not self._enabled():
                self._audit(row[0], "receipt_check_suppressed", actor_id, {"tombstone": True})
                return None
            if current is None or current[0] != row[0]:
                return None
            if current[4] != "active":
                return self._state_result(current[0], current[4], current[5])
            self._connection.execute(
                "UPDATE faithful_goal_cache_entries SET updated_at=? WHERE cache_id=?",
                (_utc_now(), row[0]),
            )
            self._audit(row[0], "receipt_rechecked", actor_id, {"grade_ceiling": "L2"})
        return {"cache_id": row[0], "status": "rechecked", "grade": "L2", "result": safe_result}

    def invalidate(self, identity: GoalCacheIdentity, *, actor_id: str, reason: str) -> None:
        """Append an invalidation tombstone for the latest matching identity."""
        self._check_actor(actor_id)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("goal_cache_invalidation_reason_required")
        with _LOCK, self._savepoint():
            row = self._latest_by_key(identity.key)
            if row is None:
                raise ValueError("goal_cache_receipt_not_found")
            self._transition(row[0], "invalidated", reason.strip(), actor_id)

    def disable(self, *, actor_id: str) -> None:
        """Hide this workspace's cache and retain an audit tombstone."""
        self._set_enabled(False, actor_id)

    def enable(self, *, actor_id: str) -> None:
        """Re-enable cache access without changing prior receipt states."""
        self._set_enabled(True, actor_id)

    def clear(self, *, actor_id: str) -> None:
        """Invalidate active receipts in place and append one tombstone per receipt."""
        self._check_actor(actor_id)
        with _LOCK, self._savepoint():
            rows = self._connection.execute(
                """SELECT cache_id FROM faithful_goal_cache_entries
                   WHERE owner_id=? AND workspace_id=? AND state IN ('active','stale')""",
                (self.owner_id, self.workspace_id),
            ).fetchall()
            for row in rows:
                self._transition(row[0], "invalidated", "cache_cleared", actor_id)
            self._audit(None, "cache_cleared", actor_id, {"tombstone": True})

    def list_audit_events(self) -> list[dict[str, Any]]:
        """Return audit records for this owner and workspace only."""
        with _LOCK:
            rows = self._connection.execute(
                """SELECT cache_id, event, actor_id, details_json, created_at
                   FROM faithful_goal_cache_audit
                   WHERE owner_id=? AND workspace_id=? ORDER BY created_at, event_id""",
                (self.owner_id, self.workspace_id),
            ).fetchall()
        return [
            {
                "cache_id": row[0], "event": row[1], "actor_id": row[2],
                "details": json.loads(row[3]), "created_at": row[4],
            }
            for row in rows
        ]

    def list_entries(self) -> list[dict[str, Any]]:
        """Return cache metadata and lifecycle states without exposing old receipts."""
        with _LOCK:
            rows = self._connection.execute(
                """SELECT cache_id, identity_key, state, state_reason, grade,
                          source_run_id, source_attempt_id, created_at, updated_at
                   FROM faithful_goal_cache_entries
                   WHERE owner_id=? AND workspace_id=?
                   ORDER BY created_at, cache_id""",
                (self.owner_id, self.workspace_id),
            ).fetchall()
        return [
            {
                "cache_id": row[0], "identity_key": row[1], "state": row[2],
                "reason": row[3], "grade_ceiling": "L2", "source_grade": row[4],
                "source_run_id": row[5], "source_attempt_id": row[6],
                "created_at": row[7], "updated_at": row[8],
            }
            for row in rows
        ]

    @staticmethod
    def _verified_grade(request: Mapping[str, Any], result: Mapping[str, Any], prover: Any) -> str:
        from ..formal import LeanTacticProver
        from ..formal_docker import LeanDockerExecutor

        if not isinstance(prover, LeanTacticProver) or not isinstance(
            prover.executor, LeanDockerExecutor
        ):
            raise ValueError("goal_cache_requires_trusted_lean")
        if not isinstance(result, Mapping) or result.get("status") != "solved":
            raise ValueError("goal_cache_result_not_solved")
        grade = result.get("grade")
        if grade not in {"L2", "L3"} or prover.verify_result(request, result) != grade:
            raise ValueError("goal_cache_result_not_trusted")
        manifest = prover.executor.manifest
        dependencies = manifest.get("dependency_audit", {})
        artifact = result.get("proof_artifact") or {}
        audit = artifact.get("dependency_audit", {})
        if (
            dependencies.get("passed") is not True
            or not dependencies.get("packages")
            or audit.get("passed") is not True
            or audit.get("recursive") is not True
            or artifact.get("environment_hash") != prover.executor.environment_hash
        ):
            raise ValueError("goal_cache_dependency_audit_incomplete")
        return "L2"

    def _check_identity(self, identity: GoalCacheIdentity, request: Mapping[str, Any], prover: Any) -> None:
        if not isinstance(identity, GoalCacheIdentity):
            raise ValueError("goal_cache_identity_invalid")
        current = GoalCacheIdentity.from_request(request, prover=prover)
        if current.key != identity.key:
            raise ValueError("goal_cache_identity_mismatch")

    def _latest_by_key(self, identity_key: str):
        return self._connection.execute(
            """SELECT cache_id, identity_key, lookup_key, identity_json, state,
                      state_reason, proof_source_hash, proof_hash, target_hash,
                      environment_hash, grade, source_run_id, source_attempt_id,
                      created_at, updated_at
               FROM faithful_goal_cache_entries
               WHERE owner_id=? AND workspace_id=? AND identity_key=?
               ORDER BY created_at DESC, cache_id DESC LIMIT 1""",
            (self.owner_id, self.workspace_id, identity_key),
        ).fetchone()

    def _latest_by_lookup(self, lookup_key: str):
        return self._connection.execute(
            """SELECT cache_id, identity_key, lookup_key, identity_json, state,
                      state_reason, proof_source_hash, proof_hash, target_hash,
                      environment_hash, grade, source_run_id, source_attempt_id,
                      created_at, updated_at
               FROM faithful_goal_cache_entries
               WHERE owner_id=? AND workspace_id=? AND lookup_key=? AND state='active'
               ORDER BY created_at DESC, cache_id DESC LIMIT 1""",
            (self.owner_id, self.workspace_id, lookup_key),
        ).fetchone()

    @staticmethod
    def _identity_drift_reason(previous_json: str, current: GoalCacheIdentity) -> str:
        """Name the first changed cache dimension without exposing stored proof data."""
        previous = json.loads(previous_json)
        current_value = current.to_dict()
        for key, reason in (
            ("declarations", "declaration_drift"),
            ("imports", "import_dependency_drift"),
            ("template_version", "template_drift"),
            ("axiom_policy", "axiom_policy_drift"),
            ("proof_identity", "proof_identity_drift"),
        ):
            if previous.get(key) != current_value[key]:
                return reason
        if previous.get("environment", {}).get("dependency_audit") != (
            current_value["environment"].get("dependency_audit")
        ):
            return "dependency_audit_drift"
        if previous.get("environment") != current_value["environment"]:
            return "lean_environment_drift"
        return "goal_cache_key_drift"

    def _audit_rejected_receipt(self, actor_id: str, error: Exception) -> None:
        """Persist a bounded admission reason only while this scope is enabled."""
        message = str(error)
        reason = (
            message if re.fullmatch(r"goal_cache_[a-z0-9_]{1,80}", message)
            else "goal_cache_admission_validation_failed"
        )
        with _LOCK, self._savepoint():
            if self._enabled():
                self._audit(None, "receipt_rejected", actor_id, {"reason": reason})

    def _transition(self, cache_id: str, state: str, reason: str, actor_id: str) -> None:
        with _LOCK, self._savepoint():
            allowed_prior = "state IN ('active','stale')" if state == "invalidated" else "state='active'"
            changed = self._connection.execute(
                f"""UPDATE faithful_goal_cache_entries
                    SET state=?, state_reason=?, updated_at=?
                    WHERE cache_id=? AND {allowed_prior}""",
                (state, reason, _utc_now(), cache_id),
            ).rowcount
            if changed:
                self._audit(
                    cache_id,
                    "receipt_stale" if state == "stale" else "receipt_invalidated",
                    actor_id,
                    {"reason": reason, "tombstone": state == "invalidated"},
                )

    def _state_result(self, cache_id: str, state: str, reason: str | None) -> dict[str, Any]:
        return {"cache_id": cache_id, "status": state, "reason": reason, "grade": None}

    def _set_enabled(self, enabled: bool, actor_id: str) -> None:
        self._check_actor(actor_id)
        with _LOCK, self._savepoint():
            self._connection.execute(
                """INSERT INTO faithful_goal_cache_control(
                       owner_id, workspace_id, enabled, updated_at
                   ) VALUES (?, ?, ?, ?)
                   ON CONFLICT(owner_id, workspace_id)
                   DO UPDATE SET enabled=excluded.enabled, updated_at=excluded.updated_at""",
                (self.owner_id, self.workspace_id, int(enabled), _utc_now()),
            )
            self._audit(
                None,
                "cache_enabled" if enabled else "cache_disabled",
                actor_id,
                {"tombstone": not enabled},
            )

    def _enabled(self) -> bool:
        row = self._connection.execute(
            """SELECT enabled FROM faithful_goal_cache_control
               WHERE owner_id=? AND workspace_id=?""",
            (self.owner_id, self.workspace_id),
        ).fetchone()
        return row is not None and row[0] == 1

    def _require_enabled(self) -> None:
        if not self._enabled():
            raise ValueError("goal_cache_disabled")

    def _audit(
        self, cache_id: str | None, event: str, actor_id: str, details: Mapping[str, Any]
    ) -> None:
        self._connection.execute(
            """INSERT INTO faithful_goal_cache_audit(
                   event_id, owner_id, workspace_id, cache_id, event, actor_id,
                   details_json, created_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, self.owner_id, self.workspace_id, cache_id, event,
             actor_id, _canonical_json(dict(details)), _utc_now()),
        )

    def _check_actor(self, actor_id: str) -> None:
        if not isinstance(actor_id, str) or actor_id != self.owner_id:
            raise ValueError("goal_cache_actor_mismatch")

    @staticmethod
    def _required_identity(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"goal_cache_{name}_required")
        return value.strip()

    def _savepoint(self):
        return _Savepoint(self._connection)


class _Savepoint:
    """Keep cache writes inside the caller's transaction boundary."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.name = "faithful_goal_cache_" + uuid.uuid4().hex

    def __enter__(self):
        self.connection.execute(f"SAVEPOINT {self.name}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            self.connection.execute(f"ROLLBACK TO {self.name}")
        self.connection.execute(f"RELEASE {self.name}")
        return False
