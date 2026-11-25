"""Offline contracts for serial candidate population search."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ricl_runtime import (
    Candidate,
    CandidateRoute,
    ModelReply,
    PopulationBudget,
    Runtime,
    ToolCall,
    ToolReceipt,
)
from ricl_runtime.providers.deepseek import ProviderTimeoutError

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ScriptedModelPort:
    name = "scripted-offline"

    def __init__(self, replies: list[ModelReply]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def complete(self, problem: str) -> ModelReply:
        self.prompts.append(problem)
        return self.replies.pop(0)


class ScriptedToolExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ToolCall]] = []

    def execute(self, invocation_id: str, call: ToolCall) -> ToolReceipt:
        self.calls.append((invocation_id, call))
        return ToolReceipt(invocation_id, f"receipt-{len(self.calls)}", call.tool_name, True, "4")


def opportunities() -> tuple[CandidateRoute, ...]:
    return (
        CandidateRoute(
            Candidate("route-first", novelty=5, known_token_cost=10),
            prompt="try the first route",
            source="root-proposal",
            parent_route_id="root",
            elapsed_ms_reserved=10,
            cost_usd_reserved=0,
        ),
        CandidateRoute(
            Candidate("route-verified", novelty=0, known_token_cost=20),
            prompt="try the verified route",
            source="root-proposal",
            parent_route_id="root",
            elapsed_ms_reserved=10,
            cost_usd_reserved=0,
        ),
    )


def replies() -> list[ModelReply]:
    return [ModelReply("5"), ModelReply("4")]


class SerialPopulationTests(unittest.TestCase):
    def test_provider_backed_port_is_recorded_as_live_in_run_artifact(self) -> None:
        port = ScriptedModelPort(replies())
        port.provider = "deepseek"
        budget = PopulationBudget(model_requests=2, tokens=30, tools=0, elapsed_ms=100, cost_usd=0)
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port).run_population(
                "Compute 2 + 2.", opportunities(), budget=budget, output_root=Path(directory),
            )
            artifact = json.loads(Path(run["artifacts"]["run"]).read_text(encoding="utf-8"))

        self.assertEqual(artifact["config"]["mode"], "live")

    def test_route_timeout_keeps_the_run_and_stops_the_population(self) -> None:
        port = ScriptedModelPort([])
        budget = PopulationBudget(model_requests=2, tokens=30, tools=0, elapsed_ms=100, cost_usd=0)
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(port, "complete", side_effect=ProviderTimeoutError("private detail")) as complete,
        ):
            run = Runtime(port).run_population(
                "Compute 2 + 2.", opportunities(), budget=budget, output_root=Path(directory),
            )
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")
        self.assertEqual(run["run"]["status"], "failed")
        self.assertEqual(run["run"]["stop_reason"], "timeout")
        self.assertEqual(run["budget"]["model_requests"], {"limit": 2, "used": 1})
        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertIn("model_request_failed", trace)
        self.assertNotIn("private detail", trace + json.dumps(run))
        complete.assert_called_once()

    def test_plain_and_aprs_expand_same_opportunities_and_budget_then_select_with_evidence(self) -> None:
        routes = opportunities()
        budget = PopulationBudget(model_requests=2, tokens=30, tools=0, elapsed_ms=100, cost_usd=0)
        outcomes = []

        for enabled in (False, True):
            port = ScriptedModelPort(replies())
            with tempfile.TemporaryDirectory() as directory:
                result = Runtime(port).run_population(
                    "Compute 2 + 2.", routes, budget=budget,
                    output_root=Path(directory), aprs_enabled=enabled,
                )
                events = [
                    json.loads(line)
                    for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
                ]
            outcomes.append((result, port, events))

        plain, aprs = outcomes
        self.assertEqual(len(plain[1].prompts), 2)
        self.assertEqual(len(aprs[1].prompts), 2)
        self.assertEqual(plain[0]["config"]["budget"], aprs[0]["config"]["budget"])
        self.assertEqual(plain[0]["population"]["candidate_ids"], ["route-first", "route-verified"])
        self.assertEqual(aprs[0]["population"]["candidate_ids"], plain[0]["population"]["candidate_ids"])
        self.assertEqual(plain[0]["population"]["selected_candidate_id"], "route-first")
        self.assertEqual(aprs[0]["population"]["selected_candidate_id"], "route-verified")
        self.assertEqual(aprs[0]["result"]["answer"], "4")
        expansion = [event for event in aprs[2] if event["event"] == "candidate_expanded"]
        self.assertEqual([event["source"] for event in expansion], ["root-proposal"] * 2)
        self.assertEqual([event["parent_route_id"] for event in expansion], ["root"] * 2)
        self.assertTrue(all(event["evidence_ids"] for event in expansion))
        self.assertTrue(any(event["event"] == "candidate_selected" for event in aprs[2]))
        self.assertTrue(any(event["event"] == "candidate_discarded" for event in aprs[2]))
        self.assertEqual(aprs[0]["run"]["stop_reason"], "candidate_set_exhausted")
        self.assertEqual(
            [route["status"] for route in aprs[0]["population"]["routes"]],
            ["discarded", "selected"],
        )
        self.assertEqual(
            aprs[0]["population"]["routes"][0]["stop_reason"], "not_selected"
        )
        self.assertNotIn("try the verified route", json.dumps(aprs[2]))


    def test_cli_population_example_exposes_selection_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ricl_runtime",
                    "--population",
                    "--problem",
                    "Compute 2 + 2.",
                    "--offline-answer",
                    "4",
                    "--model-request-limit",
                    "2",
                    "--output-root",
                    directory,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(completed.stdout)
            trace_events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text().splitlines()
            ]

        self.assertEqual(result["population"]["ranking_mode"], "aprs")
        self.assertEqual(result["population"]["selected_candidate_id"], "route-novel")
        self.assertTrue(any(event["event"] == "candidate_selected" for event in trace_events))

    def test_cli_population_plain_search_uses_the_same_example_opportunities(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ricl_runtime",
                    "--population",
                    "--no-aprs",
                    "--problem",
                    "Compute 2 + 2.",
                    "--offline-answer",
                    "4",
                    "--model-request-limit",
                    "2",
                    "--output-root",
                    directory,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

        result = json.loads(completed.stdout)
        self.assertEqual(result["population"]["ranking_mode"], "plain_search")
        self.assertEqual(result["population"]["candidate_ids"], ["route-baseline", "route-novel"])
        self.assertEqual(result["population"]["selected_candidate_id"], "route-baseline")

    def test_insufficient_shared_token_budget_stops_before_next_route(self) -> None:
        port = ScriptedModelPort(replies())
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", opportunities(),
                budget=PopulationBudget(model_requests=2, tokens=15, tools=0, elapsed_ms=100, cost_usd=0),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(result["budget"]["model_requests"], {"limit": 2, "used": 1})
        self.assertEqual(result["run"]["stop_reason"], "budget_insufficient")
        discarded = [event for event in events if event["event"] == "candidate_discarded"]
        self.assertEqual(discarded[-1]["candidate_id"], "route-verified")
        self.assertIn("tokens", discarded[-1]["insufficient_dimensions"])

    def test_unknown_route_reservation_is_not_treated_as_free_budget(self) -> None:
        route = CandidateRoute(
            Candidate("unknown-cost", known_token_cost=None),
            prompt="unbounded route",
            source="test",
            elapsed_ms_reserved=1,
            cost_usd_reserved=0,
        )
        port = ScriptedModelPort([ModelReply("4")])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", (route,),
                budget=PopulationBudget(model_requests=1, tokens=10, tools=0, elapsed_ms=10, cost_usd=0),
                output_root=Path(directory),
            )

        self.assertEqual(port.prompts, [])
        self.assertEqual(result["run"]["stop_reason"], "budget_insufficient")
        self.assertEqual(result["population"]["selected_candidate_id"], None)

    def test_tool_reservations_are_shared_across_route_expansions(self) -> None:
        routes = tuple(
            CandidateRoute(
                Candidate(f"route-{index}", known_token_cost=5),
                prompt=f"route {index}",
                source="root",
                tool_calls_reserved=1,
                elapsed_ms_reserved=1,
                cost_usd_reserved=0,
            )
            for index in (1, 2)
        )
        port = ScriptedModelPort([
            ModelReply("4", tool_calls=(ToolCall("calculator", "2+2"),)),
            ModelReply("4", tool_calls=(ToolCall("calculator", "2+2"),)),
        ])
        executor = ScriptedToolExecutor()
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port, tool_executor=executor).run_population(
                "Compute 2 + 2.", routes,
                budget=PopulationBudget(model_requests=2, tokens=10, tools=1, elapsed_ms=10, cost_usd=0),
                output_root=Path(directory),
            )

        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(result["budget"]["tools"], {"limit": 1, "used": 1})
        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(result["run"]["stop_reason"], "budget_insufficient")


    def test_request_budget_stops_before_the_next_expansion(self) -> None:
        port = ScriptedModelPort(replies())
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", opportunities(),
                budget=PopulationBudget(model_requests=1, tokens=30, tools=0, elapsed_ms=100, cost_usd=0),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(result["run"]["stop_reason"], "budget_insufficient")
        blocked = next(
            event for event in events
            if event["event"] == "candidate_discarded" and event["candidate_id"] == "route-verified"
        )
        self.assertIn("model_requests", blocked["insufficient_dimensions"])

    def test_cost_reservations_share_one_budget_with_exact_boundary(self) -> None:
        routes = tuple(
            CandidateRoute(
                Candidate(f"cost-{index}", known_token_cost=1),
                prompt=f"route {index}", source="test", elapsed_ms_reserved=1,
                cost_usd_reserved=cost,
            )
            for index, cost in enumerate((0.4, 0.5, 0.1), start=1)
        )
        port = ScriptedModelPort([ModelReply("4"), ModelReply("4"), ModelReply("4")])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", routes,
                budget=PopulationBudget(model_requests=3, tokens=3, tools=0, elapsed_ms=100, cost_usd=0.9),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 2)
        self.assertEqual(result["budget"]["cost_usd"]["reserved"], 0.9)
        blocked = next(
            event for event in events
            if event["event"] == "candidate_discarded" and event["candidate_id"] == "cost-3"
        )
        self.assertIn("cost_usd", blocked["insufficient_dimensions"])

    def test_elapsed_reservations_share_one_budget(self) -> None:
        routes = tuple(
            CandidateRoute(
                Candidate(f"time-{index}", known_token_cost=1),
                prompt=f"route {index}", source="test", elapsed_ms_reserved=reservation,
                cost_usd_reserved=0,
            )
            for index, reservation in enumerate((600, 500), start=1)
        )
        port = ScriptedModelPort([ModelReply("4"), ModelReply("4")])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", routes,
                budget=PopulationBudget(model_requests=2, tokens=2, tools=0, elapsed_ms=1000, cost_usd=0),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 1)
        self.assertEqual(result["run"]["stop_reason"], "budget_insufficient")
        blocked = next(
            event for event in events
            if event["event"] == "candidate_discarded" and event["candidate_id"] == "time-2"
        )
        self.assertIn("elapsed_ms", blocked["insufficient_dimensions"])

    def test_elapsed_time_overrun_stops_after_the_current_expansion(self) -> None:
        port = ScriptedModelPort(replies())
        route_opportunities = opportunities()
        with tempfile.TemporaryDirectory() as directory:
            with patch("ricl_runtime.runtime.time.perf_counter", side_effect=(0, 0, 2, 2, 2)):
                result = Runtime(port).run_population(
                    "Compute 2 + 2.", route_opportunities,
                    budget=PopulationBudget(model_requests=2, tokens=30, tools=0, elapsed_ms=1000, cost_usd=0),
                    output_root=Path(directory),
                )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 1)
        exceeded = next(event for event in events if event["event"] == "population_budget_exceeded")
        self.assertEqual((exceeded["dimension"], exceeded["used"], exceeded["limit"]), ("elapsed_ms", 2000, 1000))

    def test_unknown_elapsed_and_cost_reservations_are_not_free(self) -> None:
        for dimension in ("elapsed_ms", "cost_usd"):
            with self.subTest(dimension=dimension):
                route = CandidateRoute(
                    Candidate(f"unknown-{dimension}", known_token_cost=1),
                    prompt="unknown reservation", source="test",
                    elapsed_ms_reserved=None if dimension == "elapsed_ms" else 1,
                    cost_usd_reserved=None if dimension == "cost_usd" else 0,
                )
                port = ScriptedModelPort([ModelReply("4")])
                with tempfile.TemporaryDirectory() as directory:
                    result = Runtime(port).run_population(
                        "Compute 2 + 2.", (route,),
                        budget=PopulationBudget(model_requests=1, tokens=1, tools=0, elapsed_ms=100, cost_usd=0),
                        output_root=Path(directory),
                    )
                    events = [
                        json.loads(line)
                        for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
                    ]

                self.assertEqual(port.prompts, [])
                blocked = next(event for event in events if event["event"] == "candidate_discarded")
                self.assertIn(f"{dimension}_unknown", blocked["insufficient_dimensions"])

    def test_mixed_known_and_unknown_usage_preserves_shared_token_commitments(self) -> None:
        routes = tuple(
            CandidateRoute(
                Candidate(f"mixed-{index}", known_token_cost=10),
                prompt=f"route {index}", source="test", elapsed_ms_reserved=1,
                cost_usd_reserved=0,
            )
            for index in range(1, 4)
        )
        port = ScriptedModelPort([
            ModelReply("5", input_tokens=10, output_tokens=5),
            ModelReply("5"),
            ModelReply("4"),
        ])
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(port).run_population(
                "Compute 2 + 2.", routes,
                budget=PopulationBudget(model_requests=3, tokens=30, tools=0, elapsed_ms=100, cost_usd=0),
                output_root=Path(directory),
            )
            events = [
                json.loads(line)
                for line in Path(result["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(port.prompts), 2)
        self.assertEqual(result["budget"]["tokens"]["committed"], 25)
        blocked = next(
            event for event in events
            if event["event"] == "candidate_discarded" and event["candidate_id"] == "mixed-3"
        )
        self.assertIn("tokens", blocked["insufficient_dimensions"])



if __name__ == "__main__":
    unittest.main()
