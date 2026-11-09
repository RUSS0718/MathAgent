import copy
import unittest

from showcase.solver_harness.population_evidence import (
    capture_dependencies,
    merge_route_evidence,
    validate_dependencies,
)
from showcase.solver_harness.proof_graph import initial_proof_graph, proposition_id

OWNER = {"id": "owner-a", "epoch": 3}
RUN_ID = "run-population"
PROBLEM_HASH = "problem-hash"
CONFIG_HASH = "config-hash"
PLAN_VERSION = 8


def _accepted_record(state, step_id, result_id, call_prefix, statement):
    report_call_id = f"{call_prefix}-reasoner"
    review_call_id = f"{call_prefix}-verifier"
    claim = {"statement": statement}
    outcome = {
        "category": "Lemma",
        "statement": statement,
        "scope": "problem",
        "claim_indexes": [0],
        "receipt_ids": [],
        "dependencies": [],
    }
    review_response = {"verdict": "ACCEPT", "classified_outcomes": [outcome]}
    state["calls"][report_call_id] = {
        "call_id": report_call_id,
        "role": "reasoner",
        "run_id": RUN_ID,
        "problem_hash": PROBLEM_HASH,
        "config_hash": CONFIG_HASH,
        "plan_version": PLAN_VERSION,
        "attempt_index": 0,
        "request_revision": 10,
        "request": {"step": {"step_id": step_id}},
        "response": {"claims": [claim]},
        "status": "completed",
        "route_id": "route-1",
        "action_id": "action-1",
    }
    state["calls"][review_call_id] = {
        "call_id": review_call_id,
        "role": "step_verifier",
        "run_id": RUN_ID,
        "problem_hash": PROBLEM_HASH,
        "config_hash": CONFIG_HASH,
        "plan_version": PLAN_VERSION,
        "attempt_index": 0,
        "request_revision": 11,
        "request": {"step_id": step_id},
        "response": review_response,
        "status": "completed",
        "route_id": "route-1",
        "action_id": "action-1",
    }
    state["steps"][step_id] = {
        "status": "ACCEPTED",
        "report": {"claims": [claim]},
        "verification": {"valid": True, "verdict": "ACCEPT"},
    }
    return {
        "result_id": result_id,
        "category": "Lemma",
        "statement": statement,
        "scope": "problem",
        "source": step_id,
        "claim_indexes": [0],
        "review_call_id": review_call_id,
        "receipt_ids": [],
        "dependencies": [],
        "evidence_level": "llm_reviewed",
        "proven": True,
        "valid": True,
        "invalidated": False,
        "plan_version": PLAN_VERSION,
        "attempt_index": 0,
        "specification_version": 2,
    }


def _graph_with_result(state, record):
    graph = initial_proof_graph()
    snapshot = graph["snapshots"][-1]
    prop_id = proposition_id(state, record["statement"], record["scope"])
    attempt_id = f"attempt:{record['result_id']}"
    report_call_id = next(
        call_id for call_id, call in state["calls"].items()
        if call["role"] == "reasoner"
        and call["request"].get("step", {}).get("step_id") == record["source"]
    )
    snapshot["propositions"][prop_id] = {
        "id": prop_id,
        "statement": record["statement"],
        "scope": record["scope"],
        "problem_version": 2,
        "status": "supported",
        "conflict": False,
        "sources": [f"review:{record['review_call_id']}"],
    }
    snapshot["attempts"][attempt_id] = {
        "id": attempt_id,
        "status": "accepted",
        "direction": "support",
        "grade": "llm_reviewed",
        "conclusion": prop_id,
        "premises": [],
        "source_refs": [f"report:{report_call_id}",
                         f"review:{record['review_call_id']}"],
        "result_id": record["result_id"],
    }
    snapshot["derivations"][f"derivation:{record['result_id']}"] = {
        "id": f"derivation:{record['result_id']}",
        "status": "accepted",
        "conclusion": prop_id,
        "premises": [],
        "attempt_id": attempt_id,
        "result_id": record["result_id"],
        "source_refs": list(snapshot["attempts"][attempt_id]["source_refs"]),
        "ledger_dependencies": [],
    }
    graph["current_version"] = 1
    snapshot["graph_version"] = 1
    graph["snapshots"].append(copy.deepcopy(snapshot))
    graph["snapshots"][0]["graph_version"] = 0
    state["proof_graph"] = graph
    return prop_id


def _base_state():
    state = {
        "run_id": RUN_ID,
        "problem_hash": PROBLEM_HASH,
        "config_hash": CONFIG_HASH,
        "specification_version": 2,
        "plan_version": PLAN_VERSION,
        "state_revision": 30,
        "calls": {},
        "steps": {},
        "accepted_results": [],
        "verified_results_ledger": [],
        "obligation_evidence_ledger": [],
        "obligation_ledger": [],
        "population": {"owner": dict(OWNER), "routes": {}, "actions": {}},
    }
    base = _accepted_record(state, "base:step", "base-result", "base", "Base lemma")
    state["verified_results_ledger"].append(base)
    _graph_with_result(state, base)
    return state


