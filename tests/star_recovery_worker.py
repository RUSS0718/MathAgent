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
# ALIGN-01 crash windows: die right after a ruling commit, before its executor runs.
GUIDANCE_WINDOWS = {"guidance_decided", "meta_decided"}
# ALIGN-03 crash window: die after the replan Guidance commit, before the
# independent ReplanDecision is consulted.
REPLAN_GUIDANCE_WINDOW = "replan_guidance_decided"
GUIDANCE_TRACE_1 = {
    "action_type": "trace_back", "specific_task": "REDO_FROM_SENTINEL",
    "use_pure_reasoning": False, "trace_back_to": 1,
    "rationale": "Retry from the first step",
}
META_TRACE_2 = {
    "decision": "TRACE_BACK", "reason_summary": "The rebuilt route also failed",
    "plan_summary": "Rebuild from the second step", "forbidden_directions": [],
    "reusable_results": [], "trace_back_to": 2,
}
REPLAN_GUIDANCE = {
    "action_type": "replan", "specific_task": "REPLAN_WORKER_SENTINEL",
    "use_pure_reasoning": False, "trace_back_to": None,
    "rationale": "The blocked route needs a new plan",
}
REPLAN_RULING = {
    "decision": "APPROVE_REPLAN", "reason_summary": "Switch to the direct route",
    "plan_summary": "Plan the direct route", "forbidden_directions": ["WORKER_DIRECTION"],
    "reusable_results": [], "trace_back_to": None,
}
PROPOSE_REPLAN = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN",
                  "objection": "The conclusion does not follow"}
ACCEPT_VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
# ALIGN-07 classified-outcome crash window: die right after the step-reviewed
# commit that appended the classified outcome, before the challenge continues.
CLASSIFIED_LEMMA = "Forward direction holds for the boundary case"
CLASSIFIED_CHALLENGE = {
    "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
    "objection": "The reverse direction is not justified.",
    "classified_outcomes": [
        {"category": "Lemma", "statement": CLASSIFIED_LEMMA,
         "scope": "boundary case of the base step", "claim_indexes": []},
    ],
}
# ALIGN-09 chain windows: one public Run crosses every new persistent boundary
# with a real process exit at each. chain_a seeds the Job; chain_b..chain_e are
# resume processes that die at the next boundary; the test resumes the last leg.
CHAIN_WINDOWS = {"chain_a", "chain_b", "chain_c", "chain_d", "chain_e"}
CHAIN_RESUME_WINDOWS = {"chain_b", "chain_c", "chain_d", "chain_e"}
CHAIN_LEMMA = "CHAIN-LEMMA forward direction of the addition identity"
CHAIN_CLASSIFIED = {
    "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN", "verdict": "CHALLENGE",
    "objection": "The computation must precede the conclusion.",
    "classified_outcomes": [
        {"category": "Lemma", "statement": CHAIN_LEMMA,
         "scope": "forward direction of the base step", "claim_indexes": [0]},
    ],
}
CHAIN_GUIDANCE = {
    "action_type": "trace_back", "specific_task": "REDO_CHAIN_SENTINEL",
    "use_pure_reasoning": False, "trace_back_to": 1,
    "rationale": "Rebuild the base step with its own computation",
}


def requests_so_far(folder):
    path = folder / "requests.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def guidance_reply(role, context, folder):
    """Two-fallback scenario: Guidance trace-back to 1, then a new Meta ruling to 2."""
    sent = requests_so_far(folder)  # The current request is already appended.
    window = (folder / "window").read_text()
    if role == "explore":
        return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
    if role == "planner":
        if window == REPLAN_GUIDANCE_WINDOW:
            # The replacement planner must be told this ruling's directions.
            return {**PLAN, "version": context.get("plan_version", 1)}
        return PLAN
    if role == "reasoner":
        step_id = context.get("step", {}).get("step_id")
        blocked = step_id == "s2" and sum(
            1 for item in sent if item.get("role") == "reasoner"
            and item.get("step", {}).get("step_id") == "s2") == 1
        return {"argument": "Addition", "claims": [], "blocked": blocked}
    if role == "step_verifier":
        step_id = context.get("step", {}).get("step_id")
        if window == REPLAN_GUIDANCE_WINDOW:
            # The replan window stays bounded: every review accepts.
            return ACCEPT_VERDICT
        reviewed = sum(1 for item in sent if item.get("role") == "step_verifier"
                       and item.get("step", {}).get("step_id") == step_id)
        # Only the first s3 review proposes; every other review accepts.
        return PROPOSE_REPLAN if step_id == "s3" and reviewed == 1 else ACCEPT_VERDICT
    if role == "meta":
        # A guidance request carries a non-null guidance_request; a ruling does not.
        if context.get("guidance_request") is not None:
            return REPLAN_GUIDANCE if window == REPLAN_GUIDANCE_WINDOW else GUIDANCE_TRACE_1
        return REPLAN_RULING if window == REPLAN_GUIDANCE_WINDOW else META_TRACE_2
    if role == "final_generator":
        return {"final_response": "2"}
    return {"verdict": "ACCEPT", "reason": "Addition"}


