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
    request.update(
        {
            "session_key": identity["session_key"],
            "session_backend": "local",
            "session_history": deepcopy(record["history"]),
            "session_history_authority": "historical_dialogue_only; current role projection and ledgers are authoritative",
        }
    )
    return record, request


def append_exchange(record, request, response):
    record = deepcopy(record)
    # Persist structured dialogue only: never the original problem or composed prompts.
    excluded = {"problem", "prompt_layers", "session_history", "role_context"}
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
    record["last_injected_state_revision"] = latest["state_revision"] + 1
    registered = harness.commit_event(
        run["run_id"],
        expected_revision=latest["state_revision"],
        event={
            "event_id": f"session-start-{prepared['call_id']}-{latest['state_revision']}",
            "type": "session_started",
            "session_key": record["session_key"],
        },
        state_updates={
            "session_registry": {
                **latest["state"].get("session_registry", {}),
                record["session_key"]: record,
            }
        },
    )
    run.clear()
    run.update(registered)
    latest = registered
    prepared = harness.prepare_request(latest, prepared)
    prepared["state_revision"] = latest["state_revision"]
    response = operation(deepcopy(prepared))
    latest = harness.get_run(run["run_id"])
    record = append_exchange(record, prepared, response)
    registry = {**latest["state"].get("session_registry", {}), record["session_key"]: record}
    updated = harness.commit_event(
        run["run_id"],
        expected_revision=latest["state_revision"],
        event={
            "event_id": f"session-{prepared['call_id']}-{latest['state_revision']}",
            "type": "session_recorded",
            "session_key": record["session_key"],
        },
        state_updates={"session_registry": registry},
    )
    run.clear()
    run.update(updated)
    return response
