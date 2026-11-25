"""Offline acceptance for the integrated RiCL mechanism path."""

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from test_runtime_math_verification import ANSWER, CHECKS, PROBLEM, increment
from test_runtime_online_search import CANDIDATES, captured_route

from ricl_runtime import Runtime
from ricl_runtime.experiments import run_mechanism_ablation, summarize_mechanism_run
from ricl_runtime.port import ModelPortFailure, ModelReply, ToolCall, ToolReceipt

DIAGNOSIS = json.dumps({
    "hypothesis": "The squared constraint used the wrong constant term.",
    "strategy": "Recompute the squared polynomial before testing candidates.",
})
BAD_CONSTRAINT = {**CHECKS[1], "coefficients": ["1", "-1", "-5"]}


def measured(text: str, input_tokens: int, output_tokens: int) -> ModelReply:
    return ModelReply(
        text,
        model="mechanism-fixture",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        usage_source="fixture",
        cost_usd=0.0,
    )


class MechanismPort:
    """Route prompts by their public task content rather than condition identity."""

    name = "mechanism-fixture"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.route_expansions: Counter[str] = Counter()

    def complete(self, prompt: str) -> ModelReply:
        self.prompts.append(prompt)
        if "Propose 1 to 3 distinct routes" in prompt:
            return measured(CANDIDATES, 3, 2)
        if "return only JSON with two short strings" in prompt:
            return measured(DIAGNOSIS, 1, 2)
        if "Submit only one bounded repair increment" in prompt:
            targeted = "Targeted strategy:" in prompt
            check = CHECKS[1] if targeted else BAD_CONSTRAINT
            return measured(increment(check, answer="One bounded repair increment."), 1, 1)
        route_id = captured_route(prompt)
        if route_id == "route_01":
            reply = measured(
                increment(CHECKS[0], answer="The real-domain condition is established."), 1, 1
            )
            return ModelReply(
                reply.text,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                usage_source=reply.usage_source,
                cost_usd=reply.cost_usd,
                tool_calls=(ToolCall("addition", "1 + 1"),),
            )
        self.route_expansions[route_id] += 1
        if self.route_expansions[route_id] == 1:
            return measured(increment(BAD_CONSTRAINT, answer="The squared constraint is ready."), 5, 5)
        _, _, context = prompt.partition("Previously verified public claims:\n")
        prior = json.loads(context.split("\n\n", 1)[0])
        evidence_ids = [item["evidence_id"] for item in prior]
        response = json.loads(increment(*CHECKS[2:], answer=ANSWER))
        response["used_evidence_ids"] = evidence_ids
        return measured(json.dumps(response), 5, 5)


class MechanismTool:
    def execute(self, invocation_id: str, call: ToolCall) -> ToolReceipt:
        return ToolReceipt(invocation_id, f"{invocation_id}_receipt", call.tool_name, True, "2")


class AblationPort(MechanismPort):
    def __init__(self, condition_id: str) -> None:
        super().__init__()
        self.condition_id = condition_id

    def complete(self, prompt: str) -> ModelReply:
        if "Propose 1 to 3 distinct routes" in prompt:
            return measured(CANDIDATES, 3, 2)
        if "return only JSON with two short strings" in prompt:
            return measured(DIAGNOSIS, 1, 2)
        if "Submit only one bounded repair increment" in prompt:
            check = CHECKS[1] if "Targeted strategy:" in prompt else BAD_CONSTRAINT
            return measured(increment(check, answer="One bounded repair increment."), 1, 1)
        if "Route expansion:\n" in prompt:
            route_id = captured_route(prompt)
            self.route_expansions[route_id] += 1
            if route_id == "route_01" and self.route_expansions[route_id] == 1:
                return measured(increment(CHECKS[0], answer="The real domain is established."), 80, 20)
            if route_id == "route_02" and self.route_expansions[route_id] == 1:
                return measured(increment(BAD_CONSTRAINT, answer="The constraint is ready."), 5, 5)
            if self.condition_id == "ricl-search" and route_id == "route_01":
                raise ModelPortFailure("controlled search interruption")
            checks = CHECKS[1:] if route_id == "route_01" else CHECKS[2:]
            return measured(self._with_prior_evidence(prompt, checks), 5, 5)
        if self.condition_id == "baseline":
            reply = measured(increment(*CHECKS), 5, 5)
            return ModelReply(
                reply.text,
                model=reply.model,
                input_tokens=reply.input_tokens,
                output_tokens=reply.output_tokens,
                usage_source=reply.usage_source,
                cost_usd=reply.cost_usd,
                tool_calls=(ToolCall("addition", "1 + 1"),),
            )
        if self.condition_id == "ricl-state":
            return ModelReply(
                increment(BAD_CONSTRAINT, answer="The constraint is ready."),
                model=self.name,
                input_tokens="unknown",
                output_tokens=5,
                usage_source="fixture",
                cost_usd=0.0,
            )
        if "Previously verified public claims:" not in prompt:
            return measured(increment(BAD_CONSTRAINT, answer="The constraint is ready."), 5, 5)
        return measured(self._with_prior_evidence(prompt, CHECKS[2:]), 5, 5)

    @staticmethod
    def _with_prior_evidence(prompt: str, checks: tuple[dict[str, object], ...]) -> str:
        _, _, context = prompt.partition("Previously verified public claims:\n")
        prior = json.loads(context.split("\n\n", 1)[0])
        response = json.loads(increment(*checks, answer=ANSWER))
        response["used_evidence_ids"] = [item["evidence_id"] for item in prior]
        return json.dumps(response)


