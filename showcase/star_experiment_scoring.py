"""Independent mathematics and product evidence are separate experiment axes."""

from .star_acceptance import evaluate_delivery
from .star_experiment_math import compare_conclusion
from .star_experiment_registration import digest


def score(question_id, question, bundle, review, *, expected=None, stage=None, provenance=None):
    job, report, evidence = (bundle[key] for key in ("job", "report", "evidence"))
    answer = report.get("answer", "")
    obligations = question["obligations"]
    valid_review = (isinstance(review, dict) and review.get("question_sha256") == question["prompt_sha256"]
                    and review.get("answer_sha256") == digest(answer)
                    and isinstance(review.get("reviewer"), str) and review["reviewer"].strip()
                    and review["reviewer"] != "intern-s2"
                    and isinstance(review.get("reason"), str) and review["reason"].strip()
                    and isinstance(review.get("obligations"), dict) and set(review["obligations"]) == set(obligations)
                    and all(isinstance(v, str) and v in {"pass", "reject", "undecided"}
                            for v in review["obligations"].values()))
    mathematics = "undecided"
    if valid_review:
        values = review["obligations"].values()
        mathematics = "reject" if "reject" in values else "undecided" if "undecided" in values else "pass"
    if expected is not None:
        conclusion = compare_conclusion(answer, expected, review.get("conclusion_span") if valid_review else None)
        if conclusion == "reject" or mathematics != "reject" and conclusion == "undecided":
            mathematics = conclusion
    semantics = report.get("semantics") or {}
    checks = report.get("checks") or {}
    bound = semantics.get("whole_review") == "accepted" and semantics.get("binding") == "same_artifact"
    consistent = (report.get("semantics") == evidence.get("semantics")
                  and checks == evidence.get("verification")
                  and report.get("budget") == evidence.get("budget")
                  and answer == (job.get("result") or {}).get("final_response", "")
                  and report.get("request_attempts") == evidence.get("request_attempts")
                  and bundle["run"].get("run_id") == job["job_id"] == evidence["run"]["run_id"])
    complete = job["status"] == "succeeded" and semantics.get("execution") == "completed" and bound
    snapshot, contexts = provenance if provenance is not None else (None, [])
    delivery = evaluate_delivery(job, snapshot, contexts)
    nonfastpath = bool(complete and consistent and delivery["nonfastpath"])
    budget = report.get("budget") or {}
    usage = budget.get("provider_known") or {}
    recovery = ((job.get("result") or {}).get("solver") or {}).get("recovery", {})
    unknown = (semantics.get("transport") == "unknown" or budget.get("unresolved_attempts", 0)
               or budget.get("unknown_tool_calls", 0))
    e1 = stage == "E1"
    latency = bundle.get("delivery_wall_time_seconds", float("inf")) <= (120 if e1 else 600)
    efficient = (budget.get("logical_calls", 999) <= 3
                 and usage.get("total_tokens") is not None and usage["total_tokens"] <= 8192
                 and not budget.get("unknown_attempts", 0) and not budget.get("tool_calls", 0)
                 and latency)
    return dict(mathematics=mathematics, independent_review=review if valid_review else None,
                flow_complete=complete, latency_met=latency, evidence_complete=consistent and bound,
                state_consistent=consistent,
                delivery=delivery, nonfastpath=nonfastpath, unknown=bool(unknown), e1_gate=(bool(
                    complete and consistent and efficient and mathematics == "pass") if e1 else None),
                protocol_defect=bool(recovery.get("protocol_failures")), cost=None)


def aggregate(records):
    budgets = [r["bundle"]["report"]["budget"] for r in records]
    return {**{key: sum(b.get(key, 0) for b in budgets) for key in (
        "logical_calls", "http_attempts", "tool_calls", "charged_tokens", "reserved_tokens",
        "local_input_estimate", "unknown_attempts", "unresolved_attempts", "unknown_tool_calls")},
        "known_tokens": (None if budgets and all((b.get("provider_known") or {}).get("total_tokens") is None
                                                 for b in budgets) else sum(
            (b.get("provider_known") or {}).get("total_tokens") or 0 for b in budgets)),
        "cost": None}


def admit(used, limits, elapsed, preflights):
    """Reserve a whole next-Run envelope against aggregates of S3 snapshots."""
    ceilings = dict(logical_calls=96, http_attempts=128, tool_calls=22, charged_tokens=524288)
    fields = dict(logical_calls="max_model_calls", http_attempts="max_http_attempts",
                  tool_calls="max_tool_calls", charged_tokens="max_tokens")
    if elapsed >= 4800:
        return "round_deadline_exhausted"
    if preflights >= 12:
        return "environment_budget_exhausted"
    if used["tool_calls"] + preflights >= 34:
        return "environment_budget_exhausted"
    for key, maximum in ceilings.items():
        if used[key] + limits[fields[key]] > maximum:
            return "round_" + key + "_insufficient"
    return None
