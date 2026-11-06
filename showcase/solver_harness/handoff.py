"""Explicit engineering delivery policy; drafts never become proven premises."""

from copy import deepcopy

from .final_binding import review_binding


def enabled(config):
    return config.get("acceptance_mode", "strict") == "handoff"


def reviewed_drafts(state):
    drafts = []
    for step in state.get("plan", {}).get("steps", []):
        record = state.get("steps", {}).get(step["step_id"], {})
        if record.get("status") not in {"ACCEPTED", "REVIEWED"}:
            continue
        review = record.get("verification", {})
        if review.get("valid") is not True or review.get("verdict") not in {"ACCEPT", "CHALLENGE"}:
            continue
        drafts.append({
            "step_id": step["step_id"], "objective": step["objective"],
            "provenance": "reviewed_draft_not_proof",
            "report": deepcopy(record.get("report", {})), "review": deepcopy(review),
            "tool_receipts": [deepcopy(receipt) for receipt in state.get("tool_receipts", [])
                              if receipt.get("step_id") == step["step_id"]
                              and receipt.get("run_id") == state["run_id"]
                              and receipt.get("plan_version") == state["plan_version"]
                              and receipt.get("attempt_index") == state["attempt_index"]],
        })
    return drafts


def prepare_request(run, request):
    request = {**request, "acceptance_mode": "handoff"}
    if "session_history" in request:
        request["session_history"] = deepcopy(request["session_history"])
    if request.get("role") in {"reasoner", "reason_noncoding", "step_verifier",
                               "final_generator", "whole_solution_verifier"}:
        request["reviewed_drafts"] = reviewed_drafts(run["state"])
        current = request["reviewed_drafts"]
        for exchange in request.get("session_history", []):
            previous = exchange.get("request", {})
            old = previous.get("reviewed_drafts")
            if (isinstance(old, list) and old and old == current[:len(old)]
                    and isinstance(request.get("session_key"), str) and request["session_key"]
                    and previous.get("run_id") == run["run_id"]
                    and previous.get("session_key") == request.get("session_key")
                    and previous.get("acceptance_mode") == "handoff"):
                previous.pop("reviewed_drafts")
                previous["reviewed_drafts_prefix_ref"] = {
                    "source": "current_request.reviewed_drafts", "length": len(old),
                }
    return request


def delivery_check(run, answer):
    """Engineering result only; mathematical approval uses delivery_verification."""
    state = run["state"]
    binding = review_binding(run, answer)
    complete = (
        isinstance(answer, str) and bool(answer.strip())
        and state.get("phase") == "TERMINAL"
        and (state.get("result_reason") == "handoff_final_reviewed"
             or state.get("status") == "completed_llm_reviewed")
        and binding["binding"] == "same_artifact"
        and binding["whole_review"] in {"accepted", "rejected"}
        and len(reviewed_drafts(state)) == len(state.get("plan", {}).get("steps", []))
        and not any(call.get("status") in {"dispatched", "unknown_outcome", "provider_failed"}
                    for call in state.get("calls", {}).values())
        and not any(receipt.get("unknown_outcome") is True
                    or (receipt.get("executed") is True
                        and receipt.get("source") == "docker_isolated"
                        and receipt.get("cleanup_verified") is not True)
                    for receipt in state.get("tool_receipts", []))
    )
    return {"contract": "handoff-delivery-v1", "status": "PASS" if complete else "FAIL",
            "math_review": binding["whole_review"], "binding": binding["binding"]}
