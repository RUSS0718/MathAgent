"""Explicit command-line entry point for the offline RiCL Runtime."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .aprs import Candidate
from .population import CandidateRoute, PopulationBudget
from .port import DeterministicModelPort
from .runtime import Runtime


def main(argv: Sequence[str] | None = None) -> int:
    """Run a single deterministic offline example and print its result JSON."""

    parser = argparse.ArgumentParser(description="Run one offline RiCL Runtime problem.")
    parser.add_argument("--problem", required=True, help="single text math problem")
    parser.add_argument(
        "--offline-answer", required=True, help="fixed answer returned by the offline test port"
    )
    parser.add_argument("--problem-id", help="optional stable problem identifier")
    parser.add_argument("--condition-id", default="offline-single-route")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--reasoning-state", action="store_true", help="enable shared reasoning state")
    parser.add_argument("--population", action="store_true", help="run the serial candidate population example")
    parser.add_argument(
        "--aprs", action=argparse.BooleanOptionalAction, default=True,
        help="use APRS/Pareto selection for --population",
    )
    parser.add_argument("--model-request-limit", type=int, default=1)
    parser.add_argument("--tool-call-limit", type=int, default=0)
    parser.add_argument("--token-limit", type=int, default=20)
    parser.add_argument("--elapsed-limit-ms", type=int, default=100)
    parser.add_argument("--cost-limit-usd", type=float, default=0.0)
    args = parser.parse_args(argv)

    port = DeterministicModelPort(args.offline_answer)
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
        result = Runtime(port).run_population(
            args.problem,
            routes,
            problem_id=args.problem_id,
            condition_id=args.condition_id,
            output_root=args.output_root,
            aprs_enabled=args.aprs,
            budget=PopulationBudget(
                model_requests=args.model_request_limit,
                tokens=args.token_limit,
                tools=args.tool_call_limit,
                elapsed_ms=args.elapsed_limit_ms,
                cost_usd=args.cost_limit_usd,
            ),
        )
    else:
        result = Runtime(port).run(
            args.problem,
            problem_id=args.problem_id,
            condition_id=args.condition_id,
            output_root=args.output_root,
            reasoning_state_enabled=args.reasoning_state,
            model_request_limit=args.model_request_limit,
            tool_call_limit=args.tool_call_limit,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())