"""Synthetic checkpoint identity contracts at the Intern and Harness boundaries."""

import json
import unittest
from copy import deepcopy

from showcase.adapters import InternModelAdapter
from showcase.solver_harness import (
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)
from showcase.solver_harness.intern_port import InternModelPort
from tests.test_dependency_id_contract_206 import CaptureClient
from tests.test_solver_harness_reasoner_checkpoint import ACCEPT, CHALLENGE, PLAN, checkpoint


class CheckpointIdentityContract206Test(unittest.TestCase):
    def test_challenge_marker_scopes_guidance_for_both_checkpoint_reasoners(self):
        for role in ("reasoner", "reason_noncoding"):
            for challenge in (False, True):
                with self.subTest(role=role, challenge=challenge):
                    request = {"role": role, "problem": "Synthetic objection",
                               "checkpoint_protocol": True, "objection": CHALLENGE["objection"],
                               "parent_checkpoint_id": "cp-1",
                               "reasoner_checkpoint": checkpoint()["checkpoint"]}
                    if challenge:
                        request.update(round=1, challenge_history=[])
                    original = deepcopy(request)
                    client = CaptureClient(checkpoint("FINAL"))
                    port = InternModelPort(adapter=InternModelAdapter(client=client))
                    port.complete(request)
                    self.assertEqual(original, request)
                    self.assertEqual(1, len(client.requests))
                    messages, _ = client.requests[0]
                    guidance = messages[0]["content"]
                    self.assertEqual(challenge, "Challenge replies must use a fresh checkpoint_id" in guidance)
                    self.assertEqual(challenge, "substantively address the objection" in guidance)
                    self.assertEqual(not challenge, "Only the same-object tool completion exception" in guidance)
                    self.assertIn("still requires a new independent Verifier review", guidance)
                    if not challenge:
                        self.assertIn("ordinary checkpoint continuations", guidance)
                        self.assertIn("supported by the runtime", guidance)

    def test_identity_guidance_reaches_only_checkpoint_reasoners(self):
        cases = []
        for role in ("reasoner", "reason_noncoding"):
            for continuation in (False, True):
                fields = {"role": role, "checkpoint_protocol": True, "current_goal": "derive"}
                if continuation:
                    fields.update(parent_checkpoint_id="cp-1",
                                  reasoner_checkpoint=checkpoint()["checkpoint"])
                cases.append((fields, checkpoint("FINAL"), True))
            cases.append(({"role": role},
                          {"argument": "derive", "claims": [], "blocked": False}, False))
        cases.extend([
            ({"role": "planner", "checkpoint_protocol": True},
             {"checkpoint": {"protocol_version": 1, "checkpoint_id": "plan-1", "status": "FINAL",
                             "objective": "Plan", "dependencies": [], "evidence": [],
                             "gaps": [], "next_action": "Execute"}, "plan": PLAN}, False),
            ({"role": "step_verifier", "checkpoint": checkpoint()["checkpoint"]}, CHALLENGE, False),
            ({"role": "whole_solution_verifier"},
             {"verdict": "REJECT", "reason": "Incomplete"}, False),
        ])
        options = None
        for fields, reply, applicable in cases:
            with self.subTest(fields=fields):
                request = {"problem": "Synthetic identity task", **fields}
                original = deepcopy(request)
                client = CaptureClient(reply)
                port = InternModelPort(adapter=InternModelAdapter(client=client))
                response = port.complete(request)
                self.assertEqual(reply, {key: response[key] for key in reply})
                self.assertEqual(original, request)
                self.assertEqual(1, len(client.requests))
                self.assertEqual(1, len(port.invocations))
                self.assertEqual(17, port.invocations[0]["usage"]["total_tokens"])
                messages, kwargs = client.requests[0]
                context = json.loads(messages[-1]["content"])
                self.assertEqual({**request, "original_problem": request["problem"],
                                  "tool_argument_schemas": {}}, context)
                self.assertEqual(fields["role"], kwargs["request_purpose"])
                limits = {key: value for key, value in kwargs.items() if key != "request_purpose"}
                options = limits if options is None else options
                self.assertEqual(options, limits)
                for rule in (
                    "checkpoint_id identifies an immutable handoff",
                    "new claims, changed claim statements, dependencies or top-level evidence",
                    "use a fresh checkpoint_id",
                    "Only the same-object tool completion exception",
                    "same objective, dependencies and top-level evidence",
                    "same claim count and statements",
                    "runtime-committed successful receipts",
                    "matching Run, plan, attempt, specification, step, claim and tool input",
                    "non-tool claims keep their labels and have no tool_evidence_refs",
                    "FINAL with blocked=false and gaps=[]",
                    "failed, absent, unknown or output-free receipts do not qualify",
                    "still requires a new independent Verifier review",
                    "verified label never upgrades evidence authority",
                ):
                    self.assertEqual(applicable, rule in messages[0]["content"], rule)


