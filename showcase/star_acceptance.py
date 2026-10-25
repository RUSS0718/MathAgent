"""Offline acceptance of the delivered candidate, never a first/last-role guess.

Inputs are trusted controller snapshots and captured outbound contexts. This API
performs no dispatch and returns identities/counts only, never private prompts.
LLM acceptance is not an independent mathematical correctness assessment.
"""

from .final_evidence import artifact_identity
from .solver_harness.final_binding import _proof_source, review_binding
from .solver_harness.protocol_repair import completed_call_id
from .star_result_semantics import result_semantics

RUNNER_VERSION = "star-delivery-replay-v1"


def _evaluate_delivery(job, run, contexts):
    """Resolve a delivered review against completed calls and actual wire inputs.

    Missing or ambiguous provenance fails closed. Contexts must include call IDs;
    role order is irrelevant. Fastpath can bind without step proofs, but cannot
    qualify as nonfastpath proof delivery.
    """
    result = dict(
        runner_version=RUNNER_VERSION,
        review_bound=False,
        proof_delivered=False,
        nonfastpath=False,
        reason="evidence_missing",
    )
    if not run or not isinstance(run.get("state"), dict):
        return result
    state = run["state"]
    records = state.get("whole_solution_reviews", [])
    if not records:
        return result
    record = records[-1]
    source = record.get("source", {})
    calls = state.get("calls", {})
    answer = (job.get("result") or {}).get("final_response", "")
    call_id = source.get("call_id")
    call = calls.get(call_id, {})
    request = call.get("request", {})
    wire = [item for item in contexts if item.get("call_id") == call_id]
    valid = (
        job.get("status") == "succeeded"
        and bool(answer.strip())
        and job.get("job_id") == run.get("run_id") == source.get("run_id")
        and state.get("final_response") == answer
        and state.get("status") == "completed_llm_reviewed"
        and review_binding(run, answer) == {"whole_review": "accepted", "binding": "same_artifact"}
        and len(wire) == 1
        and wire[0].get("run_id") == run["run_id"]
        and wire[0].get("role") == "whole_solution_verifier"
        and wire[0].get("solution_candidate") == request.get("solution_candidate")
        and wire[0].get("step_proofs", []) == request.get("step_proofs", [])
    )
    if not valid:
        return {**result, "reason": "review_not_bound"}
    proofs = request.get("step_proofs", [])
    if source.get("origin") == "explore_polish":
        return {
            **result,
            "review_bound": True,
            "reason": "fastpath_no_step_proofs",
            "review_call_id": call_id,
            "candidate_version": source["candidate_version"],
        }
    attempts = [
        attempt
        for attempt in state.get("final_solution_attempts", [])
        if attempt.get("candidate") == request.get("solution_candidate")
        and attempt.get("plan_version") == source["plan_version"]
        and attempt.get("attempt_index") == source["attempt_index"]
        and completed_call_id(calls, "whole-review:" + attempt.get("session_key", "")) == call_id
    ]
    if len(attempts) != 1:
        return {**result, "reason": "candidate_source_missing_or_ambiguous"}
    # Candidate generation events are in the same order as the persisted
    # final_solution_attempts (including archived plans). Their revision window
    # distinguishes repeated identical text without a role-order heuristic.
    generated = [
        event for event in run.get("events", []) if event.get("type") == "final_candidate_generated"
    ]
    ordinal = attempts[0].get("attempt")
    if not isinstance(ordinal, int) or ordinal < 0 or ordinal >= len(generated):
        return {**result, "reason": "candidate_generation_event_missing"}
    upper = generated[ordinal]["state_revision"]
    lower = generated[ordinal - 1]["state_revision"] if ordinal else 0
    generators = [
        item
        for item in calls.values()
        if item.get("role") == "final_generator"
        and item.get("status") == "completed"
        and item.get("run_id") == run["run_id"]
        and item.get("response", {}).get("final_response") == answer
        and item.get("request", {}).get("step_proofs", []) == proofs
        and lower < item.get("request_revision", 0) < upper
        and upper < call.get("request_revision", 0)
    ]
    if len(generators) != 1:
        return {**result, "reason": "generator_source_missing_or_ambiguous"}
    generator = generators[0]
    generated_wire = [item for item in contexts if item.get("call_id") == generator["call_id"]]
    delivered = (
        bool(proofs)
        and len(generated_wire) == 1
        and generated_wire[0].get("run_id") == run["run_id"]
        and generated_wire[0].get("step_proofs") == proofs
        and all(item.get("step_ordinal") is not None for item in record.get("proof_sources", []))
        and all(
            proof.get("artifact") == artifact_identity(proof.get("argument", ""))
            for proof in proofs
        )
        and record.get("proof_sources")
        == [_proof_source(proof, state.get("plan", {})) for proof in proofs]
    )
    return {
        **result,
        "review_bound": True,
        "proof_delivered": delivered,
        "nonfastpath": delivered,
        "reason": "proof_bound" if delivered else "proof_source_missing",
        "review_call_id": call_id,
        "generator_call_id": generator["call_id"],
        "candidate_version": source["candidate_version"],
        "proof_count": len(proofs),
    }


def evaluate_delivery(job, run, contexts):
    """Public zero-dispatch API; malformed saved provenance cannot imply success."""
    try:
        result = _evaluate_delivery(job, run, contexts)
        if run and isinstance(run.get("state"), dict):
            lifecycle = {"succeeded": "COMPLETED"}.get(job.get("status"), str(job.get("status", "")).upper())
            if job.get("status") == "failed" and job.get("error") in {
                "needs_review", "star_needs_review", "verification_needs_review",
            }:
                lifecycle = "NEEDS_REVIEW"
            result["semantics"] = result_semantics(
                run, (job.get("result") or {}).get("final_response", ""),
                verification_mode=job.get("verification_mode", "auto"),
                execution_status=lifecycle,
            )
        return result
    except (KeyError, TypeError, AttributeError, ValueError):
        return dict(
            runner_version=RUNNER_VERSION,
            review_bound=False,
            proof_delivered=False,
            nonfastpath=False,
            reason="invalid_provenance",
        )