def chain_reply(role, context, folder):
    """One Run, five boundaries: guidance, tool receipt, classified review,
    CONTINUE new action and the final candidate, each followed by an exit."""
    sent = requests_so_far(folder)

    def seen(role_name, step_id=None):
        return sum(1 for item in sent if item.get("role") == role_name
                   and (step_id is None or item.get("step", {}).get("step_id") == step_id))

    if role == "explore":
        return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
    if role == "planner":
        return PLAN
    if role == "reasoner":
        step_id = context.get("step", {}).get("step_id")
        if step_id == "s1":
            attempt = seen("reasoner", "s1")
            if attempt == 2:
                return {"argument": "Redo with its own computation CHAIN-S1R", "claims": [
                    {"statement": "1+1=2 by the registered check", "label": "easy-verify",
                     "tool_request": {"tool": "polynomial_check", "arguments": {},
                                      "expected_output": 2, "scope": "finite_computation"}}],
                    "blocked": False}
            if attempt > 2:
                return {"argument": "Boundary case handled CHAIN-S1B",
                        "claims": [], "blocked": False}
            return {"argument": "Attempt one CHAIN-S1", "claims": [], "blocked": False}
        if step_id == "s2":
            if seen("reasoner", "s2") == 1:
                return {"argument": "Stuck second attempt CHAIN-S2", "claims": [],
                        "blocked": True}
            return {"argument": "Second fact CHAIN-S2B", "claims": [], "blocked": False}
        if seen("reasoner", "s3") == 1:
            return {"argument": "Conclusion attempt CHAIN-S3A", "claims": [], "blocked": False}
        return {"argument": "Conclusion CHAIN-S3B", "claims": [], "blocked": False}
    if role == "step_verifier":
        step_id = context.get("step", {}).get("step_id")
        if step_id == "s1":
            review = seen("step_verifier", "s1")
            if review == 2:
                return CHAIN_CLASSIFIED
            return ACCEPT_VERDICT
        if step_id == "s3" and seen("step_verifier", "s3") == 1:
            return PROPOSE_REPLAN
        return ACCEPT_VERDICT
    if role == "meta":
        if context.get("guidance_request") is not None:
            return CHAIN_GUIDANCE
        return META_CONTINUE_DECISION
    if role == "final_generator":
        return {"final_response": "1+1=2 CHAIN-ANSWER"}
    return {"verdict": "ACCEPT", "reason": "Addition"}


def config(folder, *, crash_tools=False):
    registry = ToolRegistry()
    def tool(_arguments):
        if crash_tools:
            os._exit(71)
        with (folder / "tool_runs.txt").open("a", encoding="utf-8") as output:
            output.write("executed\n")
        return 2
    registry.register("polynomial_check", tool)
    window = (folder / "window").read_text() if (folder / "window").exists() else ""
    # Guidance windows replay two fallback rulings; trace-back windows re-execute
    # every archived step on resume; meta_continue replays s1 as a new action.
    calls = (32 if window in CHAIN_WINDOWS
             else 24 if window in GUIDANCE_WINDOWS or window == REPLAN_GUIDANCE_WINDOW
             else 16 if window in TRACE_WINDOWS
             or window in {"meta_continue", "classified", "explore_tool"}
             else 12)
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
                                       "local_code_tool": True,
                                       **({"meta_guidance": True}
                                          if window in GUIDANCE_WINDOWS
                                          or window == REPLAN_GUIDANCE_WINDOW
                                          or window in CHAIN_WINDOWS else {})}}


