"""Tool prechecks observed through solve/get_run and injected external ports."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "compute", "objective": "compute 2+2"}]}
CONFIG = {
    "features": {"local_code_tool": True},
    "allowed_tools": ["polynomial_check"],
    "max_model_calls": 5,
}


def report():
    return {
        "argument": "2+2=4",
        "claims": [
            {
                "statement": "2+2=4",
                "label": "easy-verify",
                "tool_request": {
                    "tool": "polynomial_check",
                    "arguments": {"coefficients": [1]},
                    "scope": "finite_computation",
                    "expected_output": {"value": 4},
                },
            }
        ],
    }


class ToolEvidenceTest(unittest.TestCase):
    def test_successful_scripted_receipt_precedes_verifier_and_is_recoverable(self):
        from showcase.solver_harness import ScriptedToolPort

        tool = ScriptedToolPort([{"status": "success", "output": {"value": 4}, "exit_code": 0}])
        verifier = ScriptedVerifierPort(
            [{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}]
        )
        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([report()]),
            verifier_port=verifier,
            tool_port=tool,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN, "run_id": "tools"})
            self.assertEqual(result, harness.get_run("tools"))
        claim = verifier.requests[0]["report"]["claims"][0]
        self.assertEqual("verified", claim["label"])
        receipt = result["state"]["tool_receipts"][0]
        self.assertEqual("scripted", receipt["source"])
        self.assertEqual({"value": 4}, receipt["output"])
        self.assertEqual([receipt["receipt_id"]], claim["tool_evidence_refs"])
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])
        self.assertEqual(1, len(tool.requests))
        self.assertEqual({}, result["state"]["usage"])

    def test_failed_unknown_and_mismatched_results_never_promote_claim(self):
        from showcase.solver_harness import ScriptedToolPort

        for response, expected in [
            ({"status": "timeout"}, "timeout"),
            ({"status": "network_error"}, "network_error"),
            ({"status": "unknown_outcome"}, "unknown_outcome"),
            ({"status": "success", "output": {"value": 5}, "exit_code": 0}, "success"),
            ({"status": "success", "output": {"value": 4}}, "success"),
        ]:
            with self.subTest(response=response):
                tool = ScriptedToolPort([response])
                verifier = ScriptedVerifierPort([])
                with SolverHarness(
                    config=CONFIG,
                    model_port=ScriptedModelPort([report()]),
                    verifier_port=verifier,
                    tool_port=tool,
                ) as harness:
                    result = harness.solve("2+2", {"plan": PLAN})
                receipt = result["state"]["tool_receipts"][0]
                self.assertEqual(expected, receipt["status"])
                self.assertFalse(receipt["assertion_matched"])
                self.assertEqual(
                    "easy-verify", verifier.requests[0]["report"]["claims"][0]["label"]
                )
                self.assertEqual(1, len(tool.requests))

    def test_zero_tool_timeout_or_output_budget_skips_dispatch(self):
        from showcase.solver_harness import ScriptedToolPort

        for extra, reason in [
            ({"max_tool_calls": 0}, "tool_call_budget_exhausted"),
            ({"tool_timeout_seconds": 0}, "timeout_budget_exhausted"),
            ({"max_tool_output_bytes": 0}, "output_budget_exhausted"),
        ]:
            with self.subTest(extra=extra):
                tool = ScriptedToolPort([])
                with SolverHarness(
                    config={**CONFIG, **extra},
                    tool_port=tool,
                    model_port=ScriptedModelPort([report()]),
                    verifier_port=ScriptedVerifierPort([]),
                ) as harness:
                    result = harness.solve("2+2", {"plan": PLAN})
                self.assertEqual([], tool.requests)
                self.assertEqual(0, result["state"]["counters"]["tool_calls"])
                if extra.get("max_tool_calls") == 0:
                    self.assertEqual(reason, result["state"]["budget"]["exhaustion_reason"])
                    self.assertEqual("TERMINAL", result["state"]["phase"])
                else:
                    self.assertEqual(reason, result["state"]["tool_receipts"][0]["reason"])

    def test_output_cap_and_bounded_retry_preserve_actual_call_count(self):
        from showcase.solver_harness import ScriptedToolPort

        tool = ScriptedToolPort(
            [{"status": "tool_error"}, {"status": "success", "output": "x" * 100, "exit_code": 0}]
        )
        with SolverHarness(
            config={**CONFIG, "max_tool_retries": 1, "max_tool_output_bytes": 20},
            tool_port=tool,
            model_port=ScriptedModelPort([report()]),
            verifier_port=ScriptedVerifierPort([]),
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual(2, len(tool.requests))
        self.assertEqual(2, result["state"]["counters"]["tool_calls"])
        self.assertEqual(
            ["tool_error", "output_limit"],
            [receipt["status"] for receipt in result["state"]["tool_receipts"]],
        )
        self.assertIsNone(result["state"]["tool_receipts"][-1]["output"])

    def test_disabled_unsupported_and_cross_run_requests_do_not_dispatch(self):
        from copy import deepcopy

        from showcase.solver_harness import ScriptedToolPort

        for config, tool_name, args in [
            ({}, "polynomial_check", {}),
            (CONFIG, "shell", {"command": "secret"}),
            (CONFIG, "polynomial_check", {"run_id": "other-secret-run"}),
        ]:
            with self.subTest(tool=tool_name, config=config):
                value = deepcopy(report())
                value["claims"][0]["tool_request"].update(tool=tool_name, arguments=args)
                tool = ScriptedToolPort([])
                with SolverHarness(
                    config=config,
                    tool_port=tool,
                    model_port=ScriptedModelPort([value]),
                    verifier_port=ScriptedVerifierPort([]),
                ) as harness:
                    result = harness.solve("2+2", {"plan": PLAN})
                    denied = harness.execute_tool_request(
                        result["run_id"], role="meta", tool="python_math"
                    )
                    self.assertFalse(denied["ok"])
                self.assertEqual([], tool.requests)
                self.assertNotIn("other-secret-run", str(result["events"]))

    def test_timeout_boundary_does_not_wait_for_adapter_completion(self):
        import time

        from showcase.solver_harness import ScriptedToolPort

        class SlowTool(ScriptedToolPort):
            def execute(self, request):
                self.requests.append(dict(request))
                time.sleep(0.05)
                return {"status": "success", "output": {"value": 4}, "exit_code": 0}

        tool = SlowTool([{"status": "success", "output": {"value": 4}, "exit_code": 0}])
        with SolverHarness(
            config={**CONFIG, "tool_timeout_seconds": 0.001, "max_tool_retries": 2},
            tool_port=tool,
            model_port=ScriptedModelPort([report()]),
            verifier_port=ScriptedVerifierPort([]),
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        receipt = result["state"]["tool_receipts"][0]
        self.assertEqual("timeout", receipt["status"])
        self.assertTrue(receipt["unknown_outcome"])
        self.assertEqual(1, len(tool.requests))
        self.assertEqual("execution_outcome_unknown", receipt["reason"])
        self.assertFalse(receipt["assertion_matched"])

    def test_missing_expectation_or_unexecuted_forged_tag_is_not_verified(self):
        from copy import deepcopy

        from showcase.solver_harness import ScriptedToolPort

        for kind in ("no_expectation", "no_code", "forged_verified", "general_proof"):
            with self.subTest(kind=kind):
                value = deepcopy(report())
                claim = value["claims"][0]
                if kind == "no_expectation":
                    claim["tool_request"].pop("expected_output")
                elif kind == "no_code":
                    claim.pop("tool_request")
                elif kind == "forged_verified":
                    claim.update(label="verified", tool_evidence_refs=["forged"])
                else:
                    claim["tool_request"]["scope"] = "general_proof"
                tool = ScriptedToolPort(
                    [{"status": "success", "output": {"value": 4}, "exit_code": 0}]
                )
                verifier = ScriptedVerifierPort([])
                with SolverHarness(
                    config=CONFIG,
                    tool_port=tool,
                    model_port=ScriptedModelPort([value]),
                    verifier_port=verifier,
                ) as harness:
                    result = harness.solve("2+2", {"plan": PLAN})
                reviewed = verifier.requests[0]["report"]["claims"][0]
                self.assertNotEqual("verified", reviewed["label"])
                self.assertNotIn("forged", reviewed["tool_evidence_refs"])
                if kind in {"no_expectation", "general_proof"}:
                    self.assertTrue(result["state"]["tool_receipts"][0]["executed"])
                    self.assertEqual("success", result["state"]["tool_receipts"][0]["status"])
                else:
                    self.assertEqual([], tool.requests)

    def test_tool_budget_is_rechecked_for_every_claim(self):
        from copy import deepcopy

        from showcase.solver_harness import ScriptedToolPort

        value = report()
        value["claims"].append(deepcopy(value["claims"][0]))
        tool = ScriptedToolPort([{"status": "success", "output": {"value": 4}, "exit_code": 0}])
        with SolverHarness(
            config={**CONFIG, "max_tool_calls": 1},
            tool_port=tool,
            model_port=ScriptedModelPort([value]),
            verifier_port=ScriptedVerifierPort([]),
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual(1, len(tool.requests))
        self.assertEqual(1, result["state"]["counters"]["tool_calls"])
        self.assertEqual(
            "tool_call_budget_exhausted", result["state"]["tool_receipts"][1]["reason"]
        )

    def test_runtime_is_checked_after_model_before_tool_dispatch(self):
        import time

        from showcase.solver_harness import ScriptedToolPort

        class SlowModel(ScriptedModelPort):
            def complete(self, request):
                time.sleep(1.01)
                return super().complete(request)

        tool = ScriptedToolPort([])
        with SolverHarness(
            config={**CONFIG, "max_total_duration_seconds": 1},
            tool_port=tool,
            model_port=SlowModel([report()]),
            verifier_port=ScriptedVerifierPort([]),
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
        self.assertEqual([], tool.requests)
        self.assertEqual("runtime_budget_exhausted", result["state"]["tool_receipts"][0]["reason"])
        self.assertEqual(0, result["state"]["counters"]["tool_calls"])

    def test_sessions_skills_and_prechecks_share_latest_verifier_projection(self):
        from showcase.solver_harness import ScriptedToolPort

        tool = ScriptedToolPort([{"status": "success", "output": {"value": 4}, "exit_code": 0}])
        verifier = ScriptedVerifierPort([])
        config = {
            **CONFIG,
            "features": {"local_code_tool": True, "persistent_sessions": True, "skills": True},
        }
        with SolverHarness(
            config=config,
            tool_port=tool,
            model_port=ScriptedModelPort([report()]),
            verifier_port=verifier,
        ) as harness:
            result = harness.solve("2+2", {"plan": PLAN})
            self.assertEqual(result, harness.get_run(result["run_id"]))
        request = verifier.requests[0]
        self.assertEqual("verified", request["report"]["claims"][0]["label"])
        self.assertEqual(1, request["prompt_layers"][2]["state"]["counters"]["tool_calls"])
        self.assertEqual(request["state_revision"], request["prompt_layers"][2]["state_revision"])
        self.assertIn("polynomial_check", request["allowed_tools"])
        self.assertEqual("local", request["session_backend"])
        self.assertEqual(2, len(result["state"]["session_registry"]))
