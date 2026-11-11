"""Persisted child evidence integrity checks and descriptive, denominator-preserving effects."""

import hashlib
import json
from copy import deepcopy
from statistics import mean

from .aprs import verified_gain
from .faithful_intervention_records import _encode


def recheck_native_report(connection, report):
    """Recompute measurements and audit persisted child evidence without rerunning Verifier."""
    report = deepcopy(report)
    if report.get("branch_engine") != "native_solver_checkpoint":
        return report
    row = connection.execute(
        "SELECT checkpoint_json FROM faithful_intervention_pairs WHERE pair_id=?",
        (report["pair_id"],)).fetchone()
    checkpoint = json.loads(row[0])
    plan_row = connection.execute(
        "SELECT payload_json FROM faithful_intervention_analysis_plans WHERE pair_id=?",
        (report["pair_id"],)).fetchone()
    analysis = json.loads(plan_row[0]) if plan_row else None
    identity_valid = (
        hashlib.sha256(_encode(checkpoint).encode()).hexdigest() == report["checkpoint_hash"]
        and report.get("config_hash", checkpoint["config_hash"]) == checkpoint["config_hash"]
        and report.get("problem_hash", checkpoint["problem_hash"]) == checkpoint["problem_hash"]
        and analysis is not None and report.get("analysis_plan") == analysis
        and report.get("analysis_plan_hash") == hashlib.sha256(_encode(analysis).encode()).hexdigest())
    before = set(verified_gain(checkpoint["state"]))
    from .faithful_intervention_budget import arm_budget_snapshot

    for arm, outcome in report["arms"].items():
        child = connection.execute(
            "SELECT pair_id,arm,checkpoint_hash,state_json,status FROM faithful_intervention_children "
            "WHERE branch_id=?", (outcome["branch_id"],)).fetchone()
        outcome["evidence_integrity"] = "not_checked"
        outcome["branch_verifier_verdict"] = None
        child_state = json.loads(child[3]) if child is not None else None
        action_row = connection.execute(
            "SELECT payload_json FROM faithful_intervention_actions WHERE action_id=?",
            (outcome["action_id"],)).fetchone()
        action = json.loads(action_row[0]) if action_row else {}
        review = (child_state.get("steps", {}).get(action.get("target"), {}).get("verification", {})
                  if isinstance(child_state, dict) else {})
        if isinstance(review.get("verdict"), str):
            outcome["branch_verifier_verdict"] = review["verdict"]
        review_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='faithful_intervention_reviews'"
        ).fetchone()
        review_row = connection.execute(
            "SELECT pair_id,source_branch_id,arm,checkpoint_hash,state_json,events_json,status "
            "FROM faithful_intervention_reviews WHERE pair_id=? AND arm=?",
            (report["pair_id"], arm),
        ).fetchone() if review_table else None
        outcome["independent_recheck_verdict"] = None
        recheck_valid = False
        if review_row is not None:
            recheck_state = json.loads(review_row[4])
            recheck_step = recheck_state.get("steps", {}).get(action.get("target"), {})
            recheck = recheck_step.get("verification", {})
            outcome["independent_recheck_verdict"] = recheck.get("verdict")
            old_call_ids = set(child_state.get("calls", {})) if isinstance(child_state, dict) else set()
            fresh_review_calls = [
                item for call_id, item in recheck_state.get("calls", {}).items()
                if call_id not in old_call_ids and item.get("role") == "step_verifier"
                and item.get("status") == "completed"
            ]
            physical = {item.get("solver_call_id") for item in json.loads(
                connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?",
                                   (report["run_id"],)).fetchone()[0]
            )["actions"] if item.get("reservation_id") == report["pair_id"]
                and item.get("kind") == "http"
                and item.get("role") == report["budget_reservation"]["arm_roles"][arm]
                and item.get("status") != "pre_reserved"}
            branch_report = (child_state.get("steps", {}).get(action.get("target"), {}).get("report")
                             if isinstance(child_state, dict) else None)
            review_call_bound = len(fresh_review_calls) == 1 and (
                fresh_review_calls[0]["call_id"] in physical
                and isinstance(fresh_review_calls[0].get("request"), dict)
                and fresh_review_calls[0]["request"].get("report") == branch_report
            )
            recheck_valid = (
                review_row[0] == report["pair_id"]
                and review_row[1] == outcome["branch_id"]
                and review_row[2] == arm
                and review_row[3] == report["checkpoint_hash"]
                and review_row[6] == "reviewed"
                and recheck.get("valid") is True
                and recheck.get("verdict") == "ACCEPT"
                and recheck_state.get("problem_hash") == checkpoint["problem_hash"]
                and recheck_state.get("config_hash") == checkpoint["config_hash"]
                and recheck_step.get("report") == branch_report
                and review_call_bound
            )
        if outcome["status"] != "completed":
            if outcome.get("branch_verifier_verdict") == "ACCEPT" and review_row is not None:
                outcome["evidence_integrity"] = (
                    "verified" if recheck_valid else "rejected"
                )
            continue
        accepted = False
        if (identity_valid and child is not None and child[0] == report["pair_id"] and child[1] == arm
                and child[2] == report["checkpoint_hash"] and child[4] == "reviewed"):
            state = child_state
            gain = sorted(set(verified_gain(state)) - before)
            accepted = (
                state.get("run_id") == checkpoint["run_id"]
                and state.get("problem_hash") == checkpoint["problem_hash"]
                and state.get("config_hash") == checkpoint["config_hash"]
                and state.get("route_policy") == checkpoint["state"].get("route_policy")
                and review.get("valid") is True
                and review.get("verdict") == "ACCEPT"
                and type(outcome.get("measurement")) in {int, float}
                and outcome["measurement"] == len(gain)
                and outcome.get("evidence", {}).get("current_verified_gain") == gain
            )
            resources = arm_budget_snapshot(connection, report["run_id"], report["pair_id"], arm)
            calls = [item for item in state.get("calls", {}).values()
                     if item.get("request_revision", -1) > checkpoint["state_revision"]
                     and item.get("status") == "completed"
                     and item.get("problem_hash") == checkpoint["problem_hash"]
                     and item.get("config_hash") == checkpoint["config_hash"]]
            roles = {item.get("role") for item in calls}
            ledger_row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?",
                                            (report["run_id"],)).fetchone()
            physical = {item.get("solver_call_id") for item in json.loads(ledger_row[0])["actions"]
                        if item.get("reservation_id") == report["pair_id"] and item.get("kind") == "http"
                        and item.get("role") == report["budget_reservation"]["arm_roles"][arm]
                        and item.get("status") != "pre_reserved"}
            bound_calls = all(item["call_id"] in physical
                              for item in calls if item.get("role") in {"reasoner", "step_verifier"})
            accepted = (accepted and {"reasoner", "step_verifier"}.issubset(resources["native_roles"])
                        and {"reasoner", "step_verifier"}.issubset(roles) and bound_calls
                        and not resources["unknown_attempts"] and not resources["unknown_tool_calls"])
        if accepted and recheck_valid:
            outcome["evidence_integrity"] = "verified"
        else:
            outcome.update(status="incomplete", measurement=None)
            outcome["evidence_integrity"] = "rejected"
    return report


