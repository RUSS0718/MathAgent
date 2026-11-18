"""Delivery remains independent of unknown request accounting."""

import json
import sqlite3
import unittest

from showcase.solver_harness.population_delivery import delivery_allowed


class PopulationDeliveryTests(unittest.TestCase):
    def test_whole_review_accept_does_not_discharge_known_graph_conflict(self):
        from showcase.solver_harness.proof_graph import initial_proof_graph, proposition_id

        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute("CREATE TABLE run_budgets(run_id TEXT,ledger_json TEXT)")
        connection.execute("INSERT INTO run_budgets VALUES(?,?)",
                           ("run", json.dumps({"limits": {}, "actions": []})))
        graph = initial_proof_graph()
        graph["snapshots"][0]["propositions"]["known"] = {
            "status": "supported", "conflict": True,
        }
        state = {"run_id": "run", "proof_graph": graph,
                 "whole_solution_reviews": [{"verdict": "ACCEPT"}]}
        self.assertEqual((False, "population_unresolved_proof_conflict"),
                         delivery_allowed(connection, state))
        graph["current_version"] = 1
        graph["snapshots"].append({"graph_version": 1, "propositions": {
            "known": {"status": "supported", "conflict": False},
        }})
        self.assertEqual((True, None), delivery_allowed(connection, state))
        state.update(problem_hash="problem", specification_version=1,
                     steps={"step": {"report": {"claims": [{"statement": "Claim"}]}}},
                     obligation_evidence_ledger=[{"source": "step", "claim_indexes": [0],
                                                 "valid": True}])
        state["verified_results_ledger"] = [{
            "source": "step", "statement": "Claim", "scope": "step-specific domain",
            "claim_indexes": [0],
        }]
        graph["snapshots"][-1]["propositions"][proposition_id(state, "Claim", "problem")] = {
            "status": "refuted", "conflict": False,
        }
        self.assertEqual((True, None), delivery_allowed(connection, state))
        prop_id = proposition_id(state, "Claim", "step-specific domain")
        graph["snapshots"][-1]["propositions"][prop_id] = {
            "status": "refuted", "conflict": False,
        }
        self.assertEqual((False, "population_unresolved_proof_conflict"),
                         delivery_allowed(connection, state))

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
