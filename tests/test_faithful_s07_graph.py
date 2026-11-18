"""F1/S07 proof graph persistence, provenance, invalidation, and projection contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import SolverHarness
from showcase.solver_harness.proof_graph import proposition_id
from showcase.solver_harness.proof_graph_projection import proof_graph_summary
from showcase.solver_harness.proof_graph_sources import counterexample_attempts, dependency_closure
from showcase.solver_harness.proof_graph_state import active_supports
from showcase.solver_harness.storage import SolverPersistenceError, SolverRevisionConflictError


class FaithfulS07GraphTest(unittest.TestCase):
    def test_existing_result_cannot_rewrite_its_dependencies(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve('problem')
            run = self._commit(harness, run, 'seed-existing', self._ledger_patch(run, [('a', 'A', 'scope', [])]))
            before = harness.get_run(run['run_id'])
            for dependencies in (['missing'], ['a']):
                with self.subTest(dependencies=dependencies), self.assertRaises(SolverPersistenceError):
                    self._commit(harness, run, 'rewrite-existing', self._ledger_patch(run, [('a', 'A', 'scope', dependencies)]))
                self.assertEqual(before, harness.get_run(run['run_id']))

    def test_new_cyclic_and_dangling_dependencies_roll_back_whole_transaction(self):
        for entries in ([('a', 'A', 'scope', ['missing'])],
                        [('a', 'A', 'scope', ['b']), ('b', 'B', 'scope', ['a'])]):
            with self.subTest(entries=entries), SolverHarness(config={"features": {"proof_graph": True}}) as harness:
                run = harness.solve('problem')
                run = self._commit(harness, run, 'finish-bootstrap', {})
                before = harness.get_run(run['run_id'])
                with self.assertRaises(SolverPersistenceError):
                    self._commit(harness, run, 'invalid-graph', self._ledger_patch(run, entries))
                self.assertEqual(before, harness.get_run(run['run_id']))

    def test_bootstrap_rejects_grade_upgrade_and_unbound_claim_indexes(self):
        from showcase.solver_harness.proof_graph_sources import importable_ledger_rows

        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve('problem')
            patch = self._ledger_patch(run, [('a', 'A', 'scope', [])])
            state = {**run['state'], **patch}
            row = patch['verified_results_ledger'][0]
            row['evidence_level'] = 'tool_verified'
            imported, rejected = importable_ledger_rows(state, [row])
            self.assertEqual([], imported)
            self.assertEqual('unsupported_evidence_upgrade', rejected[0]['reason'])
            row['evidence_level'] = 'llm_reviewed'
            patch['calls']['review-1']['response']['classified_outcomes'][0]['claim_indexes'] = []
            imported, rejected = importable_ledger_rows(state, [row])
            self.assertEqual([], imported)
            self.assertEqual('review_did_not_accept_record', rejected[0]['reason'])

    @staticmethod
    def _ledger_patch(run, entries):
        """Build reviewed source rows for an end-to-end persisted Harness event."""
        steps, calls, rows, plan_steps = {}, {}, [], []
        for index, (result_id, statement, scope, dependencies) in enumerate(entries, 1):
            step_id = f"ledger-step-{index}"
            report_id, review_id = f"report-{index}", f"review-{index}"
            report = {"claims": [{"statement": statement}]}
            classified = {"category": "Lemma", "statement": statement, "scope": scope,
                          "claim_indexes": [0], "dependencies": dependencies}
            steps[step_id] = {
                "report": report,
                "verification": {"valid": True, "verdict": "ACCEPT"},
            }
            plan_steps.append({"step_id": step_id, "objective": scope})
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
                "response": {"verdict": "ACCEPT", "classified_outcomes": [classified]},
            }
            rows.append({
                "result_id": result_id, "category": "Lemma", "statement": statement,
                "scope": scope, "valid": True, "proven": True,
                "evidence_level": "llm_reviewed", "source": step_id,
                "plan_version": 1, "attempt_index": 0, "review_call_id": review_id,
                "claim_indexes": [0], "receipt_ids": [], "dependencies": dependencies,
            })
        return {
            "plan": {"version": 1, "steps": plan_steps},
            "steps": steps,
            "calls": calls,
            "verified_results_ledger": rows,
        }

    @staticmethod
    def _commit(harness, run, event_id, patch):
        return harness.commit_event(
            run["run_id"], expected_revision=run["state_revision"],
            event={"event_id": event_id, "type": "test_ledger_committed"},
            state_updates=patch,
        )

    @staticmethod
    def _counterexample_patch(run, claim):
        """Create a persisted researcher candidate tied to its Verifier review."""
        from showcase.solver_harness.counterexample import target

        step_id, verifier_id, researcher_id = "ce-step", "ce-review", "ce-research"
        report = {"claims": [{"statement": claim}]}
        declaration = {
            "claim_index": 0, "both_directions_proved": False,
            "assumptions": ["x is real"], "approach": "Check x=0 independently",
        }
        bound_target = target(report, declaration)
        result = {
            "verdict": "FOUND_COUNTEREXAMPLE", "counterexample": "1",
            "assumptions_checked": ["x is real"],
            "violated_conclusion": "x=1 is not a root of polynomial coefficients 1,0",
            "searched_scope": "the declared witness",
        }
        return {
            "steps": {step_id: {
                "report": report,
                "counterexample_checks": {verifier_id: {
                    "verifier_call_id": verifier_id, "call_id": researcher_id,
                    "target": bound_target, "status": "completed", "result": result,
                }},
            }},
            "calls": {
                verifier_id: {
                    "call_id": verifier_id, "run_id": run["run_id"],
                    "problem_hash": run["state"]["problem_hash"],
                    "config_hash": run["state"]["config_hash"],
                    "role": "step_verifier", "status": "completed",
                    "request": {"step": {"step_id": step_id}},
                    "response": {"answer_claim": declaration},
                },
                researcher_id: {
                    "call_id": researcher_id, "run_id": run["run_id"],
                    "problem_hash": run["state"]["problem_hash"],
                    "config_hash": run["state"]["config_hash"],
                    "role": "researcher", "status": "completed",
                    "request": {"action": "counterexample_check", "claim": claim},
                    "response": result,
                },
            },
        }

    def test_default_run_keeps_legacy_shape_and_graph_off(self):
        with SolverHarness() as harness:
            run = harness.solve("private problem", {"run_id": "legacy-proof-graph"})

        self.assertIsNone(proof_graph_summary(run["state"]))
        self.assertNotIn("proof_graph", run["state"])
        self.assertFalse(any("proof_graph" in event["type"] for event in run["events"]))

    def test_opt_in_run_freezes_policy_and_records_bootstrap(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve("private problem", {"run_id": "proof-graph-opt-in"})

        self.assertEqual({"enabled": True, "version": "proof-graph-v1",
                          "schema_version": "proof-graph-v1"},
                         run["state"]["proof_graph_policy"])
        summary = proof_graph_summary(run["state"])
        self.assertEqual(1, summary["graph_version"])
        self.assertEqual([], summary["propositions"])
        self.assertTrue(any(event["type"] == "proof_graph_bootstrapped"
                            for event in run["events"]))

    def test_public_projection_is_allowlisted_and_never_contains_proof_text_or_source_ids(self):
        state = {"proof_graph": {
            "current_version": 2,
            "snapshots": [{"graph_version": 2,
                           "propositions": {"prop-secret": {
                               "status": "supported", "conflict": False,
                               "statement": "PRIVATE PROOF BODY", "scope": "secret scope",
                               "supporting_attempts": ["attempt-secret"],
                           }},
                           "derivations": {"deriv-secret": {
                               "status": "accepted", "conclusion": "prop-secret",
                               "premises": [], "grade": "llm_reviewed",
                               "source_refs": ["call-id-secret"],
                           }},
                           "attempts": {"attempt-secret": {
                               "status": "accepted", "direction": "support",
                               "grade": "llm_reviewed", "conclusion": "prop-secret",
                               "premises": [], "source_refs": ["call-id-secret"],
                           }},
                           "sources": {"call-id-secret": {
                               "call_id": "call-id-secret", "prompt": "SECRET PROMPT",
                           }}}],
        }}

        summary = proof_graph_summary(state)
        encoded = repr(summary)
        self.assertEqual({"graph_version", "propositions", "attempts"}, set(summary))
        self.assertIn("p1", summary["propositions"][0]["id"])
        self.assertEqual(["source-1"], summary["attempts"][0]["sources"])
        for secret in ("PRIVATE PROOF BODY", "secret scope", "prop-secret",
                       "attempt-secret", "call-id-secret", "SECRET PROMPT"):
            self.assertNotIn(secret, encoded)

    def test_counterexample_attempt_requires_consumed_recorded_research_call(self):
        from showcase.solver_harness.counterexample import target

        report = {"claims": [{"statement": "The minimum is zero."}]}
        declaration = {"claim_index": 0, "both_directions_proved": False,
                       "assumptions": ["x is real"], "approach": "test one point"}
        verified_target = target(report, declaration)
        found = {"verdict": "FOUND_COUNTEREXAMPLE", "counterexample": "x=-1",
                 "assumptions_checked": ["x is real"], "violated_conclusion": "-1 < 0",
                 "searched_scope": "one valid input"}
        state = {
            "run_id": "run-1", "problem_hash": "problem-hash", "config_hash": "config-hash",
            "steps": {"s1": {"report": report, "counterexample_checks": {
                "review-1": {"verifier_call_id": "review-1", "call_id": "research-1",
                             "target": verified_target, "status": "completed",
                             "result": found, "evidence_category": "Counterexample"},
            }}},
            "calls": {
                "review-1": {"run_id": "run-1", "problem_hash": "problem-hash",
                             "config_hash": "config-hash", "role": "step_verifier",
                             "status": "completed", "request_revision": 2,
                             "request": {"report": report, "step": {"step_id": "s1"}},
                             "response": {"answer_claim": declaration}},
                "research-1": {"run_id": "run-1", "problem_hash": "problem-hash",
                               "config_hash": "config-hash", "role": "researcher",
                               "status": "completed", "request": {
                                   "action": "counterexample_check",
                                   "claim": verified_target["claim"],
                               }, "response": found},
            },
        }

        attempts = counterexample_attempts(state, proposition_id)

        self.assertEqual(1, len(attempts))
        self.assertEqual("proposed", attempts[0]["status"])
        self.assertEqual("counterexample", attempts[0]["direction"])
        self.assertTrue(attempts[0]["conclusion"].startswith("prop_"))

    def test_unconsumed_counterexample_response_never_refutes(self):
        state = {"run_id": "run-1", "steps": {"s1": {"counterexample_checks": {
            "review-1": {"verifier_call_id": "review-1", "call_id": "research-1",
                         "target": {"claim": "A", "assumptions": []},
                         "status": "requested", "result": None},
        }}}, "calls": {}}
        self.assertEqual([], counterexample_attempts(state, proposition_id))

    def test_dependency_closure_drops_descendants_of_unimportable_sources(self):
        parent = {"result_id": "parent", "dependencies": []}
        child = {"result_id": "child", "dependencies": ["parent"]}
        imported, rejected = dependency_closure(
            [(child, {}), (parent, {})], rejected_ids={"parent"},
        )
        self.assertEqual([], imported)
        self.assertEqual({"child": "unmapped_dependency"},
                         {row["source_id"]: row["reason"] for row in rejected})

    def test_dependency_closure_imports_reverse_order_and_and_premises(self):
        rows = [({"result_id": "c", "dependencies": ["a", "b"]}, {}),
                ({"result_id": "b", "dependencies": []}, {}),
                ({"result_id": "a", "dependencies": []}, {})]
        imported, rejected = dependency_closure(rows)
        self.assertEqual([], rejected)
        self.assertEqual(["b", "a", "c"], [row["result_id"] for row, _ in imported])

    def test_support_fixed_point_is_independent_of_derivation_order_and_blocks_conflict(self):
        props = {
            "a": {"status": "supported", "conflict": False},
            "b": {"status": "supported", "conflict": False},
            "c": {"status": "unresolved", "conflict": False},
            "d": {"status": "unresolved", "conflict": False},
        }
        attempts = {key: {"status": "accepted", "direction": "support"}
                    for key in ("a", "b", "c", "d")}
        derivations = {
            "c": {"status": "accepted", "attempt_id": "c", "conclusion": "c",
                  "premises": ["a", "b"]},
            "b": {"status": "accepted", "attempt_id": "b", "conclusion": "b", "premises": []},
            "a": {"status": "accepted", "attempt_id": "a", "conclusion": "a", "premises": []},
            "d": {"status": "accepted", "attempt_id": "d", "conclusion": "d", "premises": ["c"]},
        }
        active = active_supports(props, attempts, derivations)
        self.assertEqual({"a", "b", "c", "d"}, active)

        props["c"]["conflict"] = True
        active = active_supports(props, attempts, derivations)
        self.assertEqual({"a", "b"}, active)
        self.assertNotIn("d", active)

    def test_sqlite_or_support_withdrawal_restart_snapshot_and_cas(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "proof-graph.sqlite")
            config = {"features": {"proof_graph": True}}
            with SolverHarness(database_path=database, config=config) as harness:
                run = harness.solve("private problem", {"run_id": "graph-or-restart"})
                entries = [
                    ("C", "Claim C", "scope-C", ["A", "D"]),
                    ("B", "Claim P", "scope-P", []),
                    ("A", "Claim P", "scope-P", []),
                    ("D", "Claim D", "scope-D", []),
                ]
                run = self._commit(harness, run, "ledger-a-b-c", self._ledger_patch(run, entries))
                original = run["state"]["proof_graph"]["snapshots"][-1]
                proposition_p = next(key for key, item in original["propositions"].items()
                                     if item["statement"] == "Claim P")
                proposition_c = next(key for key, item in original["propositions"].items()
                                     if item["statement"] == "Claim C")
                self.assertEqual("supported", original["propositions"][proposition_c]["status"])
                self.assertEqual(2, original["graph_version"])

                first_withdrawal = self._ledger_patch(run, entries)
                first_withdrawal["verified_results_ledger"][2].update(
                    valid=False, invalidated=True
                )
                run = self._commit(harness, run, "withdraw-A", first_withdrawal)
                current = run["state"]["proof_graph"]["snapshots"][-1]
                self.assertEqual("supported", current["propositions"][proposition_p]["status"])
                self.assertEqual("supported", current["propositions"][proposition_c]["status"])

                second_withdrawal = self._ledger_patch(run, entries)
                second_withdrawal["verified_results_ledger"][1].update(
                    valid=False, invalidated=True
                )
                run = self._commit(harness, run, "withdraw-B", second_withdrawal)
                final_snapshot = run["state"]["proof_graph"]["snapshots"][-1]
                final_revision = run["state_revision"]
                final_event_count = len(run["events"])
                self.assertEqual("invalidated", final_snapshot["propositions"][proposition_p]["status"])
                self.assertEqual("invalidated", final_snapshot["propositions"][proposition_c]["status"])

                with self.assertRaises(SolverRevisionConflictError):
                    harness.commit_event(
                        run["run_id"], expected_revision=final_revision - 1,
                        event={"event_id": "stale-graph-write", "type": "test_stale"},
                        state_updates={"verified_results_ledger": []},
                    )
                duplicate_patch = self._ledger_patch(run, entries[:1] * 2)
                with self.assertRaises(SolverPersistenceError):
                    self._commit(harness, run, "duplicate-result-id", duplicate_patch)

                persisted = harness.get_run(run["run_id"])
                self.assertEqual(final_revision, persisted["state_revision"])
                self.assertEqual(final_event_count, len(persisted["events"]))
                self.assertEqual(final_snapshot, persisted["state"]["proof_graph"]["snapshots"][-1])
                self.assertEqual([], proof_graph_summary(persisted["state"], graph_version=0)["propositions"])
                self.assertIsNone(proof_graph_summary(persisted["state"], graph_version=999))

            with SolverHarness(database_path=database, config=config) as restarted:
                restored = restarted.get_run("graph-or-restart")
                self.assertEqual(final_revision, restored["state_revision"])
                self.assertEqual(final_snapshot,
                                 restored["state"]["proof_graph"]["snapshots"][-1])
                self.assertEqual(0, proof_graph_summary(restored["state"], 0)["graph_version"])

    def test_persisted_independent_receipt_conflicts_and_blocks_dependents_until_review(self):
        from showcase.solver_harness.tool_ports import RegistryToolPort
        from showcase.solver_harness.tool_precheck import _execute
        from showcase.tools import ToolRegistry

        registry = ToolRegistry()
        registry.register_polynomial_check()
        config = {
            "features": {"proof_graph": True, "local_code_tool": True},
            "allowed_tools": ["polynomial_check"], "max_tool_calls": 5,
            "tool_timeout_seconds": 2, "max_tool_output_bytes": 16000,
            "max_total_duration_seconds": 3600,
        }
        with SolverHarness(config=config, tool_port=RegistryToolPort(registry)) as harness:
            run = harness.solve("private problem", {"run_id": "graph-counterexample"})
            patch = self._ledger_patch(run, [
                ("P", "x=1 is a root of polynomial coefficients 1,0",
                 "counterexample:x is real", []),
                ("C", "Claim C", "scope-C", ["P"]),
            ])
            candidate = self._counterexample_patch(
                run, "x=1 is a root of polynomial coefficients 1,0"
            )
            patch["steps"].update(candidate["steps"])
            patch["calls"].update(candidate["calls"])
            run = self._commit(harness, run, "accept-P-and-propose-counterexample", patch)
            snapshot = run["state"]["proof_graph"]["snapshots"][-1]
            counterexample = next(item for item in snapshot["attempts"].values()
                                  if item["direction"] == "counterexample")
            proposition_p = counterexample["conclusion"]
            proposition_c = next(key for key, item in snapshot["propositions"].items()
                                 if item["statement"] == "Claim C")
            self.assertEqual("proposed", counterexample["status"])
            self.assertEqual("supported", snapshot["propositions"][proposition_c]["status"])

            run, receipt = _execute(
                harness, run,
                {"tool": "polynomial_check", "arguments": {
                    "schema_version": 1, "variable": "x", "coefficients": ["1", "0"],
                    "domain": {"kind": "real"}, "candidates": ["1"],
                }},
                config, harness._tool_port, "ce-step", 0,
            )
            receipt_id = receipt["receipt_id"]
            run = harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": "attach-independent-check", "type": "proof_graph_receipt_attached"},
                state_updates={"tool_receipts": [receipt]},
            )
            from showcase.solver_harness.proof_graph_commands import (
                accept_counterexample,
                resolve_conflict,
            )

            run = accept_counterexample(
                harness, run["run_id"], expected_revision=run["state_revision"],
                graph_version=run["state"]["proof_graph"]["current_version"],
                event_id="verify-counterexample-receipt",
                attempt_id=counterexample["id"], receipt_id=receipt_id,
            )
            snapshot = run["state"]["proof_graph"]["snapshots"][-1]
            self.assertEqual("accepted", snapshot["attempts"][counterexample["id"]]["status"])
            self.assertEqual("tool_verified", snapshot["attempts"][counterexample["id"]]["grade"])
            self.assertTrue(snapshot["propositions"][proposition_p]["conflict"])
            self.assertEqual("invalidated", snapshot["propositions"][proposition_c]["status"])

            run = harness.commit_event(
                run["run_id"], expected_revision=run["state_revision"],
                event={"event_id": "withdraw-counterexample-receipt",
                       "type": "test_receipt_withdrawn"},
                state_updates={"tool_receipts": []},
            )
            snapshot = run["state"]["proof_graph"]["snapshots"][-1]
            self.assertTrue(snapshot["propositions"][proposition_p]["conflict"])
            self.assertEqual("invalidated", snapshot["attempts"][counterexample["id"]]["status"])

            resolution_id = "conflict-review"
            resolution = {"proposition_id": proposition_p, "ruling": "support",
                          "review_call_id": resolution_id}
            review_call = {
                "call_id": resolution_id, "run_id": run["run_id"],
                "problem_hash": run["state"]["problem_hash"],
                "config_hash": run["state"]["config_hash"],
                "role": "step_verifier", "status": "completed",
                "request_revision": run["state_revision"],
                "request": {"proof_graph_conflict_ids": [proposition_p]},
                "response": {"proof_graph_proposition_id": proposition_p,
                             "proof_graph_resolution": "support"},
            }
            run = self._commit(harness, run, "persist-conflict-review", {
                "calls": {**run["state"].get("calls", {}), resolution_id: review_call},
            })
            from showcase.solver_harness.proof_graph import _resolution_valid

            stale_state = {**run['state'], 'calls': {
                **run['state']['calls'], resolution_id: {**review_call, 'request_revision': 0},
            }}
            self.assertFalse(_resolution_valid(stale_state, proposition_p, resolution))
            run = resolve_conflict(
                harness, run["run_id"], expected_revision=run["state_revision"],
                graph_version=run["state"]["proof_graph"]["current_version"],
                event_id="resolve-proof-graph-conflict", **resolution,
            )
            snapshot = run["state"]["proof_graph"]["snapshots"][-1]
            self.assertFalse(snapshot["propositions"][proposition_p]["conflict"])
            self.assertEqual("rejected", snapshot["attempts"][counterexample["id"]]["status"])
            self.assertEqual("invalidated", snapshot["propositions"][proposition_c]["status"])


if __name__ == "__main__":
    unittest.main()
