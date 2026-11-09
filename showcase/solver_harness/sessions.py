"""Audited local role sessions; authority remains in the run ledgers."""

from copy import deepcopy

from ..redaction import redact


class SessionIdentityError(ValueError):
    """A restored session does not belong to the requested role scope."""


def session_identity(state, request):
    from .roles import session_role

    role = session_role(request["role"])
    plan = state["plan_version"] if role not in {"meta", "explore"} else None
    attempt = state["attempt_index"] if role not in {"meta", "explore"} else None
    step = state["current_step"] if role == "step_verifier" else None
    scope = [state["run_id"], state["run_salt"], role, plan, step, attempt]
    if role == "explore":
        scope.append(request.get("round", 1))
    if role == "researcher":
        scope.append(request.get("session_key", request["call_id"]))
    if role == "whole_solution_verifier":
        scope.append(request["call_id"])
    return {
        "session_key": ":".join(str(part) for part in scope),
        "scope": scope,
        "run_id": state["run_id"],
        "run_salt": state["run_salt"],
        "problem_hash": state["problem_hash"],
        "config_hash": state["config_hash"],
        "role": role,
        "plan_version": plan,
        "step_id": step,
        "attempt_index": attempt,
        "provider_session_id": None,
        "backend": "local",
        "transcript_ref": None,
    }


def validate_registry(state):
    for key, record in state.get("session_registry", {}).items():
        scope = record.get("scope", [])
        expected_scope = [
            state["run_id"],
            state["run_salt"],
            record.get("role"),
            record.get("plan_version"),
            record.get("step_id"),
            record.get("attempt_index"),
        ]
        if (
            (
                scope[:6] != expected_scope
                or key != ":".join(str(part) for part in scope)
                or key != record.get("session_key")
            )
            or any(
                record.get(field) != state[field]
                for field in ("run_id", "run_salt", "problem_hash", "config_hash")
            )
            or record.get("backend") != "local"
            or record.get("provider_session_id") is not None
        ):
            raise SessionIdentityError("session identity conflicts with persisted run")


def prepare_session(run, request):
    state = run["state"]
    validate_registry(state)
    if request.get("provider_session_id") is not None:
        raise SessionIdentityError("local backend cannot resume a provider session")
    identity = session_identity(state, request)
    record = state.get("session_registry", {}).get(identity["session_key"])
    if record is not None and any(record.get(k) != v for k, v in identity.items()):
        raise SessionIdentityError("session role scope conflicts with registered identity")
    record = deepcopy(record or {**identity, "created_at": state["updated_at"], "history": []})
    request = deepcopy(dict(request))
    history = deepcopy(record["history"])
    current = request.get("challenge_history")
    step_id = (request.get("step") or {}).get("step_id")
    if isinstance(current, list) and current and step_id:
        for exchange in history:
            previous = exchange.get("request", {})
            old = previous.get("challenge_history")
            if ((previous.get("step") or {}).get("step_id") != step_id
                    or not isinstance(old, list) or "challenge_history_prefix_ref" in previous):
                continue
            length = 0
            for prior, latest in zip(old, current):
                if prior != latest:
                    break
                length += 1
            if length:
                previous["challenge_history"] = old[length:]
                previous["challenge_history_prefix_ref"] = {
                    "source": "current_request.challenge_history", "length": length,
                }
    request.update(
        {
            "session_key": identity["session_key"],
            "session_backend": "local",
            "session_history": history,
            "session_history_authority": "historical_dialogue_only; current role projection and ledgers are authoritative",
        }
    )
    return record, request


def append_exchange(record, request, response):
    record = deepcopy(record)
    # Persist structured dialogue only: never the original problem or composed prompts.
    excluded = {"problem", "prompt_layers", "session_history", "role_context",
                "session_history_summary", "_context_pack", "_context_policy"}
    task = {k: deepcopy(v) for k, v in request.items() if k not in excluded}
    record["history"].append({"request": task, "response": deepcopy(response)})
    record["last_injected_state_revision"] = request["state_revision"]
    return redact(record)


def dispatch(harness, run, operation, request):
    """Dispatch detached context and atomically retain the local role exchange."""
    from copy import deepcopy

    enabled = harness._config.get("features", {}).get("persistent_sessions") is True
    if not enabled:
        return operation(harness.prepare_request(run, request))
    latest = harness.get_run(run["run_id"])
    record, prepared = prepare_session(latest, request)
    if getattr(harness, "_product_recovery", False) and any(
        item["request"].get("call_id") == prepared["call_id"] for item in record["history"]
    ):
        return operation(harness.prepare_request(latest, prepared))
    record["last_injected_state_revision"] = latest["state_revision"] + 1
    registered = _commit_session(harness, run["run_id"], record, prepared["call_id"], "session_started")
    run.clear()
    run.update(registered)
    prepared = harness.prepare_request(registered, prepared)
    prepared["state_revision"] = registered["state_revision"]
    response = operation(deepcopy(prepared))
    record = append_exchange(record, prepared, response)
    updated = _commit_session(harness, run["run_id"], record, prepared["call_id"], "session_recorded")
    run.clear()
    run.update(updated)
    return response


def _commit_session(harness, run_id, record, call_id, kind):
    """Retry only local session CAS, never the provider operation."""
    from .storage import SolverRevisionConflictError

    while True:
        latest = harness.get_run(run_id)
        prefix = "session-start" if kind == "session_started" else "session"
        try:
            return harness.commit_event(
                run_id, expected_revision=latest["state_revision"],
                event={"event_id": f"{prefix}-{call_id}-{latest['state_revision']}",
                       "type": kind, "session_key": record["session_key"]},
                state_updates={"session_registry": {
                    **latest["state"].get("session_registry", {}), record["session_key"]: record,
                }},
            )
        except SolverRevisionConflictError:
            if harness._config.get("features", {}).get("concurrent_routes") is not True:
                raise
            from ..run_control import check_control

            check_control()