class RuntimeMechanismIntegrationTests(unittest.TestCase):
    def test_ablation_rejects_provider_capabilities_before_any_request(self) -> None:
        class LivePort:
            name = "provider-capability"
            provider = "deepseek"

            def complete(self, prompt: str) -> ModelReply:
                raise AssertionError("provider port must not be called")

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "offline ModelPorts only"):
                run_mechanism_ablation(
                    lambda _: LivePort(),
                    PROBLEM,
                    output_root=Path(directory),
                )

    def test_counterfactual_merge_continues_parent_route_with_merged_evidence(self) -> None:
        port = MechanismPort()
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port, tool_executor=MechanismTool()).run(
                PROBLEM,
                online_search="aprs",
                counterfactual_enabled=True,
                tool_call_limit=1,
                model_request_limit=8,
                output_root=Path(directory),
            )
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 8, "used": 7})
        self.assertEqual(run["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertEqual(run["usage"]["tokens"], 34)
        self.assertEqual(len(port.prompts), 7)
        self.assertEqual(trace[0]["trace_schema_version"], 1)
        self.assertNotIn(PROBLEM, json.dumps(trace, ensure_ascii=False))
        self.assertNotIn(ANSWER, json.dumps(trace))
        self.assertNotIn("Study the domain first.", json.dumps(trace))
        self.assertNotIn("The squared constraint used the wrong constant term.", json.dumps(trace))

        decisions = [event for event in trace if event["event"] == "route_selection"]
        self.assertEqual([(event["route_id"], event["strategy"]) for event in decisions], [
            ("route_01", "cold_start"),
            ("route_02", "cold_start"),
            ("route_01", "gain"),
        ])
        for decision in decisions:
            sent = next(
                event for event in trace
                if event["event"] == "model_request_sent"
                and event["request_id"] == decision["request_id"]
            )
            self.assertLess(trace.index(decision), trace.index(sent))
        merge = next(event for event in trace if event["event"] == "counterfactual_merge")
        self.assertEqual(merge["status"], "merged")
        self.assertEqual(len(merge["merged_evidence_ids"]), 1)

        search_completed = next(
            event for event in trace if event["event"] == "online_search_completed"
        )
        self.assertEqual(search_completed["selection_counts"], {"cold_start": 2, "gain": 1})
        route_rows = {row["route_id"]: row for row in search_completed["routes"]}
        merged_evidence_id = merge["merged_evidence_ids"][0]
        merged_credit = next(
            credit for credit in route_rows["route_02"]["credit"]
            if credit["evidence_id"] == merged_evidence_id
        )
        self.assertEqual(merged_credit["attribution"], "intervention_merge")
        self.assertEqual(route_rows["route_02"]["cost"]["tokens"], 27)
        self.assertEqual(route_rows["route_02"]["cost"]["request_ids"], [
            run["provider_requests"][2]["request_id"],
            run["provider_requests"][3]["request_id"],
            run["provider_requests"][4]["request_id"],
            run["provider_requests"][5]["request_id"],
            run["provider_requests"][6]["request_id"],
        ])
        continuation = next(
            event for event in trace
            if event["event"] == "route_continuation_selected"
        )
        self.assertEqual(continuation["route_id"], "route_02")
        self.assertEqual(continuation["selection_strategy"], "gain")
        self.assertEqual(continuation["aprs_selected_route_id"], decisions[-1]["route_id"])
        self.assertEqual(continuation["aprs_selection_overridden"], decisions[-1]["route_id"] != "route_02")
        self.assertEqual(continuation["decision_id"], decisions[-1]["decision_id"])
        self.assertEqual(continuation["checkpoint_id"], merge["checkpoint_id"])
        self.assertEqual(
            continuation["merged_evidence_ids"], merge["merged_evidence_ids"]
        )
        self.assertEqual(
            continuation["reason"], "merged_evidence_reserved_for_parent_route"
        )
        self.assertEqual(
            run["provider_requests"][-1]["request_id"], continuation["request_id"]
        )
        self.assertEqual(run["provider_requests"][-1]["route_id"], "route_02")
        self.assertIn(
            merged_evidence_id,
            run["provider_requests"][-1]["delivered_check_evidence_ids"],
        )

        counterfactual_requests = [
            request for request in run["provider_requests"]
            if str(request.get("request_kind", "")).startswith("counterfactual_")
        ]
        self.assertEqual(len(counterfactual_requests), 4)
        self.assertTrue(all(request["route_id"] == "route_02" for request in counterfactual_requests))
        self.assertEqual([request["request_kind"] for request in run["provider_requests"]], [
            "candidate_generation",
            "route_expansion",
            "route_expansion",
            "counterfactual_diagnosis",
            "counterfactual_arm",
            "counterfactual_arm",
            "counterfactual_continuation",
        ])
        arm_checks = [event for event in trace if event["event"] == "counterfactual_arm_checked"]
        self.assertEqual(
            [event["used"]["local_verifications"] for event in arm_checks],
            [1, 1],
        )
        parent = next(event for event in trace if event["event"] == "counterfactual_parent_action")
        self.assertIn(merged_evidence_id, parent["used_evidence_ids"])
        self.assertLess(
            trace.index(merge),
            next(
                index for index, event in enumerate(trace)
                if event["event"] == "model_request_sent"
                and event["request_id"] == continuation["request_id"]
            ),
        )

    def test_five_ablations_share_runtime_contract_and_leave_recomputable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = run_mechanism_ablation(
                lambda condition_id: AblationPort(condition_id),
                PROBLEM,
                output_root=Path(directory),
                model_request_limit=8,
                tool_call_limit=3,
                token_limit=262_144,
                elapsed_limit_ms=30_000,
                cost_limit_usd=0.1,
                tool_executor_factory=lambda _: MechanismTool(),
            )
            public_path = Path(manifest["public_input_path"])
            evaluation_path = Path(manifest["evaluation_path"])
            public = json.loads(public_path.read_text(encoding="utf-8"))
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
            runs = {
                item["condition"]: (
                    json.loads(Path(item["run"]).read_text(encoding="utf-8")),
                    [
                        json.loads(line)
                        for line in Path(item["trace"]).read_text(encoding="utf-8").splitlines()
                    ],
                )
                for item in public["runs"]
            }

        self.assertEqual(list(runs), [
            "Baseline", "RiCL-State", "RiCL-Search", "RiCL-Full", "RiCL w/o Search",
        ])
        self.assertEqual(public["trace_schema_version"], 1)
        self.assertEqual(public["budget"]["model_requests"], 8)
        self.assertEqual(public["budget"]["tools"], 3)
        self.assertEqual(public["budget"]["tokens"], 262_144)
        self.assertEqual(public["budget"]["elapsed_limit_ms"], 30_000)
        self.assertEqual(public["budget"]["cost_limit_usd"], 0.1)
        self.assertEqual(public["capabilities"]["max_candidates"], 3)
        self.assertTrue(public["capabilities"]["tools"])
        self.assertTrue(public["capabilities"]["capability_checks"]["model_port"])
        self.assertTrue(public["capabilities"]["capability_checks"]["candidate_generation"])
        self.assertTrue(public["capabilities"]["capability_checks"]["independent_verification"])
        self.assertTrue(public["capabilities"]["capability_checks"]["tools"])
        self.assertTrue(public["capabilities"]["capability_checks"]["budget"])
        self.assertEqual(
            {run["config"]["verifier"] for run, _ in runs.values()},
            {"real_radical_equation_v1"},
        )
        self.assertEqual({run["model"]["requested"] for run, _ in runs.values()}, {"mechanism-fixture"})
        self.assertEqual(
            {run["budget"]["model_requests"]["limit"] for run, _ in runs.values()}, {8}
        )
        for run, trace in runs.values():
            self.assertEqual(trace[0]["trace_schema_version"], 1)
            self.assertNotIn(PROBLEM, json.dumps(trace, ensure_ascii=False))
            self.assertNotIn(ANSWER, json.dumps(trace))
        self.assertNotIn(PROBLEM, json.dumps(public, ensure_ascii=False))
        self.assertNotIn(ANSWER, json.dumps(public))
        self.assertNotIn("Study the domain first.", json.dumps(public))

        self.assertEqual(runs["Baseline"][0]["verification"]["status"], "verified")
        self.assertEqual(runs["Baseline"][0]["budget"]["tools"], {"limit": 3, "used": 1})
        self.assertEqual(runs["RiCL-State"][0]["verification"]["status"], "unknown")
        self.assertEqual(runs["RiCL-State"][0]["usage"]["tokens"], "unknown")
        self.assertEqual(runs["RiCL-Search"][0]["run"]["status"], "failed")
        self.assertEqual(runs["RiCL-Search"][0]["run"]["stop_reason"], "unknown_outcome")
        self.assertEqual(runs["RiCL-Search"][0]["usage"]["tokens"], "unknown")
        search_candidates = next(
            event["candidates"] for event in runs["RiCL-Search"][1]
            if event["event"] == "route_candidates_generated"
        )
        full_candidates = next(
            event["candidates"] for event in runs["RiCL-Full"][1]
            if event["event"] == "route_candidates_generated"
        )
        self.assertEqual(search_candidates, full_candidates)
        full_run, full_trace = runs["RiCL-Full"]
        self.assertIsInstance(full_run["usage"]["tokens"], int)
        decisions = [event for event in full_trace if event["event"] == "route_selection"]
        self.assertEqual([(event["route_id"], event["strategy"]) for event in decisions], [
            ("route_01", "cold_start"),
            ("route_02", "cold_start"),
            ("route_02", "gain"),
        ])
        merge = next(event for event in full_trace if event["event"] == "counterfactual_merge")
        continuation = next(
            event for event in full_trace
            if event["event"] == "route_continuation_selected"
        )
        continued = next(
            event for event in full_trace
            if event["event"] == "model_request_sent"
            and event["request_id"] == continuation["request_id"]
        )
        self.assertEqual(continuation["route_id"], "route_02")
        self.assertEqual(continuation["checkpoint_id"], merge["checkpoint_id"])
        self.assertIn(merge["merged_evidence_ids"][0], continued["delivered_check_evidence_ids"])
        evaluated = {item["condition"]: item for item in evaluation["runs"]}
        self.assertEqual(evaluated["RiCL-Full"]["verified_gain"], 4)
        self.assertEqual(
            evaluated["RiCL-Full"]["search"]["route_expansions_without_new_evidence"], 1
        )
        self.assertEqual(
            evaluated["RiCL-Full"]["route_selections"],
            [
                {
                    "decision_id": event["decision_id"],
                    "request_id": event["request_id"],
                    "route_id": event["route_id"],
                    "strategy": event["strategy"],
                }
                for event in decisions
            ],
        )
        self.assertEqual(summarize_mechanism_run(full_run, full_trace), evaluated["RiCL-Full"])
        self.assertEqual(evaluated["RiCL-State"]["verification"]["status"], "unknown")
        self.assertGreater(full_run["budget"]["model_requests"]["used"], 1)

    def test_ablation_rejects_mismatched_model_and_tool_capabilities(self) -> None:
        class AlternatePort(AblationPort):
            pass

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "matched ModelPort capability"):
                run_mechanism_ablation(
                    lambda condition_id: (
                        AlternatePort(condition_id)
                        if condition_id == "ricl-full"
                        else AblationPort(condition_id)
                    ),
                    PROBLEM,
                    output_root=Path(directory),
                )

        class AlternateTool(MechanismTool):
            pass

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "matched tool capabilities"):
                run_mechanism_ablation(
                    AblationPort,
                    PROBLEM,
                    output_root=Path(directory),
                    tool_call_limit=1,
                    tool_executor_factory=lambda condition_id: (
                        AlternateTool()
                        if condition_id == "ricl-full"
                        else MechanismTool()
                    ),
                )

    def test_ablation_checks_candidate_generation_and_tool_execution(self) -> None:
        class NoCandidateGeneration:
            name = "mechanism-fixture"
            provider = "offline"
            thinking = "none"
            max_output_tokens = 100
            complete = None

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "candidate generation capability"):
                run_mechanism_ablation(
                    lambda _: NoCandidateGeneration(),
                    PROBLEM,
                    output_root=Path(directory),
                )

        class BrokenTool:
            execute = None

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "executable tool capability"):
                run_mechanism_ablation(
                    AblationPort,
                    PROBLEM,
                    output_root=Path(directory),
                    tool_call_limit=1,
                    tool_executor_factory=lambda _: BrokenTool(),
                )


if __name__ == "__main__":
    unittest.main()
