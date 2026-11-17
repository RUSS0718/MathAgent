"""Receipt-backed same-object checkpoint completion through the public Harness."""

import unittest
from copy import deepcopy

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import ScriptedVerifierPort, SolverHarness
from showcase.solver_harness.tool_ports import RegistryToolPort
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT as WHOLE_ACCEPT
from tests.star_product_support import StarJobFixture
from tests.test_solver_harness_reasoner_checkpoint import ACCEPT, checkpoint
from tests.test_star_product_tools import NEED_PLAN

PLAN = {"version": 1, "steps": [
    {"step_id": "S1", "title": "Compute", "objective": "derive"},
    {"step_id": "S2", "title": "Use", "objective": "derive", "depends_on": ["S1"]},
]}


class ToolCheckpointTest(unittest.TestCase):
    def run_case(self, *, status="FINAL", marker="S1", code="print(3)", tool=True,
                 change=None, initial_reply=None, final_reply=None, plan=PLAN,
                 max_model_calls=8, registry=None, verdicts=None):
        if registry is None:
            registry = ToolRegistry()
            registry.register_python_math()
        initial = initial_reply or checkpoint(marker="S1", tool_request={
            "tool": "python_math", "arguments": {"code": code},
            "scope": "finite_computation",
        } if tool else None)
        case = self

        class Model:
            def __init__(self):
                self.requests = []

            def complete(self, request):
                self.requests.append(deepcopy(request))
                if len(self.requests) == 1:
                    return deepcopy(initial)
                if request["step"]["step_id"] == "S2":
                    reply = checkpoint("FINAL", marker="S2")
                    reply["checkpoint"]["objective"] = request["step"]["objective"]
                    return reply
                reply = deepcopy(final_reply) if final_reply else checkpoint(status, marker=marker)
                receipts = harness.get_run(request["run_id"])["state"]["tool_receipts"]
                reply["checkpoint"]["claims"] = [{
                    "statement": initial["checkpoint"]["claims"][0]["statement"], "label": "verified",
                    "tool_evidence_refs": [r["receipt_id"] for r in receipts],
                    "tool_request": None,
                }]
                # Assert the continuation consumes the receipt actually committed by runtime.
                if tool:
                    case.assertEqual(1, len(receipts))
                    case.assertTrue(receipts[0]["executed"])
                if change:
                    change(reply["checkpoint"])
                return reply

        model = Model()
        verifier = ScriptedVerifierPort(verdicts or [ACCEPT, ACCEPT, ACCEPT])
        with SolverHarness(config={
            "features": {"reasoner_checkpoints": True, "local_code_tool": True,
                         "stream_recovery": True},
            "allowed_tools": ["python_math"], "max_model_calls": max_model_calls,
        }, model_port=model, verifier_port=verifier,
            tool_port=RegistryToolPort(registry)) as harness:
            result = harness.solve("compute then use", {"plan": plan})
        return result, model, verifier

    def test_tool_final_same_object_advances_to_dependent_step(self):
        result, model, verifier = self.run_case()
        state = result["state"]
        self.assertEqual("FINAL_GENERATE", state["phase"], {
            "run_id": result["run_id"], "reason": state.get("result_reason")})
        self.assertEqual("ACCEPTED", state["steps"]["S1"]["status"])
        self.assertEqual(["S1", "S1", "S2"], [r["step"]["step_id"] for r in model.requests])
        self.assertEqual(1, state["counters"]["tool_calls"])
        receipt = state["tool_receipts"][0]
        self.assertEqual("success", receipt["status"])
        self.assertIn("3", str(receipt["output"]))
        self.assertEqual("FINAL", verifier.requests[1]["checkpoint"]["status"])
        self.assertEqual([receipt["receipt_id"]], verifier.requests[1]["report"]["tool_evidence_refs"])
        self.assertNotEqual(verifier.requests[0]["call_id"], verifier.requests[1]["call_id"])
        self.assertEqual(2, len([c for c in state["reasoner_checkpoints"] if c["step_id"] == "S1"]))

    def test_new_yield_does_not_upgrade(self):
        result, _, verifier = self.run_case(status="YIELD")
        self.assertEqual("reasoner_checkpoint_no_progress", result["state"]["result_reason"])
        self.assertEqual(1, len(verifier.requests))

    def test_fresh_yield_still_stops_at_original_round_limit(self):
        result, model, verifier = self.run_case(status="YIELD", marker="fresh")
        self.assertEqual("reasoner_checkpoint_round_limit", result["state"]["result_reason"])
        self.assertEqual(2, len(model.requests))
        self.assertEqual(2, len(verifier.requests))

    def test_new_final_must_pass_a_new_independent_review(self):
        result, model, verifier = self.run_case(verdicts=[ACCEPT, {
            "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
            "objection": "the computation does not establish uniqueness",
        }])
        self.assertEqual(2, len(verifier.requests))
        self.assertNotEqual("ACCEPTED", result["state"]["steps"]["S1"]["status"])
        self.assertTrue(all(r["step"]["step_id"] == "S1" for r in model.requests))

    def test_failed_or_absent_tool_does_not_upgrade(self):
        for kwargs in ({"tool": False}, {"code": "raise ValueError('expected')"}, {"code": "x = 3"}):
            with self.subTest(kwargs=kwargs):
                result, _, verifier = self.run_case(**kwargs)
                self.assertEqual("reasoner_checkpoint_no_progress", result["state"]["result_reason"])
                self.assertEqual(1, len(verifier.requests))

    def test_changed_object_or_foreign_receipt_does_not_upgrade(self):
        for field, value in (("objective", "foreign step"), ("dependencies", ["foreign"]),
                             ("evidence", ["foreign"]), ("blocked", True)):
            with self.subTest(field=field):
                result, _, verifier = self.run_case(change=lambda cp: cp.update({field: value}))
                self.assertEqual("TERMINAL", result["state"]["phase"])
                self.assertEqual(1, len(verifier.requests))
        for field, value in (("statement", "foreign claim"), ("tool_evidence_refs", ["foreign"]),
                             ("tool_request", {"tool": "python_math", "arguments": {"code": "print(9)"},
                                               "scope": "finite_computation"})):
            with self.subTest(claim=field):
                result, _, verifier = self.run_case(
                    change=lambda cp: cp["claims"][0].update({field: value}))
                self.assertEqual("reasoner_checkpoint_no_progress", result["state"]["result_reason"])
                self.assertEqual(1, len(verifier.requests))

    def test_different_id_is_a_normal_new_checkpoint(self):
        result, _, verifier = self.run_case(marker="fresh")
        self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
        self.assertEqual("fresh", verifier.requests[1]["checkpoint"]["checkpoint_id"])

    def test_budget_does_not_expand_for_completion(self):
        result, _, verifier = self.run_case(max_model_calls=3)
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])

    def test_receipt_binding_rejects_foreign_step_spec_attempt_and_unknown(self):
        from showcase.solver_harness.reasoner_checkpoint import tool_completion_receipts

        # Supplemental pure validation of snapshots produced by the public Harness;
        # no internal verifier result is replaced.
        result, _, _ = self.run_case()
        state = result["state"]
        parent, final = state["reasoner_checkpoints"][:2]
        reply = state["calls"][final["call_id"]]["response"]["checkpoint"]
        self.assertIsNotNone(tool_completion_receipts(reply, parent, state, "S1"))
        paths = [
            (("problem_spec",), {"specification_version": 2}),
            (("calls", parent["call_id"], "request", "step", "step_id"), "S2"),
            (("calls", parent["call_id"], "status"), "unknown_outcome"),
            (("calls", parent["call_id"], "plan_version"), 2),
            (("calls", parent["call_id"], "attempt_index"), 2),
            (("tool_receipts", 0, "step_id"), "S2"),
            (("tool_receipts", 0, "run_id"), "foreign"),
            (("tool_receipts", 0, "plan_version"), 2),
            (("tool_receipts", 0, "attempt_index"), 2),
            (("tool_receipts", 0, "unknown_outcome"), True),
        ]
        for path, value in paths:
            with self.subTest(path=path):
                altered = deepcopy(state)
                target = altered
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                self.assertIsNone(tool_completion_receipts(reply, parent, altered, "S1"))


