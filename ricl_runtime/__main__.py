"""Explicit command-line entry point for the offline RiCL Runtime."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

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
    parser.add_argument("--model-request-limit", type=int, default=1)
    parser.add_argument("--tool-call-limit", type=int, default=0)
    args = parser.parse_args(argv)

    result = Runtime(DeterministicModelPort(args.offline_answer)).run(
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