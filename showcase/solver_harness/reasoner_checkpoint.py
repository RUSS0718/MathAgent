"""Opt-in Reasoner checkpoint handoff with bounded Verifier review."""

from collections.abc import Mapping
from copy import deepcopy

from ..redaction import redact
from ..tool_schemas import schema_error
from .intern_schemas import response_schema

CHECKPOINT_VERSION = 1
CHECKPOINT_STATUSES = frozenset({"YIELD", "FINAL", "BLOCKED", "FAILED"})
MAX_CHECKPOINT_ROUNDS = 2


def enabled(config):
    return config.get("features", {}).get("reasoner_checkpoints") is True


def parse(reply):
    """Validate the role payload, excluding only the runtime's stream usage envelope."""
    if (
        not isinstance(reply, Mapping)
        or "checkpoint" not in reply
        or set(reply) - {"checkpoint", "usage"}
        or not isinstance(reply.get("checkpoint"), Mapping)
    ):
        raise ValueError("invalid_reasoner_checkpoint")
    if schema_error({"checkpoint": reply["checkpoint"]}, response_schema({"role": "reasoner", "checkpoint_protocol": True})):
        raise ValueError("invalid_reasoner_checkpoint")
    checkpoint = dict(reply["checkpoint"])
    expected = {
        "protocol_version", "checkpoint_id", "status", "objective", "argument", "claims",
        "blocked", "dependencies", "evidence", "gaps", "next_action",
    }
    if set(checkpoint) != expected:
        raise ValueError("invalid_reasoner_checkpoint_content")
    if type(checkpoint.get("protocol_version")) is not int or checkpoint["protocol_version"] != CHECKPOINT_VERSION:
        raise ValueError("invalid_reasoner_checkpoint_version")
    if checkpoint.get("status") not in CHECKPOINT_STATUSES:
        raise ValueError("invalid_reasoner_checkpoint_status")
    checkpoint_id = checkpoint.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("invalid_reasoner_checkpoint_id")
    for key in ("objective", "argument", "next_action"):
        if not isinstance(checkpoint.get(key), str) or not checkpoint[key].strip():
            raise ValueError("invalid_reasoner_checkpoint_content")
    if not isinstance(checkpoint.get("blocked"), bool):
        raise ValueError("invalid_reasoner_checkpoint_content")
    if not isinstance(checkpoint.get("claims"), list):
        raise ValueError("invalid_reasoner_checkpoint_content")
    for claim in checkpoint["claims"]:
        if not isinstance(claim, Mapping):
            raise ValueError("invalid_reasoner_checkpoint_content")
        if set(claim) - {
            "statement", "label", "tool_request", "tool_evidence_refs"
        } or set(claim) < {"statement", "label"}:
            raise ValueError("invalid_reasoner_checkpoint_content")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            raise ValueError("invalid_reasoner_checkpoint_content")
        if claim.get("label") not in {"verified", "easy-verify", "hard-verify"}:
            raise ValueError("invalid_reasoner_checkpoint_content")
    for key in ("dependencies", "evidence", "gaps"):
        values = checkpoint.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise ValueError("invalid_reasoner_checkpoint_content")
    if checkpoint["status"] == "YIELD" and not checkpoint["gaps"]:
        raise ValueError("invalid_reasoner_checkpoint_content")
    if checkpoint["status"] == "FINAL" and checkpoint["gaps"]:
        raise ValueError("invalid_reasoner_checkpoint_content")
    return redact(checkpoint)


def same_draft(left, right):
    keys = ("objective", "argument", "claims", "dependencies", "evidence", "gaps", "next_action")
    return all(left.get(key) == right.get(key) for key in keys)


def feedback(checkpoint, *, objection=None):
    result = {
        "accepted": ["checkpoint_schema_and_semantics"],
        "objective": checkpoint["objective"],
        "gaps": list(checkpoint["gaps"]),
        "next_action": checkpoint["next_action"],
        "instruction": "Address the open obligations and return a new checkpoint.",
    }
    if isinstance(objection, str) and objection.strip():
        result["objection"] = objection
    return result