def reply_value(window, context, folder):
    role = context["role"]
    if window in CHAIN_WINDOWS:
        return chain_reply(role, context, folder)
    if window in GUIDANCE_WINDOWS or window == REPLAN_GUIDANCE_WINDOW:
        return guidance_reply(role, context, folder)
    if role == "explore":
        value = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
        if window == "explore_tool" and sum(
            1
            for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            if (item := json.loads(line)).get("role") == "explore"
        ) == 1:
            # The first exploration demands its own computation before concluding.
            value = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                     "solution_candidate": "2", "tool_request": {
                         "tool": "polynomial_check", "arguments": {},
                         "scope": "finite_computation", "expected_output": 2}}
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
    elif (
        role == "step_verifier"
        and window == "classified"
        and context["step"]["step_id"] == "s1"
        and sum(
            1
            for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            if (item := json.loads(line)).get("role") == "step_verifier"
            and item.get("step", {}).get("step_id") == "s1"
        )
        == 1
    ):
        # The first s1 review challenges and classifies; the continuation accepts.
        value = CLASSIFIED_CHALLENGE
    elif role == "step_verifier":
        value = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
        if window == "verifier_tool" and context["step"]["step_id"] == "s2":
            seen = sum(
                1
                for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
                if (item := json.loads(line)).get("role") == "step_verifier"
                and item.get("step", {}).get("step_id") == "s2"
            )
            if seen == 1:
                # The first s2 review demands its own computation before accepting.
                value = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                         "objection": "", "tool_request": {
                             "tool": "polynomial_check", "arguments": {},
                             "scope": "finite_computation", "expected_output": 2}}
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
        if window == REPLAN_GUIDANCE_WINDOW:
            # Die after the replan Guidance commits, before the independent
            # ReplanDecision is consulted; resume must rule exactly once.
            if (event.get("solver_event_type") == "meta_guidance_decided"
                    and event.get("action_type") == "replan" and last.get("role") == "meta"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            return
        if window in GUIDANCE_WINDOWS:
            ruling = "meta_guidance_decided" if window == "guidance_decided" else "meta_decided"
            if event.get("solver_event_type") == ruling and last.get("role") == "meta":
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            return
        if window == "explore_tool":
            # ALIGN-06 crash window: die after the exploration's own tool receipt
            # commits, before the continuation reply is requested.
            if event.get("solver_event_type") == "tool_receipt" and last.get("role") == "explore":
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            return
        if window in CHAIN_WINDOWS:
            # ALIGN-09 combination windows: each dies at exactly one new
            # persistent boundary of the same public Run.
            if window == "chain_a" and event.get("solver_event_type") == "meta_guidance_decided":
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            if (window == "chain_b" and event.get("solver_event_type") == "tool_receipt"
                    and last.get("role") == "reasoner"
                    and last.get("step", {}).get("step_id") == "s1"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            if (window == "chain_c" and event.get("solver_event_type") == "step_reviewed"
                    and event.get("classified_outcomes")
                    and last.get("step", {}).get("step_id") == "s1"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            if (window == "chain_d" and event.get("solver_event_type") == "meta_decided"
                    and last.get("role") == "meta"
                    and last.get("progress", {}).get("current_step") == "s3"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            if (window == "chain_e"
                    and event.get("solver_event_type") == "final_candidate_generated"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)
            return
        target = {"accepted": "step_reviewed", "response": "call_audit",
                  "unknown": "never",
                  "tool_unknown": "never",
                  "tool": "tool_receipt",
                  "verifier_tool": "tool_receipt",
                  "exchange": "session_recorded",
                  "trace_before": "step_reviewed",
                  "trace_after": "trace_back_applied",
                  "stream_exit": "never",
                  "meta_continue": "meta_decided",
                  "classified": "step_reviewed"}[window]
        target_role = "reasoner" if window == "tool" else (
            "meta" if window == "meta_continue" else "step_verifier")
        if window == "meta_continue":
            hit_step = last.get("progress", {}).get("current_step") == "s1"
        else:
            hit_step = last.get("step", {}).get("step_id") == ("s1" if window == "classified" else "s2")
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
        if window in CHAIN_RESUME_WINDOWS:
            # Resume the Job crashed by the previous chain window and die at the
            # next persistent boundary of the same public Run.
            job_id = (folder / "job_id").read_text()
            response = client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                   headers=headers)
            (folder / "resume_status").write_text(str(response.status_code))
            time.sleep(20)
            raise RuntimeError("chain resume window was not reached")
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = str(uuid.uuid4())
        response = client.post("/api/agent/jobs", json={"message": "1+1", "session_id": session,
                               "solver_mode": "star_limited"}, headers=headers)
        (folder / "job_id").write_text(response.get_json()["job_id"])
        time.sleep(20)
    raise RuntimeError("crash window was not reached")


if __name__ == "__main__":
    main()
