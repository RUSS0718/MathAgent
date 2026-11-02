"""Public export and immutable decision replay contracts."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedVerifierPort,
    SolverHarness,
    export_result,
    replay_snapshot,
)


class ResultReplayTest(unittest.TestCase):
    def test_persisted_budget_result_exports_only_answer_and_replays_without_calls(self):
        config = {"max_model_calls": 1, "features": {"best_effort": True, "stream_recovery": True}}
        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "answer"}])
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.db"
            with SolverHarness(
                database_path=database,
                model_port=model,
                verifier_port=ScriptedVerifierPort([]),
                config=config,
            ) as harness:
                run = harness.solve("prove", {"run_id": "replay"})
            frozen = copy.deepcopy(run)
            self.assertEqual({"final_response": "answer"}, export_result(run))
            first = replay_snapshot(run)
            second = replay_snapshot(json.loads(json.dumps(run)))
            self.assertEqual(first, second)
            self.assertEqual(frozen, run)
            original = run["state"]["best_effort_decision"]
            self.assertEqual(
                original["selected_candidate_id"], first["decision"]["selected_candidate_id"]
            )
            self.assertEqual(original["confidence_level"], first["decision"]["confidence_level"])
            self.assertTrue(first["audit"]["matches_persisted_decision"])
            self.assertEqual(64, len(first["audit"]["snapshot_hash"]))
            spy, verifier = ScriptedModelPort([]), ScriptedVerifierPort([])
            with SolverHarness(
                database_path=database, model_port=spy, verifier_port=verifier, config=config
            ) as harness:
                recovered = harness.get_run("replay")
                self.assertEqual(first, replay_snapshot(recovered["state"], recovered["events"]))
            self.assertEqual([], spy.requests)
            self.assertEqual([], verifier.requests)
        self.assertEqual(1, len(model.requests))

    def test_adapter_never_exposes_internal_decision_or_empty_answer(self):
        result = export_result(
            {
                "final_response": "answer",
                "best_effort_decision": {"secret": "x"},
                "confidence": "high",
                "usage": {"tokens": "unknown"},
            }
        )
        self.assertEqual({"final_response": "answer"}, result)
        self.assertTrue(export_result({"final_response": " "})["final_response"].strip())

    def test_replay_audits_source_change_and_rejects_cross_run_events(self):
        with SolverHarness(
            model_port=ScriptedModelPort(
                [{"assessment": "SOLVED", "solution_candidate": "answer"}]
            ),
            config={"max_model_calls": 1, "features": {"best_effort": True}},
        ) as harness:
            run = harness.solve("prove", {"run_id": "audit"})
        original = replay_snapshot(run)
        changed = copy.deepcopy(run)
        changed["state"]["candidate_registry"][-1]["answer_text"] = "different answer"
        replayed = replay_snapshot(changed)
        self.assertNotEqual(original["audit"]["snapshot_hash"], replayed["audit"]["snapshot_hash"])
        self.assertFalse(replayed["audit"]["matches_persisted_decision"])
        changed["events"][0]["run_id"] = "another-run"
        with self.assertRaisesRegex(ValueError, "identity"):
            replay_snapshot(changed)

    def test_empty_snapshot_replay_is_deterministic_without_optional_fields(self):
        with SolverHarness() as harness:
            run = harness.solve("prove", {"run_id": "empty"})
        self.assertIsNone(run["state"]["candidate_registry"])
        self.assertIsNone(run["state"]["best_effort_decision"])
        first = replay_snapshot(run)
        self.assertEqual(first, replay_snapshot(run))
        self.assertEqual("no_eligible_candidate", first["decision"]["status"])
        self.assertIsNone(first["audit"]["matches_persisted_decision"])
        self.assertIsNone(run["state"]["best_effort_decision"])
