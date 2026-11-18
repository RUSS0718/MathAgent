"""Checkpoint tool provenance at the public SQLite Harness boundary (no provider)."""

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from showcase.solver_harness.intern_port import InternPortError
from tests.test_solver_harness_reasoner_checkpoint import ACCEPT, PLAN, checkpoint


class CheckpointProvenanceTest(unittest.TestCase):
    def citation_case(self, *, label="verified", tool_result=None, mutate=None, dependent=True, fault=None):
        initial = checkpoint("FINAL", marker="finite-result", tool_request={
            "tool": "polynomial_check", "arguments": {"coefficients": [1]},
            "scope": "finite_computation", "expected_output": {"value": 3}})
        plan = {"version": 1, "steps": [
            {"step_id": "s1", "title": "Compute", "objective": "derive"},
            {"step_id": "s2", "title": "Use", "objective": "derive",
             "depends_on": ["s1"] if dependent else []}]}

        class CitationPort(ScriptedModelPort):
            def complete(self, request):
                if not self.requests:
                    return super().complete(request)
                self.requests.append(deepcopy(request))
                reply = checkpoint("FINAL", marker="use-result")
                run = harness.get_run(request["run_id"])
                receipt = run["state"]["tool_receipts"][0]
                if fault:
                    kind, key, value = fault
                    updates = {}
                    event = {"event_id": "synthetic-fault", "type": "synthetic_fault"}
                    if kind == "receipt":
                        receipt[key] = value
                        updates["tool_receipts"] = [receipt]
                        event.update(type="tool_receipt", receipt=receipt)
                    else:
                        calls = run["state"]["calls"]
                        source_id = run["state"]["reasoner_checkpoints"][0]["call_id"]
                        calls[source_id]["request"][key] = value
                        updates["calls"] = calls
                    harness.commit_event(request["run_id"], expected_revision=run["state_revision"],
                                         event=event, state_updates=updates)
                reply["checkpoint"]["claims"] = [{"statement": "finite-result", "label": label,
                    "tool_evidence_refs": [receipt["receipt_id"]]}]
                if mutate:
                    mutate(reply["checkpoint"])
                return reply

        model = CitationPort([initial])
        verifier = ScriptedVerifierPort([ACCEPT, ACCEPT])
        with tempfile.TemporaryDirectory() as directory, SolverHarness(
            database_path=Path(directory) / "state.sqlite",
            config={"features": {"reasoner_checkpoints": True, "stream_recovery": True,
                                 "local_code_tool": True}, "allowed_tools": ["polynomial_check"],
                    "max_model_calls": 8},
            model_port=model, verifier_port=verifier,
            tool_port=ScriptedToolPort([tool_result or {
                "status": "success", "exit_code": 0, "output": {"value": 3}}]),
        ) as harness:
            result = harness.solve("synthetic computation", {"plan": plan})
        return result, verifier

    def test_committed_but_foreign_stale_or_mismatched_receipt_is_rejected(self):
        for fault in (("receipt", "run_id", "another-run"), ("receipt", "plan_version", 2),
                      ("receipt", "attempt_index", 1), ("receipt", "step_id", "unrelated"),
                      ("receipt", "tool", "python_math"), ("receipt", "input", {"code": "print(99)"}),
                      ("receipt", "claim_index", 1), ("receipt", "executed", False),
                      ("receipt", "unknown_outcome", True), ("call", "problem_spec_version", 99)):
            with self.subTest(field=fault[1]):
                result, verifier = self.citation_case(fault=fault)
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("invalid_checkpoint_tool_evidence", result["state"]["result_reason"])

    def test_accepted_predecessor_citation_reaches_review_with_finite_receipt(self):
        for label in ("verified", "easy-verify", "hard-verify"):
            with self.subTest(label=label):
                result, verifier = self.citation_case(label=label)
                self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
                review = verifier.requests[-1]
                self.assertEqual(1, len(review["report"]["tool_receipts"]))
                self.assertEqual(1, result["state"]["counters"]["tool_calls"])
                self.assertEqual("finite_computation", review["report"]["claims"][0]["verification_scope"])

    def test_failed_unknown_and_outputless_receipts_cannot_be_cited(self):
        for output in ({"status": "tool_error", "exit_code": 1, "output": {"value": 3}},
                       {"status": "unknown_outcome", "exit_code": None, "output": {"value": 3}},
                       {"status": "success", "exit_code": 0, "output": None},
                       {"status": "success", "exit_code": 1, "output": {"value": 3}},
                       {"status": "success", "exit_code": 0, "output": {"value": 99}}):
            with self.subTest(status=output["status"], output=output["output"]):
                result, verifier = self.citation_case(tool_result=output)
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("invalid_checkpoint_tool_evidence", result["state"]["result_reason"])

    def test_unrelated_step_and_changed_computational_target_are_rejected(self):
        for kwargs in ({"dependent": False}, {"mutate": lambda cp:
                cp["claims"][0].update(statement="different target")}, {"mutate": lambda cp:
                cp["claims"][0].update(tool_request={"tool": "python_math",
                    "arguments": {"code": "print(99)"}, "scope": "finite_computation"})}):
            with self.subTest(case=list(kwargs)):
                result, verifier = self.citation_case(**kwargs)
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("invalid_checkpoint_tool_evidence", result["state"]["result_reason"])

    def test_preserved_pure_proof_format_repair_remains_legal(self):
        reply = checkpoint("FINAL")
        original = deepcopy(reply)
        original["checkpoint"]["verdict"] = "not_a_checkpoint_field"
        result, verifier, model = self.repair_case(json.dumps(original), reply)
        self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(2, len(model.requests))

    def test_original_d3_pattern_is_blocked_with_zero_tools(self):
        original = checkpoint(tool_request={"tool": "python_math",
            "arguments": {"code": "print(3)"}, "scope": "finite_computation"})
        original["checkpoint"]["claims"].append({"statement": "candidate substitution",
            "label": "easy-verify", "tool_request": {"tool": "polynomial_check",
                "arguments": {"coefficients": [1]}, "scope": "finite_computation"}})
        text = json.dumps(original).replace(', "status"', ' "status"', 1)
        repaired = checkpoint("FINAL", marker="repaired")
        repaired["checkpoint"]["claims"][0].update(label="verified", tool_request=None,
            tool_evidence_refs=["tool:synthetic:1047:0", "tool:synthetic:1047:1"])
        result, verifier, _ = self.repair_case(text, repaired, "invalid_json")
        self.assertEqual(0, len(verifier.requests))
        self.assertEqual(0, result["state"]["counters"]["tool_calls"])
        self.assertEqual("checkpoint_repair_semantics_unavailable", result["state"]["result_reason"])

    def repair_case(self, original, repaired, category="invalid_role_schema"):
        class RepairPort(ScriptedModelPort):
            def complete(self, request):
                if not self.requests:
                    self.requests.append(deepcopy(request))
                    def stream():
                        yield original
                        raise InternPortError(category)
                    return stream()
                return super().complete(request)

        verifier = ScriptedVerifierPort([ACCEPT, ACCEPT])
        model = RepairPort([repaired])
        with tempfile.TemporaryDirectory() as directory, SolverHarness(
            database_path=Path(directory) / "state.sqlite",
            config={"features": {"reasoner_checkpoints": True, "star_routing": True,
                                 "stream_recovery": True}, "max_model_calls": 4},
            model_port=model, verifier_port=verifier,
        ) as harness:
            result = harness.solve("synthetic proof", {"plan": PLAN})
        return result, verifier, model

    def test_format_repair_cannot_drop_pending_actions_even_without_fake_refs(self):
        original = checkpoint(tool_request={"tool": "python_math",
            "arguments": {"code": "print(3)"}, "scope": "finite_computation"})
        repaired = checkpoint("FINAL")
        repaired["checkpoint"]["claims"][0]["label"] = "verified"
        result, verifier, _ = self.repair_case(json.dumps(original), repaired)
        self.assertEqual(0, len(verifier.requests))
        self.assertEqual("checkpoint_repair_changed_semantics", result["state"]["result_reason"])

    def test_unparseable_repair_does_not_claim_serialization_equivalence(self):
        result, verifier, _ = self.repair_case('{"checkpoint":', checkpoint("FINAL"), "invalid_json")
        self.assertEqual(0, len(verifier.requests))
        self.assertEqual("checkpoint_repair_semantics_unavailable", result["state"]["result_reason"])

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
