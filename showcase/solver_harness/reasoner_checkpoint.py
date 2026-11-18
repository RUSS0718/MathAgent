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


def tool_completion_receipts(checkpoint, parent, state, step_id):
    """Allow one same-object FINAL only against its committed successful precheck."""
    from .computation_evidence import has_computation_output

    if (parent is None or parent.get("status") != "YIELD"
            or checkpoint["status"] != "FINAL" or checkpoint["blocked"]
            or checkpoint["checkpoint_id"] != parent["checkpoint_id"]
            or any(checkpoint[key] != parent[key]
                   for key in ("objective", "dependencies", "evidence"))
            or len(checkpoint["claims"]) != len(parent["claims"])):
        return None
    call = state.get("calls", {}).get(parent.get("call_id"), {})
    if (call.get("status") != "completed" or call.get("role") != "reasoner"
            or call.get("request", {}).get("problem_spec_version")
            != (state.get("problem_spec") or {}).get("specification_version")
            or any(call.get(key) != state.get(key)
                   for key in ("run_id", "plan_version", "attempt_index", "problem_hash", "config_hash"))
            or call.get("request", {}).get("step", {}).get("step_id") != step_id):
        return None
    report = state.get("steps", {}).get(step_id, {}).get("report", {})
    prior_claims = report.get("claims", [])
    if len(prior_claims) != len(checkpoint["claims"]):
        return None
    receipts = {r["receipt_id"]: r for r in state.get("tool_receipts", [])}
    used = []
    for index, (old, new, checked) in enumerate(zip(parent["claims"], checkpoint["claims"], prior_claims)):
        if new["statement"] != old["statement"] or new.get("tool_request"):
            return None
        refs = new.get("tool_evidence_refs", [])
        if not old.get("tool_request"):
            if refs or new["label"] != old["label"]:
                return None
            continue
        if (old["label"] != "easy-verify" or new["label"] != "verified"
                or not refs or refs != checked.get("tool_evidence_refs")):
            return None
        for ref in refs:
            receipt = receipts.get(ref, {})
            if (receipt.get("status") != "success" or receipt.get("executed") is not True
                    or receipt.get("unknown_outcome") or not has_computation_output(receipt)
                    or receipt.get("claim_index") != index or receipt.get("step_id") != step_id
                    or receipt.get("tool") != old["tool_request"]["tool"]
                    or receipt.get("input") != old["tool_request"]["arguments"]
                    or any(receipt.get(key) != state.get(key)
                           for key in ("run_id", "plan_version", "attempt_index"))):
                return None
            used.append(deepcopy(receipt))
    return used or None


def checkpoint_tool_receipts(checkpoint, run, step):
    """Resolve explicit citations to committed, successful, scoped computations."""
    from .computation_evidence import has_computation_output

    state = run["state"]
    receipts = {r["receipt_id"]: r for r in state.get("tool_receipts", [])}
    committed = {e.get("receipt", {}).get("receipt_id"): e.get("receipt")
                 for e in run["events"] if e.get("type") == "tool_receipt"}
    allowed_steps = {step["step_id"]}
    pending = list(step.get("depends_on", []))
    plan_steps = {s["step_id"]: s for s in (state.get("plan") or {}).get("steps", [])}
    while pending:
        source = pending.pop()
        if source in allowed_steps:
            continue
        record = state.get("steps", {}).get(source, {})
        if (record.get("status") != "ACCEPTED"
                or record.get("verification", {}).get("valid") is not True):
            continue
        allowed_steps.add(source)
        pending.extend(plan_steps.get(source, {}).get("depends_on", []))
    used = {}
    for claim in checkpoint["claims"]:
        for ref in claim.get("tool_evidence_refs", []):
            receipt = receipts.get(ref, {})
            if (not receipt or committed.get(ref) != receipt
                    or receipt.get("status") != "success" or receipt.get("executed") is not True
                    or type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0
                    or receipt.get("comparison_status") == "mismatched"
                    or receipt.get("unknown_outcome") or not has_computation_output(receipt)
                    or receipt.get("step_id") not in allowed_steps
                    or (receipt.get("step_id") != step["step_id"] and ref not in
                        state["steps"][receipt["step_id"]].get("report", {}).get("tool_evidence_refs", []))
                    or any(receipt.get(k) != state.get(k)
                           for k in ("run_id", "plan_version", "attempt_index"))):
                raise ValueError("invalid_checkpoint_tool_evidence")
            # Bind the target and input to the original request, never to a label.
            source_found = False
            for source in current_checkpoints({**state, "current_step": receipt["step_id"]}):
                call = state.get("calls", {}).get(source.get("call_id"), {})
                index = receipt.get("claim_index")
                claims = source.get("claims", [])
                if (source.get("step_id") != receipt["step_id"]
                        or type(index) is not int or not 0 <= index < len(claims)
                        or call.get("status") != "completed" or call.get("role") != "reasoner"
                        or any(call.get(k) != state.get(k) for k in
                               ("run_id", "plan_version", "attempt_index", "problem_hash", "config_hash"))
                        or call.get("request", {}).get("problem_spec_version")
                        != (state.get("problem_spec") or {}).get("specification_version")
                        or call.get("request", {}).get("step", {}).get("step_id") != receipt["step_id"]):
                    continue
                original = claims[index]
                request = original.get("tool_request") or {}
                if (original["statement"] == claim["statement"]
                        and request.get("scope") == "finite_computation"
                        and request.get("tool") == receipt.get("tool")
                        and request.get("arguments") == receipt.get("input")
                        and (not claim.get("tool_request") or claim["tool_request"] == request)):
                    source_found = True
                    break
            if not source_found:
                raise ValueError("invalid_checkpoint_tool_evidence")
            used[ref] = deepcopy(receipt)
    return list(used.values())


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
            "tool_evidence_refs": list(claim.get("tool_evidence_refs", [])),
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
