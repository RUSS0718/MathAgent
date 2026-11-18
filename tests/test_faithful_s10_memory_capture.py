import sqlite3
import unittest

from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from showcase.solver_harness.faithful_memory_capture import capture_population_observation
from showcase.solver_harness.faithful_memory_injection import load_population_memory


class FaithfulPopulationMemoryCaptureTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript(
            """
            CREATE TABLE chat_sessions(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
            CREATE TABLE workspace_jobs(
                job_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                user_id TEXT NOT NULL, status TEXT NOT NULL
            );
            """
        )
        self.db.execute("INSERT INTO chat_sessions VALUES ('session-a','user-a')")
        self.db.execute("INSERT INTO workspace_jobs VALUES ('run-1','session-a','user-a','succeeded')")
        self.store = FaithfulMemoryStore(self.db)
        self.scope = MemoryScope("population", "session-a", "user-a", "session-a")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_explicitly_enabled_terminal_run_is_captured_once_with_cost_and_source(self):
        self.store.set_injection_enabled(self.scope, True, actor_id="user-a")
        self.db.commit()
        state = {
            "status": "completed_llm_reviewed",
            "phase": "TERMINAL",
            "state_revision": 12,
            "plan_version": 3,
            "problem_spec": {"domain": "Algebra"},
            "route_registry": [{"status": "stopped"}, {"status": "completed"}],
        }
        budget = {
            "logical_calls": 4,
            "http_attempts": 5,
            "tool_calls": 1,
            "charged_tokens": 80,
            "unknown_attempts": 0,
            "wall_time_seconds": 2.5,
        }

        self.assertTrue(capture_population_observation(
            self.db, run_id="run-1", state=state, budget=budget, reviewed=True
        ))
        self.assertFalse(capture_population_observation(
            self.db, run_id="run-1", state=state, budget=budget, reviewed=True
        ))

        loaded = load_population_memory(
            self.db, run_id="run-1", problem_spec={"domain": "algebra"}
        )
        self.assertEqual("success", loaded["observations"][0]["outcome"])
        self.assertEqual({"charged_tokens": 80, "http_attempts": 5, "logical_calls": 4,
                          "tool_calls": 1, "unknown_attempts": 0, "wall_time_seconds": 2.5},
                         loaded["observations"][0]["cost"])
        self.assertEqual("run-1", loaded["observations"][0]["provenance"]["source_run_id"])
        self.assertEqual({
            "run_status": "completed_llm_reviewed",
            "route_status_counts": {"completed": 1, "stopped": 1},
        },
                         loaded["observations"][0]["content"])

    def test_memory_is_not_captured_without_explicit_injection_consent(self):
        captured = capture_population_observation(
            self.db,
            run_id="run-1",
            state={"phase": "TERMINAL", "status": "completed_llm_reviewed",
                   "problem_spec": {"domain": "Algebra"}},
            budget={},
            reviewed=True,
        )

        self.assertFalse(captured)
        self.assertEqual([], self.store.list_observations(self.scope))

    def test_unreviewed_or_unknown_run_is_diagnostic_only(self):
        self.store.set_injection_enabled(self.scope, True, actor_id="user-a")
        self.db.commit()

        self.assertTrue(capture_population_observation(
            self.db,
            run_id="run-1",
            state={"phase": "TERMINAL", "status": "partial_budget_exhausted",
                   "problem_spec": {"domain": "Algebra"}},
            budget={"unknown_attempts": 1},
            reviewed=False,
        ))

        loaded = load_population_memory(
            self.db, run_id="run-1", problem_spec={"domain": "Algebra"}
        )
        self.assertEqual("unknown", loaded["observations"][0]["outcome"])
        self.assertEqual("diagnostic_only", loaded["observations"][0]["use"])


if __name__ == "__main__":
    unittest.main()
