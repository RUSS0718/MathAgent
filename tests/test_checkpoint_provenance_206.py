"""Checkpoint tool provenance at the public SQLite Harness boundary (no provider)."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness
from tests.test_solver_harness_reasoner_checkpoint import ACCEPT, PLAN, checkpoint


class CheckpointProvenanceTest(unittest.TestCase):
    def test_new_checkpoint_cannot_cite_absent_receipts_under_any_label(self):
        for label in ("verified", "easy-verify", "hard-verify"):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                reply = checkpoint("FINAL")
                reply["checkpoint"]["claims"][0].update(
                    label=label, tool_evidence_refs=["tool:synthetic:1047:0", "tool:synthetic:1047:1"])
                verifier = ScriptedVerifierPort([ACCEPT])
                with SolverHarness(
                    database_path=Path(directory) / "state.sqlite",
                    config={"features": {"reasoner_checkpoints": True}},
                    model_port=ScriptedModelPort([reply]), verifier_port=verifier,
                ) as harness:
                    result = harness.solve("synthetic proof", {"plan": PLAN})
                self.assertEqual([], verifier.requests)
                self.assertEqual("invalid_checkpoint_tool_evidence", result["state"]["result_reason"])
