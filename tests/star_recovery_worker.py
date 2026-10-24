"""Disposable subprocess for real process-exit recovery acceptance."""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter, InternStreamAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from showcase.workspace import WorkspaceStore

PLAN = {"version": 1, "steps": [
    {"step_id": "s1", "title": "First", "objective": "first fact"},
    {"step_id": "s2", "title": "Second", "objective": "second fact", "depends_on": ["s1"]},
    {"step_id": "s3", "title": "Third", "objective": "conclusion", "depends_on": ["s2"]},
]}

TRACE_WINDOWS = {"trace_before", "trace_after"}
STREAM_WINDOWS = {"stream_exit"}
META_CONTINUE_DECISION = {"decision": "CONTINUE",
                          "reason_summary": "Re-solve the same step against the objection.",
                          "plan_summary": "", "forbidden_directions": [],
                          "reusable_results": [], "trace_back_to": None}


def config(folder, *, crash_tools=False):
    registry = ToolRegistry()
    def tool(_arguments):
        if crash_tools:
            os._exit(71)
        return 2
    registry.register("polynomial_check", tool)
    window = (folder / "window").read_text() if (folder / "window").exists() else ""
    # Trace-back windows re-execute every archived step on resume and need more calls;
    # meta_continue replays s1 as a new action after the CONTINUE decision.
    calls = 16 if window in TRACE_WINDOWS or window == "meta_continue" else 12
    adapter = (InternStreamAdapter(InternChatClient(retry=1), max_tokens=256)
               if window in STREAM_WINDOWS
               else InternModelAdapter(InternChatClient(retry=1), max_tokens=256))
    return {"TESTING": True, "SHOWCASE_DATA_DIR": str(folder),
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": adapter,
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=calls, max_http_attempts=calls),
            "SHOWCASE_STAR_REGISTRY": registry,
            "SHOWCASE_STAR_FEATURES": {"final_generation": True, "final_solution_review": True,
                                       "local_code_tool": True}}


def reply_value(window, context, folder):
    role = context["role"]
    if role == "explore":
        value = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
    elif role == "planner":
        value = PLAN
    elif role == "meta" and window == "meta_continue":
        value = META_CONTINUE_DECISION
    elif role == "reasoner":
        value = {"argument": "Addition", "claims": [], "blocked": False}
        if (window in {"tool", "tool_unknown"}
                and context["step"]["step_id"] == "s2"):
            value["claims"] = [{"statement": "1+1=2", "label": "easy-verify",
                               "tool_request": {"tool": "polynomial_check", "arguments": {},
                                                "expected_output": 2, "scope": "finite_computation"}}]
    elif (
        role == "step_verifier"
        and window == "meta_continue"
        and context["step"]["step_id"] == "s1"
        and sum(
            1
            for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            if (item := json.loads(line)).get("role") == "step_verifier"
            and item.get("step", {}).get("step_id") == "s1"
        )
        == 1
    ):
        # Only the first s1 review proposes replan; the new action's re-review accepts.
        value = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
                 "objection": "First route is unsupported"}
    elif (
        role == "step_verifier"
        and window in TRACE_WINDOWS
        and context["step"]["step_id"] == "s2"
        and sum(
            1
            for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            if (item := json.loads(line)).get("role") == "step_verifier"
            and item.get("step", {}).get("step_id") == "s2"
        )
        == 1
    ):
        # Only the first s2 review demands the archive; the re-executed attempt accepts.
        value = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK",
                 "trace_back_to": 1, "objection": "First route is unsupported"}
    elif role == "step_verifier":
        value = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
    elif role == "final_generator":
        value = {"final_response": "2"}
    else:
        value = {"verdict": "ACCEPT", "reason": "Addition"}
    return value


def provider(folder, request):
    context = json.loads(json.loads(request["data"])["messages"][-1]["content"])
    with (folder / "requests.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(context) + "\n")
    value = reply_value((folder / "window").read_text(), context, folder)

    class Reply:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}
    return Reply()


def stream_transport(folder, window):
    """SSE wire fake for the injected streaming adapter; ``stream_exit`` dies mid-stream."""
    def post(_url, **kwargs):
        context = json.loads(json.loads(kwargs["data"])["messages"][-1]["content"])
        with (folder / "requests.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(context) + "\n")
        value = reply_value(window, context, folder)

        class StreamReply:
            status_code = 200
            def raise_for_status(self):
                pass
            def close(self):
                pass
            def iter_lines(self, decode_unicode=True):
                text = json.dumps(value)
                size = max(1, len(text) // 3)
                pieces = [text[index:index + size] for index in range(0, len(text), size)]
                for index, piece in enumerate(pieces):
                    if window == "stream_exit" and index == 1:
                        # Fragment one was persisted by the audit; die before fragment two.
                        while not (folder / "job_id").exists():
                            time.sleep(.01)
                        os._exit(71)
                    yield "data: " + json.dumps({"choices": [{"delta": {"content": piece}}]})
                yield "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}],
                                             "usage": {"prompt_tokens": 7, "completion_tokens": 3,
                                                       "total_tokens": 10}, "model": "intern-s2"})
                yield "data: [DONE]"
        return StreamReply()
    return post


def main():
    folder, window = Path(sys.argv[1]), sys.argv[2]
    (folder / "window").write_text(window)
    original = WorkspaceStore.append_event
    def crash(store, job_id, event):
        original(store, job_id, event)
        log = folder / "requests.jsonl"
        last = json.loads(log.read_text(encoding="utf-8").splitlines()[-1]) if log.exists() else {}
        target = {"accepted": "step_reviewed", "response": "call_audit",
                  "unknown": "never",
                  "tool_unknown": "never",
                  "tool": "tool_receipt",
                  "exchange": "session_recorded",
                  "trace_before": "step_reviewed",
                  "trace_after": "trace_back_applied",
                  "stream_exit": "never",
                  "meta_continue": "meta_decided"}[window]
        target_role = "reasoner" if window == "tool" else (
            "meta" if window == "meta_continue" else "step_verifier")
        if window == "meta_continue":
            hit_step = last.get("progress", {}).get("current_step") == "s1"
        else:
            hit_step = last.get("step", {}).get("step_id") == "s2"
        if (event.get("solver_event_type") == target and last.get("role") == target_role
                and hit_step):
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
    patches = [patch("llm_client.requests.post", side_effect=transport),
               patch.object(WorkspaceStore, "append_event", crash)]
    if window in STREAM_WINDOWS:
        patches.append(patch("showcase.adapters.requests.post",
                             side_effect=stream_transport(folder, window)))
    from contextlib import ExitStack
    with ExitStack() as stack:
        for item in patches:
            stack.enter_context(item)
        app = create_app(config(folder, crash_tools=window == "tool_unknown"))
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
