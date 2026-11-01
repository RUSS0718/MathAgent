"""Disposable public Job worker for CP04 checkpoint and receipt recovery."""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from showcase.workspace import WorkspaceStore

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "Compute", "objective": "Compute 1+1"},
]}


def requests_so_far(folder):
    path = folder / "requests.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def checkpoint(context, status, checkpoint_id):
    claim = {"statement": "1+1=2 by the registered computation",
             "label": "easy-verify" if status == "YIELD" else "hard-verify"}
    if status == "YIELD":
        claim["tool_request"] = {
            "tool": "polynomial_check", "arguments": {},
            "scope": "finite_computation", "expected_output": 2,
        }
    return {"checkpoint": {
        "protocol_version": 1,
        "checkpoint_id": checkpoint_id,
        "status": status,
        "objective": context["step"]["objective"],
        "argument": "A registered finite computation establishes the claim.",
        "claims": [claim],
        "blocked": False,
        "dependencies": [],
        "evidence": ["registered computation"],
        "gaps": ["finish the checkpoint handoff"] if status == "YIELD" else [],
        "next_action": "finish the checkpoint handoff",
    }}


def reply(context, folder):
    role = context["role"]
    if role == "explore":
        return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
    if role == "planner":
        return PLAN
    if role == "reasoner":
        count = sum(item.get("role") == "reasoner" for item in requests_so_far(folder))
        return checkpoint(context, "YIELD", "completed-yield") if count == 1 else \
            checkpoint(context, "FINAL", "completed-final")
    if role == "step_verifier":
        return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                "objection": ""}
    if role == "final_generator":
        return {"final_response": "2"}
    return {"verdict": "ACCEPT", "reason": "Addition"}


def provider(folder, request):
    context = json.loads(json.loads(request["data"])["messages"][-1]["content"])
    with (folder / "requests.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(context) + "\n")
    value = reply(context, folder)

    class Reply:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(value)}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

    return Reply()


def config(folder):
    registry = ToolRegistry()

    def tool(_arguments):
        with (folder / "tool_runs.txt").open("a", encoding="utf-8") as output:
            output.write("executed\n")
        return 2

    registry.register("polynomial_check", tool)
    return {
        "TESTING": True,
        "SHOWCASE_DATA_DIR": str(folder),
        "SHOWCASE_JOB_DELAY_SECONDS": 0,
        "SHOWCASE_STAR_ENABLED": True,
        "SHOWCASE_STAR_ADAPTER": InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
        "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
        "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=20, max_http_attempts=20),
        "SHOWCASE_STAR_REGISTRY": registry,
        "SHOWCASE_STAR_FEATURES": {
            "final_generation": True,
            "final_solution_review": True,
            "reasoner_checkpoints": True,
            "local_code_tool": True,
        },
    }


def main():
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    original = WorkspaceStore.append_event

    def crash(store, job_id, event):
        original(store, job_id, event)
        requests = requests_so_far(folder)
        if ((event.get("solver_event_type") in {"challenge_recorded", "step_reviewed"}
             or event.get("type") == "challenge_recorded")
                and requests and requests[-1].get("role") == "step_verifier"):
            while not (folder / "job_id").exists():
                time.sleep(.01)
            os._exit(71)

    os.environ["INTERN_API_KEY"] = "scripted-only"
    with patch("llm_client.requests.post", side_effect=lambda *args, **kwargs:
               provider(folder, kwargs)), patch.object(WorkspaceStore, "append_event", crash):
        app = create_app(config(folder))
        client = app.test_client()
        headers = {"X-CSRF-Token": client.get("/api/check_auth").get_json()["csrf_token"],
                   "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = str(uuid.uuid4())
        response = client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": session, "solver_mode": "star_limited",
        }, headers=headers)
        (folder / "job_id").write_text(response.get_json()["job_id"], encoding="utf-8")
        time.sleep(20)


if __name__ == "__main__":
    main()
