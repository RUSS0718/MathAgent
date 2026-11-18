"""Untrusted intake proposals, with server-owned provenance and capability policy."""
import re
from collections.abc import Mapping
from copy import deepcopy

from ..formal_specification import canonical_identity, normalize_target, public_target

AUTHORITY_QUESTION = {
    "question": "Do you require a machine-checked proof of the entire conclusion? Reply yes or no.",
    "reason": "formal_requirement_user_authority_unresolved",
}

# Whole user sentences only: quotations, conditionals and negations cannot match.
_REQUEST = re.compile(
    r"(?:please )?(?:provide|give)(?: me)? a machine[- ]checked proof(?: of the entire conclusion)?"
    r"|(?:please )?(?:use lean to verify|verify in lean)(?: the entire conclusion| the whole conclusion)"
    r"|请用\s*lean\s*验证整个结论", re.IGNORECASE)
_MENTION = re.compile(r"(?<![a-z])(?:lean\d*|coq|isabelle|agda)(?![a-z])|\b(?:formal\w*|machine|computer[- ]checked|proof assistant)\b|形式化|机器验证|机器核验|机器证明|机检", re.IGNORECASE)


def requirement_authority(problem, value, clarification=None, *, server_question_confirmed=False):
    """Witness a bounded affirmative syntax; route uncertainty, never guess it away."""
    sources = [("original_problem", problem)]
    if clarification:
        sources.append(("clarification_answer", clarification["answer"]))
    for source, text in sources:
        if any(mark in text for mark in ('"', "'", "“", "”", "「", "」", "`")):
            continue
        if re.search(r"\b(?:if|unless|when|never|do\s+not|must\s+not)\b|如果|若|如有必要|不要|禁止|无需|不必", text, re.IGNORECASE):
            continue
        for sentence in re.split(r"[.!?。！？\n]+", text):
            if _REQUEST.fullmatch(sentence.strip()):
                return {"status": "requested", "source": source,
                        "input_hash": canonical_identity(text)}
    if clarification and server_question_confirmed:
        answer = clarification["answer"].strip().lower().rstrip(".。!")
        if answer in {"yes", "是", "需要", "no", "否", "不需要"}:
            return {"status": "requested" if answer in {"yes", "是", "需要"} else "not_requested",
                    "source": "clarification_answer",
                    "input_hash": canonical_identity(clarification["answer"])}
    unresolved = value.get("require_formal") is True or any(_MENTION.search(t) for _, t in sources)
    return {"status": "unresolved" if unresolved else "not_requested"}


def explicit_requirement(harness, run):
    """Read the already frozen client policy, without changing its identity."""
    import json

    connection = harness._state_store._connection
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE name='workspace_jobs'").fetchone():
        return None
    row = connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?",
                             (run["run_id"],)).fetchone()
    policy = json.loads(row[0]).get("formal_policy") if row and row[0] else None
    return policy if isinstance(policy, Mapping) and policy.get("require_formal") is True else None


def select_formalization(value, spec, call_id, *, clarification=None, explicit_policy=None, server_question_confirmed=False):
    if not isinstance(value, Mapping):
        value = {}
        if requirement_authority(spec["original_problem"], value, clarification,
                                 server_question_confirmed=server_question_confirmed)["status"] == "not_requested":
            return None
    ids = value.get("obligation_ids", [])
    roots = {item["obligation_id"] for item in spec["root_obligations"]}
    valid_ids = isinstance(ids, list) and all(isinstance(i, str) and i in roots for i in ids)
    authority = requirement_authority(spec["original_problem"], value, clarification,
                                 server_question_confirmed=server_question_confirmed)
    if explicit_policy:
        authority = {"status": "requested", "source": "explicit_formal_policy",
                     "policy_hash": canonical_identity(explicit_policy)}
    result = {"status": value.get("status", "unsupported"),
              "reason": str(value.get("reason", "not_selected")),
              "require_formal": authority["status"] == "requested",
              "requirement_authority": authority,
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
