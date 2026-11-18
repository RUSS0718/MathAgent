import copy
import unittest

from showcase.solver_harness.population_evidence import (
    merge_route_evidence,
    prepare_adoption,
    validate_dependencies,
)
from tests.test_population_evidence import (
    OWNER,
    PLAN_VERSION,
    RUN_ID,
    _accepted_record,
    _base_state,
    _graph_with_result,
)

CURRENT_OWNER = {"id": "owner-b", "epoch": 4}


def _takeover_case(acceptance_owner=True):
    parent = _base_state()
    route_id, action_id, step_id = "route-1", "action-1", "route-1:step-1"
    old_owner = dict(OWNER)
    route = {
        "route_id": route_id,
        "plan_version": PLAN_VERSION,
        "revision": 14,
        "owner": old_owner,
        "snapshot": {},
        "events": [],
        "status": "pending_commit",
    }
    action = {
        "action_id": action_id,
        "route_id": route_id,
        "status": "completed",
        "owner": old_owner,
        "epoch": old_owner["epoch"],
        "dependencies": [],
    }
    if acceptance_owner:
        action["acceptance_owner"] = dict(CURRENT_OWNER)
        route["acceptance_owner"] = dict(CURRENT_OWNER)

    branch = copy.deepcopy(parent)
    result = _accepted_record(branch, step_id, "route-result", "route", "Route lemma")
    branch["verified_results_ledger"].append(result)
    _graph_with_result(branch, result)
    for call in branch["calls"].values():
        if call.get("request", {}).get("step", {}).get("step_id") == step_id:
            call.update(route_id=route_id, action_id=action_id)
    event = {
        "event_id": "route-reviewed",
        "run_id": RUN_ID,
        "type": "step_reviewed",
        "step_id": step_id,
        "verdict": "ACCEPT",
    }
    snapshot = {"run_id": RUN_ID, "state": branch, "events": [event], "state_revision": 14}
    parent["population"]["owner"] = dict(CURRENT_OWNER)
    return parent, route, action, snapshot, old_owner


