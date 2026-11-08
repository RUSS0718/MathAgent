"""F1/S07 public persistence fences and bootstrap provenance."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.run_control import RunStopped
from showcase.solver_harness import SolverHarness, SolverValidationError


class FaithfulS07BoundaryTest(unittest.TestCase):
    @staticmethod
    def _ledger_patch(run):
        """Build one accepted source and two source rows that must stay out."""
        steps, calls, rows, plan_steps = {}, {}, [], []
        entries = [
            ("accepted", "Accepted lemma", "scope-accepted", 0, True),
            ("invalid", "Withdrawn lemma", "scope-invalid", 0, False),
            ("future", "Future lemma", "scope-future", 1, True),
        ]
        for index, (result_id, statement, scope, version, valid) in enumerate(entries, 1):
            step_id = f"bootstrap-step-{index}"
            report_id, review_id = f"bootstrap-report-{index}", f"bootstrap-review-{index}"
            report = {"claims": [{"statement": statement}]}
            steps[step_id] = {
                "report": report,
                "verification": {"valid": True, "verdict": "ACCEPT"},
            }
            calls[report_id] = {
                "call_id": report_id, "run_id": run["run_id"],
                "problem_hash": run["state"]["problem_hash"],
                "config_hash": run["state"]["config_hash"], "role": "reasoner",
                "status": "completed", "plan_version": 1, "attempt_index": 0,
                "request_revision": index * 2 - 1,
                "request": {"step": {"step_id": step_id}}, "response": report,
            }
            calls[review_id] = {
                "call_id": review_id, "run_id": run["run_id"],
                "problem_hash": run["state"]["problem_hash"],
                "config_hash": run["state"]["config_hash"], "role": "step_verifier",
                "status": "completed", "plan_version": 1, "attempt_index": 0,
                "request_revision": index * 2,
                "request": {"step": {"step_id": step_id}},
                "response": {
                    "verdict": "ACCEPT",
                    "classified_outcomes": [{
                        "category": "Lemma", "statement": statement, "scope": scope,
                    }],
                },
            }
            rows.append({
                "result_id": result_id, "category": "Lemma", "statement": statement,
                "scope": scope, "valid": valid, "proven": True,
                "evidence_level": "llm_reviewed", "source": step_id,
                "plan_version": 1, "attempt_index": 0, "review_call_id": review_id,
                "claim_indexes": [0], "receipt_ids": [], "dependencies": [],
                "specification_version": version,
            })
            plan_steps.append({"step_id": step_id, "objective": scope})
        return {
            "plan": {"version": 1, "steps": plan_steps},
            "steps": steps, "calls": calls, "verified_results_ledger": rows,
        }

    def test_public_patch_rejects_valid_forged_graph_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with SolverHarness(
                database_path=str(Path(directory) / "graph.sqlite"),
                config={"features": {"proof_graph": True}},
            ) as harness:
                run = harness.solve("private problem", {"run_id": "invalid-version"})
                before = harness.get_run(run["run_id"])
                forged_graph = copy.deepcopy(before["state"]["proof_graph"])
                forged_graph["current_version"] += 1
                forged_snapshot = copy.deepcopy(forged_graph["snapshots"][-1])
                forged_snapshot["graph_version"] = forged_graph["current_version"]
                forged_snapshot["propositions"]["prop_forged"] = {
                    "id": "prop_forged", "statement": "unsupported claim",
                    "scope": "forged", "problem_version": 0,
                    "status": "supported", "conflict": False,
                    "sources": ["report:untrusted"],
                }
                forged_snapshot["attempts"]["attempt_forged"] = {
                    "id": "attempt_forged", "status": "accepted",
                    "direction": "support", "grade": "llm_reviewed",
                    "conclusion": "prop_forged", "premises": [],
                    "source_refs": ["report:untrusted"],
                    "result_id": "forged-result", "lineage": None,
                }
                forged_snapshot["derivations"]["derivation_forged"] = {
                    "id": "derivation_forged", "status": "accepted",
                    "grade": "llm_reviewed", "conclusion": "prop_forged",
                    "premises": [], "attempt_id": "attempt_forged",
                    "source_refs": ["report:untrusted"],
                    "result_id": "forged-result",
                }
                forged_snapshot["sources"]["report:untrusted"] = {
                    "kind": "report", "grade": "llm_reviewed",
                }
                forged_graph["snapshots"].append(forged_snapshot)
                with self.assertRaises(SolverValidationError):
                    harness.commit_event(
                        run["run_id"], expected_revision=run["state_revision"],
                        event={"event_id": "forged-graph-history", "type": "test_graph"},
                        state_updates={"proof_graph": forged_graph},
                    )
                after = harness.get_run(run["run_id"])
                self.assertEqual(before["state_revision"], after["state_revision"])
                self.assertEqual(before["events"], after["events"])
                self.assertEqual(before["state"]["proof_graph"], after["state"]["proof_graph"])

    def test_legacy_run_cannot_be_hot_enabled_by_general_patch(self):
        with SolverHarness() as harness:
            run = harness.solve("legacy problem", {"run_id": "legacy-hot-enable"})
            before = harness.get_run(run["run_id"])
            with self.assertRaises(SolverValidationError):
                harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "legacy-hot-enable", "type": "test_graph"},
                    state_updates={
                        "proof_graph_policy": {
                            "enabled": True, "version": "proof-graph-v1",
                            "schema_version": "proof-graph-v1",
                        },
                        "proof_graph": {
                            "current_version": 0,
                            "snapshots": [{
                                "graph_version": 0, "propositions": {},
                                "derivations": {}, "attempts": {}, "sources": {},
                                "not_imported_records": [], "bootstrap_complete": False,
                                "conflict_resolutions": {},
                            }],
                        },
                    },
                )
            after = harness.get_run(run["run_id"])
            self.assertEqual(before["state_revision"], after["state_revision"])
            self.assertEqual(before["events"], after["events"])
            self.assertNotIn("proof_graph_policy", after["state"])
            self.assertNotIn("proof_graph", after["state"])

    def test_cancel_and_deadline_fences_rollback_graph_derivation(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve("private problem", {"run_id": "graph-fences"})
            connection = harness._showcase_store._connection
            connection.executescript(
                """
                CREATE TABLE workspace_jobs (
                    job_id TEXT PRIMARY KEY, status TEXT NOT NULL, result_json TEXT
                );
                CREATE TABLE run_budgets (
                    run_id TEXT PRIMARY KEY, ledger_json TEXT NOT NULL
                );
                """
            )
            connection.execute(
                "INSERT INTO workspace_jobs VALUES (?, ?, ?)",
                (run["run_id"], "canceled", "{}"),
            )
            connection.execute(
                "INSERT INTO run_budgets VALUES (?, ?)",
                (run["run_id"], '{"deadline_at": 9999999999}'),
            )
            connection.commit()
            with self.assertRaises(RunStopped) as canceled:
                harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "canceled-graph-write", "type": "test_graph"},
                    state_updates={"verified_results_ledger": []},
                )
            self.assertEqual("run_stopped", canceled.exception.category)

            connection.execute(
                "UPDATE workspace_jobs SET status='running' WHERE job_id=?", (run["run_id"],)
            )
            connection.execute(
                "UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
                ('{"deadline_at": 100.5}', run["run_id"]),
            )
            connection.commit()
            with patch("showcase.solver_harness.product_control.time.time",
                       side_effect=[100.0, 101.0]):
                with self.assertRaises(RunStopped) as deadline:
                    harness.commit_event(
                        run["run_id"], expected_revision=run["state_revision"],
                        event={"event_id": "deadline-graph-write", "type": "test_graph"},
                        state_updates={"verified_results_ledger": []},
                    )
            self.assertEqual("run_deadline_exhausted", deadline.exception.category)
            after = harness.get_run(run["run_id"])
            self.assertEqual(run["state_revision"], after["state_revision"])
            self.assertEqual(run["events"], after["events"])

    def test_bootstrap_persists_imported_source_and_rejection_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "bootstrap.sqlite")
            config = {"features": {"proof_graph": True}}
            with SolverHarness(database_path=database, config=config) as harness:
                run = harness.solve("private problem", {"run_id": "bootstrap-sources"})
                run = harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "bootstrap-ledger", "type": "test_ledger"},
                    state_updates=self._ledger_patch(run),
                )
                snapshot = run["state"]["proof_graph"]["snapshots"][-1]
                self.assertEqual(1, len(snapshot["derivations"]))
                imported = next(iter(snapshot["derivations"].values()))
                self.assertEqual("accepted", imported["status"])
                self.assertEqual("llm_reviewed", imported["grade"])
                self.assertEqual("accepted", imported["result_id"])
                reasons = {
                    (item["source_id"], item["reason"])
                    for item in snapshot["not_imported_records"]
                }
                self.assertIn(("invalid", "source_invalidated"), reasons)
                self.assertIn(("future", "cross_version_source"), reasons)
                bootstrap = next(
                    event for event in run["events"] if event["type"] == "proof_graph_bootstrapped"
                )
                self.assertEqual(0, bootstrap["imported_count"])
                self.assertEqual(0, bootstrap["not_imported_count"])
                ledger_event = next(
                    event for event in run["events"] if event["event_id"] == "bootstrap-ledger"
                )
                self.assertEqual(1, ledger_event["proof_graph"]["derivation_count"])
                self.assertEqual(2, ledger_event["proof_graph"]["not_imported_count"])
                self.assertEqual(2, snapshot["graph_version"])
                expected_snapshot = copy.deepcopy(snapshot)

            with SolverHarness(database_path=database, config=config) as restarted:
                recovered = restarted.get_run("bootstrap-sources")
                recovered_snapshot = recovered["state"]["proof_graph"]["snapshots"][-1]
                self.assertEqual(expected_snapshot, recovered_snapshot)
                self.assertEqual(reasons, {
                    (item["source_id"], item["reason"])
                    for item in recovered_snapshot["not_imported_records"]
                })


if __name__ == "__main__":
    unittest.main()
