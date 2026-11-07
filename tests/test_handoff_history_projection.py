"""Historical draft snapshots can reference an identical current prefix only."""

import unittest
from copy import deepcopy

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from tests.test_solver_handoff_delivery import CONFIG, DISPUTE, PLAN


class HandoffHistoryProjectionTest(unittest.TestCase):
    def test_current_drafts_cover_old_snapshots_without_erasing_dialogue(self):
        plan = {**PLAN, "steps": [*PLAN["steps"],
                {"step_id": "s3", "title": "finish", "objective": "finish", "depends_on": ["s2"]}]}
        model = ScriptedModelPort([{"argument": text} for text in ("draft1", "draft2", "draft3")]
                                  + [{"final_response": "disputed answer"}])
        verifier = ScriptedVerifierPort([DISPUTE] * 3 + [{"verdict": "REJECT"}])
        with SolverHarness(config=CONFIG, model_port=model, verifier_port=verifier) as harness:
            run = harness.solve("prove", {"plan": plan})
            current = model.requests[2]
            old = current["session_history"][1]
            self.assertNotIn("reviewed_drafts", old["request"])
            self.assertEqual({"source": "current_request.reviewed_drafts", "length": 1},
                             old["request"]["reviewed_drafts_prefix_ref"])
            self.assertEqual("draft2", old["response"]["argument"])
            self.assertEqual(2, len(current["reviewed_drafts"]))
            self.assertNotIn("reviewed_drafts", current["role_context"]["state"])
            self.assertEqual("current_request.reviewed_drafts",
                             current["role_context"]["state"]["reviewed_drafts_ref"])
            registry = run["state"]["session_registry"][current["session_key"]]
            persistent = registry["history"][1]["request"]["reviewed_drafts"]
            self.assertEqual("draft1", persistent[0]["report"]["argument"])
            self.assertNotIn("reviewed_drafts_prefix_ref", registry["history"][1]["request"])
            for mismatch in ("content", "session", "run", "mode"):
                with self.subTest(mismatch=mismatch):
                    request = deepcopy(current)
                    prior = deepcopy(registry["history"][1])
                    if mismatch == "content":
                        prior["request"]["reviewed_drafts"][0]["report"]["argument"] = "different"
                    else:
                        prior["request"][{"session": "session_key", "run": "run_id",
                                          "mode": "acceptance_mode"}[mismatch]] = "different"
                    request["session_history"] = [prior]
                    prepared = harness.prepare_request(run, request)
                    self.assertEqual(prior, prepared["session_history"][0])
