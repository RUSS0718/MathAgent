"""Known invalid Meta decisions terminate their owning stage without redispatch."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, SolverHarness


class MetaDecisionTerminalTest(unittest.TestCase):
    def test_invalid_continue_target_stops_and_stays_terminal_after_reopen(self):
        invalid = {
            "decision": "CONTINUE",
            "reason_summary": "continue the current route",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": 1,
        }
        port = ScriptedModelPort([invalid, invalid])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "solver.sqlite3"
            with SolverHarness(database_path=database, meta_port=port) as harness:
                run = harness.solve("Prove the claim", {"run_id": "invalid-meta"})
                harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "decision-stage", "type": "test_decision_stage"},
                    state_updates={
                        "phase": "META_DECIDE", "plan_version": 1,
                        "plan": {"version": 1, "steps": [{
                            "step_id": "s1", "title": "derive", "objective": "claim",
                        }]}, "current_step": "s1",
                    },
                )
                result = harness.solve("Prove the claim", {"run_id": "invalid-meta"})
                self.assertEqual("TERMINAL", result["state"]["phase"])
                self.assertEqual("partial_aborted", result["state"]["status"])
                self.assertEqual("invalid_meta_decision", result["state"]["result_reason"])
                self.assertEqual("meta_invalid", result["events"][-1]["type"])
                self.assertEqual(1, len(port.requests))
            with SolverHarness(database_path=database, meta_port=port) as harness:
                restored = harness.solve("Prove the claim", {"run_id": "invalid-meta"})
                self.assertEqual("TERMINAL", restored["state"]["phase"])
                self.assertEqual(1, len(port.requests))


if __name__ == "__main__":
    unittest.main()
