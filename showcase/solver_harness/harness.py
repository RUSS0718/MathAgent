"""Public Solver Harness entry and recovery seam."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..redaction import redact
from ..storage import SQLiteStore
from .explore import ModelPort, run_exploration
from .storage import (
    SolverEventConflictError,
    SolverPersistenceError,
    SolverRevisionConflictError,
    SolverStateStore,
)

__all__ = [
    "SolverHarness",
    "SolverHarnessError",
    "SolverEventConflictError",
    "SolverIdentityError",
    "SolverRevisionConflictError",
    "SolverRunNotFoundError",
    "SolverValidationError",
]


class SolverHarnessError(RuntimeError):
    """Base error for Solver Harness operations."""


class SolverValidationError(SolverHarnessError, ValueError):
    """Raised when a Solver Harness input is invalid."""


class SolverIdentityError(SolverHarnessError, ValueError):
    """Raised when a run_id is reused with a different problem or config."""


class SolverRunNotFoundError(SolverHarnessError, KeyError):
    """Raised when a Solver Run is not present in the configured store."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"solver_run_not_found: {run_id}")
        self.run_id = run_id


class SolverHarness:
    """Initialize, explicitly explore, or recover a Solver Run from Showcase SQLite."""

    def __init__(
        self,
        *,
        database_path: str | Path | None = None,
        store: SQLiteStore | None = None,
        config: Mapping[str, Any] | None = None,
        model_port: ModelPort | None = None,
    ) -> None:
        if store is not None and database_path is not None:
            raise SolverValidationError("provide either store or database_path")
        self._config = _normalize_config(config)
        self._config_hash = _hash_json(self._config)
        self._model_port = model_port
        self._owns_showcase_store = store is None
        self._showcase_store = (
            store if store is not None else SQLiteStore(database_path or ":memory:")
        )
        self._state_store = SolverStateStore(self._showcase_store._connection)

    def solve(
        self,
        problem: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Initialize or recover a run; optional ``metadata['run_id']`` selects its ID.

        If metadata omits ``run_id``, one is generated. The input problem and metadata
        are not persisted. An injected model port enables bounded exploration;
        otherwise only initialization runs. Reusing a run ID with different problem
        or config content is rejected.
        """

        if not isinstance(problem, str) or not problem.strip():
            raise SolverValidationError("problem must be a non-empty string")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise SolverValidationError("metadata must be a mapping")
        run_id = _run_id(metadata)
        problem_hash = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        existing = self._state_store.get_run(run_id)
        if existing is not None:
            self._validate_identity(existing, run_id, problem_hash)
            if self._model_port is None or existing["state"].get("phase") != "SETUP":
                return existing
            return self._run_exploration(existing, problem)

        state = _initial_state(run_id, problem_hash, self._config_hash)
        event = {
            "event_id": "initialized",
            "run_id": run_id,
            "type": "run_initialized",
            "state_revision": 0,
            "summary": "Solver run initialized",
            "created_at": state["created_at"],
        }
        if not self._state_store.create_run(state, event):
            existing = self._state_store.get_run(run_id)
            if existing is None:
                raise SolverPersistenceError("create_run")
            self._validate_identity(existing, run_id, problem_hash)
            return existing
        created = self._state_store.get_run(run_id)
        if created is None:
            raise SolverPersistenceError("create_run")
        if self._model_port is None:
            return created
        return self._run_exploration(created, problem)

    def get_run(self, run_id: str, *, problem: str | None = None) -> dict[str, Any]:
        """Recover a run and optionally verify the expected problem identity."""

        if not isinstance(run_id, str) or not run_id.strip():
            raise SolverValidationError("run_id must be a non-empty string")
        normalized_run_id = run_id.strip()
        result = self._state_store.get_run(normalized_run_id)
        if result is None:
            raise SolverRunNotFoundError(normalized_run_id)
        if problem is not None and (not isinstance(problem, str) or not problem.strip()):
            raise SolverValidationError("problem must be a non-empty string")
        problem_hash = (
            None if problem is None else hashlib.sha256(problem.encode("utf-8")).hexdigest()
        )
        self._validate_identity(result, normalized_run_id, problem_hash)
        return result

    def commit_event(
        self,
        run_id: str,
        *,
        expected_revision: int,
        event: Mapping[str, Any],
        state_updates: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one event and apply its state patch using revision compare-and-swap.

        The event must include a stable ``event_id`` and ``type``. Replaying the
        same event and patch is idempotent, even when ``expected_revision`` is now
        stale. Snapshot identity, revision, and timestamps are maintained here.
        """

        if not isinstance(run_id, str) or not run_id.strip():
            raise SolverValidationError("run_id must be a non-empty string")
        normalized_run_id = run_id.strip()
        if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
            raise SolverValidationError("expected_revision must be a non-negative integer")
        if expected_revision < 0:
            raise SolverValidationError("expected_revision must be a non-negative integer")

        normalized_event = redact(_normalize_json_mapping(event, "event"))
        event_id = normalized_event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise SolverValidationError("event.event_id must be a non-empty string")
        normalized_event["event_id"] = event_id.strip()
        event_type = normalized_event.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            raise SolverValidationError("event.type must be a non-empty string")
        normalized_event["type"] = event_type.strip()
        if {"run_id", "state_revision", "created_at", "_request_hash"} & normalized_event.keys():
            raise SolverValidationError("event cannot set storage-managed fields")

        update_input = {} if state_updates is None else state_updates
        normalized_updates = _normalize_json_mapping(update_input, "state_updates")
        if {
            "run_id",
            "problem_hash",
            "config_hash",
            "state_revision",
            "created_at",
            "updated_at",
        } & normalized_updates.keys():
            raise SolverValidationError("state_updates cannot change identity or revision fields")

        # Validate the persisted run identity before writing through this Harness.
        self.get_run(normalized_run_id)
        request_hash = _hash_json(
            {"event": normalized_event, "state_updates": normalized_updates}
        )
        return self._state_store.commit_event(
            normalized_run_id,
            expected_revision=expected_revision,
            event=normalized_event,
            state_updates=normalized_updates,
            request_hash=request_hash,
        )

    def _validate_identity(
        self,
        result: Mapping[str, Any],
        run_id: str,
        problem_hash: str | None,
    ) -> None:
        state = result["state"]
        if result.get("run_id") != run_id or state.get("run_id") != run_id:
            raise SolverIdentityError("run_id does not match the persisted Solver Run")
        if problem_hash is not None and state.get("problem_hash") != problem_hash:
            raise SolverIdentityError("run_id already belongs to a different problem")
        if state.get("config_hash") != self._config_hash:
            raise SolverIdentityError("run_id already belongs to a different config")

    def _run_exploration(self, run: dict[str, Any], problem: str) -> dict[str, Any]:
        if self._model_port is None:
            return run
        max_model_calls = _non_negative_config_int(self._config, "max_model_calls", 2)
        max_explore_rounds = min(
            2, _positive_config_int(self._config, "max_explore_rounds", 2)
        )
        # STAR's 3600-second default bounds this Showcase run, not official scoring.
        return run_exploration(
            self,
            run,
            problem=problem,
            model_port=self._model_port,
            max_model_calls=max_model_calls,
            max_explore_rounds=max_explore_rounds,
            max_runtime_seconds=_non_negative_config_int(
                self._config, "max_total_duration_seconds", 3600
            ),
        )

    def close(self) -> None:
        """Close the Showcase SQLite connection if this Harness created it."""

        if self._owns_showcase_store:
            self._showcase_store.close()

    def __enter__(self) -> SolverHarness:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _run_id(metadata: Mapping[str, Any] | None) -> str:
    requested = None if metadata is None else metadata.get("run_id")
    if requested is None:
        return f"solver_{uuid.uuid4().hex}"
    if not isinstance(requested, str) or not requested.strip():
        raise SolverValidationError("metadata.run_id must be a non-empty string")
    return requested.strip()


def _normalize_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise SolverValidationError("config must be a mapping")
    try:
        normalized = json.loads(
            json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as exc:
        raise SolverValidationError("config must be JSON serializable") from exc
    if not isinstance(normalized, dict):
        raise SolverValidationError("config must be a mapping")
    return normalized


def _hash_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_json_mapping(value: Mapping[str, Any] | None, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SolverValidationError(f"{label} must be a mapping")
    try:
        normalized = json.loads(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    except (TypeError, ValueError) as exc:
        raise SolverValidationError(f"{label} must be JSON serializable") from exc
    if not isinstance(normalized, dict):
        raise SolverValidationError(f"{label} must be a mapping")
    return normalized


def _non_negative_config_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise SolverValidationError(f"config.{key} must be a non-negative integer")
    return value


def _positive_config_int(config: Mapping[str, Any], key: str, default: int) -> int:
    value = config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SolverValidationError(f"config.{key} must be a positive integer")
    return value


def _initial_state(run_id: str, problem_hash: str, config_hash: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": "1.1",
        "run_id": run_id,
        "problem_hash": problem_hash,
        "config_hash": config_hash,
        "phase": "SETUP",
        "status": "running",
        "plan_version": 0,
        "attempt_index": 0,
        "current_step": None,
        "steps": {},
        "exploration_findings": [],
        "accepted_results": [],
        "failure_records": [],
        "verified_results_ledger": [],
        "confirmed_failures_ledger": [],
        "meta_interventions": [],
        "reexploration_tasks": [],
        "session_registry": {},
        "run_salt": uuid.uuid4().hex,
        "state_revision": 0,
        "tool_policy": {"allow": []},
        "partial_transcript_refs": [],
        "session_refs": {},
        "counters": {"model_calls": 0, "tool_calls": 0},
        "budget": {},
        "usage": {},
        "artifact_refs": {},
        "created_at": now,
        "updated_at": now,
        "candidate_registry": None,
        "best_effort_decision": None,
        "finalization_reason": None,
    }
