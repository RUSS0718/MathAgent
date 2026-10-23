"""Controller-owned records of the actual whole-solution review object."""

from copy import deepcopy

from ..final_evidence import artifact_identity, bind_verification


def fact_reference(value):
    """Step/result identifiers can contain private hints; publish opaque identities."""
    return "fact:" + artifact_identity(value)["sha256"]


def review_record(run, candidate, verdict, *, call_id, origin, versions=None, facts=None):
    state = run["state"]
    return {
        "artifact": artifact_identity(candidate),
        "verdict": verdict,
        "source": {
            "run_id": run["run_id"], "call_id": call_id,
            "plan_version": state["plan_version"], "attempt_index": state["attempt_index"],
            "state_revision": run["state_revision"], "origin": origin,
            "candidate_version": len(state.get("whole_solution_reviews", [])) + 1,
        },
        "versions": [
            {**deepcopy(version), "artifact": artifact_identity(version["text"])}
            for version in (versions or [{"text": candidate}])
        ],
        "fact_sources": [
            {**{key: fact_reference(fact[key]) for key in ("result_id", "source") if key in fact},
             "dependencies": [fact_reference(value) for value in fact.get("dependencies", [])],
             "evidence_level": fact["evidence_level"],
             "statement_artifact": artifact_identity(fact["statement"]),
             "rescued": fact in state.get("rescued_results", [])}
            for fact in (facts or [])
        ],
    }


def delivery_verification(run, answer):
    """Never infer a whole review from a step verdict or model supplied reference."""
    records = run["state"].get("whole_solution_reviews", [])
    latest = records[-1] if records else {}
    source = latest.get("source", {})
    call = run["state"].get("calls", {}).get(source.get("call_id"), {})
    valid = (
        latest.get("verdict") == "ACCEPT"
        and latest.get("artifact") == artifact_identity(answer)
        and source.get("run_id") == run["run_id"]
        and source.get("plan_version") == run["state"]["plan_version"]
        and source.get("attempt_index") == run["state"]["attempt_index"]
        and call.get("status") == "completed"
        and call.get("role") == "whole_solution_verifier"
        and call.get("run_id") == run["run_id"]
        and call.get("response", {}).get("verdict") == "ACCEPT"
        and artifact_identity(call.get("request", {}).get("solution_candidate", "")) == latest.get("artifact")
    )
    history = [bind_verification(answer, {
        "status": "unknown", "checker": "whole_solution_verifier",
        "checker_version": "star-whole-review-v1", "scope": "whole_solution_llm_review",
        "findings": ["llm_whole_review_" + record["verdict"].lower()],
        "limitations": ["LLM review does not prove mathematical correctness or completeness."],
        **{key: record[key] for key in ("artifact", "source", "versions", "fact_sources")
           if key in record},
    })["history"][0] for record in records]
    check = bind_verification(answer, {
        **(history[-1] if history else {}),
        "status": "unknown", "checker_version": "star-whole-review-v1",
        "findings": ["llm_whole_review_accepted" if valid else "whole_review_not_bound"],
        "history": history,
    })
    return valid, check
