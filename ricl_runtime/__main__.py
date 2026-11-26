"""Explicit command-line entry point for the RiCL Runtime."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .aprs import Candidate
from .population import CandidateRoute, PopulationBudget
from .port import DeterministicModelPort, ModelReply
from .providers.chat_completions import ProviderConfigurationError
from .providers.deepseek import GATEWAY_EXPANDED_OUTPUT_TOKENS, DeepSeekModelPort
from .providers.minimax import MiniMaxModelPort
from .runtime import Runtime


class _OfflineReplySequence:
    name = "deterministic-offline"

    def __init__(self, answers: Sequence[str]) -> None:
        self._answers = iter(answers)

    def complete(self, problem: str) -> ModelReply:
        del problem
        return ModelReply(next(self._answers, ""), model=self.name)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one offline or explicitly selected Provider problem."""

    parser = argparse.ArgumentParser(description="Run one RiCL Runtime problem.")
    parser.add_argument("--provider", choices=("offline", "deepseek", "minimax"), default="offline")
    parser.add_argument("--problem", required=True, help="single text math problem")
    parser.add_argument(
        "--offline-answer", action="append",
        help="offline reply (repeat in dispatch order for online search or counterfactual intervention)",
    )
    parser.add_argument("--thinking", choices=("enabled", "disabled"))
    parser.add_argument(
        "--gateway-output-tokens", type=int, choices=(GATEWAY_EXPANDED_OUTPUT_TOKENS,),
        help="opt in to the expanded DeepSeek gateway output budget",
    )
    parser.add_argument("--problem-id", help="optional stable problem identifier")
    parser.add_argument("--condition-id", default="offline-single-route")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--reasoning-state", action="store_true", help="enable shared reasoning state"
    )
    parser.add_argument(
        "--counterfactual", action="store_true", help="enable bounded online intervention on a checked failure"
    )
    route = parser.add_mutually_exclusive_group()
    route.add_argument(
        "--population", action="store_true", help="run the offline serial population example"
    )
    route.add_argument(
        "--online-search", choices=("aprs", "round_robin"), help="schedule model-proposed routes online"
    )
    parser.add_argument(
        "--aprs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="use APRS/Pareto selection for --population",
    )
    parser.add_argument("--model-request-limit", type=int, default=1, help="maximum requests per Run")
    parser.add_argument("--tool-call-limit", type=int, default=0)
    parser.add_argument("--token-limit", type=int, help="total token limit for --population (default: 20)")
    parser.add_argument("--elapsed-limit-ms", type=int, help="time limit for --population (default: 100)")
    parser.add_argument("--cost-limit-usd", type=float, help="cost limit for --population (default: 0)")
    args = parser.parse_args(argv)

    if args.gateway_output_tokens is not None and args.provider != "deepseek":
        parser.error("--gateway-output-tokens requires the DeepSeek gateway")
    if args.population and args.provider != "offline":
        parser.error("--population requires the offline provider")
    if args.population and args.counterfactual:
        parser.error("--counterfactual requires the single-route Runtime")
    if args.provider == "offline":
        if args.offline_answer is None:
            parser.error("--offline-answer is required for the offline provider")
        model_port = (
            _OfflineReplySequence(args.offline_answer) if args.online_search or args.counterfactual
            else DeterministicModelPort(args.offline_answer[-1])
        )
    else:
        if args.thinking is None:
            parser.error("--thinking must be explicitly set for a live provider")
        if args.model_request_limit < 1:
            parser.error("--model-request-limit must be positive for a live provider")
        if args.provider == "minimax" and args.thinking != "enabled":
            parser.error("MiniMax M3.1 Flash requires --thinking enabled")
        try:
            model_port = (
                MiniMaxModelPort.from_environment()
                if args.provider == "minimax"
                else DeepSeekModelPort.from_environment(
                    thinking=args.thinking, gateway_output_tokens=args.gateway_output_tokens,
                )
            )
        except ProviderConfigurationError as error:
            parser.error(str(error))

    if args.population:
        routes = (
            CandidateRoute(
                Candidate("route-baseline", novelty=0, known_token_cost=10),
                prompt="baseline route",
                source="cli-sample",
                parent_route_id="root",
                elapsed_ms_reserved=1,
                cost_usd_reserved=0,
            ),
            CandidateRoute(
                Candidate("route-novel", novelty=1, known_token_cost=10),
                prompt="novel route",
                source="cli-sample",
                parent_route_id="root",
                elapsed_ms_reserved=1,
                cost_usd_reserved=0,
            ),
        )
        result = Runtime(model_port).run_population(
            args.problem,
            routes,
            problem_id=args.problem_id,
            condition_id=args.condition_id,
            output_root=args.output_root,
            aprs_enabled=args.aprs,
            budget=PopulationBudget(
                model_requests=args.model_request_limit,
                tokens=20 if args.token_limit is None else args.token_limit,
                tools=args.tool_call_limit,
                elapsed_ms=100 if args.elapsed_limit_ms is None else args.elapsed_limit_ms,
                cost_usd=0.0 if args.cost_limit_usd is None else args.cost_limit_usd,
            ),
        )
    else:
        result = Runtime(model_port).run(
            args.problem,
            problem_id=args.problem_id,
            condition_id=args.condition_id,
            output_root=args.output_root,
            reasoning_state_enabled=args.reasoning_state,
            counterfactual_enabled=args.counterfactual,
            model_request_limit=args.model_request_limit,
            tool_call_limit=args.tool_call_limit,
            token_limit=args.token_limit,
            elapsed_limit_ms=args.elapsed_limit_ms,
            cost_limit_usd=args.cost_limit_usd,
            online_search=args.online_search,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["run"]["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
