"""Qualitative evidence grades, never calibrated mathematical probabilities."""


def applicable_independent_refs(record, state):
    """Only actual successful local receipts bound to this candidate's claims count.

    Support covers the checked finite computation; it never asserts formal proof.
    Scripted, unknown, unbound and model-declared verification do not count.
    """
    if (
        record.get("run_id") != state.get("run_id")
        or record.get("problem_hash") != state.get("problem_hash")
        or record.get("plan_version") != state.get("plan_version")
        or record.get("attempt_index") != state.get("attempt_index")
        or record.get("review_state") in {"refuted", "invalidated"}
    ):
        return []
    receipts = {item["receipt_id"]: item for item in state.get("tool_receipts", [])}
    refs = []
    for step_id in record.get("step_refs", []):
        report = state.get("steps", {}).get(step_id, {}).get("report", {})
        for index, claim in enumerate(report.get("claims", [])):
            if (
                claim.get("label") != "verified"
                or claim.get("verification_scope") != "finite_computation"
            ):
                continue
            for ref in claim.get("tool_evidence_refs", []):
                receipt = receipts.get(ref, {})
                if (
                    receipt.get("step_id") == step_id
                    and receipt.get("claim_index") == index
                    and receipt.get("executed") is True
                    and receipt.get("status") == "success"
                    and receipt.get("source") == "local_precheck"
                    and receipt.get("assertion_matched") is True
                    and receipt.get("comparison_status") == "matched"
                    and type(receipt.get("exit_code")) is int
                    and receipt["exit_code"] == 0
                    and not receipt.get("timeout")
                    and not receipt.get("unknown_outcome")
                    and receipt.get("code_ref")
                    and receipt.get("stdout_ref")
                ):
                    refs.append(ref)
    return list(dict.fromkeys(refs))


def _review_refs(record, state, events, whole):
    source_types = {
        "EXPLORE": {"explore_assessed", "exploration_polished"},
        "STEP_EXECUTE": {"step_reported", "challenge_replied"},
        "FINAL_GENERATE": {"final_candidate_generated"},
    }.get(record.get("source_phase"), set())
    sources = record.get("source_event_refs", [])
    start = next(
        (
            index
            for index, event in enumerate(events)
            if sources
            and event.get("event_id") == sources[0]
            and event.get("type") in source_types
            and event.get("run_id") == record.get("run_id")
        ),
        None,
    )
    if start is None or record.get("run_id") != state.get("run_id"):
        return []
    refs = []
    for event in events[start + 1 :]:
        if event.get("type") in source_types:
            break
        if (
            event.get("event_id") not in record.get("evidence_refs", [])
            or event.get("event_id") not in sources
            or event.get("run_id") != record.get("run_id")
        ):
            continue
        kind = event.get("type")
        if whole and kind not in {"solution_review_assessed", "final_candidate_reviewed"}:
            continue
        if not whole and (
            kind != "step_reviewed" or event.get("step_id") not in record.get("step_refs", [])
        ):
            continue
        review = event.get("review", event)
        if review.get("verdict") == "ACCEPT" and (whole or review.get("valid") is True):
            refs.append(event["event_id"])
    return refs


def verified_whole_review_refs(record, state, events=None):
    """Accepted whole-review events in this candidate's source window only."""
    return _review_refs(record, state, events or [], True)


def grade_candidate(record, state, events=None):
    """Explain grades from audited events; raw snapshots without events stay conservative."""
    events = events or []
    event_ids = {event["event_id"] for event in events}
    reasons = {}
    questions = list(record.get("known_objections", []))
    evidence = [
        ref
        for ref in [*record.get("source_event_refs", []), *record.get("evidence_refs", [])]
        if ref in event_ids
    ]
    whole_refs = verified_whole_review_refs(record, state, events)
    local_refs = _review_refs(record, state, events, False)
    review_refs = whole_refs or local_refs
    support = applicable_independent_refs(record, state)
    level = "low"
    status = record.get("review_state")
    if status == "refuted":
        level = "rejected"
        refs = [ref for ref in record.get("evidence_refs", []) if ref in event_ids]
        reasons["decisively_refuted"] = refs or ["missing:refutation_reference"]
    elif status == "invalidated" or record.get("invalidated_by"):
        refs = [ref for ref in record.get("invalidated_by", []) if ref in event_ids]
        reasons["invalidated_dependency"] = refs or ["missing:invalidation_reference"]
        questions.append("Candidate dependencies have been invalidated.")
    elif (
        record.get("answer_completeness") != "complete" or not record.get("answer_text", "").strip()
    ):
        reasons["incomplete_answer"] = evidence or ["missing:complete_answer"]
        questions.append("A complete parseable answer is missing.")
    else:
        if review_refs:
            level = "medium"
            reasons["whole_review_accepted" if whole_refs else "local_review_accepted"] = (
                review_refs
            )
        else:
            reasons["missing_key_review"] = ["missing:accepted_review"]
            questions.append("No accepted mathematical review is recorded.")
        if support:
            reasons["applicable_finite_computation_support"] = support
        else:
            reasons["missing_independent_support"] = ["missing:independent_support"]
            questions.append("Independent applicable execution evidence is missing.")
        if not whole_refs:
            reasons["missing_whole_review"] = ["missing:whole_problem_review"]
            questions.append("Whole-problem review is missing.")
        if whole_refs and support and not questions:
            level = "high"
        if record.get("conflicting_candidate_ids"):
            level = "low"
            reasons["same_rank_candidate_conflict"] = record["conflicting_candidate_ids"]
            questions.append("Equally ranked candidates conflict; their answers remain unresolved.")
        if record.get("known_objections"):
            reasons["unresolved_material_objections"] = evidence or ["missing:objection_reference"]
            level = "low"
    return {
        "confidence_level": level,
        "reason_codes": list(reasons),
        "reason_evidence": reasons,
        "evidence_refs": list(dict.fromkeys([*evidence, *support])),
        "verified_whole_review_refs": whole_refs,
        "independent_evidence_refs": support,
        "unresolved_questions": list(dict.fromkeys(questions)),
        "evidence_scope": "heuristic_review_and_finite_computation",
    }