def aggregate_pairs(engine, *, hypothesis_id=None, run_id=None):
    """Retain every started denominator; provide no unregistered interval or policy update."""
    rows = engine._connection.execute(
        "SELECT pair_id FROM faithful_intervention_pairs ORDER BY pair_id").fetchall()
    reports = [engine.get_pair(row[0]) for row in rows]
    if run_id is not None:
        reports = [item for item in reports if item["run_id"] == run_id]
    if hypothesis_id is not None:
        reports = [item for item in reports if item["hypothesis_id"] == hypothesis_id]
    started = [item for item in reports if item["started_pairs"]]
    native = [item for item in started if item.get("branch_engine") == "native_solver_checkpoint"]
    evaluable = [item for item in native if item["evaluable_pairs"]
                 and all(arm.get("evidence_integrity") == "verified"
                         for arm in item["arms"].values())]
    deltas = [item["effect"]["measurement_delta"] for item in evaluable]
    comparisons = {(item["hypothesis_id"], item["arms"]["control"]["action_id"],
                    item["arms"]["intervention"]["action_id"], item.get("policy_version"),
                    item.get("problem_hash"), item.get("config_hash"),
                    tuple(item["budget_reservation"].get(key) for key in
                          ("logical_calls", "http_attempts", "token_ceiling", "tool_calls", "time_seconds")))
                   for item in evaluable}
    return {
        "schema": "faithful-intervention-effects-v1",
        "started_pairs": len(started), "denominator": len(started),
        "pair_ids": [item["pair_id"] for item in started],
        "evaluable_pairs": len(evaluable),
        "unknown_pairs": sum(bool(item["unknown_pairs"]) for item in started),
        "incomplete_pairs": sum(not item["unknown_pairs"] and item not in evaluable for item in started),
        "mean_measurement_delta": mean(deltas) if deltas and len(comparisons) == 1 else None,
        "comparison_count": len(comparisons),
        "policy_versions": sorted({item["policy_version"] for item in native if item.get("policy_version")}),
        "interval": None, "interval_reason": "independent_sample_and_method_not_preregistered",
        "method": "descriptive_native_pairs_only", "policy_updated": False,
        "feedback": "offline_new_policy_review_required",
        "parent_evidence_merge": "not_merged_parent_checkpoint_preserved",
    }
