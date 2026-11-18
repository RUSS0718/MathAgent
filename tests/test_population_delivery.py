"""Delivery remains independent of unknown request accounting."""

import json
import sqlite3
import unittest

from showcase.solver_harness.population_delivery import delivery_allowed


class PopulationDeliveryTests(unittest.TestCase):
    def test_independent_answer_keeps_unrelated_unknown_but_rejects_missing_hold(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE run_budgets(run_id TEXT,ledger_json TEXT)")
        state = {
            "run_id": "run",
            "population": {"actions": {"pending": {"action_id": "pending", "status": "unknown"}}},
        }
        connection.execute(
            "INSERT INTO run_budgets VALUES(?,?)",
            (
                "run",
                json.dumps(
                    {"limits": {}, "actions": [{"kind": "http", "population_action_id": "pending"}]}
                ),
            ),
        )
        self.assertEqual((True, None), delivery_allowed(connection, state))
        connection.execute(
            "UPDATE run_budgets SET ledger_json=?",
            (
                json.dumps(
                    {"limits": {}, "actions": [{"kind": "logical", "solver_call_id": "unknown"}, {"kind": "http", "solver_call_id": "unknown", "status": "success"}]}
                ),
            ),
        )
        self.assertEqual(
            (False, "population_ledger_incomplete"), delivery_allowed(connection, state)
        )

    def test_incomplete_public_attempt_identity_blocks_delivery(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE run_budgets(run_id TEXT,ledger_json TEXT)")
        connection.execute("CREATE TABLE workspace_events(job_id TEXT,event_type TEXT,payload_json TEXT)")
        connection.execute("INSERT INTO run_budgets VALUES(?,?)", ("run", json.dumps({"limits": {}, "actions": []})))
        connection.execute("INSERT INTO workspace_events VALUES(?,?,?)", ("run", "request_attempt", json.dumps({"attempt": {}})))
        self.assertEqual((False, "population_ledger_incomplete"), delivery_allowed(connection, {"run_id": "run"}))

    def test_unknown_proof_source_rejects_delivery(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE run_budgets(run_id TEXT,ledger_json TEXT)")
        connection.execute(
            "INSERT INTO run_budgets VALUES(?,?)",
            (
                "run",
                json.dumps(
                    {"limits": {}, "actions": [{"kind": "logical", "solver_call_id": "unknown"}, {"kind": "http", "solver_call_id": "unknown", "status": "success"}]}
                ),
            ),
        )
        state = {
            "run_id": "run",
            "verified_results_ledger": [{"review_call_id": "unknown"}],
            "calls": {"unknown": {"call_id": "unknown", "status": "unknown_outcome"}},
        }
        self.assertEqual(
            (False, "population_unknown_proof_dependency"), delivery_allowed(connection, state)
        )
