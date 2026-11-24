"""Explicit command-line entry point for the offline RiCL Runtime."""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .port import DeterministicModelPort
from .providers.deepseek import DeepSeekModelPort, ProviderConfigurationError
from .runtime import Runtime


def main(argv: Sequence[str] | None = None) -> int:
    """Run one offline or explicitly selected DeepSeek Runtime problem."""

    parser = argparse.ArgumentParser(description="Run one RiCL Runtime problem.")
    parser.add_argument("--provider", choices=("offline", "deepseek"), default="offline")
    parser.add_argument("--problem", required=True, help="single text math problem")
    parser.add_argument("--offline-answer", help="fixed answer returned by the offline test port")
    parser.add_argument("--thinking", choices=("enabled", "disabled"))
    parser.add_argument("--problem-id", help="optional stable problem identifier")
    parser.add_argument("--condition-id", default="offline-single-route")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--reasoning-state", action="store_true", help="enable shared reasoning state"
    )
    parser.add_argument("--model-request-limit", type=int, default=1)
    parser.add_argument("--tool-call-limit", type=int, default=0)
    args = parser.parse_args(argv)

    if args.provider == "offline":
        if args.offline_answer is None:
            parser.error("--offline-answer is required for the offline provider")
        model_port = DeterministicModelPort(args.offline_answer)
    else:
        if args.thinking is None:
            parser.error("--thinking must be explicitly set for DeepSeek")
        try:
            model_port = DeepSeekModelPort.from_environment(thinking=args.thinking)
        except ProviderConfigurationError as error:
            parser.error(str(error))

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
