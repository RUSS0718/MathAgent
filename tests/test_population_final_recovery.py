"""Rejected final candidates restore only routes with unfinished work."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from showcase.solver_harness.initial_state import initial_state
from showcase.solver_harness.population_recovery import (
    evidence_fingerprint,
    review_rejected,
)
from showcase.solver_harness.population_store import initial_population
from showcase.solver_harness.storage import SolverStateStore
from showcase.storage import SQLiteStore

RUN_ID = "population-final-recovery"
OWNER = {"id": "final-recovery-owner", "epoch": 4}


def _route(route_id, phase, current_step):
    steps = ([{"step_id": current_step, "title": "Continue", "objective": "Continue"}]
             if current_step else [])
    return {
        "route_id": route_id,
        "frontier_digest": f"frontier-{route_id}",
        "revision": 2,
        "owner": OWNER,
        "status": "frozen",
        "inflight_action_id": None,
        "snapshot": {
            "phase": phase,
            "status": "running",
            "current_step": current_step,
            "plan": {"steps": steps},
            "steps": {},
        },
        "events": [],
    }


class PopulationFinalRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sqlite = SQLiteStore(str(Path(self.temp.name) / "recovery.sqlite"))
        self.addCleanup(self.sqlite.close)
        self.state_store = SolverStateStore(self.sqlite._connection)
        self.population = initial_population()
        self.population.update(
            owner=OWNER,
            epoch=OWNER["epoch"],
            freeze={"candidate": {"revision": 10}, "state_revision": 10,
                    "pending_actions": []},
            routes={
                "route-live": _route("route-live", "STEP_EXECUTE", "route-live:next"),
                "route-done": _route("route-done", "FINAL_GENERATE", None),
            },
        )
        state = initial_state(
            RUN_ID, "problem-hash", "config-hash",
            problem_spec={
                "specification_version": 1,
                "original_problem": "P",
                "domain": "real",
                "quantifiers": [],
                "assumptions": [],
                "directions": [],
                "output_requirements": [],
                "root_obligations": [{
                    "obligation_id": "root:answer",
                    "obligation_type": "result",
                    "statement": "Give the answer",
                }],
                "auxiliary_goals": [],
            },
        )
        state.update(
            phase="FINAL_GENERATE",
            state_revision=10,
            population_policy={"enabled": True, "version": "concurrent-aprs-v1"},
            population=self.population,
            final_solution_attempts=[{
                "session_key": "final:population-final-recovery:candidate0",
                "candidate": "Rejected candidate",
                "review": {"verdict": "REJECT", "reason": "Missing a required case."},
                "plan_version": 1,
                "attempt_index": 0,
                "accepted_results": [],
            }],
            verified_results_ledger=[],
            obligation_evidence_ledger=[],
            obligation_ledger=[],
        )
        self.state_store.create_run(state, {
            "event_id": "initialized",
            "run_id": RUN_ID,
            "type": "run_initialized",
            "state_revision": 10,
            "created_at": state["created_at"],
        })
        self.harness = SimpleNamespace(
            _state_store=self.state_store,
            _population_owner=OWNER,
            _event_observer=None,
        )
        self.run = self.state_store.get_run(RUN_ID)

    def test_rejected_candidate_restores_only_route_with_pending_work(self):
        recovered = review_rejected(self.harness, self.run)
        population = recovered["state"]["population"]

        self.assertEqual("POPULATION", recovered["state"]["phase"])
        self.assertIsNone(population["freeze"])
        self.assertEqual("eligible", population["routes"]["route-live"]["status"])
        self.assertEqual("STEP_EXECUTE", population["routes"]["route-live"]["snapshot"]["phase"])
        self.assertEqual("finished", population["routes"]["route-done"]["status"])
        self.assertEqual("final:population-final-recovery:candidate0",
                         population["rejected_evidence"]["candidate_key"])
        self.assertEqual(evidence_fingerprint(self.run["state"]),
                         population["rejected_evidence"]["evidence_hash"])

    def test_no_legal_route_keeps_freeze_for_bounded_final_generation_retry(self):
        state = self.run["state"]
        state["population"]["routes"]["route-live"]["snapshot"].update(
            phase="FINAL_GENERATE", current_step=None, plan={"steps": []},
        )
        self.state_store._connection.execute(
            "UPDATE solver_states SET state_json=? WHERE run_id=?",
            (json.dumps(state), RUN_ID),
        )
        self.state_store._connection.commit()
        current = self.state_store.get_run(RUN_ID)

        retried = review_rejected(self.harness, current)

        self.assertEqual(current["state_revision"], retried["state_revision"])
        self.assertEqual("FINAL_GENERATE", retried["state"]["phase"])
        self.assertIsNotNone(retried["state"]["population"]["freeze"])


if __name__ == "__main__":
    unittest.main()
