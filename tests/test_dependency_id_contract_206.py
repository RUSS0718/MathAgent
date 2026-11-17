"""Dependency identity guidance observed through the actual Intern adapter."""

import json
import unittest
from copy import deepcopy

from showcase.adapters import InternModelAdapter
from showcase.solver_harness.intern_port import InternModelPort
from tests.test_solver_harness_reasoner_checkpoint import checkpoint


class CaptureClient:
    model = "intern-test"

    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append((deepcopy(messages), kwargs))
        return {"content": json.dumps(self.reply), "finish_reason": "stop",
                "usage": {"prompt_tokens": 12, "completion_tokens": 5, "total_tokens": 17}}


class DependencyIdContract206Test(unittest.TestCase):
    def test_dependency_identity_contract_reaches_only_applicable_roles(self):
        cases = [
            ({"role": role, "checkpoint_protocol": True, "current_goal": "derive",
              "valid_sources": [{"source": "s1", "result_id": "s1:outcome-1",
                                 "category": "Lemma", "valid": True}]},
             checkpoint("FINAL"), True)
            for role in ("reasoner", "reason_noncoding")
        ]
        review = {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                  "verdict": "CHALLENGE", "objection": "Missing established source"}
        cases += [
            ({"role": "step_verifier", "checkpoint": checkpoint()["checkpoint"]}, review, True),
            ({"role": "step_verifier", "reclassification_of": "original-review",
              "admission_rejections": [{"reason": "unknown_dependency"}]}, review, True),
            ({"role": "reasoner"}, {"argument": "derive", "claims": [], "blocked": False}, False),
            ({"role": "planner"}, {"version": 1, "steps": [
                {"step_id": "s1", "title": "Derive", "objective": "derive"}]}, False),
            ({"role": "whole_solution_verifier"},
             {"verdict": "REJECT", "reason": "Incomplete argument"}, False),
        ]
        options = None
        for fields, reply, enabled in cases:
            with self.subTest(fields=fields):
                request = {"problem": "A generic dependency task", **fields}
                original = deepcopy(request)
                client = CaptureClient(reply)
                port = InternModelPort(adapter=InternModelAdapter(client=client))
                response = port.complete(request)
                self.assertEqual(reply, {k: response[k] for k in reply})
                self.assertEqual(original, request)
                self.assertEqual(1, len(client.requests))
                self.assertEqual(1, len(port.invocations))
                self.assertEqual(17, port.invocations[0]["usage"]["total_tokens"])
                messages, kwargs = client.requests[0]
                context = json.loads(messages[-1]["content"])
                self.assertEqual({**request, "original_problem": request["problem"],
                                  "tool_argument_schemas": {}}, context)
                self.assertEqual(fields["role"], kwargs["request_purpose"])
                limits = {k: v for k, v in kwargs.items() if k != "request_purpose"}
                options = limits if options is None else options
                self.assertEqual(options, limits)
                guidance = messages[0]["content"]
                for rule in ("established step IDs", "accepted ledger result IDs",
                             "valid_sources", "checkpoint_id identifies a handoff",
                             "never copy it into dependencies", "retain an unresolved objection"):
                    if enabled:
                        self.assertTrue(rule in guidance, "Missing dependency rule: " + rule)
                    else:
                        self.assertFalse(rule in guidance, "Unexpected dependency rule: " + rule)
