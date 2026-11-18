import unittest
from copy import deepcopy

from showcase.solver_harness.context_injection import prepare_role_context
from showcase.solver_harness.faithful_memory_injection import has_population_memory


class FaithfulPopulationMemoryContextTest(unittest.TestCase):
    def test_memory_prompt_marker_survives_both_current_and_recovery_context_shapes(self):
        memory = {"authority": "advisory_only"}
        for request in (
            {"population_memory_advisory": memory},
            {"role_context": {"state": {"population_memory_advisory": memory}}},
            {"prompt_layers": [{"state": {"population_memory_advisory": memory}}]},
        ):
            with self.subTest(request=request):
                self.assertTrue(has_population_memory(request))
        self.assertFalse(has_population_memory({"role_context": {"state": {}}}))

    def test_advisory_observations_reach_roles_without_becoming_evidence(self):
        memory = {
            "schema": "population-memory-injection-v1",
            "authority": "advisory_only",
            "review_status": "requires_current_run_review",
            "observations": [{"record_id": "memory-1", "use": "diagnostic_only"}],
        }
        run = {
            "run_id": "run-current",
            "state_revision": 4,
            "state": {
                "phase": "PLAN",
                "plan_version": 1,
                "accepted_results": [{"result_id": "proof-1"}],
                "population_memory_advisory": memory,
            },
        }

        context = prepare_role_context(run, {"role": "reasoner"})["state"]

        self.assertEqual(memory, context["population_memory_advisory"])
        self.assertEqual([{"result_id": "proof-1"}], context["accepted_results"])
        self.assertNotIn("memory-1", str(context["accepted_results"]))

    def test_final_review_receives_advisory_memory_for_current_run_recheck(self):
        memory = {
            "schema": "population-memory-injection-v1",
            "authority": "advisory_only",
            "review_status": "requires_current_run_review",
            "observations": [{"record_id": "memory-1", "use": "candidate_guidance"}],
        }
        run = {
            "run_id": "run-current",
            "state_revision": 8,
            "state": {"population_memory_advisory": deepcopy(memory)},
        }

        context = prepare_role_context(
            run,
            {
                "role": "verifier",
                "finalization_scope": True,
                "accepted_results": [],
                "step_proofs": [],
            },
        )

        self.assertEqual(memory, context["state"]["population_memory_advisory"])


if __name__ == "__main__":
    unittest.main()
