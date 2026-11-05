import unittest

from showcase.solver_harness import ScriptedModelPort, SolverHarness


class MetaTest(unittest.TestCase):
    def test_decision_is_persisted_and_tools_are_empty(self):
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
        with SolverHarness(meta_port=port) as harness:
            result = harness.solve("prove", {"run_id": "meta", "meta_trigger": "plan-blocked"})
            self.assertEqual("partial_aborted", result["state"]["status"])
            self.assertEqual(result, harness.get_run("meta"))
        self.assertEqual([], port.requests[0]["allowed_tools"])
        self.assertEqual("meta:meta", port.requests[0]["session_key"])

    def test_history_survives_versions_and_new_harness_and_isolates_runs(self):
        import tempfile
        from pathlib import Path

        decision = {
            "decision": "CONTINUE",
            "reason_summary": "proceed",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.db"
            with SolverHarness(
                database_path=database, meta_port=ScriptedModelPort([decision])
            ) as harness:
                run = harness.solve("prove", {"run_id": "one", "meta_trigger": "plan-blocked"})
                harness.commit_event(
                    "one",
                    expected_revision=run["state_revision"],
                    event={"event_id": "plan2", "type": "plan_changed"},
                    state_updates={"plan_version": 2},
                )
            port = ScriptedModelPort([decision, decision])
            with SolverHarness(database_path=database, meta_port=port) as harness:
                run = harness.solve("prove", {"run_id": "one", "meta_trigger": "plan-blocked"})
                self.assertEqual(4, len(run["state"]["meta_history"]))
                harness.solve("other", {"run_id": "two", "meta_trigger": "plan-blocked"})
            self.assertEqual(2, port.requests[0]["plan_version"])
            self.assertEqual(2, len(port.requests[0]["history"]))
            self.assertEqual([], port.requests[1]["history"])

    def test_failures_get_actionable_guidance_without_state_access(self):
        for failure in ("timeout", "code_issue", "stuck"):
            with self.subTest(failure=failure):
                port = ScriptedModelPort(
                    [
                        {
                            "action_type": "retry_different_method",
                            "specific_task": "derive a symbolic bound",
                            "use_pure_reasoning": True,
                            "trace_back_to": None,
                            "rationale": "avoid computation",
                        }
                    ]
                )
                with SolverHarness(meta_port=port) as harness:
                    result = harness.solve("prove", {"meta_guidance": {"failure_type": failure}})
                self.assertEqual("STEP_EXECUTE", result["state"]["phase"])
                self.assertEqual({"allow": []}, result["state"]["tool_policy"])
                self.assertEqual(
                    "derive a symbolic bound",
                    result["state"]["meta_guidance_decision"]["specific_task"],
                )
                self.assertNotIn("meta_decision", result["state"])
                self.assertEqual("derive a symbolic bound", result["state"]["pending_guidance_task"])
                self.assertNotIn("state", port.requests[0])

    def test_invalid_response_is_audited_and_does_not_route(self):
        with SolverHarness(meta_port=ScriptedModelPort([{"decision": "ABORT"}])) as harness:
            result = harness.solve("prove", {"meta_trigger": "plan-blocked"})
        self.assertEqual("SETUP", result["state"]["phase"])
        self.assertEqual("meta_invalid", result["events"][-1]["type"])

    def test_stream_usage_sidecar_does_not_invalidate_meta_and_remains_in_call_audit(self):
        decision = {
            "decision": "CONTINUE",
            "reason_summary": "proceed",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": None,
        }
        usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
        class StreamingMetaPort(ScriptedModelPort):
            def complete(self, request):
                response = super().complete(request)
                request["transport_decision_observer"](
                    {"transport": "stream", "policy": "legacy"}, request
                )
                return iter([{"result": response, "usage": usage}])

        port = StreamingMetaPort([decision])
        with SolverHarness(
            meta_port=port, config={"features": {"stream_recovery": True}}
        ) as harness:
            result = harness.solve("prove", {"run_id": "usage-meta", "meta_trigger": "plan-blocked"})

        self.assertEqual("meta_decided", result["events"][-1]["type"])
        committed = result["state"]["meta_decision"]
        self.assertEqual(decision, {key: committed[key] for key in decision})
        self.assertNotIn("usage", committed)
        call = next(iter(result["state"]["calls"].values()))
        self.assertEqual(usage, call["usage"])
        self.assertEqual(usage, call["response"]["usage"])

    def test_verified_intern_stream_keeps_usage_outside_meta_business_schema(self):
        import json

        from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT
        from showcase.solver_harness.intern_port import InternModelPort

        decision = {
            "decision": "CONTINUE",
            "reason_summary": "proceed",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": None,
        }
        usage = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}

        class MockInternStreamAdapter:
            model_id = "intern-s2"
            temperature = 0.2
            max_tokens = 32768
            thinking_mode = False

            class Client:
                model = "intern-s2"
                api_base = INTERN_S2_LIVE_ENDPOINT

            def __init__(self, response):
                self.client = self.Client()
                self.response = response

            def _get_client(self):
                return self.client

            def stream_complete(self, messages, *, metadata=None):
                yield {"type": "text_delta", "text": json.dumps(self.response)}
                yield {
                    "type": "result",
                    "text": json.dumps(self.response),
                    "model": self.model_id,
                    "finish_reason": "stop",
                    "usage": usage,
                }

        for response, expected_event in (
            (decision, "meta_decided"),
            ({**decision, "unexpected_business_field": "value"}, "protocol_failure_unrepaired"),
        ):
            with self.subTest(expected_event=expected_event), SolverHarness(
                meta_port=InternModelPort(
                    MockInternStreamAdapter(response), original_problem="prove",
                    transport_policy="stream_first"
                ),
                config={"features": {"stream_recovery": True}},
            ) as harness:
                result = harness.solve(
                    "prove", {"run_id": f"verified-stream-{expected_event}", "meta_trigger": "plan-blocked"}
                )

            event_types = [event["type"] for event in result["events"]]
            self.assertEqual(expected_event, event_types[-1])
            call = next(iter(result["state"]["calls"].values()))
            self.assertEqual("stream", call["transport_decision"]["transport"])
            if expected_event == "meta_decided":
                self.assertEqual(usage, call["usage"])
                committed = result["state"]["meta_decision"]
                self.assertEqual(decision, {key: committed[key] for key in decision})
                self.assertNotIn("usage", result["state"]["meta_decision"])
            else:
                self.assertEqual("invalid_role_schema", call["error_category"])
                self.assertEqual("protocol_failed", call["status"])
                self.assertNotIn("meta_decision", result["state"])

    def test_nonstream_usage_and_unknown_business_fields_are_rejected(self):
        decision = {
            "decision": "CONTINUE",
            "reason_summary": "proceed",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": None,
        }
        responses = [
            {**decision, "usage": {"total_tokens": 1}},
            {**decision, "unexpected_business_field": "value"},
            {**decision, "decision": "UNREGISTERED"},
        ]
        for index, response in enumerate(responses):
            with self.subTest(index=index), SolverHarness(
                meta_port=ScriptedModelPort([response]),
                config={"features": {"stream_recovery": True}},
            ) as harness:
                result = harness.solve("prove", {"run_id": f"invalid-meta-{index}", "meta_trigger": "plan-blocked"})
                self.assertEqual("meta_invalid", result["events"][-1]["type"])

    def test_absent_port_makes_no_meta_dispatch(self):
        with SolverHarness() as harness:
            result = harness.solve("prove", {"meta_trigger": "plan-blocked"})
        self.assertEqual(["run_initialized"], [event["type"] for event in result["events"]])

    def test_strict_decisions_route_without_replacing_plan(self):
        plan = {"version": 1, "steps": [{"step_id": "s1", "title": "derive", "objective": "bound"}]}
        for action, phase in [
            ("CONTINUE", "STEP_EXECUTE"),
            ("TRACE_BACK", "TRACE_BACK"),
            ("APPROVE_REPLAN", "REPLAN"),
        ]:
            with self.subTest(action=action):
                decision = {
                    "decision": action,
                    "reason_summary": "bounded intervention",
                    "plan_summary": "use a bound",
                    "forbidden_directions": ["numeric search"],
                    "reusable_results": [],
                    "trace_back_to": 1 if action == "TRACE_BACK" else None,
                }
                with SolverHarness(meta_port=ScriptedModelPort([decision])) as harness:
                    run = harness.solve("prove", {"run_id": action})
                    harness.commit_event(
                        action,
                        expected_revision=run["state_revision"],
                        event={"event_id": "plan", "type": "plan_supplied"},
                        state_updates={"plan": plan, "plan_version": 1, "current_step": "s1"},
                    )
                    result = harness.solve(
                        "prove", {"run_id": action, "meta_trigger": "plan-blocked"}
                    )
                self.assertEqual(phase, result["state"]["phase"])
                self.assertEqual(plan, result["state"]["plan"])
                self.assertEqual(1, result["state"]["plan_version"])

    def test_meta_cannot_mutate_run_through_request(self):
        class MutatingPort:
            def complete(self, request):
                request["history"].append({"role": "assistant", "decision": "forged"})
                request["failures"].append({"forged": True})
                return {
                    "decision": "ABORT",
                    "reason_summary": "stop",
                    "plan_summary": "",
                    "forbidden_directions": [],
                    "reusable_results": [],
                    "trace_back_to": None,
                }

        with SolverHarness(meta_port=MutatingPort()) as harness:
            result = harness.solve("prove", {"meta_trigger": "plan-blocked"})
        self.assertEqual([], result["state"]["failure_records"])
        self.assertEqual(2, len(result["state"]["meta_history"]))

    def test_terminal_run_cannot_be_reopened(self):
        decision = {
            "decision": "ABORT",
            "reason_summary": "stop",
            "plan_summary": "",
            "forbidden_directions": [],
            "reusable_results": [],
            "trace_back_to": None,
        }
        port = ScriptedModelPort([decision])
        with SolverHarness(meta_port=port) as harness:
            first = harness.solve("prove", {"run_id": "terminal", "meta_trigger": "plan-blocked"})
            second = harness.solve("prove", {"run_id": "terminal", "meta_trigger": "plan-blocked"})
        self.assertEqual(first, second)
        self.assertEqual(1, len(port.requests))

    def test_meta_budget_exhaustion_is_explicit_without_dispatch(self):
        port = ScriptedModelPort([])
        with SolverHarness(meta_port=port, config={"max_model_calls": 0}) as harness:
            result = harness.solve("prove", {"meta_trigger": "plan-blocked"})
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        self.assertEqual(
            "model_call_budget_exhausted", result["state"]["budget"]["exhaustion_reason"]
        )
        self.assertEqual([], port.requests)