def request(base, *, call_id, round_number, parent=None, objection=None, guidance=None):
    result = {
        **base,
        "call_id": call_id,
        "checkpoint_protocol": True,
        "checkpoint_round": round_number,
        "checkpoint_max_rounds": MAX_CHECKPOINT_ROUNDS,
        "checkpoint_remaining_rounds": MAX_CHECKPOINT_ROUNDS - round_number,
        "checkpoint_last_round": round_number == MAX_CHECKPOINT_ROUNDS,
    }
    if parent is not None:
        result.update({
            "parent_checkpoint_id": parent["checkpoint_id"],
            "reasoner_checkpoint": deepcopy(parent),
            "feedback": feedback(parent, objection=objection),
        })
    if isinstance(objection, str) and objection.strip():
        result["objection"] = objection
    if isinstance(guidance, Mapping):
        result["adopted_guidance"] = deepcopy(dict(guidance))
    return result


def to_report(checkpoint, step):
    claims = []
    for claim in checkpoint["claims"]:
        normalized = {
            "statement": claim["statement"],
            "label": claim["label"],
            "tool_evidence_refs": [],
        }
        if isinstance(claim.get("tool_request"), Mapping):
            normalized["tool_request"] = dict(claim["tool_request"])
        claims.append(normalized)
    return {
        "step_id": step["step_id"],
        "objective": step["objective"],
        "argument": checkpoint["argument"],
        "claims": claims,
        "tool_evidence_refs": [],
        "blocked": checkpoint["blocked"],
    }


def record(run, checkpoint, *, call_id, checkpoint_round, plan_version, attempt_index, step_id, parent=None):
    return {
        "checkpoint_id": checkpoint["checkpoint_id"],
        "run_id": run["run_id"],
        "role": "reasoner",
        "call_id": call_id,
        "round": checkpoint_round,
        "plan_version": plan_version,
        "attempt_index": attempt_index,
        "step_id": step_id,
        "state_revision": run["state_revision"],
        "parent_checkpoint_id": parent.get("checkpoint_id") if parent else None,
        "status": checkpoint["status"],
        "protocol_version": CHECKPOINT_VERSION,
        "objective": checkpoint["objective"],
        "argument": checkpoint["argument"],
        "claims": deepcopy(checkpoint["claims"]),
        "blocked": checkpoint["blocked"],
        "dependencies": checkpoint["dependencies"],
        "evidence": checkpoint["evidence"],
        "gaps": checkpoint["gaps"],
        "next_action": checkpoint["next_action"],
        "source": {"call_id": call_id, "state_revision": run["state_revision"]},
    }


def current_checkpoints(state):
    records = state.get("reasoner_checkpoints", [])
    archived = set()
    for failure in state.get("failure_records", []):
        for record in failure.get("archived_steps", {}).values():
            if not isinstance(record, Mapping):
                continue
            if isinstance(record.get("checkpoint_id"), str):
                archived.add(record["checkpoint_id"])
            archived.update(
                item["checkpoint_id"]
                for item in record.get("challenge_history", [])
                if isinstance(item, Mapping) and isinstance(item.get("checkpoint_id"), str)
            )
    changed = True
    while changed:
        before = len(archived)
        archived.update(
            item.get("parent_checkpoint_id")
            for item in records
            if item.get("checkpoint_id") in archived
            and isinstance(item.get("parent_checkpoint_id"), str)
        )
        changed = len(archived) != before
    return [
        item for item in records
        if item.get("plan_version") == state.get("plan_version")
        and item.get("attempt_index") == state.get("attempt_index")
        and item.get("step_id") == state.get("current_step")
        and item.get("checkpoint_id") not in archived
    ]
