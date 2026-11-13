"""Public Solver Harness entry and recovery seam."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..redaction import redact
from ..storage import SQLiteStore
from .context_pack import frozen_policy, prepare_context_request
from .controller import advance, protocol_failure_exit, run_supplied_plan_or_explore
from .explore import ModelPort
from .harness_config import (
    SolverHarnessError,
    SolverValidationError,
    _hash_json,
    _normalize_config,
    _normalize_json_mapping,
    _run_id,
)
from .initial_state import initial_state
from .meta import MetaPort
from .plan import validate_plan
from .review import VerifierPort
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
        verifier_port: VerifierPort | None = None,
        meta_port: MetaPort | None = None,
        tool_port=None,
        event_observer=None,
    ) -> None:
        if store is not None and database_path is not None:
            raise SolverValidationError("provide either store or database_path")
        self._instance_id = uuid.uuid4().hex
        self._product_recovery = False
        self._population_owner = None
        self._population_futures = {}
        self._event_observer = event_observer
        self._config = _normalize_config(config)
        if self._config.get("features", {}).get("auto_problem_spec") is True and any(
            self._config.get("features", {}).get(key) is not True
            for key in ("problem_spec", "stream_recovery")
        ):
            raise SolverValidationError("auto_problem_spec_requires_problem_spec_and_stream_recovery")
        if self._config.get("features", {}).get("concurrent_routes") is True:
            from .population_lifecycle import validate_config

            validate_config(self._config)
        if self._config.get("features", {}).get("problem_spec") is True:
            if (self._config.get("acceptance_mode", "strict") != "strict"
                    or self._config.get("features", {}).get("final_generation") is not True
                    or self._config.get("features", {}).get("final_solution_review") is not True):
                raise SolverValidationError(
                    "problem_spec_requires_strict_final_generation_and_review"
                )
        self._context_policy = frozen_policy(self._config)
        identity_config = deepcopy(self._config)
        if "context_capacity" in identity_config or "context_pack" in identity_config.get("features", {}):
            identity_config.pop("context_capacity", None)
            identity_features = dict(identity_config.get("features", {}))
            identity_features.pop("context_pack", None)
            if identity_features:
                identity_config["features"] = identity_features
            else:
                identity_config.pop("features", None)
        self._config_hash = _hash_json(identity_config)
        self._tool_port = tool_port
        self._meta_port = meta_port
        self._model_port = model_port
        self._verifier_port = verifier_port
        self._owns_showcase_store = store is None
        self._showcase_store = (
            store if store is not None else SQLiteStore(database_path or ":memory:")
        )
        self._state_store = SolverStateStore(self._showcase_store._connection)

    def solve(self, problem, metadata=None):
        """Solve or recover; interrupted calls require explicit retry authorization."""
        from .best_effort import run_best_effort
        from .budget import HardBudgetStop
        from .calls import CallInterrupted

        try:
            return run_best_effort(self, self._solve(problem, metadata))
        except HardBudgetStop as exc:
            return run_best_effort(self, self.get_run(exc.run_id))
        except CallInterrupted as exc:
            run = self.get_run(exc.run_id)
            terminated = protocol_failure_exit(self, run, exc)
            return run if terminated is None else terminated

    def _solve(
        self,
        problem: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Initialize or recover a run; optional ``metadata['run_id']`` selects its ID.

        If metadata omits ``run_id``, one is generated. The input problem is not persisted. An explicit ``metadata['plan']``
        runs its first step; the supplied Plan and report are persisted.
        An injected model port otherwise enables bounded exploration;
        otherwise only initialization runs. Reusing a run ID with different problem
        or config content is rejected.
        """

        if not isinstance(problem, str) or not problem.strip():
            raise SolverValidationError("problem must be a non-empty string")
        if metadata is not None and not isinstance(metadata, Mapping):
            raise SolverValidationError("metadata must be a mapping")
        if metadata is not None and "plan" in metadata:
            try:
                validate_plan(metadata["plan"])
                _normalize_json_mapping(metadata["plan"], "plan")
            except ValueError as exc:
                raise SolverValidationError(str(exc)) from exc
        spec_enabled = self._config.get("features", {}).get("problem_spec") is True
        serial_routes = self._config.get("features", {}).get("serial_routes") is True
        if (serial_routes
                and self._config.get("features", {}).get("progress_scheduling") is not True):
            raise SolverValidationError("serial_routes_requires_progress_scheduling")
        supplied_spec = None if metadata is None else metadata.get("problem_spec")
        if supplied_spec is not None and not spec_enabled:
            raise SolverValidationError("problem_spec_feature_disabled")
        auto_spec = self._config.get("features", {}).get("auto_problem_spec") is True
        if spec_enabled and supplied_spec is None and not auto_spec:
            if self._state_store.get_run(_run_id(metadata)) is None:
                raise SolverValidationError("problem_spec_required")
        if supplied_spec is not None:
            from .specification import normalize_problem_spec

            try:
                supplied_spec = normalize_problem_spec(supplied_spec)
            except (TypeError, ValueError) as exc:
                raise SolverValidationError(str(exc)) from exc
            if supplied_spec["original_problem"] != problem:
                raise SolverValidationError("problem_spec_original_problem_mismatch")
        effective_metadata = None if metadata is None else dict(metadata)
        work_units = []
        if spec_enabled and supplied_spec is not None and effective_metadata is not None:
            supplied_plan = effective_metadata.get("plan")
            if supplied_plan is not None:
                from .specification import bind_plan_work_units

                try:
                    normalized_plan, work_units = bind_plan_work_units(
                        supplied_plan, supplied_spec
                    )
                except (TypeError, ValueError) as exc:
                    raise SolverValidationError(str(exc)) from exc
                effective_metadata["plan"] = normalized_plan
                if serial_routes:
                    from .routes import route_plan_error

                    error = route_plan_error(normalized_plan)
                    if error is not None:
                        raise SolverValidationError(error)
        run_id = _run_id(effective_metadata)
        problem_hash = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        existing = self._state_store.get_run(run_id)
        if existing is not None:
            self._validate_identity(existing, run_id, problem_hash)
            from .problem_intake import ensure_problem_spec, intake_pending

            if intake_pending(existing):
                existing = self.get_run(run_id, problem=problem)
                retry = (effective_metadata or {}).get("retry_call")
                if retry is not None:
                    from .calls import retry_call

                    existing = retry_call(self, existing, problem, retry)
                    effective_metadata.pop("retry_call")
                existing = ensure_problem_spec(self, existing, problem)
                if intake_pending(existing) or existing["state"]["phase"] == "TERMINAL":
                    return existing
            if existing["state"].get("population_policy", {}).get("enabled") is True:
                from .population_lifecycle import resume_population

                return resume_population(self, existing, problem, effective_metadata or {})
            if (serial_routes
                    and existing["state"].get("progress_policy") != {
                        "enabled": True, "version": "progress-v1"
                    }):
                raise SolverIdentityError("serial_routes_requires_frozen_progress_policy")
            if supplied_spec is not None and supplied_spec != existing["state"].get("problem_spec"):
                raise SolverIdentityError(
                    "problem specification is frozen; use update_problem_spec"
                )
            if (
                self._config.get("features", {}).get("best_effort") is True
                and existing["state"]["status"] == "partial_budget_exhausted"
            ):
                return existing
            if self._config.get("features", {}).get("stream_recovery") is True:
                from .calls import recover_inflight, retry_call

                existing = recover_inflight(self, existing)
                if existing["state"]["phase"] == "TERMINAL":
                    return existing
                if effective_metadata is not None and "retry_call" in effective_metadata:
                    return retry_call(self, existing, problem, effective_metadata["retry_call"])
                if existing["state"].get("status") in {
                    "interrupted",
                    "recovered_pending_validation",
                }:
                    return existing
            resumable = existing["state"].get("phase") == "SETUP" or (
                self._config.get("features", {}).get("persistent_sessions") is True
                and existing["state"].get("phase") == "PLAN"
                and effective_metadata is not None
                and "plan" in effective_metadata
            )
            if self._model_port is None or not resumable:
                return advance(self, existing, effective_metadata, problem)
            return advance(
                self,
                run_supplied_plan_or_explore(self, existing, problem, effective_metadata),
                effective_metadata,
                problem,
            )

        state = initial_state(run_id, problem_hash, self._config_hash,
                              context_policy=self._context_policy,
                              problem_spec=supplied_spec,
                              work_units=work_units,
                              proof_graph=self._config.get("features", {}).get("proof_graph") is True,
                              serial_routes=self._config.get("features", {}).get("serial_routes") is True,
                              population_memory_advisory=(
                                  effective_metadata.get("population_memory_advisory")
                                  if isinstance(effective_metadata, Mapping) else None
                              ))
        pending_intake = auto_spec and supplied_spec is None
        if pending_intake:
            from .autonomous_routes import initial_permission
            from .problem_intake import POLICY

            state["problem_intake"] = dict(POLICY)
            state["autonomous_routes"] = initial_permission(
                self._config, (effective_metadata or {}).get("population_unavailable_reason"))
        if serial_routes and supplied_spec is None and not pending_intake:
            raise SolverValidationError("serial_routes_requires_problem_spec")
        if self._config.get("features", {}).get("progress_scheduling") is True:
            if supplied_spec is None and not pending_intake:
                raise SolverValidationError("progress_scheduling_requires_problem_spec")
            state["progress_policy"] = {"enabled": True, "version": "progress-v1"}
        if self._config.get("features", {}).get("concurrent_routes") is True and not pending_intake:
            from .population_store import initial_population

            state["population_policy"] = deepcopy(self._config["population_policy"])
            state["population_policy"]["enabled"] = True
            state["population"] = initial_population()
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
        if self._event_observer is not None:
            self._event_observer(created, event)
        if pending_intake:
            from .problem_intake import ensure_problem_spec, intake_pending

            created = ensure_problem_spec(self, created, problem)
            if intake_pending(created) or created["state"]["phase"] == "TERMINAL":
                return created
        if created["state"].get("population_policy", {}).get("enabled") is True:
            from .population_lifecycle import claim

            created = claim(self, created)
            from .population_lifecycle import _ensure_closing_reserve

            created = _ensure_closing_reserve(self, created, problem)
            if created["state"]["phase"] == "TERMINAL":
                return created
        if self._model_port is None:
            return advance(self, created, effective_metadata, problem)
        return advance(
            self,
            run_supplied_plan_or_explore(self, created, problem, effective_metadata),
            effective_metadata,
            problem,
        )

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
        if (self._config.get("features", {}).get("stream_recovery") is True
                and result["state"].get("population_policy", {}).get("enabled") is not True):
            from .calls import recover_inflight

            result = recover_inflight(self, result)
        from .best_effort import run_best_effort

        return run_best_effort(self, result, require_termination=True)

    def update_problem_spec(
        self,
        run_id: str,
        *,
        expected_revision: int,
        problem_spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create a new frozen specification version and invalidate its affected branch."""
        if self._config.get("features", {}).get("problem_spec") is not True:
            raise SolverValidationError("problem_spec_feature_disabled")
        current = self._state_store.get_run(run_id)
        if current is None:
            raise SolverRunNotFoundError(run_id)
        self._validate_identity(current, run_id, None)
        from .specification import normalize_problem_spec

        try:
            revised = normalize_problem_spec(problem_spec)
        except (TypeError, ValueError) as exc:
            raise SolverValidationError(str(exc)) from exc
        old = current["state"].get("problem_spec")
        if not isinstance(old, Mapping):
            raise SolverValidationError("problem_spec_missing_from_run")
        if revised["specification_version"] != old["specification_version"] + 1:
            raise SolverValidationError("specification_version_must_increment_by_one")
        from .specification_change import build_specification_change

        change = build_specification_change(current["state"], revised)
        return self._commit_event(
            run_id,
            expected_revision=expected_revision,
            event=change["event"],
            state_updates=change["updates"],
            current=current,
        )

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
        With stream recovery enabled, terminal runs permit empty audit events and
        call_audit patches of calls only; business state remains frozen.
        """

        return self._commit_event(
            run_id, expected_revision=expected_revision, event=event, state_updates=state_updates
        )

    def _commit_event(
        self,
        run_id: str,
        *,
        expected_revision: int,
        event: Mapping[str, Any],
        state_updates: Mapping[str, Any] | None = None,
        current: Mapping[str, Any] | None = None,
        route_authorized: bool = False,
    ) -> dict[str, Any]:
        """Reuse an internal caller's fresh snapshot; keep identity checks and storage CAS."""

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
        if {"proof_graph", "proof_graph_policy"} & normalized_updates.keys():
            raise SolverValidationError("state_updates cannot change storage-managed proof graph fields")
        route_fields = {
            "route_policy", "route_registry", "route_lineage", "route_evaluations",
            "aprs_decisions", "route_invalidations", "active_route_id", "route_budget",
        }
        if route_fields.intersection(normalized_updates) and not route_authorized:
            raise SolverValidationError("route_state_requires_internal_commit")
        if "route_policy" in normalized_updates:
            raise SolverValidationError("route_policy_is_run_frozen")

        # Validate the persisted run identity before writing through this Harness.
        current = self._state_store.get_run(normalized_run_id) if current is None else current
        if current is None:
            raise SolverRunNotFoundError(normalized_run_id)
        self._validate_identity(current, normalized_run_id, None)
        if self._product_recovery and normalized_event["type"].endswith("_dispatched"):
            from .calls import pending_call

            pending = pending_call(current)
            if pending is not None:
                return current
            previous = next((item for item in current["events"]
                             if item["event_id"] == normalized_event["event_id"]), None)
            if previous is not None:
                return current
        if (
            self._config.get("features", {}).get("stream_recovery") is True
            and current["state"]["phase"] == "TERMINAL"
            and not any(
                item["event_id"] == normalized_event["event_id"] for item in current["events"]
            )
            and normalized_updates
            and not (
                (
                    normalized_event["type"] in {"call_audit", "call_activity"}
                    and set(normalized_updates) <= {"calls"}
                ) or (
                    normalized_event["type"].startswith("formal_")
                    and set(normalized_updates) == {"formal_verification"}
                )
            )
        ):
            raise SolverValidationError(
                "terminal run is frozen; only call audit updates are allowed"
            )
        request_hash = _hash_json({"event": normalized_event, "state_updates": normalized_updates})
        from .candidates import enabled, prepare_candidates

        candidate_patch, candidate_events = ({}, [])
        if enabled(self._config):
            candidate_patch, candidate_events = prepare_candidates(
                current, normalized_event, normalized_updates
            )
        from .progress import review_progress

        progress_patch = review_progress(current["state"], normalized_event, normalized_updates)
        if progress_patch:
            normalized_event["progress"] = {
                key: progress_patch["progress"][key]
                for key in ("rounds", "no_evidence_rounds", "trigger")
            }
        result = self._state_store.commit_event(
            normalized_run_id,
            expected_revision=expected_revision,
            event=normalized_event,
            state_updates={**normalized_updates, **candidate_patch, **progress_patch},
            request_hash=request_hash,
            validated_run=current,
            route_authorized=route_authorized,
            population_owner=self._population_owner,
        )
        if self._event_observer is not None:
            self._event_observer(result, next(item for item in result["events"] if item["event_id"] == normalized_event["event_id"]))
        for audit in candidate_events:
            result = self.commit_event(
                normalized_run_id, expected_revision=result["state_revision"], event=audit
            )
        return result

    def _commit_route_event(
        self,
        run_id: str,
        *,
        expected_revision: int,
        event: Mapping[str, Any],
        state_updates: Mapping[str, Any] | None = None,
        authorization: object,
    ) -> dict[str, Any]:
        """Commit a route-derived patch through the private controller seam."""
        from .routes import ROUTE_COMMIT_TOKEN

        if authorization is not ROUTE_COMMIT_TOKEN:
            raise SolverValidationError("route_commit_authorization_invalid")
        return self._commit_event(
            run_id,
            expected_revision=expected_revision,
            event=event,
            state_updates=state_updates,
            route_authorized=True,
        )

    def prepare_request(
        self, run: Mapping[str, Any], request: Mapping[str, Any], *, use_snapshot=False
    ) -> dict[str, Any]:
        """Compose opt-in protocols from the current persisted run projection."""
        from copy import deepcopy

        from .context_injection import prepare_role_context
        from .prompts import compose_request
        from .tool_precheck import allowed_tool_ids

        latest = run if use_snapshot else self.get_run(run["run_id"])
        from . import handoff

        if handoff.enabled(self._config):
            request = handoff.prepare_request(latest, request)
        if latest["state"].get("progress_policy", {}).get("enabled") is True:
            request = {**request,
                       "progress_policy": deepcopy(latest["state"]["progress_policy"]),
                       "progress": deepcopy(latest["state"].get("progress", {}))}
        population_policy = latest["state"].get("population_policy")
        if population_policy and population_policy.get("enabled") is True:
            request = {**request,
                       "timeout_seconds": population_policy.get(
                           "finalization_timeout_seconds", population_policy.get("request_timeout_seconds"))
                       if request.get("role") in {"final_generator", "whole_solution_verifier"}
                       else population_policy.get("request_timeout_seconds"),
                       "retry_limit": population_policy.get("retry_limit", 1)}
        specification = latest["state"].get("problem_spec")
        if isinstance(specification, Mapping):
            request = {
                **request,
                "problem": deepcopy(specification["original_problem"]),
                "problem_spec": deepcopy(specification),
                "problem_spec_version": specification["specification_version"],
            }
        prepared = (
            compose_request(latest, request)
            if self._config.get("features", {}).get("skills") is True
            else deepcopy(dict(request))
        )
        if (
            self._config.get("features", {}).get("persistent_sessions") is True
            and self._config.get("features", {}).get("skills") is not True
        ):
            prepared["role_context"] = prepare_role_context(latest, prepared)
            prepared["state_revision"] = latest["state_revision"]
        if self._config.get("features", {}).get("strict_completion") is True:
            prepared["strict_completion"] = True
        context_policy = latest["state"].get(
            "context_policy", {"enabled": False, "version": "context-pack-v1"}
        )
        if context_policy.get("enabled") is True:
            prepared = prepare_context_request(
                prepared, context_policy, run_id=latest["run_id"],
                state_revision=latest["state_revision"],
                problem_hash=latest["state"]["problem_hash"],
                config_hash=latest["state"]["config_hash"],
            )
            prepared["_context_policy"] = context_policy
        tools = allowed_tool_ids(latest, request.get("role"), self._config, self._tool_port)
        prepared["allowed_tools"] = tools
        prepared["tool_policy"] = {"allow": tools}
        return prepared

    def precheck_report(self, run):
        """Execute explicitly permitted claim checks before Verifier dispatch."""
        from .tool_precheck import precheck_report

        return precheck_report(self, run, config=self._config, tool_port=self._tool_port)

    def dispatch(self, run, operation, request):
        """Invoke one model operation with optional audited session continuity."""
        from .budget import HardBudgetStop, budget_reason, stop

        latest = self.get_run(run["run_id"])
        # Phase owners reserved this model call already; only future reservations count.
        check = {
            **latest["state"],
            "counters": {
                **latest["state"]["counters"],
                "model_calls": max(0, latest["state"]["counters"]["model_calls"] - 1),
            },
        }
        reason = budget_reason(check, self._config, role=request.get("role"))
        if reason:
            stop(self, latest, reason)
            raise HardBudgetStop(run["run_id"])
        from contextlib import nullcontext

        from .sessions import dispatch

        scope = nullcontext()
        if (latest["state"].get("population_policy", {}).get("enabled") is True
                and not hasattr(self, "_route_id")):
            from .population_budget import bind_population_action

            scope = bind_population_action(None, self._population_owner)
        with scope:
            if self._config.get("features", {}).get("stream_recovery") is True:
                from .calls import dispatch as audit_dispatch

                return audit_dispatch(self, run, operation, request, dispatch)
            return dispatch(self, run, operation, request)

    def execute_tool_request(
        self,
        run_id: str,
        *,
        role: str,
        tool: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Enforce a same-run read whitelist before accessing state."""
        from .tool_policy import execute_tool_request

        return execute_tool_request(
            self, run_id, role=role, tool=tool, arguments=arguments, config=self._config
        )

    def _validate_identity(
        self,
        result: Mapping[str, Any],
        run_id: str,
        problem_hash: str | None,
    ) -> None:
        state = result["state"]
        from .sessions import validate_registry

        validate_registry(state)
        if result.get("run_id") != run_id or state.get("run_id") != run_id:
            raise SolverIdentityError("run_id does not match the persisted Solver Run")
        if problem_hash is not None and state.get("problem_hash") != problem_hash:
            raise SolverIdentityError("run_id already belongs to a different problem")
        if state.get("config_hash") != self._config_hash:
            raise SolverIdentityError("run_id already belongs to a different config")

    def close(self) -> None:
        """Close the Showcase SQLite connection if this Harness created it."""

        executor = getattr(self, "_population_executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=False)
        if self._owns_showcase_store:
            self._showcase_store.close()

    def __enter__(self) -> SolverHarness:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
