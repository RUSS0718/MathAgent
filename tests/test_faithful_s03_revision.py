"""C07 specification revision invalidation stays branch scoped."""

import unittest
from copy import deepcopy

from showcase.final_evidence import artifact_identity
from showcase.solver_harness.final_binding import review_binding
from showcase.solver_harness.specification_change import build_specification_change


class FaithfulS03RevisionTest(unittest.TestCase):
    def test_missing_result_ids_do_not_invalidate_an_unrelated_branch(self):
        problem = "Prove both directions."
        old = {
            "specification_version": 1,
            "original_problem": problem,
            "domain": "integers",
            "quantifiers": ["for all integers"],
            "assumptions": ["n is an integer"],
            "directions": ["necessary", "sufficient"],
            "output_requirements": ["prove both directions"],
            "root_obligations": [
                {"obligation_id": "root:necessary", "obligation_type": "universal",
                 "statement": "The necessary direction holds."},
                {"obligation_id": "root:sufficient", "obligation_type": "universal",
                 "statement": "The sufficient direction holds."},
            ],
            "auxiliary_goals": [],
        }
        revised = deepcopy(old)
        revised["specification_version"] = 2
        revised["root_obligations"][0]["statement"] = "The revised necessary direction holds."
        state = {
            "problem_spec": old,
            "plan": {"version": 1, "steps": [
                {"step_id": "necessary", "depends_on": []},
                {"step_id": "sufficient", "depends_on": []},
            ]},
            "work_units": [
                {"step_id": "necessary", "obligation_ids": ["root:necessary"],
                 "auxiliary_goal_ids": []},
                {"step_id": "sufficient", "obligation_ids": ["root:sufficient"],
                 "auxiliary_goal_ids": []},
            ],
            "steps": {"necessary": {"status": "ACCEPTED"},
                      "sufficient": {"status": "ACCEPTED"}},
            "accepted_results": [
                {"source": "necessary", "statement": "Affected result.", "dependencies": []},
                {"source": "sufficient", "statement": "Unrelated result.", "dependencies": []},
            ],
            "verified_results_ledger": [],
            "final_solution_attempts": [{
                "plan_version": 1, "attempt_index": 0, "candidate": "old candidate",
                "review": {"verdict": "ACCEPT"},
            }],
            "whole_solution_reviews": [{
                "artifact": artifact_identity("old candidate"),
                "verdict": "ACCEPT",
                "source": {"run_id": "revision-run", "call_id": "review-call",
                           "plan_version": 1, "attempt_index": 0,
                           "candidate_version": 1, "specification_version": 1},
            }],
            "obligation_evidence_ledger": [],
            "obligation_ledger": [],
        }

        change = build_specification_change(state, revised)

        results = change["updates"]["accepted_results"]
        self.assertTrue(results[0]["invalidated"])
        self.assertNotIn("invalidated", results[1])
        self.assertEqual(["Affected result."], [
            item["statement"]
            for item in change["updates"]["failure_records"][-1]["invalidated_results"]
        ])
        for history in ("final_solution_attempts", "whole_solution_reviews"):
            record = change["updates"][history][0]
            self.assertTrue(record["invalidated"])
            self.assertEqual(2, record["invalidated_by_specification_version"])
        invalidated_review = change["updates"]["whole_solution_reviews"][0]
        self.assertEqual({"whole_review": "invalid_source", "binding": "unbound"},
                         review_binding({
                             "run_id": "revision-run",
                             "state": {
                                 "plan_version": 1,
                                 "attempt_index": 0,
                                 "specification_version": 2,
                                 "whole_solution_reviews": [invalidated_review],
                                 "calls": {"review-call": {
                                     "status": "completed",
                                     "role": "whole_solution_verifier",
                                     "run_id": "revision-run",
                                     "response": {"verdict": "ACCEPT", "tool_request": None},
                                     "request": {"solution_candidate": "old candidate"},
                                 }},
                             },
                         }, "old candidate"))


if __name__ == "__main__":
    unittest.main()
