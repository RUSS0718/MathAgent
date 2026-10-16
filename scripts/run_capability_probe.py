"""Run one safe fake or Intern live capability probe."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from showcase.run_service import RunService  # noqa: E402
from showcase.server import create_live_service  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Showcase capability probe")
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument(
        "--problem",
        default="求方程 x^2 - 1 = 0 的实数解，并说明是否需要计算工具。",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    service: RunService
    if args.mode == "live":
        service = create_live_service()
    else:
        service = RunService()
    try:
        snapshot = service.create_run({"problem": args.problem})
        events = service.get_events(snapshot["run_id"])
        result: dict[str, Any] = {
            "created_at": datetime.now(UTC).isoformat(),
            "mode": args.mode,
            "execution_mode": snapshot.get("execution_mode"),
            "run_id": snapshot.get("run_id"),
            "status": snapshot.get("status"),
            "stage": snapshot.get("stage"),
            "final_response_present": bool(snapshot.get("final_response")),
            "error": snapshot.get("error"),
            "event_types": [event.get("type") for event in events],
            "tool_statuses": [
                event.get("status")
                for event in events
                if event.get("type") == "tool_completed"
            ],
        }
    finally:
        service.close()

    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0 if result["status"] == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
