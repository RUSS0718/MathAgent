"""Opt-in Planner checkpoint handoff and bounded continuation."""

from collections.abc import Mapping
from copy import deepcopy

from ..redaction import redact
from .budget import budget_reason
from .finalize import commit, dispatch, finish
from .plan import validate_plan

CHECKPOINT_VERSION = 1
CHECKPOINT_STATUSES = frozenset({"YIELD", "FINAL", "BLOCKED", "FAILED"})


def _positive_limit(config):
    value = config.get("max_planner_checkpoint_rounds", 2)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("config.max_planner_checkpoint_rounds must be positive")
    return value


def _parse(reply):
    if not isinstance(reply, Mapping) or not isinstance(reply.get("checkpoint"), Mapping):
        raise ValueError("invalid_planner_checkpoint")
    checkpoint = dict(reply["checkpoint"])
    if checkpoint.get("protocol_version") != CHECKPOINT_VERSION:
        raise ValueError("invalid_planner_checkpoint_version")
    if checkpoint.get("status") not in CHECKPOINT_STATUSES:
        raise ValueError("invalid_planner_checkpoint_status")
    checkpoint_id = checkpoint.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("invalid_planner_checkpoint_id")
    for key in ("objective", "next_action"):
        if not isinstance(checkpoint.get(key), str) or not checkpoint[key].strip():
            raise ValueError("invalid_planner_checkpoint_content")
    for key in ("dependencies", "evidence", "gaps"):
        values = checkpoint.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise ValueError("invalid_planner_checkpoint_content")
    return redact(checkpoint), reply.get("plan", checkpoint.get("plan"))


def _same_draft(left, right):
    keys = ("objective", "dependencies", "evidence", "gaps", "next_action")
    return all(left.get(key) == right.get(key) for key in keys)


def _feedback(checkpoint):
    return {
        "accepted": ["checkpoint_schema_and_semantics"],
        "objective": checkpoint["objective"],
        "gaps": list(checkpoint["gaps"]),
        "next_action": checkpoint["next_action"],
        "instruction": "Address the listed gaps and return a new checkpoint or a complete Plan.",
    }


def _request(base, *, call_id, round_number, checkpoint=None, feedback=None):
    request = {
        **base,
        "call_id": call_id,
        "checkpoint_protocol": True,
        "checkpoint_round": round_number,
    }
    if checkpoint is not None:
        request.update({
            "parent_checkpoint_id": checkpoint["checkpoint_id"],
            "planner_checkpoint": deepcopy(checkpoint),
            "feedback": deepcopy(feedback),
        })
    return request


def generate_checkpoint_plan(harness, run, *, problem, model_port, request, version, config):
    """Run the explicit Planner checkpoint protocol until a valid Plan arrives."""

    if model_port is None:
        return run, None
    checkpoints = list(run["state"].get("planner_checkpoints", []))
    limit = _positive_limit(config)
    for round_number in range(len(checkpoints), limit):
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason), None
        parent = checkpoints[-1] if checkpoints else None
        call_id = (
            f"{run['run_id']}:planner:checkpoint:{round_number + 1}"
            if parent is None
            else f"{run['run_id']}:planner:checkpoint:{round_number + 1}:from:{parent['checkpoint_id']}"
        )
        current_request = _request(
            request,
            call_id=call_id,
            round_number=round_number + 1,
            checkpoint=parent,
            feedback=_feedback(parent) if parent else None,
        )
        run, reply = dispatch(harness, run, model_port.complete, current_request)
        try:
            checkpoint, plan = _parse(reply)
        except ValueError:
            return finish(harness, run, "partial_aborted", "invalid_planner_checkpoint"), None
        status = checkpoint["status"]
        if status == "FINAL":
            try:
                validate_plan(plan)
                if plan["version"] != version:
                    raise ValueError("wrong_plan_version")
            except (TypeError, ValueError):
                return finish(harness, run, "partial_aborted", "invalid_planner_checkpoint"), None
            return run, redact(plan)
        if status in {"BLOCKED", "FAILED"}:
            return finish(harness, run, "partial_aborted", f"planner_checkpoint_{status.lower()}"), None
        if parent is not None and (
            checkpoint["checkpoint_id"] == parent["checkpoint_id"] or _same_draft(checkpoint, parent)
        ):
            return finish(harness, run, "partial_aborted", "planner_checkpoint_no_progress"), None
        record = {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "run_id": run["run_id"],
            "role": "planner",
            "call_id": call_id,
            "plan_attempt": run["state"].get("attempt_index", 0),
            "plan_version": version,
            "state_revision": run["state_revision"],
            "parent_checkpoint_id": parent.get("checkpoint_id") if parent else None,
            "status": "YIELD",
            "protocol_version": CHECKPOINT_VERSION,
            "objective": checkpoint["objective"],
            "dependencies": checkpoint["dependencies"],
            "evidence": checkpoint["evidence"],
            "gaps": checkpoint["gaps"],
            "next_action": checkpoint["next_action"],
            "feedback": _feedback(checkpoint),
        }
        checkpoints.append(record)
        run = commit(
            harness,
            run,
            "planner_checkpoint_yielded",
            {"phase": "PLAN", "planner_checkpoints": checkpoints},
            checkpoint_id=record["checkpoint_id"],
            parent_checkpoint_id=record["parent_checkpoint_id"],
            plan_version=version,
        )
    return finish(harness, run, "partial_aborted", "planner_checkpoint_round_limit"), None
