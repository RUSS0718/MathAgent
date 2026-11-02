"""Crash real product processes, then inspect public Job/Run recovery contracts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def child(root, scenario, phase):
    from llm_client import InternChatClient
    from showcase.adapters import InternModelAdapter
    from showcase.flask_app import create_app
    from showcase.live_pipeline import LiveAgentPipeline
    from showcase.tools import ToolRegistry

    calls = root / "dispatch.jsonl"

    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

    def respond(*args, **kwargs):
        with calls.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"phase": phase, "call_id": str(uuid.uuid4())}) + "\n")
        if scenario == "unknown" and phase == "before":
            write(root / "inflight.json", {"request_received": True})
            time.sleep(60)  # Parent kills this process before any response exists.
        return Reply()

    with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-local-only"}), patch(
        "llm_client.requests.post", side_effect=respond
    ):
        pipeline = LiveAgentPipeline(InternModelAdapter(InternChatClient(retry=1), max_tokens=256), ToolRegistry())
        pipeline.pause_after_planner = scenario == "safe" and phase == "before"
        app = create_app({"TESTING": True, "SHOWCASE_MODE": "live", "SHOWCASE_DATA_DIR": str(root / "data"),
                          "SHOWCASE_LIVE_PIPELINE": pipeline, "SHOWCASE_JOB_DELAY_SECONDS": 0})
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]

        def headers():
            return {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}

        def observation(job_id):
            return {
                "job": client.get(f"/api/agent/jobs/{job_id}").get_json(),
                "run": client.get(f"/api/runs/{job_id}").get_json(),
                "report": client.get(f"/api/agent/jobs/{job_id}/report").get_json(),
                "checkpoint": app.extensions["showcase_run_service"].get_checkpoint(job_id),
            }

        if phase == "before":
            session = client.post("/api/new_chat", headers=headers()).get_json()["new_session_id"]
            result = client.post("/api/agent/jobs", json={"message": "1+1", "session_id": session}, headers=headers())
            job_id = result.get_json()["job_id"]
            write(root / "identity.json", {"job_id": job_id})
            for _ in range(1000):
                current = observation(job_id)
                if (scenario == "safe" and current["job"]["status"] == "waiting_input") or (
                    scenario == "unknown" and (root / "inflight.json").exists()
                ):
                    write(root / "before.json", current)
                    time.sleep(60)
                time.sleep(0.01)
            raise RuntimeError("crash boundary not reached")

        job_id = json.loads((root / "identity.json").read_text(encoding="utf-8"))["job_id"]
        recovered = observation(job_id)
        response = client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=headers())
        for _ in range(1000):
            current = observation(job_id)
            if current["job"]["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(0.01)
        write(root / "after.json", {
            "recovered": recovered, "resume_http": response.status_code, "resume": response.get_json(),
            "after": current, "evidence": client.get(f"/api/runs/{job_id}/evidence").get_json(),
            "events": client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True),
        })
        for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            app.extensions[key].close()


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--child", choices=["before", "after"])
    parser.add_argument("--scenario", choices=["safe", "unknown"])
    args = parser.parse_args()
    if args.child:
        child(args.output, args.scenario, args.child)
        return 0
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    assertions = {}
    for scenario in ("safe", "unknown"):
        root = output / scenario
        root.mkdir()
        command = [sys.executable, __file__, "--output", str(root), "--scenario", scenario, "--child"]
        with (root / "process.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen([*command, "before"], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 20
                while not (root / "before.json").exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError(f"{scenario}: crash boundary unavailable; see {log.name}")
                    time.sleep(0.02)
            finally:
                process.kill()
                process.wait(timeout=10)
            subprocess.run([*command, "after"], stdout=log, stderr=log, timeout=30, check=True)
        before = json.loads((root / "before.json").read_text(encoding="utf-8"))
        after = json.loads((root / "after.json").read_text(encoding="utf-8"))
        first = before["report"]["report"]["budget"]
        last = after["after"]["report"]["report"]["budget"]
        dispatches = (root / "dispatch.jsonl").read_text(encoding="utf-8").splitlines()
        assertions[scenario + "_same_deadline"] = first["deadline_at"] == last["deadline_at"]
        assertions[scenario + "_same_run"] = before["run"]["run_id"] == after["after"]["run"]["run_id"]
        if scenario == "safe":
            assertions["safe_no_planner_repeat"] = len(dispatches) == 3 and last["http_attempts"] == 3
            assertions["safe_completed"] = after["resume_http"] == 202 and after["after"]["job"]["status"] == "succeeded"
            assertions["safe_usage_cumulative"] = last["provider_known"]["total_tokens"] == 30
        else:
            assertions["unknown_no_redispatch"] = len(dispatches) == 1 and after["resume_http"] == 409
            assertions["unknown_preserved"] = last["unresolved_attempts"] == 1 and last["reserved_tokens"] > 0
            assertions["unknown_needs_review"] = after["after"]["job"]["error"] == "needs_review"
    write(output / "summary.json", {
        "evidence_mode": "scripted+process-kill", "external_api_calls": 0,
        "budget": {"scripted_http_attempts": 4, "tool_calls": 0, "max_seconds": 120},
        "assertions": assertions, "baseline_recovery": "pass" if all(assertions.values()) else "fail",
        "star_step_acceptance_recovery": "blocked: public Job does not dispatch STAR steps at source baseline",
        "scope": "planner checkpoint and unknown request only; no claim of step-2-to-3 STAR recovery",
    })
    print(json.dumps(assertions))
    return 0 if all(assertions.values()) else 1


if __name__ == "__main__":
    raise SystemExit(run())
