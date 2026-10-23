"""Disposable subprocess for real process-exit recovery acceptance."""

import json
import os
from pathlib import Path
import sys
import time
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.workspace import WorkspaceStore

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "First", "objective": "first fact"},
    {"step_id": "s2", "title": "Second", "objective": "second fact", "depends_on": ["s1"]},
    {"step_id": "s3", "title": "Third", "objective": "conclusion", "depends_on": ["s2"]},
]}


def config(folder):
    return {"TESTING": True, "SHOWCASE_DATA_DIR": str(folder),
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=12, max_http_attempts=12),
            "SHOWCASE_STAR_FEATURES": {"final_generation": True, "final_solution_review": True}}


def provider(folder, request):
    context = json.loads(json.loads(request["data"])["messages"][-1]["content"])
    with (folder / "requests.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(context) + "\n")
    role = context["role"]
    if role == "explore":
        value = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
    elif role == "planner":
        value = PLAN
    elif role == "reasoner":
        value = {"argument": "Addition", "claims": [], "blocked": False}
    elif role == "step_verifier":
        value = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
    elif role == "final_generator":
        value = {"final_response": "2"}
    else:
        value = {"verdict": "ACCEPT", "reason": "Addition"}

    class Reply:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
    return Reply()


def main():
    folder, window = Path(sys.argv[1]), sys.argv[2]
    original = WorkspaceStore.append_event
    def crash(store, job_id, event):
        original(store, job_id, event)
        log = folder / "requests.jsonl"
        last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1]) if log.exists() else {}
        target = {"accepted": "step_reviewed", "response": "call_audit",
                  "unknown": "never",
                  "exchange": "session_recorded"}[window]
        if (event.get("solver_event_type") == target and last.get("role") == "step_verifier"
                and last.get("step", {}).get("step_id") == "s2"):
            while not (folder / "job_id").exists():
                time.sleep(.01)
            os._exit(71)
    os.environ["INTERN_API_KEY"] = "scripted-only"
    def transport(*args, **kwargs):
        response = provider(folder, kwargs)
        context = json.loads((folder / "requests.jsonl").read_text().splitlines()[-1])
        if (window == "unknown" and context.get("role") == "step_verifier"
                and context.get("step", {}).get("step_id") == "s2"):
            os._exit(71)
        return response
    with patch("llm_client.requests.post", side_effect=transport), \
            patch.object(WorkspaceStore, "append_event", crash):
        app = create_app(config(folder))
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = str(uuid.uuid4())
        response = client.post("/api/agent/jobs", json={"message": "1+1", "session_id": session,
                               "solver_mode": "star_limited"}, headers=headers)
        (folder / "job_id").write_text(response.get_json()["job_id"])
        time.sleep(20)
    raise RuntimeError("crash window was not reached")


if __name__ == "__main__":
    main()
