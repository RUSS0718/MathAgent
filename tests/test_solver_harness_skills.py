"""Public invocation contracts for opt-in protocol composition."""

import unittest
from showcase.solver_harness import ScriptedModelPort, SolverHarness


class SkillsTest(unittest.TestCase):
    def test_explore_loads_only_triggered_protocol_at_current_revision(self):
        port = ScriptedModelPort([{"assessment": "NEED_PLAN"}])
        with SolverHarness(model_port=port, config={"features": {"skills": True}}) as harness:
            result = harness.solve("求解", {"run_id": "skills"})
            self.assertEqual(result, harness.get_run("skills"))
        request = port.requests[0]
        self.assertEqual(["exploration-protocol"], request["active_skill_ids"])
        self.assertEqual(request["state_revision"], request["prompt_layers"][2]["state_revision"])
        self.assertEqual(3, len(request["prompt_layers"]))
        self.assertTrue(request["prompt_fingerprint"])

    def test_disabled_keeps_original_request(self):
        port = ScriptedModelPort([{"assessment": "NEED_PLAN"}])
        with SolverHarness(model_port=port) as harness:
            harness.solve("求解")
        self.assertNotIn("prompt_layers", port.requests[0])

    def test_triggered_protocol_contracts_and_meta_runtime_policy(self):
        with SolverHarness(config={"features": {"skills": True}}) as harness:
            run = harness.solve("求解", {"run_id": "source"})
            request = harness.prepare_request(
                run,
                {
                    "role": "meta",
                    "suspected_false_claim": True,
                    "tool_failure": "timeout",
                },
            )
            self.assertEqual(
                [
                    "meta-intervention-protocol",
                    "math-solving-strategies",
                    "construct-counterexamples",
                    "code-issue-resolution",
                ],
                request["active_skill_ids"],
            )
            self.assertEqual([], request["allowed_tools"])
            for protocol in request["prompt_layers"][1]["protocols"]:
                for field in ("trigger", "input", "output", "instructions"):
                    self.assertTrue(protocol[field])
            denied = harness.execute_tool_request("source", role="meta", tool="shell")
            self.assertFalse(denied["ok"])
            read = harness.execute_tool_request("source", role="reasoner", tool="read_state")
            self.assertTrue(read["ok"])
            self.assertNotIn("problem", read["result"])
            denied = harness.execute_tool_request(
                "source",
                role="reasoner",
                tool="read_ledger",
                arguments={"run_id": "secret-other-run", "token": "credential"},
            )
            self.assertEqual("cross_run_denied", denied["reason"])
            audit = str(harness.get_run("source")["events"])
            self.assertNotIn("secret-other-run", audit)
            self.assertNotIn("credential", audit)

    def test_report_and_verifier_requests_load_both_review_protocols(self):
        from showcase.solver_harness import ScriptedVerifierPort

        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "求值", "objective": "求值"}]}
        model = ScriptedModelPort([{"argument": "4", "claims": []}])
        verifier = ScriptedVerifierPort(
            [{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}]
        )
        with SolverHarness(
            config={"features": {"skills": True}, "max_model_calls": 5},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            harness.solve("2+2", {"plan": plan})
        self.assertEqual(["verification-tag-protocol"], model.requests[0]["active_skill_ids"])
        self.assertEqual(
            ["verifier-review-protocol", "verification-tag-protocol"],
            verifier.requests[0]["active_skill_ids"],
        )

    def test_meta_dispatch_composes_protocols_with_no_tools(self):
        port = ScriptedModelPort(
            [
                {
                    "decision": "ABORT",
                    "reason_summary": "blocked",
                    "plan_summary": "",
                    "forbidden_directions": [],
                    "reusable_results": [],
                    "trace_back_to": None,
                }
            ]
        )
        with SolverHarness(meta_port=port, config={"features": {"skills": True}}) as harness:
            result = harness.solve("prove", {"meta_trigger": "plan-blocked"})
            self.assertEqual(result, harness.get_run(result["run_id"]))
        request = port.requests[0]
        self.assertEqual(
            ["meta-intervention-protocol", "math-solving-strategies"], request["active_skill_ids"]
        )
        self.assertEqual([], request["allowed_tools"])
        self.assertEqual({"allow": []}, request["tool_policy"])
        self.assertEqual(request["state_revision"], request["prompt_layers"][2]["state_revision"])
