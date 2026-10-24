"""Intern transmission observed through public Solver Harness ports."""

import json
import unittest

from showcase.adapters import InternModelAdapter
from showcase.solver_harness import SolverHarness


class FakeClient:
    model = "intern-test"

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def chat(self, messages, **kwargs):
        self.requests.append((messages, kwargs))
        return self.replies.pop(0)


class InternPortTest(unittest.TestCase):
    def test_original_problem_context_and_provider_metadata_survive_port(self):
        from showcase.solver_harness.intern_port import InternModelPort

        client = FakeClient(
            [
                {
                    "content": json.dumps(
                        {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
                    ),
                    "model": "intern-returned",
                    "finish_reason": "stop",
                    "usage": {"prompt_tokens": 12, "completion_tokens": 10, "total_tokens": 22},
                }
            ]
        )
        port = InternModelPort(
            InternModelAdapter(client), original_problem="solve x squared minus one"
        )
        with SolverHarness(model_port=port, config={"features": {"skills": True}}) as harness:
            run = harness.solve("solve x squared minus one")
            self.assertEqual(run, harness.get_run(run["run_id"]))
        self.assertEqual("PLAN", run["state"]["phase"])
        sent = json.dumps(client.requests[0][0])
        self.assertIn("solve x squared minus one", sent)
        self.assertIn("exploration-protocol", sent)
        self.assertIn("state_revision", sent)
        self.assertEqual(22, port.invocations[0]["usage"]["total_tokens"])
        self.assertEqual("intern-returned", port.invocations[0]["returned_model"])
        self.assertIsNone(port.invocations[0]["usage"]["reasoning_tokens"])

    def test_strict_errors_retain_finish_attempts_and_unknown_usage(self):
        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        attempt = {
            "attempt_id": "fake-attempt",
            "logical_call_id": "fake-call",
            "status": "success",
            "request_model_id": "intern-test",
            "response_model_id": "returned",
            "response_id": "provider-id",
            "finish_reason": "length",
            "usage": {"total_tokens": 17},
        }
        cases = [
            (
                {"content": "{}", "finish_reason": "length", "attempts": [attempt]},
                "truncated_response",
            ),
            ({"content": "not-json", "finish_reason": "stop"}, "invalid_json"),
            (
                {"content": '{"assessment":"SOLVED"}', "finish_reason": "stop"},
                "invalid_role_schema",
            ),
            ({"content": "", "finish_reason": "stop"}, "empty_response"),
        ]
        for raw, expected in cases:
            with self.subTest(expected=expected):
                port = InternModelPort(InternModelAdapter(FakeClient([raw])))
                with SolverHarness(model_port=port) as harness:
                    with self.assertRaises(InternPortError):
                        harness.solve("public", {"run_id": "failed"})
                    self.assertEqual("EXPLORE", harness.get_run("failed")["state"]["phase"])
                record = port.invocations[0]
                self.assertEqual(expected, record["error_category"])
                self.assertIsNone(record["usage"]["total_tokens"])
                if expected == "truncated_response":
                    self.assertEqual("fake-attempt", record["request_attempts"][0]["attempt_id"])
                    self.assertEqual(
                        "provider-id", record["request_attempts"][0]["provider_request_id"]
                    )
                    self.assertEqual("{}", record["response"])

    def test_adapter_failure_attempts_are_retained_without_exception_details(self):
        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        class ProviderFailure(RuntimeError):
            category = "network"
            attempts = [
                {"attempt_id": "failed-attempt", "status": "error", "error_category": "network"}
            ]

        class FailingClient(FakeClient):
            def chat(self, messages, **kwargs):
                raise ProviderFailure("Authorization=private-value")

        port = InternModelPort(InternModelAdapter(FailingClient([])))
        with self.assertRaises(InternPortError):
            port.complete({"role": "explore", "problem": "public", "run_id": "safe"})
        record = port.invocations[0]
        self.assertEqual("network", record["error_category"])
        self.assertEqual("failed-attempt", record["request_attempts"][0]["attempt_id"])
        self.assertNotIn("private-value", str(record))

    def test_model_generated_tool_request_receipt_reaches_verifier_and_final_review(self):
        from showcase.solver_harness import RegistryToolPort
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.tools import ToolRegistry

        arguments = {
            "schema_version": 1,
            "variable": "x",
            "coefficients": ["1", "0", "-1"],
            "domain": {"kind": "real"},
            "candidates": ["-1", "1"],
        }
        replies = [
            {
                "argument": "(x-1)(x+1)=0",
                "blocked": False,
                "claims": [
                    {
                        "statement": "Candidates -1 and 1 satisfy the equation",
                        "label": "easy-verify",
                        "tool_request": {
                            "tool": "polynomial_check",
                            "arguments": arguments,
                            "scope": "finite_computation",
                        },
                    }
                ],
            },
            {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
            {"final_response": "The real roots are -1 and 1 by factorization."},
            {"verdict": "ACCEPT"},
        ]
        client = FakeClient(
            [
                {"content": json.dumps(value), "finish_reason": "stop", "model": "fake-returned"}
                for value in replies
            ]
        )
        port = InternModelPort(InternModelAdapter(client), original_problem="Solve x^2-1=0")
        registry = ToolRegistry()
        registry.register_polynomial_check()
        config = {
            "features": {
                "local_code_tool": True,
                "skills": True,
                "persistent_sessions": True,
                "final_generation": True,
                "final_solution_review": True,
            },
            "allowed_tools": ["polynomial_check"],
            "max_model_calls": 6,
        }
        plan = {
            "version": 1,
            "steps": [
                {"step_id": "roots", "title": "derive", "objective": "derive and check roots"}
            ],
        }
        with SolverHarness(
            config=config, model_port=port, verifier_port=port, tool_port=RegistryToolPort(registry)
        ) as harness:
            result = harness.solve("Solve x^2-1=0", {"plan": plan})
            self.assertEqual(result, harness.get_run(result["run_id"]))
        self.assertEqual("completed_llm_reviewed", result["state"]["status"])
        receipt = result["state"]["tool_receipts"][0]
        self.assertEqual("pass", receipt["output"]["candidate_status"])
        self.assertEqual([receipt["receipt_id"]], port.invocations[1]["consumed_receipt_ids"])
        self.assertIn(receipt["receipt_id"], json.dumps(client.requests[1][0]))
        self.assertEqual(
            ["reasoner", "step_verifier", "final_generator", "whole_solution_verifier"],
            [record["role"] for record in port.invocations],
        )

    def test_default_port_never_constructs_network_client(self):
        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        with self.assertRaisesRegex(InternPortError, "live_not_enabled"):
            InternModelPort().complete({"role": "explore", "problem": "public"})

    def test_nullable_optional_tool_request_keeps_model_generated_pending_request(self):
        from showcase.solver_harness.intern_port import InternModelPort

        value = {
            "argument": "factor",
            "blocked": False,
            "claims": [
                {"statement": "factorization", "label": "hard-verify", "tool_request": None},
                {
                    "statement": "candidate substitution",
                    "label": "easy-verify",
                    "tool_request": {
                        "tool": "polynomial_check",
                        "arguments": {"schema_version": 1},
                        "scope": "finite_computation",
                    },
                },
            ],
        }
        port = InternModelPort(
            InternModelAdapter(
                FakeClient([{"content": json.dumps(value), "finish_reason": "stop"}])
            )
        )
        result = port.complete({"role": "reasoner", "problem": "public"})
        self.assertEqual(value, result)

    def test_enabled_stream_recovery_audits_adapter_schema_error_without_empty_report(self):
        from showcase.solver_harness.intern_port import InternModelPort

        port = InternModelPort(
            InternModelAdapter(FakeClient([{"content": "{}", "finish_reason": "stop"}]))
        )
        with SolverHarness(
            model_port=port, config={"features": {"stream_recovery": True}}
        ) as harness:
            result = harness.solve("public", {"run_id": "interrupted"})
            self.assertEqual(result, harness.get_run("interrupted"))
        # ALIGN-04: the complete schema-invalid reply is a known protocol
        # failure that ends dispatch honestly, not an interrupted unknown.
        self.assertEqual("partial_aborted", result["state"]["status"])
        self.assertEqual("TERMINAL", result["state"]["phase"])
        self.assertEqual([], result["state"]["exploration_findings"])
        call = next(iter(result["state"]["calls"].values()))
        self.assertEqual("protocol_failed", call["status"])
        self.assertEqual("invalid_role_schema", port.invocations[0]["error_category"])

    def test_evidence_runner_uses_physical_attempt_budget_and_terminal_safe_audit(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from llm_client import InternChatClient
        from showcase.solver_harness.intern_evidence import run_evidence

        class MalformedResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "id": "offline-provider",
                    "model": "offline-intern",
                    "choices": [{"finish_reason": "stop", "message": {"content": "{}"}}],
                }

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}),
            patch("llm_client.requests.post", return_value=MalformedResponse()) as post,
        ):
            adapter = InternModelAdapter(
                InternChatClient(timeout=30, retry=1),
                max_tokens=1024,
                client_timeout=30,
                client_retry=1,
            )
            folder, report = run_evidence(
                adapter, Path(directory), execution_source="offline_injected", followup=True
            )
            snapshot = json.loads((folder / "run.json").read_text(encoding="utf-8"))
        # The probe config enables star_routing, so the explore entry takes its
        # one bounded format repair (ALIGN-10 round 2): both physical attempts
        # receive the same schema-invalid body and the run still ends as a
        # known protocol failure, never an interrupted unknown outcome.
        self.assertEqual(2, post.call_count)
        self.assertEqual(2, report["budget"]["http_attempts"])
        self.assertEqual(4, report["budget"]["limits"]["max_http_attempts"])
        self.assertEqual(1, report["budget"]["limits"]["max_tool_calls"])
        self.assertEqual(120, report["budget"]["limits"]["max_runtime_seconds"])
        self.assertIsNone(report["invocations"][0]["usage"]["total_tokens"])
        self.assertEqual("partial_aborted", report["final_status"])
        self.assertEqual("needs_review", report["status"])
        event = snapshot["events"][-1]
        self.assertEqual("intern_evidence_recorded", event["type"])
        self.assertEqual(report["run_id"], event["invocations"][0]["run_id"])
        self.assertEqual({}, snapshot["state"]["usage"])
