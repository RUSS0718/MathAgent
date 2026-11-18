import copy
import json
import sqlite3
import unittest

from showcase.solver_harness.population_pressure import pressure_reason

OWNER = {"id": "owner-current", "epoch": 7}


class PopulationPressureTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE TABLE run_budgets (run_id TEXT PRIMARY KEY, ledger_json TEXT NOT NULL)"
        )
        self.state = {
            "run_id": "run-pressure",
            "population": {
                "owner": dict(OWNER),
                "actions": {
                    "action-current": {
                        "action_id": "action-current",
                        "owner": dict(OWNER),
                        "epoch": OWNER["epoch"],
                        "status": "failed",
                    }
                },
            },
        }

    def tearDown(self):
        self.connection.close()

    def set_ledger_actions(self, actions):
        ledger = {"actions": actions}
        self.connection.execute(
            "INSERT OR REPLACE INTO run_budgets(run_id, ledger_json) VALUES (?, ?)",
            (self.state["run_id"], json.dumps(ledger)),
        )

    def stored_ledger(self):
        return self.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (self.state["run_id"],)
        ).fetchone()[0]

    def test_current_owner_epoch_http_429_returns_pause_reason(self):
        self.set_ledger_actions([
            {"kind": "http", "population_action_id": "action-current", "public_attempt": None},
            {"kind": "http", "population_action_id": "action-current",
             "public_attempt": {"http_status": 429}},
        ])

        self.assertEqual(
            "provider_rate_limited_current_epoch",
            pressure_reason(self.connection, self.state),
        )

    def test_previous_epoch_429_does_not_block_new_owner_or_release_unknown_hold(self):
        old_owner = {"id": "owner-old", "epoch": 6}
        unknown = {
            "action_id": "action-old",
            "owner": dict(old_owner),
            "epoch": old_owner["epoch"],
            "status": "unknown",
            "settlement_status": "pending",
            "reservation": {"http_attempts": 1},
        }
        self.state["population"]["actions"] = {"action-old": unknown}
        self.set_ledger_actions([{
            "kind": "http",
            "population_action_id": "action-old",
            "public_attempt": {"http_status": 429},
        }])
        before_state = copy.deepcopy(self.state)
        before_ledger = self.stored_ledger()

        self.assertIsNone(pressure_reason(self.connection, self.state))
        self.assertEqual(before_state, self.state)
        self.assertEqual(before_ledger, self.stored_ledger())
        self.assertEqual("unknown", self.state["population"]["actions"]["action-old"]["status"])
        self.assertEqual(
            "pending", self.state["population"]["actions"]["action-old"]["settlement_status"]
        )

    def test_current_epoch_unknown_429_pauses_without_changing_unknown_or_reservation(self):
        action = self.state["population"]["actions"]["action-current"]
        action.update(status="unknown", settlement_status="pending",
                      reservation={"http_attempts": 1})
        self.set_ledger_actions([{
            "kind": "http",
            "population_action_id": "action-current",
            "public_attempt": {"http_status": 429},
        }])
        before_state = copy.deepcopy(self.state)
        before_ledger = self.stored_ledger()

        self.assertEqual(
            "provider_rate_limited_current_epoch",
            pressure_reason(self.connection, self.state),
        )
        self.assertEqual(before_state, self.state)
        self.assertEqual(before_ledger, self.stored_ledger())

    def test_non_429_or_unlinked_attempts_do_not_signal_population_pressure(self):
        self.set_ledger_actions([
            {"kind": "logical", "population_action_id": "action-current",
             "public_attempt": {"http_status": 429}},
            {"kind": "http", "population_action_id": "action-current",
             "public_attempt": {"http_status": 503}},
            {"kind": "http", "population_action_id": "missing-action",
             "public_attempt": {"http_status": 429}},
        ])

        self.assertIsNone(pressure_reason(self.connection, self.state))


if __name__ == "__main__":
    unittest.main()
