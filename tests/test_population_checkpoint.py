"""Accepted YIELD progress resumes locally without becoming shared proof evidence."""

import unittest
from copy import deepcopy

from showcase.solver_harness.population_evidence import merge_route_evidence
from tests.test_population_evidence import OWNER, PLAN_VERSION, RUN_ID, _base_state
from tests.test_solver_harness_reasoner_checkpoint import checkpoint


def continuation_case():
    parent = _base_state()
    branch = deepcopy(parent)
    step_id, checkpoint_id = "route-1:step", "yield-1"
    source = checkpoint(marker=checkpoint_id)["checkpoint"]
    record = {**source, "call_id": "report", "round": 1, "plan_version": PLAN_VERSION,
              "attempt_index": 0, "step_id": step_id}
    report = {"argument": source["argument"], "claims": source["claims"]}
    verdict = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}
    branch.update(phase="STEP_EXECUTE", status="running", current_step=step_id,
                  attempt_index=0, reasoner_checkpoints=[record])
    branch["steps"][step_id] = {"checkpoint_id": checkpoint_id, "checkpoint_status": "YIELD",
        "status": "CHECKPOINT_ACCEPTED", "report": report, "checkpoint_verification": verdict}
    common = {"status": "completed", "route_id": "route-1", "action_id": "action-1",
              "plan_version": PLAN_VERSION, "attempt_index": 0}
    branch["calls"].update({
        "report": {**common, "role": "reasoner", "response": {"checkpoint": source},
                   "request_revision": 10},
        "review": {**common, "role": "step_verifier", "response": verdict,
                   "request": {"checkpoint": record, "report": report}, "request_revision": 11},
    })
    route = {"route_id": "route-1", "owner": dict(OWNER), "plan_version": PLAN_VERSION}
    action = {"action_id": "action-1", "route_id": "route-1", "status": "completed",
              "owner": dict(OWNER), "dependencies": []}
    snapshot = {"run_id": RUN_ID, "state": branch, "events": [{
        "event_id": "yield-reviewed", "type": "step_reviewed", "step_id": step_id,
        "checkpoint_id": checkpoint_id, "checkpoint_status": "YIELD", "verdict": "ACCEPT"}]}
    return parent, route, action, snapshot


class PopulationCheckpointTest(unittest.TestCase):
    def test_yield_progress_does_not_promote_any_parent_evidence_or_root_coverage(self):
        parent, route, action, snapshot = continuation_case()
        original = deepcopy(parent)
        updates, audit = merge_route_evidence(parent, route, action, snapshot)
        self.assertEqual({}, updates)
        self.assertTrue(audit["accepted"])
        self.assertEqual("population_checkpoint_accepted", audit["type"])
        self.assertEqual([], audit["merged_result_ids"])
        self.assertEqual([], audit["merged_obligation_ids"])
        self.assertEqual(["report"], audit["report_call_ids"])
        self.assertEqual(["review"], audit["review_call_ids"])
        self.assertEqual(original, parent)

    def test_yield_requires_completed_same_action_sources_and_valid_accept_gates(self):
        for key, value in (("status", "unknown_outcome"), ("action_id", "older-action"),
                           ("route_id", "another-route"), ("plan_version", 99),
                           ("attempt_index", 99)):
            for role in ("report", "review"):
                with self.subTest(key=key, role=role):
                    parent, route, action, snapshot = continuation_case()
                    snapshot["state"]["calls"][role][key] = value
                    updates, audit = merge_route_evidence(parent, route, action, snapshot)
                    self.assertEqual({}, updates)
                    self.assertFalse(audit["accepted"])
        parent, route, action, snapshot = continuation_case()
        snapshot["state"]["calls"]["review"]["response"] = {
            "goal_gate": "PARTIAL", "logic_gate": "PASS", "verdict": "ACCEPT"}
        self.assertFalse(merge_route_evidence(parent, route, action, snapshot)[1]["accepted"])

    def test_yield_cannot_reuse_another_checkpoint_review_or_a_model_only_checkpoint(self):
        for missing in ("review", "event", "checkpoint"):
            with self.subTest(missing=missing):
                parent, route, action, snapshot = continuation_case()
                if missing == "review":
                    snapshot["state"]["calls"].pop("review")
                elif missing == "event":
                    snapshot["events"] = []
                else:
                    snapshot["state"]["calls"]["review"]["request"]["checkpoint"] = {
                        "checkpoint_id": "older-checkpoint"}
                self.assertFalse(merge_route_evidence(parent, route, action, snapshot)[1]["accepted"])
