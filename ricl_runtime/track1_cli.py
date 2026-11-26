"""Expose the single-problem Track 1 handoff to the separate experiment runner."""

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .identity import stable_id
from .providers.chat_completions import ProviderConfigurationError
from .providers.track1 import HOST, INPUT_RATE, MODEL, OUTPUT_LIMIT, OUTPUT_RATE, Track1Provider
from .track1 import CONDITIONS, solve
from .track1_budget import AUX_OUTPUT_LIMITS, SharedBudget


def main() -> int:
    """Read the public problem file and write a redacted run and append-only trace."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem-file", type=Path, required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--condition", choices=CONDITIONS, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--token-limit", type=int, required=True)
    parser.add_argument("--request-limit", type=int, required=True)
    parser.add_argument("--cost-limit-usd", required=True)
    parser.add_argument("--max-tokens", type=int, default=OUTPUT_LIMIT)
    parser.add_argument("--reasoning-effort", choices=("none", "low", "high"), default="high")
    parser.add_argument("--screen", action="store_true", help="sample once for pass@1")
    args = parser.parse_args()
    try:
        cost_limit = Decimal(args.cost_limit_usd)
        if not cost_limit.is_finite() or cost_limit <= 0:
            raise InvalidOperation
    except InvalidOperation:
        parser.error("cost limit must be a positive finite decimal")
    if args.request_limit <= 0 or args.token_limit <= 0:
        parser.error("request and token limits must be positive")
    if args.screen and (args.condition != "B1" or args.request_limit != 1):
        parser.error("pass@1 screening requires B1 with one request")
    if not re.fullmatch("[0-9a-f]{40}", args.source_revision):
        parser.error("source revision must be a full Git commit ID")
    problem = args.problem_file.read_text(encoding="utf-8-sig").strip()
    if not problem:
        parser.error("problem must be nonempty")
    try:
        provider = Track1Provider.from_environment(args.max_tokens, args.reasoning_effort)
    except ProviderConfigurationError as exc:
        parser.error(str(exc))
    configuration = {
        "endpoint_host": HOST, "model": MODEL, "thinking": provider.thinking,
        "reasoning_effort": args.reasoning_effort, "screen": args.screen,
        "max_output_tokens": args.max_tokens, "token_limit": args.token_limit,
        "aux_output_limits": AUX_OUTPUT_LIMITS,
        "request_limit": args.request_limit, "cost_limit_usd": str(cost_limit),
        "input_usd_per_million": str(INPUT_RATE), "output_usd_per_million": str(OUTPUT_RATE),
        "source_revision": args.source_revision, "condition": args.condition,
        "problem_id": args.problem_id, "problem_hash": stable_id("problem", problem),
    }
    args.output_dir.mkdir(parents=True, exist_ok=False)
    run_path = args.output_dir / "run.json"
    trace_path = args.output_dir / "trace.jsonl"
    with trace_path.open("x", encoding="utf-8") as trace:
        def emit(event: dict) -> None:
            trace.write(json.dumps(event, ensure_ascii=False) + "\n")
            trace.flush()

        config_hash = stable_id("config", configuration)
        emit({"event": "run_started", "config_hash": config_hash, "configuration": configuration})
        budget = SharedBudget(provider, args.token_limit, args.request_limit, cost_limit, emit)
        result = solve(problem, args.condition, budget, screen=args.screen)
        result.update(configuration=configuration, config_hash=config_hash, problem_id=args.problem_id)
        emit({"event": "run_finished", "status": result["status"], "reason": result["stop_reason"]})
    temporary = run_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(run_path)
    return 1 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