class ToolCheckpointJobTest(StarJobFixture, unittest.TestCase):
    def test_public_job_reviews_new_final_with_the_same_real_receipt(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        receipts = []

        def review(ctx):
            receipts.extend(ctx["report"]["tool_receipts"])
            return {**ACCEPT, "objection": ""}

        def completed(ctx):
            reply = checkpoint("FINAL", marker="S1")
            reply["checkpoint"]["objective"] = ctx["step"]["objective"]
            reply["checkpoint"]["claims"] = [{
                "statement": "S1", "label": "verified", "tool_request": None,
                "tool_evidence_refs": [receipts[0]["receipt_id"]],
            }]
            return reply

        def draft(ctx):
            reply = checkpoint(marker="S1", tool_request={"tool": "polynomial_check",
                "arguments": {"schema_version": 1, "variable": "x", "coefficients": ["1", "-3"],
                              "domain": {"kind": "real"}, "candidates": ["3"]},
                "scope": "finite_computation"})
            reply["checkpoint"]["objective"] = ctx["step"]["objective"]
            return reply

        self.open_star([
            NEED_PLAN, PLAN,
            draft,
            review, completed, {**ACCEPT, "objection": ""},
            checkpoint("FINAL", marker="S2"), {**ACCEPT, "objection": ""},
            {"final_response": "3"}, WHOLE_ACCEPT,
        ], stream_chunk_size=4096,
            SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12,
                                               max_tool_calls=1),
            SHOWCASE_STAR_FEATURES={"reasoner_checkpoints": True, "local_code_tool": True,
                                    "final_generation": True, "final_solution_review": True})
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final)
        reviews = [r for r in self.outbound if r["role"] == "step_verifier"]
        self.assertEqual(["YIELD", "FINAL", "FINAL"],
                         [r["checkpoint"]["status"] for r in reviews])
        self.assertEqual(1, final["result"]["budget"]["tool_calls"])
        self.assertEqual("success", receipts[0]["status"])
        self.assertEqual([receipts[0]["receipt_id"]], reviews[1]["report"]["tool_evidence_refs"])
        self.assertEqual("accepted", self.report(final["job_id"])["semantics"]["whole_review"])
