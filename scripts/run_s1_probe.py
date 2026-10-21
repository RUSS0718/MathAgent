"""Run exactly one authorized S1 G1 request and archive only the public report."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Consume the separately authorized one-request G1 budget",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("explicit --live required; this command consumes one request without retries")
    from showcase.flask_app import create_app
    from showcase.s1_probe import S1ProbePipeline

    directory = Path("artifacts") / ("s1-g1-" + uuid.uuid4().hex)
    app = create_app(
        {
            "TESTING": True,
            "SHOWCASE_MODE": "live",
            "SHOWCASE_DATA_DIR": str(directory),
            "SHOWCASE_LIVE_PIPELINE": S1ProbePipeline(),
        }
    )
    try:
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session_id = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        job_id = client.post(
            "/api/agent/jobs", json={"message": "S1 G1", "session_id": session_id}, headers=headers
        ).get_json()["job_id"]
        while True:
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(0.1)
        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()
        # The gate archive contains metering only, never provider content.
        safe = {
            "job_id": job_id,
            "engineering_contract": "pass" if job["status"] == "succeeded" else "blocked",
            "request_attempts": report["report"]["request_attempts"],
        }
        target = directory / "g1-report.json"
        target.write_text(json.dumps(safe, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({**safe, "report_path": str(target)}, ensure_ascii=False))
        return 0 if safe["engineering_contract"] == "pass" else 1
    finally:
        for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            app.extensions[key].close()


if __name__ == "__main__":
    raise SystemExit(main())