class CheckpointIdentityHarness206Test(unittest.TestCase):
    def run_case(self, *, fresh=False, mutation=None, verdict=ACCEPT, first_verdict=ACCEPT):
        # All model/tool responses are synthetic. No registry, provider or subprocess tool runs.
        initial = checkpoint(marker="S1", tool_request={
            "tool": "polynomial_check", "arguments": {"coefficients": ["2", "-6"]},
            "scope": "finite_computation",
        })
        initial["checkpoint"]["evidence"] = []
        initial["checkpoint"]["claims"][0]["statement"] = "2 * 3 = 6"
        verifier = ScriptedVerifierPort([first_verdict, verdict])
        client = CaptureClient(initial)

        def completed(messages, **kwargs):
            client.requests.append((deepcopy(messages), kwargs))
            reply = deepcopy(initial)
            if len(client.requests) > 1:
                cp = reply["checkpoint"]
                cp.update(status="FINAL", gaps=[], argument="Substitution checked",
                          next_action="Review the computation")
                if fresh:
                    cp["checkpoint_id"] = "S1-completed"
                cp["claims"][0].update(
                    label="verified", tool_request=None,
                    tool_evidence_refs=verifier.requests[0]["report"]["tool_evidence_refs"])
                if mutation == "claim":
                    cp["claims"].append({"statement": "The real solution is unique",
                                         "label": "verified"})
                elif mutation == "evidence":
                    cp["evidence"] = cp["claims"][0]["tool_evidence_refs"]
                elif mutation == "dependencies":
                    cp["dependencies"] = ["S1"]
                elif mutation == "objection":
                    cp["argument"] = "Dividing 2*x=6 by nonzero 2 forces x=3; the implication is necessary."
                    cp["claims"].append({"statement": "2*x=6 implies x=3 by division by 2",
                                         "label": "hard-verify"})
                elif mutation == "changed_computational_target":
                    cp["claims"][0]["statement"] = "2*x=6 implies x=3 by division by 2"
                elif mutation == "r05":
                    cp["claims"].append({"statement": "The real solution is unique",
                                         "label": "verified"})
                    cp["evidence"] = cp["claims"][0]["tool_evidence_refs"]
            return {"content": json.dumps(reply), "finish_reason": "stop"}

        client.chat = completed
        model = InternModelPort(adapter=InternModelAdapter(client=client))
        tool = ScriptedToolPort([{"status": "success", "output": {"value": 6}, "exit_code": 0}])
        with SolverHarness(
            config={"features": {"reasoner_checkpoints": True, "local_code_tool": True,
                                  "stream_recovery": True},
                    "allowed_tools": ["polynomial_check"], "max_model_calls": 4},
            model_port=model, verifier_port=verifier, tool_port=tool,
        ) as harness:
            result = harness.solve("Synthetic substitution", {"plan": PLAN})
        return result["state"], client, verifier

    def test_challenge_same_id_completion_is_rejected_and_message_requires_fresh_id(self):
        state, client, verifier = self.run_case(first_verdict=CHALLENGE)
        self.assertEqual(2, len(client.requests))
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(3, state["counters"]["model_calls"])
        self.assertEqual(1, state["counters"]["tool_calls"])
        self.assertNotEqual("ACCEPTED", state["steps"]["s1"]["status"])
        self.assertEqual("checkpoint_no_progress", state["meta_interventions"][-1]["upgrade_reason"])
        messages, _ = client.requests[1]
        request = json.loads(messages[-1]["content"])
        self.assertEqual(1, request["round"])
        self.assertEqual(CHALLENGE["objection"], request["objection"])
        self.assertEqual("S1", request["parent_checkpoint_id"])
        self.assertIn("Challenge replies must use a fresh checkpoint_id", messages[0]["content"])
        self.assertIn("substantively address the objection", messages[0]["content"])
        self.assertNotIn("Only the same-object tool completion exception", messages[0]["content"])

    def test_fresh_challenge_response_receives_independent_review(self):
        for verdict in (ACCEPT, CHALLENGE):
            with self.subTest(verdict=verdict):
                state, client, verifier = self.run_case(
                    first_verdict=CHALLENGE, fresh=True, mutation="objection", verdict=verdict)
                self.assertEqual(2, len(client.requests))
                self.assertEqual(2, len(verifier.requests))
                self.assertEqual(4, state["counters"]["model_calls"])
                self.assertEqual(1, state["counters"]["tool_calls"])
                self.assertEqual("S1-completed", verifier.requests[1]["checkpoint"]["checkpoint_id"])
                self.assertNotEqual(verifier.requests[0]["call_id"], verifier.requests[1]["call_id"])
                self.assertEqual(verdict == ACCEPT, state["phase"] == "FINAL_GENERATE")
                claims = verifier.requests[1]["report"]["claims"]
                self.assertEqual("2 * 3 = 6", claims[0]["statement"])
                self.assertEqual([state["tool_receipts"][0]["receipt_id"]], claims[0]["tool_evidence_refs"])
                self.assertEqual("2*x=6 implies x=3 by division by 2", claims[1]["statement"])
                self.assertEqual([], claims[1]["tool_evidence_refs"])
                self.assertIn("Challenge replies must use a fresh checkpoint_id", client.requests[1][0][0]["content"])

    def test_challenge_cannot_rebind_finite_receipt_to_new_claim(self):
        state, client, verifier = self.run_case(
            first_verdict=CHALLENGE, fresh=True, mutation="changed_computational_target")
        self.assertEqual("invalid_checkpoint_tool_evidence", state["result_reason"])
        self.assertEqual(2, len(client.requests))
        self.assertEqual(1, len(verifier.requests))
        self.assertEqual(1, state["counters"]["tool_calls"])
        self.assertEqual(["S1"], [c["checkpoint_id"] for c in state["reasoner_checkpoints"]])

    def test_same_id_mutation_is_rejected_before_another_review(self):
        for mutation in ("claim", "evidence", "dependencies", "r05"):
            with self.subTest(mutation=mutation):
                state, client, verifier = self.run_case(mutation=mutation)
                self.assertEqual("reasoner_checkpoint_no_progress", state["result_reason"])
                self.assertEqual(2, len(client.requests))
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual(3, state["counters"]["model_calls"])
                self.assertEqual(1, state["counters"]["tool_calls"])

    def test_same_object_tool_completion_keeps_independent_review(self):
        state, client, verifier = self.run_case()
        self.assertEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(2, len(client.requests))
        self.assertEqual(4, state["counters"]["model_calls"])
        self.assertEqual(1, state["counters"]["tool_calls"])
        self.assertEqual(["YIELD", "FINAL"], [r["checkpoint"]["status"] for r in verifier.requests])
        self.assertNotEqual(verifier.requests[0]["call_id"], verifier.requests[1]["call_id"])
        self.assertEqual([state["tool_receipts"][0]["receipt_id"]],
                         verifier.requests[1]["report"]["tool_evidence_refs"])

    def test_fresh_id_and_verified_labels_cannot_override_independent_challenge(self):
        state, client, verifier = self.run_case(fresh=True, mutation="r05", verdict=CHALLENGE)
        self.assertEqual(2, len(client.requests))
        self.assertEqual(2, len(verifier.requests))
        self.assertEqual("S1-completed", verifier.requests[1]["checkpoint"]["checkpoint_id"])
        self.assertEqual(2, len(verifier.requests[1]["report"]["claims"]))
        self.assertEqual("verified", verifier.requests[1]["checkpoint"]["claims"][1]["label"])
        self.assertNotEqual("ACCEPTED", state["steps"]["s1"]["status"])
        self.assertNotEqual("FINAL_GENERATE", state["phase"])
        self.assertEqual(4, state["counters"]["model_calls"])
        self.assertEqual(1, state["counters"]["tool_calls"])
