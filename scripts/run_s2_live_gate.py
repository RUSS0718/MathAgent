"""Run the explicitly authorized, six-Run Intern S2 G2 protocol gate."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use the separately approved G2 budget of up to six Runs and twelve HTTP attempts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.live:
        print(json.dumps({
            "gate": "G2",
            "mode": "offline",
            "status": "not_run",
            "http_attempt_count": 0,
            "live_requires_explicit_flag": True,
        }, ensure_ascii=False))
        return 0

    return _run_live()


def _run_live() -> int:
    # Importing this module loads the existing local .env; the model is then
    # pinned to the approved service ID before the adapter creates its client.
    import llm_client  # noqa: F401
    from showcase.adapters import InternModelAdapter
    from showcase.flask_app import create_app
    from showcase.g2_campaign import run_g2_campaign
    from showcase.g2_live_gate import (
        G2_CLIENT_TIMEOUT_SECONDS,
        G2_MODEL,
        G2LivePipeline,
    )
    from showcase.run_service import RunService

    os.environ["INTERN_MODEL"] = G2_MODEL
    artifact_dir = ROOT / "artifacts" / f"g2-live-{uuid.uuid4().hex}"
    artifact_dir.mkdir(parents=True, exist_ok=False)
    database = artifact_dir / "workspace.sqlite3"
    model = InternModelAdapter(
        model_id=G2_MODEL,
        max_tokens=512,
        client_timeout=G2_CLIENT_TIMEOUT_SECONDS,
        client_retry=1,
        thinking_mode=True,
    )
    app = create_app(
        {
            "TESTING": True,
            "SHOWCASE_MODE": "live",
            "SHOWCASE_DATA_DIR": str(artifact_dir),
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_LIVE_PIPELINE": G2LivePipeline(model),
        },
        database_path=database,
        service=RunService(database_path=database),
    )
    try:
        report = run_g2_campaign(
            app.test_client(), execution_source="provider_live"
        )
        report_path = artifact_dir / "g2-report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps({
            "gate": "G2",
            "status": report["status"],
            "run_count": report["run_count"],
            "executed_run_count": report["executed_run_count"],
            "http_attempt_count": report["http_attempt_count"],
            "report_path": str(report_path),
        }, ensure_ascii=False))
        return 0 if report["status"] == "pass" else 1
    finally:
        for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            app.extensions[key].close()


if __name__ == "__main__":
    raise SystemExit(main())
