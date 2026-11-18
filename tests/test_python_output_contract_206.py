"""Python stdout guidance observed at the public Intern client boundary."""

import json
import unittest
from copy import deepcopy

from showcase.adapters import InternModelAdapter
from showcase.solver_harness.intern_port import InternModelPort
from showcase.tools import ToolRegistry

GUIDANCE = (
    "python_math runs code as an exec script and captures stdout as its output; "
    "a bare final expression is not automatically output, so use explicit print(...) "
    "for any result you need returned. "
)
REPLIES = {
    "reasoner": {"argument": "Independent reasoning", "claims": [], "blocked": False},
    "explore": {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
    "step_verifier": {"goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                      "verdict": "CHALLENGE", "objection": "An argument is needed"},
    "whole_solution_verifier": {"verdict": "REJECT"},
}


class CaptureClient:
    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append((deepcopy(messages), kwargs))
        return {"content": json.dumps(self.reply), "finish_reason": "stop"}


class PythonOutputContractTest(unittest.TestCase):
    def transmit(self, request, reply=None):
        reply = reply or REPLIES[request["role"]]
        original = deepcopy(request)
        client = CaptureClient(reply)
        port = InternModelPort(adapter=InternModelAdapter(client=client))
        response = port.complete(request)
        self.assertEqual(reply, {k: v for k, v in response.items() if k in reply})
        self.assertEqual(original, request)
        self.assertEqual(1, len(client.requests))
        self.assertEqual(1, len(port.invocations))
        messages, kwargs = client.requests[0]
        self.assertEqual(["system", "user"], [m["role"] for m in messages])
        return messages, kwargs

    def test_python_request_explains_script_stdout_contract(self):
        messages, _ = self.transmit({"role": "reasoner", "problem": "A generic task",
                                     "allowed_tools": ["python_math"]})
        guidance = messages[0]["content"]
        for rule in ("exec script", "captures stdout as its output",
                     "bare final expression is not automatically output", "explicit print"):
            with self.subTest(rule=rule):
                self.assertIn(rule, guidance)

    def test_only_python_enabled_computing_roles_receive_guidance(self):
        for role, reply in REPLIES.items():
            request = {"role": role, "problem": "Keep the original task",
                       "report": {"tool_receipts": [{"receipt_id": "current", "output": ""}]},
                       "max_output_tokens": 512}
            baseline, baseline_options = self.transmit(request, reply)
            for allowed in ([], ["polynomial_check"], ["python_math"]):
                with self.subTest(role=role, allowed=allowed):
                    messages, options = self.transmit({**request, "allowed_tools": allowed}, reply)
                    enabled = "python_math" in allowed
                    self.assertEqual(int(enabled), messages[0]["content"].count(GUIDANCE))
                    self.assertEqual(baseline[0]["content"],
                                     messages[0]["content"].replace(GUIDANCE, ""))
                    context = json.loads(messages[-1]["content"])
                    expected = {**request, "allowed_tools": allowed,
                                "original_problem": request["problem"],
                                "tool_argument_schemas": context["tool_argument_schemas"]}
                    self.assertEqual(expected, context)
                    self.assertEqual(set(allowed), set(context["tool_argument_schemas"]))
                    if enabled:
                        self.assertEqual({"type": "object", "properties": {"code": {"type": "string"}},
                                          "required": ["code"], "additionalProperties": False},
                                         context["tool_argument_schemas"]["python_math"])
                    self.assertEqual(baseline_options, options)

    def test_noncoding_and_planning_roles_do_not_receive_python_guidance(self):
        replies = {
            "reason_noncoding": REPLIES["reasoner"],
            "planner": {"version": 1, "steps": [
                {"step_id": "S1", "title": "Reason", "objective": "Explain"}]},
            "final_generator": {"final_response": "Independent argument"},
            "explore_polish": {"solution_candidate": "Independent argument"},
        }
        for role, reply in replies.items():
            with self.subTest(role=role):
                messages, _ = self.transmit({"role": role, "problem": "A generic task",
                                             "allowed_tools": ["python_math"]}, reply)
                self.assertNotIn(GUIDANCE, messages[0]["content"])

    def test_registered_python_bare_expression_and_print(self):
        registry = ToolRegistry()
        registry.register_python_math()
        for code, expected in (("value = 6 * 8\nvalue", ""),
                               ("value = 6 * 8\nprint(value)", "48")):
            with self.subTest(code=code):
                result = registry.invoke("python_math", {"code": code})
                self.assertEqual("success", result.status)
                self.assertEqual(expected, result.value)

    def test_checkpoint_preserves_pending_code_and_receipt_sources(self):
        from tests.test_solver_harness_reasoner_checkpoint import checkpoint

        proposal = {"tool": "python_math", "arguments": {"code": "value = 6 * 8\nvalue"},
                    "scope": "finite_computation"}
        reply = checkpoint(tool_request=proposal)
        request = {"role": "reasoner", "problem": "A generic task",
                   "checkpoint_protocol": True, "current_goal": "derive",
                   "checkpoint_remaining_rounds": 1, "allowed_tools": ["python_math"],
                   "valid_sources": [{"receipt_id": "prior", "output": ""}]}
        messages, _ = self.transmit(request, reply)
        self.assertIn(GUIDANCE, messages[0]["content"])
        context = json.loads(messages[-1]["content"])
        self.assertEqual(request["valid_sources"], context["valid_sources"])
        self.assertEqual("value = 6 * 8\nvalue", proposal["arguments"]["code"])
