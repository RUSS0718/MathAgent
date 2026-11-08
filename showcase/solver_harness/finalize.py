"""Opt-in final synthesis and bounded independent whole-solution review."""

import json
from collections.abc import Mapping
from copy import deepcopy

from ..final_evidence import artifact_identity
from ..redaction import redact
from .budget import budget_reason
from .calls import CallInterrupted
from .final_binding import review_record
from .results import stable_unique_results


def _serialized_request_size(harness, model_port, run, request, *, use_snapshot=False):
    prepared = harness.prepare_request(run, request, use_snapshot=use_snapshot)
    estimator = getattr(model_port, "serialized_payload_size", None)
    if callable(estimator):
        return estimator(prepared)
    return len(json.dumps(prepared, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def finalization_requests(problem, facts, proofs, session, previous_review, handoff_mode):
    generator_request = {
        "role": "final_generator",
        "call_id": f"final-generator:{session}",
        "session_key": session,
        "problem": problem,
        "accepted_results": facts,
        "step_proofs": deepcopy(proofs),
        "previous_review": previous_review,
        "finalization_scope": True,
        "instruction": "Synthesize a complete answer to the original problem from "
        + ("the accepted facts and reviewed_drafts. Drafts are unproven: address their "
           "recorded objections explicitly; do not describe them as accepted proofs. "
           if handoff_mode else "only the accepted facts and the delivered step proofs. ")
        + "Return final_response.",
    }
    review_request = {
        "role": "whole_solution_verifier",
        "call_id": f"whole-review:{session}",
        "session_key": f"whole_verify:{session}",
        "problem": problem,
        "solution_candidate": "",
        "accepted_results": facts,
        "step_proofs": deepcopy(proofs),
        "finalization_scope": True,
        "review_criteria": [
            "original_problem_consistency",
            "completeness",
            "cross_step_logic",
            "output_format",
        ],
    }
    return generator_request, review_request


def finalization_reserve_estimate(
    harness, model_port, run, generator_request, review_request, *, require_cap=False,
    use_snapshot=False,
):
    """Read-only token estimate using the exact shared finalization payload contract."""
    adapter = getattr(model_port, "adapter", None)
    output_cap = getattr(adapter, "max_tokens", None)
    if type(output_cap) is not int or output_cap < 0:
        if require_cap:
            raise ValueError("finalization_output_cap_unavailable")
        output_cap = 0
    if require_cap and output_cap == 0:
        raise ValueError("finalization_output_cap_unavailable")
    candidate_byte_cap = output_cap * 4 if output_cap else None
    review = {
        **review_request,
        "solution_candidate": "x" * candidate_byte_cap if candidate_byte_cap else "",
    }
    generator_input = _serialized_request_size(
        harness, model_port, run, generator_request, use_snapshot=use_snapshot
    ) + 1_024
    review_input = _serialized_request_size(
        harness, model_port, run, review, use_snapshot=use_snapshot
    ) + 1_024
    return {
        "model_calls": 2,
        "http_attempts": 2,
        "tokens": generator_input + output_cap + review_input + output_cap,
        "generator_input": generator_input,
        "review_input": review_input,
        "output_cap": output_cap,
        "candidate_byte_cap": candidate_byte_cap,
    }


def _reserve_finalization_pair(
    harness, budget, run, model_port, generator_request, review_request, reservation_id
):
    from ..run_budget import BudgetExhausted

    candidate_byte_cap = None
    try:
        estimate = finalization_reserve_estimate(
            harness, model_port, run, generator_request, review_request
        )
        output_cap = estimate["output_cap"]
        candidate_byte_cap = estimate["candidate_byte_cap"]
        budget.ledger.reserve_finalization_pair(
            run["run_id"],
            reservation_id=reservation_id,
            final_input_estimate=estimate["generator_input"],
            final_output_cap=output_cap,
            review_input_estimate=estimate["review_input"],
            review_output_cap=output_cap,
        )
    except BudgetExhausted as exc:
        return str(exc), candidate_byte_cap
    except Exception:
        return "finalization_reservation_estimate_unavailable", candidate_byte_cap
    return None, candidate_byte_cap


def _skip_unneeded_work_units(harness, run):
    state = run["state"]
    plan = state.get("plan") or {}
    steps = deepcopy(state.get("steps", {}))
    skipped = list(state.get("skipped_work_units", []))
    added = []
    for step in plan.get("steps", []):
        step_id = step["step_id"]
        verification = steps.get(step_id, {}).get("verification", {})
        if verification.get("valid") is True and verification.get("verdict") == "ACCEPT":
            continue
        if steps.get(step_id, {}).get("status") == "SKIPPED":
            continue
        steps[step_id] = {
            **steps.get(step_id, {}),
            "status": "SKIPPED",
            "skip_reason": "root_obligations_satisfied",
        }
        skipped.append({
            "work_unit_id": step_id,
            "specification_version": state["specification_version"],
            "reason": "root_obligations_satisfied",
        })
        added.append(step_id)
    if not added:
        return run
    return commit(
        harness,
        run,
        "auxiliary_work_skipped",
        {"steps": steps, "skipped_work_units": skipped},
        skipped_count=len(added),
        specification_version=state["specification_version"],
    )


def commit(harness, run, kind, updates, **details):
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={"event_id": f"{kind}-{run['state_revision']}", "type": kind, **details},
        state_updates=updates,
    )


def finish(harness, run, status, reason, candidate=""):
    updates = {
        "phase": "TERMINAL",
        "status": status,
        "result_reason": reason,
        "final_response": candidate or f"No verified final answer is available: {reason}.",
    }
    if "budget_exhausted" in reason:
        updates["budget"] = {**run["state"].get("budget", {}), "exhaustion_reason": reason}
    return commit(harness, run, "finalization_completed", updates, reason=reason)


def dispatch(harness, run, operation, request, _repair_attempt=0):
    from . import protocol_repair

    state = run["state"]
    run = commit(
        harness,
        run,
        "finalization_dispatched",
        {"counters": {**state["counters"], "model_calls": state["counters"]["model_calls"] + 1}},
        role=request["role"],
    )
    base_call_id = request.get("call_id") or f"{run['run_id']}:{request['role']}:{run['state_revision']}"
    request = {
        "run_id": run["run_id"],
        "allowed_tools": [],
        "tool_policy": {"allow": []},
        **request,
        "call_id": protocol_repair.repair_call_id(base_call_id) if _repair_attempt else base_call_id,
    }
    if request["role"] in {"final_generator", "whole_solution_verifier"}:
        request["finalization_scope"] = True

    def invoke(prepared):
        if request["role"] == "final_generator":
            prepared = deepcopy(prepared)
            prepared.update(allowed_tools=[], tool_policy={"allow": []})
        return operation(prepared)

    try:
        reply = harness.dispatch(run, invoke, request)
        return run, redact(deepcopy(dict(reply)))
    except CallInterrupted as exc:
        failed = protocol_repair.interrupted_call(harness, run["run_id"], exc)
        if (
            _repair_attempt == 0
            # The planner owns its bounded repair (plan_generation); this
            # wrapper only repairs the roles with no other owner.
            and request["role"] != "planner"
            and failed is not None
            and protocol_repair.repair_enabled(harness._config)
            and protocol_repair.known_protocol_failure(failed)
        ):
            # One gated format repair: the note bumps the revision, so the
            # recursive dispatch reserves again and answers under a fresh
            # revision-derived call identity. A second failure re-raises.
            noted = protocol_repair.reserve_repair(
                harness, run["run_id"], exc,
                failure_event=lambda latest, failed: {
                    "event_id": f"finalization-parse-{request['role']}-{latest['state_revision']}",
                    "type": "finalization_parse_failed", "role": request["role"],
                    "summary": "Finalization reply failed the response protocol; one bounded repair follows",
                },
            )
            repaired = protocol_repair.repair_request(request, failed_call=failed)
            repaired["call_id"] = base_call_id  # The recursive owner adds the single repair suffix.
            return dispatch(
                harness, noted, operation,
                {key: value for key, value in repaired.items()
                 if key not in {"run_id", "allowed_tools", "tool_policy"}},
                _repair_attempt=1,
            )
        raise
    except Exception:
        return run, None


def valid_facts(state):
    """Exclude invalidated, unsupported, missing or cyclic dependent records."""
    plan = state.get("plan", {})
    steps = state.get("steps", {})
    accepted_steps = {
        step["step_id"]
        for step in plan.get("steps", [])
        if steps.get(step["step_id"], {}).get("verification", {}).get("valid") is True
        and steps[step["step_id"]]["verification"].get("verdict") == "ACCEPT"
    }
    invalid_ids = {
        result.get("result_id")
        for failure in state.get("failure_records", [])
        for result in failure.get("invalidated_results", [])
        if result.get("result_id")
    }
    known = set(accepted_steps)
    # The classified ledger is authoritative for reviewer-established facts:
    # its proven entries join the accepted facts under the same dependency and
    # evidence filters, while Conjectures (evidence level "conjecture") and
    # invalidated records never become proven premises. A rescued outcome can
    # be visible through both ledgers; it is delivered once.
    combined = [
        *state.get("accepted_results", []),
        *(item for item in state.get("verified_results_ledger", []) if isinstance(item, dict)),
    ]
    pending = stable_unique_results(deepcopy(combined))
    facts = []
    while pending:
        selected = []
        for fact in pending:
            dependencies = fact.get("dependencies")
            if (
                not fact.get("invalidated")
                and fact.get("valid", True)
                and fact.get("status") not in {"INVALIDATED", "invalidated"}
                and fact.get("result_id") not in invalid_ids
                and fact.get("evidence_level") in {"llm_reviewed", "tool_verified"}
                and isinstance(fact.get("statement"), str)
                and fact["statement"].strip()
                and isinstance(dependencies, list)
                and all(d in known for d in dependencies)
                and (fact.get("source") in accepted_steps or fact.get("result_id")
                     or fact in state.get("rescued_results", []))
            ):
                facts.append(fact)
                if fact.get("result_id"):
                    known.add(fact["result_id"])
                selected.append(fact)
        if not selected:
            break
        pending = [fact for fact in pending if fact not in selected]
    return facts


def proof_basis(state):
    """Complete reports of still-valid accepted steps plus their computation basis.

    Final synthesis must integrate the accepted derivations themselves, not
    only their one-line conclusions. Only reports recorded on live plan steps
    can be delivered: an archived or invalidated derivation lives in the
    failure records and its proof body never returns here. Each delivered
    proof carries the controller-recorded review ruling, the challenge
    history and the actually executed receipts (code input, real output,
    sandbox source), so the final generator and the whole-solution reviewer
    can check the candidate against the real computation basis. Every proof
    carries the resolvable artifact identity of its original argument.
    """
    proofs = []
    for step in state.get("plan", {}).get("steps", []):
        record = state.get("steps", {}).get(step["step_id"])
        if not isinstance(record, Mapping):
            continue
        verification = record.get("verification", {})
        if (
            verification.get("verdict") != "ACCEPT"
            or verification.get("valid") is not True
        ):
            continue
        report = record.get("report", {})
        receipts = [
            deepcopy(item)
            for item in state.get("tool_receipts", [])
            if isinstance(item, Mapping)
            and item.get("step_id") == step["step_id"]
            and item.get("executed") is True
            and item.get("status") == "success"
        ]
        argument = report.get("argument", "")
        proof = {
            "step_id": step["step_id"],
            "argument": argument,
            "claims": [
                {
                    key: deepcopy(claim[key])
                    for key in (
                        "statement", "label", "verification_scope", "tool_evidence_refs"
                    )
                    if key in claim
                }
                for claim in report.get("claims", [])
                if isinstance(claim, Mapping)
            ],
            "tool_receipts": receipts,
            "review": {
                key: verification[key]
                for key in ("verdict", "goal_gate", "logic_gate")
                if key in verification
            },
            "artifact": artifact_identity(argument if isinstance(argument, str) else ""),
        }
        history = record.get("challenge_history", [])
        if history:
            proof["challenge_history"] = deepcopy(history)
        proofs.append(proof)
    return proofs


def run_finalization(harness, run, *, problem, model_port, verifier_port, config):
    from .handoff import enabled, reviewed_drafts

    features = config.get("features", {})
    state = run["state"]
    spec_enabled = isinstance(state.get("problem_spec"), Mapping)
    if run["state"]["phase"] != "FINAL_GENERATE":
        return run
    if not features.get("final_generation"):
        return finish(harness, run, "partial_aborted", "final_generation_required") if spec_enabled else run
    plan_steps = state.get("plan", {}).get("steps", [])
    handoff_mode = enabled(config)
    if spec_enabled:
        from .obligation_evidence import all_root_obligations_satisfied

        unfinished = not all_root_obligations_satisfied(state.get("obligation_ledger", []))
    else:
        unfinished = len(reviewed_drafts(state)) != len(plan_steps) if handoff_mode else any(
            state["steps"].get(step["step_id"], {}).get("verification", {}).get("verdict") != "ACCEPT"
            or state["steps"].get(step["step_id"], {}).get("verification", {}).get("valid") is not True
            for step in plan_steps
        )
    if not plan_steps or unfinished:
        return finish(
            harness, run, "partial_aborted",
            "root_obligations_incomplete" if spec_enabled else "unaccepted_plan_steps",
        )
    if spec_enabled and (not features.get("final_solution_review") or verifier_port is None):
        return finish(harness, run, "partial_aborted", "independent_final_review_required")
    retries = config.get("max_final_solution_retries", 2)
    if isinstance(retries, bool) or not isinstance(retries, int) or not 0 <= retries <= 20:
        raise ValueError("config.max_final_solution_retries must be 0..20")
    attempts = deepcopy(state.get("final_solution_attempts", []))
    current_attempts = [attempt for attempt in attempts
                        if attempt["plan_version"] == state["plan_version"]
                        and attempt["attempt_index"] == state["attempt_index"]
                        and not attempt.get("invalidated")
                        and not attempt.get("invalidated_by_specification_version")
                        and (not spec_enabled or attempt.get("specification_version")
                             == state["specification_version"])]
    previous_review = current_attempts[-1].get("review") if current_attempts else None
    pending_review = (getattr(harness, "_product_recovery", False)
                      and current_attempts and current_attempts[-1].get("review") is None)
    # Reviewing the existing candidate spends no new candidate-generation slot.
    remaining = retries + 1 - len(current_attempts) + int(bool(pending_review))
    facts = valid_facts(state)
    proofs = proof_basis(state)
    for _ in range(max(0, remaining)):
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason)
        if model_port is None:
            return finish(harness, run, "partial_aborted", "final_generator_unavailable")
        pending_review = (getattr(harness, "_product_recovery", False)
                          and current_attempts and current_attempts[-1].get("review") is None)
        if pending_review:
            attempt = current_attempts[-1]
            candidate = attempt["candidate"]
            session = attempt["session_key"]
            reservation_id = attempt.get("reservation_id")
        else:
            session = f"final:{run['run_id']}:plan{state['plan_version']}:attempt{state['attempt_index']}:candidate{len(attempts)}"
            reservation_id = (
                f"{run['run_id']}:spec{state.get('specification_version', 'legacy')}:"
                f"plan{state['plan_version']}:candidate{len(attempts)}"
            )
        generator_request, review_reservation_request = finalization_requests(
            problem, facts, proofs, session, previous_review, handoff_mode
        )
        candidate_byte_cap = None
        if spec_enabled:
            from ..run_budget import current_budget

            shared_budget = current_budget()
            if shared_budget is None:
                return finish(harness, run, "partial_aborted", "finalization_reservation_unavailable")
            reservation_error, candidate_byte_cap = _reserve_finalization_pair(
                harness,
                shared_budget,
                run,
                model_port,
                generator_request,
                review_reservation_request,
                reservation_id,
            )
            if reservation_error is not None:
                return finish(harness, run, "partial_aborted", reservation_error)
            run = _skip_unneeded_work_units(harness, run)
        if pending_review:
            pass
        else:
            run, reply = dispatch(
                harness,
                run,
                model_port.complete,
                generator_request,
            )
            candidate = reply.get("final_response") if isinstance(reply, Mapping) else None
            if not isinstance(candidate, str) or not candidate.strip():
                return finish(harness, run, "partial_aborted", "invalid_final_candidate")
            if candidate_byte_cap is not None and len(candidate.encode("utf-8")) > candidate_byte_cap:
                return finish(harness, run, "partial_aborted", "final_candidate_exceeds_reserved_review_input", candidate)
            attempt = {
                "attempt": len(attempts),
                "plan_version": state["plan_version"],
                "attempt_index": state["attempt_index"],
                **({"specification_version": state["specification_version"]}
                   if spec_enabled else {}),
                "candidate": candidate,
                "accepted_results": facts,
                "review": None,
                "session_key": session,
                "reservation_id": reservation_id if spec_enabled else None,
                "candidate_byte_cap": candidate_byte_cap,
            }
            attempts.append(attempt)
            current_attempts.append(attempt)
            run = commit(
                harness,
                run,
                "final_candidate_generated",
                {"final_solution_attempts": attempts, "phase": "FINAL_GENERATE"},
            )
        if not features.get("final_solution_review") or verifier_port is None:
            reason = (
                "final_review_disabled"
                if not features.get("final_solution_review")
                else "final_verifier_unavailable"
            )
            return finish(
                harness, run,
                "partial_aborted" if spec_enabled else "completed_unverified",
                reason, candidate,
            )
        reason = budget_reason(run["state"], config)
        if reason:
            return finish(harness, run, "partial_budget_exhausted", reason, candidate)
        base_request = {**review_reservation_request, "solution_candidate": candidate}
        run, review = dispatch(harness, run, verifier_port.verify, base_request)
        from .verifier_compute import continue_review, declared_request

        if isinstance(review, Mapping) and declared_request(review) is not None:

            def reserve_and_dispatch(current, _seq, _call_id, continuation):
                return dispatch(harness, current, verifier_port.verify, continuation)

            run, review, unfulfilled = continue_review(
                harness,
                run,
                role="whole_solution_verifier",
                step_id=None,
                round_number=0,
                attempt_index=state["attempt_index"],
                base_call_id=f"whole-review:{session}",
                base_request=base_request,
                reply=review,
                reserve_and_dispatch=reserve_and_dispatch,
            )
            if unfulfilled:
                review = {
                    "verdict": "UNAVAILABLE",
                    "reason": "verifier_tool_request_unfulfilled",
                }
        valid = (
            isinstance(review, Mapping)
            and isinstance(review.get("verdict"), str)
            and review["verdict"] in {"ACCEPT", "REJECT"}
        )
        attempt["review"] = (
            review
            if valid
            else {"verdict": "UNAVAILABLE", "reason": "invalid_or_failed_final_review"}
        )
        run = commit(
            harness,
            run,
            "final_candidate_reviewed",
            {"final_solution_attempts": attempts,
             "whole_solution_reviews": [*run["state"].get("whole_solution_reviews", []),
                 review_record(run, candidate, attempt["review"]["verdict"],
                     call_id=f"whole-review:{session}",
                     origin="final_generator", facts=facts, proofs=proofs)]},
            review=attempt["review"],
        )
        if not valid:
            return finish(
                harness, run,
                "partial_aborted" if spec_enabled else "completed_unverified",
                "final_verifier_failed", candidate,
            )
        if handoff_mode:
            return finish(
                harness, run,
                "partial_aborted" if spec_enabled else "completed_unverified",
                "handoff_final_reviewed", candidate,
            )
        if review["verdict"] == "ACCEPT":
            return finish(
                harness, run, "completed_llm_reviewed", "final_verifier_accepted", candidate
            )
        previous_review = review
    return finish(harness, run, "partial_aborted", "final_review_retries_exhausted")