class PopulationEvidenceTests(unittest.TestCase):
    def test_dependencies_bind_only_adopted_propositions_not_global_graph_version(self):
        state = _base_state()
        dependency = capture_dependencies(
            state,
            {"adopted_result_ids": ["base-result"], "adopted_proposition_ids": []},
        )
        self.assertEqual(1, len(dependency))
        self.assertEqual("base-result", dependency[0]["result_id"])
        self.assertIn("review:base-verifier", dependency[0]["evidence_ids"])

        unrelated = copy.deepcopy(state)
        unrelated["proof_graph"]["current_version"] = 2
        extra = copy.deepcopy(unrelated["proof_graph"]["snapshots"][-1])
        extra["graph_version"] = 2
        extra["propositions"]["unrelated"] = {
            "id": "unrelated", "problem_version": 2, "status": "supported",
            "conflict": False, "sources": [],
        }
        unrelated["proof_graph"]["snapshots"].append(extra)
        self.assertEqual((True, None), validate_dependencies(unrelated, dependency))

        revoked = copy.deepcopy(state)
        current = revoked["proof_graph"]["snapshots"][-1]
        current["propositions"][dependency[0]["proposition_id"]]["status"] = "invalidated"
        self.assertEqual(False, validate_dependencies(revoked, dependency)[0])

    def test_merge_accepts_only_completed_persisted_verifier_sources_and_is_incremental(self):
        parent = _base_state()
        route_id, action_id, step_id = "route-1", "action-1", "route-1:step-1"
        branch = copy.deepcopy(parent)
        branch["plan_version"] = PLAN_VERSION
        new_record = _accepted_record(branch, step_id, "route-result", "route", "Route lemma")
        branch["verified_results_ledger"].append(new_record)
        _graph_with_result(branch, new_record)
        branch["accepted_results"].append({
            "category": "step_result", "statement": "Route lemma", "source": step_id,
            "evidence_level": "llm_reviewed", "dependencies": [],
        })
        branch["state_revision"] = 14
        parent["calls"].update(copy.deepcopy({
            key: value for key, value in branch["calls"].items() if key not in parent["calls"]
        }))
        route = {
            "route_id": route_id, "frontier_digest": "frontier", "plan_version": PLAN_VERSION,
            "revision": 14, "owner": dict(OWNER), "snapshot": {}, "events": [],
            "status": "pending_commit",
        }
        action = {
            "action_id": action_id, "route_id": route_id, "status": "completed",
            "owner": dict(OWNER), "epoch": OWNER["epoch"], "dependencies": [],
            "reservation": {},
        }
        parent["population"]["routes"][route_id] = route
        parent["population"]["actions"][action_id] = action
        branch_event = {
            "event_id": "local-step-reviewed-1", "run_id": RUN_ID,
            "state_revision": 14, "type": "step_reviewed", "step_id": step_id,
            "verdict": "ACCEPT",
        }
        branch_snapshot = {
            "run_id": RUN_ID, "state": branch, "events": [branch_event],
            "state_revision": 14,
        }

        updates, audit = merge_route_evidence(parent, route, action, branch_snapshot)
        self.assertTrue(audit["accepted"])
        self.assertEqual(["route-result"], [item["result_id"] for item in updates["verified_results_ledger"]])
        self.assertEqual("step_reviewed", audit["type"])
        self.assertEqual(["local-step-reviewed-1"], audit["source_event_ids"])
        self.assertEqual(["route-reasoner"], audit["report_call_ids"])
        self.assertEqual(["route-verifier"], audit["review_call_ids"])

        committed = copy.deepcopy(parent)
        committed["verified_results_ledger"].extend(updates["verified_results_ledger"])
        committed["accepted_results"].extend(updates["accepted_results"])
        if "obligation_evidence_ledger" in updates:
            committed["obligation_evidence_ledger"].extend(updates["obligation_evidence_ledger"])
        again, second_audit = merge_route_evidence(committed, route, action, branch_snapshot)
        self.assertEqual([], again.get("verified_results_ledger", []))
        self.assertEqual([], second_audit["merged_result_ids"])

    def test_model_only_or_stale_owner_branch_cannot_change_parent_math(self):
        parent = _base_state()
        route = {"route_id": "route-1", "plan_version": PLAN_VERSION,
                 "revision": 1, "owner": dict(OWNER), "status": "pending_commit"}
        action = {"action_id": "action-1", "route_id": "route-1", "status": "completed",
                  "owner": {"id": "old-owner", "epoch": 2}, "dependencies": []}
        parent["population"]["routes"][route["route_id"]] = route
        parent["population"]["actions"][action["action_id"]] = action
        branch = copy.deepcopy(parent)
        branch["verified_results_ledger"].append({
            "result_id": "forged", "statement": "model assertion", "proven": True,
            "valid": True, "evidence_level": "llm_reviewed",
        })
        snapshot = {"run_id": RUN_ID, "state": branch, "events": [], "state_revision": 1}

        updates, audit = merge_route_evidence(parent, route, action, snapshot)
        self.assertEqual({}, updates)
        self.assertFalse(audit["accepted"])
        self.assertEqual("owner_epoch_mismatch", audit["reason"])


if __name__ == "__main__":
    unittest.main()