class PopulationAdoptionTests(unittest.TestCase):
    def test_adoption_binds_report_to_latest_completed_request_before_its_review(self):
        parent = _base_state()
        report = parent["calls"]["base-reasoner"]
        earlier = {**copy.deepcopy(report), "call_id": "earlier-challenge", "request_revision": 1}
        future = {**copy.deepcopy(report), "call_id": "future-challenge", "request_revision": 12}
        parent["calls"] = {"earlier-challenge": earlier, "future-challenge": future, **parent["calls"]}
        _, dependencies = prepare_adoption(parent, {"plan": {"steps": []}})
        self.assertEqual(1, len(dependencies))
        self.assertIn("report:base-reasoner", dependencies[0]["evidence_ids"])

    def test_prepare_adoption_shares_current_verified_parent_results_across_routes(self):
        parent = _base_state()
        parent["plan"] = {"steps": [{"step_id": "different-parent-step", "depends_on": []}]}
        parent["verified_results_ledger"].append(
            {
                "result_id": "unrelated-result",
                "source": "unrelated:step",
            }
        )
        parent["accepted_results"].append(
            {
                "category": "step_result",
                "source": "base:step",
                "statement": "Base lemma",
                "evidence_level": "llm_reviewed",
            }
        )
        route_snapshot = {
            "plan": {"steps": [{"step_id": "route:current", "depends_on": []}]},
            "current_step": "route:current",
            "steps": {},
            "accepted_results": [],
            "verified_results_ledger": [],
            "calls": {},
        }

        patch, dependencies = prepare_adoption(parent, route_snapshot)

        self.assertEqual(["base-result"], [item["result_id"] for item in dependencies])
        self.assertEqual(
            ["base-result"], [item["result_id"] for item in patch["verified_results_ledger"]]
        )
        self.assertEqual(["base-result"], patch["adopted_result_ids"])
        self.assertEqual((True, None), validate_dependencies(parent, dependencies))
        self.assertEqual(["Base lemma"], [item["statement"] for item in patch["accepted_results"]])
        self.assertIn("base-reasoner", patch["calls"])
        self.assertIn("base:step", patch["steps"])

    def test_prepare_adoption_excludes_unknown_and_invalid_parent_evidence(self):
        parent = _base_state()
        parent["plan"] = {"steps": [{"step_id": "parent-step", "depends_on": []}]}
        route_snapshot = {
            "plan": {"steps": [{"step_id": "route:current", "depends_on": []}]},
            "current_step": "route:current",
            "steps": {},
            "accepted_results": [],
            "verified_results_ledger": [],
            "calls": {},
        }
        parent["calls"]["unknown-reasoner"] = {
            **parent["calls"]["base-reasoner"],
            "status": "unknown_outcome",
        }
        parent["verified_results_ledger"].append(
            {
                "result_id": "invalid-result",
                "source": "other-route:step",
                "valid": False,
                "proven": False,
            }
        )
        parent["calls"] = {
            "unknown-reasoner": parent["calls"]["unknown-reasoner"],
            "base-reasoner": parent["calls"]["base-reasoner"],
            "base-verifier": parent["calls"]["base-verifier"],
        }

        patch, dependencies = prepare_adoption(parent, route_snapshot)

        self.assertEqual(["base-result"], [item["result_id"] for item in dependencies])
        self.assertIn("report:base-reasoner", dependencies[0]["evidence_ids"])
        self.assertEqual(
            ["base-result"], [item["result_id"] for item in patch["verified_results_ledger"]]
        )

    def test_prepare_adoption_rejects_evidence_from_another_specification_version(self):
        parent = _base_state()
        parent["specification_version"] = 3
        route_snapshot = {
            "plan": {"steps": [{"step_id": "route:current", "depends_on": []}]},
            "current_step": "route:current",
            "steps": {},
            "accepted_results": [],
            "verified_results_ledger": [],
            "calls": {},
        }

        patch, dependencies = prepare_adoption(parent, route_snapshot)

        self.assertEqual([], dependencies)
        self.assertEqual([], patch["verified_results_ledger"])
        self.assertEqual([], patch["adopted_result_ids"])

    def test_current_owner_can_revalidate_completed_action_without_rewriting_executor(self):
        parent, route, action, snapshot, execution_owner = _takeover_case()

        updates, audit = merge_route_evidence(parent, route, action, snapshot)

        self.assertTrue(audit["accepted"])
        self.assertEqual(
            ["route-result"], [item["result_id"] for item in updates["verified_results_ledger"]]
        )
        self.assertEqual(execution_owner, action["owner"])
        self.assertEqual(execution_owner["epoch"], action["epoch"])

    def test_stale_executor_without_both_current_acceptance_marks_is_rejected(self):
        for missing in ("action", "route"):
            with self.subTest(missing=missing):
                parent, route, action, snapshot, _ = _takeover_case()
                if missing == "action":
                    action.pop("acceptance_owner")
                else:
                    route.pop("acceptance_owner")

                updates, audit = merge_route_evidence(parent, route, action, snapshot)

                self.assertEqual({}, updates)
                self.assertFalse(audit["accepted"])
                self.assertEqual("owner_epoch_mismatch", audit["reason"])

    def test_stale_executor_rejects_acceptance_mark_owned_by_another_epoch(self):
        parent, route, action, snapshot, _ = _takeover_case()
        route["acceptance_owner"] = {"id": "owner-b", "epoch": 3}

        updates, audit = merge_route_evidence(parent, route, action, snapshot)

        self.assertEqual({}, updates)
        self.assertFalse(audit["accepted"])
        self.assertEqual("owner_epoch_mismatch", audit["reason"])

    def test_takeover_does_not_accept_calls_rebound_to_another_action(self):
        parent, route, action, snapshot, _ = _takeover_case()
        snapshot["state"]["calls"]["route-reasoner"]["action_id"] = "different-action"

        updates, audit = merge_route_evidence(parent, route, action, snapshot)

        self.assertEqual({}, updates)
        self.assertFalse(audit["accepted"])

    def test_takeover_requires_one_unchanged_execution_owner_for_route_and_action(self):
        parent, route, action, snapshot, _ = _takeover_case()
        route["owner"] = {"id": "another-old-owner", "epoch": 2}

        updates, audit = merge_route_evidence(parent, route, action, snapshot)

        self.assertEqual({}, updates)
        self.assertFalse(audit["accepted"])
        self.assertEqual("owner_epoch_mismatch", audit["reason"])

    def test_takeover_still_requires_completed_action(self):
        parent, route, action, snapshot, _ = _takeover_case()
        action["status"] = "unknown"

        updates, audit = merge_route_evidence(parent, route, action, snapshot)

        self.assertEqual({}, updates)
        self.assertFalse(audit["accepted"])
        self.assertEqual("action_not_completed", audit["reason"])


if __name__ == "__main__":
    unittest.main()
