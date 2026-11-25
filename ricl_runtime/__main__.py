"""Explicit command-line entry point for the RiCL Runtime."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .aprs import Candidate
from .population import CandidateRoute, PopulationBudget
from .port import DeterministicModelPort
from .providers.chat_completions import ProviderConfigurationError
from .providers.deepseek import DeepSeekModelPort
from .providers.minimax import MiniMaxModelPort
from .runtime import Runtime


def main(argv: Sequence[str] | None = None) -> int:
    """Run one offline or explicitly selected Provider problem."""

    parser = argparse.ArgumentParser(description="Run one RiCL Runtime problem.")
    parser.add_argument("--provider", choices=("offline", "deepseek", "minimax"), default="offline")
    parser.add_argument("--problem", required=True, help="single text math problem")
    parser.add_argument("--offline-answer", help="fixed answer returned by the offline test port")
    parser.add_argument("--thinking", choices=("enabled", "disabled"))
    parser.add_argument("--problem-id", help="optional stable problem identifier")
    parser.add_argument("--condition-id", default="offline-single-route")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--reasoning-state", action="store_true", help="enable shared reasoning state"
    )
    parser.add_argument(
        "--population", action="store_true", help="run the offline serial population example"
    )
    parser.add_argument(
        "--aprs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="use APRS/Pareto selection for --population",
    )
    parser.add_argument("--model-request-limit", type=int, default=1)
    parser.add_argument("--tool-call-limit", type=int, default=0)
    parser.add_argument("--token-limit", type=int, help="total token limit for --population (default: 20)")
    parser.add_argument("--elapsed-limit-ms", type=int, help="time limit for --population (default: 100)")
    parser.add_argument("--cost-limit-usd", type=float, help="cost limit for --population (default: 0)")
    args = parser.parse_args(argv)

    if args.population and args.provider != "offline":
        parser.error("--population requires the offline provider")
    if not args.population and any(
        value is not None for value in (args.token_limit, args.elapsed_limit_ms, args.cost_limit_usd)
    ):
        parser.error("--token-limit, --elapsed-limit-ms, and --cost-limit-usd require --population")
    if args.provider == "offline":
        if args.offline_answer is None:
            parser.error("--offline-answer is required for the offline provider")
        model_port = DeterministicModelPort(args.offline_answer)
    else:
        if args.thinking is None:
            parser.error("--thinking must be explicitly set for a live provider")
        if args.model_request_limit != 1:
            parser.error("the live CLI smoke requires --model-request-limit 1")
        if args.provider == "minimax" and args.thinking != "enabled":
            parser.error("MiniMax M3.1 Flash requires --thinking enabled")
        try:
            model_port = (
                MiniMaxModelPort.from_environment()
                if args.provider == "minimax"
                else DeepSeekModelPort.from_environment(thinking=args.thinking)
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
            model_request_limit=args.model_request_limit,
            tool_call_limit=args.tool_call_limit,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["run"]["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
