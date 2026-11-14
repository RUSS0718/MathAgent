"""Untrusted intake proposals, with server-owned provenance and capability policy."""
from collections.abc import Mapping
from copy import deepcopy

from ..formal_specification import canonical_identity, normalize_target, public_target


def select_formalization(value, spec, call_id):
    if not isinstance(value, Mapping):
        return None
    ids = value.get("obligation_ids", [])
    roots = {item["obligation_id"] for item in spec["root_obligations"]}
    valid_ids = isinstance(ids, list) and all(isinstance(i, str) and i in roots for i in ids)
    result = {"status": value.get("status", "unsupported"),
              "reason": str(value.get("reason", "not_selected")),
              "require_formal": value.get("require_formal") is True,
              "source": {"problem_hash": canonical_identity(spec["original_problem"]),
                         "specification_hash": canonical_identity(spec),
                         "obligation_ids": list(dict.fromkeys(ids)) if valid_ids else [],
                         "generation_call_id": call_id}}
    if result["status"] == "proposed":
        try:
            if not valid_ids or not ids:
                raise ValueError("formal_obligations_invalid")
            result["target"] = public_target(normalize_target(value.get("target")))
            target = result["target"]
            if (spec["domain"].strip().lower() not in {"rationals", "rational", "rational numbers"}
                    or spec["quantifiers"] != target["quantifiers"]
                    or spec["assumptions"] or spec["directions"] != ["equality"]):
                raise ValueError("spec_target_mismatch")
        except (TypeError, ValueError) as exc:
            result.update(status="unsupported", reason=str(exc))
            result.pop("target", None)
    elif result["status"] not in {"unsupported", "not_selected"}:
        result.update(status="unsupported", reason="formal_selection_invalid")
    return result


def generated_policy(selection, spec, server_policy, configured):
    if not selection or selection["source"]["specification_hash"] != canonical_identity(spec):
        return None
    if selection["status"] != "proposed":
        return None
    from .formal_policy import normalize_formal_policy

    policy = normalize_formal_policy({"target": selection["target"],
        "require_formal": selection["require_formal"]},
        configured=configured, server_template=server_policy)
    policy["source"] = deepcopy(selection["source"])
    return policy


def freeze_generated_policy(harness, run, identity, policy):
    """Freeze both identities in the Solver CAS transaction before dispatch."""
    import json

    digest = canonical_identity(policy)
    patch = {"formal_policy": policy, "formal_policy_hash": digest}
    event = {"event_id": "formal-generated-policy-frozen", "type": "formal_policy_frozen"}

    def persist(connection):
        row = connection.execute(
            "SELECT result_json FROM workspace_jobs WHERE job_id=?", (run["run_id"],)
        ).fetchone()
        current = json.loads(row[0]) if row and row[0] else {}
        if current.get("formal_policy") is not None:
            if current["formal_policy"] != policy:
                raise ValueError("formal_policy_already_frozen")
            return
        current.update(patch)
        connection.execute("UPDATE workspace_jobs SET result_json=? WHERE job_id=?",
                           (json.dumps(current, ensure_ascii=False), run["run_id"]))

    saved = harness._state_store.commit_event(
        run["run_id"], expected_revision=run["state_revision"], event=event,
        state_updates=patch, request_hash=canonical_identity({"event": event, "patch": patch}),
        transaction_hook=persist,
    )
    identity.update(patch)
    return saved
