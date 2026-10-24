"""AC-32: streaming fragment recovery through the public STAR Job seam."""

import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter, InternStreamAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import (ACCEPT, POLISH, SOLVED, StarJobFixture,
                                        assert_no_uncalibrated_probability)
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

PROMPT_MARKER = "Obey this exact response schema"


def split_fragments(value, parts=3):
    text = json.dumps(value, ensure_ascii=False)
    size = max(1, len(text) // parts)
    pieces = [text[index:index + size] for index in range(0, len(text), size)]
    return pieces


class ScriptedSSETransport:
    """SSE wire fake: fragments flow only after the audit persisted the prior one."""

    def __init__(self, case, plans):
        self.case = case
        self.plans = list(plans)
        self.outbound = []
        self.order_checks = 0

    def persisted_partial(self, call_id):
        import sqlite3

        connection = sqlite3.connect(
            str(Path(self.case.data_dir) / "showcase.sqlite3"), timeout=5)
        try:
            row = connection.execute(
                "SELECT state_json FROM solver_states").fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        record = json.loads(row[0]).get("calls", {}).get(call_id, {})
        return record.get("partial_text", "")

    def __call__(self, _url, **kwargs):
        context = json.loads(json.loads(kwargs["data"])["messages"][-1]["content"])
        self.outbound.append(context)
        plan = self.plans.pop(0)
        case = self.case
        seen = []
        transport = self

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_lines(self, decode_unicode=True):
                for item in plan:
                    if isinstance(item, BaseException):
                        raise item
                    if callable(item):
                        item = item(context)
                    if isinstance(item, dict) and item.get("exit_code") is not None:
                        os._exit(item["exit_code"])
                    if isinstance(item, dict) and item.get("type") == "result":
                        yield "data: " + json.dumps({"choices": [
                            {"delta": {}, "finish_reason": item.get("finish_reason", "stop")}],
                            "usage": item.get("usage", {"prompt_tokens": 7, "completion_tokens": 3,
                                                        "total_tokens": 10}),
                            "model": "intern-s2"})
                        yield "data: [DONE]"
                        return
                    # The audit must persist previously delivered fragments before
                    # the next provider fragment may be requested over the wire.
                    if seen:
                        persisted = transport.persisted_partial(context["call_id"])
                        case.assertIn("".join(seen), persisted or "")
                        transport.order_checks += 1
                    seen.append(item)
                    yield "data: " + json.dumps({"choices": [{"delta": {"content": item}}]})

        return Reply()


class StarStreamingRecoveryTest(StarJobFixture, unittest.TestCase):
    def open_stream(self, plans, **config):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data_dir = folder.name
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        self.transport = ScriptedSSETransport(self, plans)
        self.enterContext(patch("showcase.adapters.requests.post", side_effect=self.transport))
        self.outbound = self.transport.outbound
        self.app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": folder.name,
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection", **config})
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]

    def plan_for(self, replies):
        return [[*split_fragments(reply), {"type": "result"}] for reply in replies]

    def public_outputs(self, job_id):
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return stream, json.dumps([
            self.job(job_id), self.report(job_id),
            self.client.get(f"/api/runs/{job_id}/evidence").get_json()])

    def test_streamed_job_persists_each_delta_before_next_fragment_and_publishes_counts_only(self):
        self.open_stream(self.plan_for([
            NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
        ]), SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                          "final_generator", "whole_solution_verifier"],
                         [request["role"] for request in self.outbound])
        # Every later fragment waited for the persisted earlier fragment.
        self.assertGreaterEqual(self.transport.order_checks, 2 * len(self.outbound))
        stream, dumps = self.public_outputs(job_id)
        metrics = [json.loads(line[6:]) for line in stream.splitlines()
                   if line.startswith("data: ") and "stream_metrics" in line]
        reported = next(event for event in metrics
                        if event.get("solver_event_type") == "step_reported")
        self.assertEqual(3, reported["stream_metrics"]["fragments"])
        self.assertEqual("completed", reported["stream_metrics"]["status"])
        expected_bytes = sum(len(piece.encode("utf-8"))
                             for piece in split_fragments(STEP))
        self.assertEqual(expected_bytes, reported["stream_metrics"]["bytes"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        timeline_metrics = [event["stream_metrics"] for event in evidence["timeline"]
                            if event.get("stream_metrics")]
        self.assertTrue(timeline_metrics)
        self.assertTrue(all(set(item) == {"fragments", "bytes", "status"}
                            for item in timeline_metrics))
        # Public outputs never carry the streamed fragment text or the prompt.
        self.assertNotIn(split_fragments(VERDICT)[0], stream + dumps)
        self.assertNotIn(split_fragments(STEP)[0], stream + dumps)
        self.assertNotIn(PROMPT_MARKER, stream + dumps)
        self.assertNotIn("partial_text", stream + dumps)
        budget = final["result"]["budget"]
        self.assertEqual(6, budget["http_attempts"])
        self.assertEqual(6, budget["logical_calls"])
        self.assertEqual(16, budget["limits"]["max_model_calls"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertEqual(budget, evidence["budget"])

    def test_default_adapter_stays_non_streaming(self):
        self.open_star([SOLVED, POLISH, ACCEPT],
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
        self.assertFalse(callable(getattr(
            InternModelAdapter(InternChatClient(retry=1)), "stream_complete", None)))
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        stream, dumps = self.public_outputs(job_id)
        self.assertNotIn("stream_metrics", stream + dumps)
        self.assertNotIn("text_delta", stream + dumps)

    def test_mid_stream_timeout_keeps_unknown_reservation_and_requires_explicit_retry(self):
        timeout_plan = [
            *split_fragments(STEP)[:1],
            requests.Timeout("connection lost mid-stream"),
        ]
        self.open_stream([
            [*split_fragments(NEED_PLAN), {"type": "result"}],
            [*split_fragments(PLAN), {"type": "result"}],
            timeout_plan,
            [*split_fragments(STEP), {"type": "result"}],
            [*split_fragments(VERDICT), {"type": "result"}],
            [*split_fragments({"final_response": "2"}), {"type": "result"}],
            [*split_fragments(ACCEPT), {"type": "result"}],
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16))
        job_id = self.create_job()
        failed = self.terminal(job_id)
        self.assertEqual("failed", failed["status"], failed)
        recovery = failed["result"]["solver"]["recovery"]
        self.assertEqual("needs_review", recovery["status"])
        self.assertEqual(1, len(recovery["unknown_calls"]))
        old_id = recovery["unknown_calls"][0]["call_id"]
        original = failed["result"]["budget"]
        self.assertEqual(1, original["unknown_attempts"])
        self.assertGreater(original["reserved_tokens"], 0)
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        self.assertEqual("star_retry_decision_required", rejected.get_json()["error"])
        self.assertEqual(3, len(self.outbound))
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(7, len(self.outbound))
        budget = final["result"]["budget"]
        self.assertEqual(original["deadline_at"], budget["deadline_at"])
        self.assertEqual(original["reserved_tokens"], budget["reserved_tokens"])
        self.assertEqual(1, budget["unknown_attempts"])
        self.assertEqual(7, budget["http_attempts"])
        stream, dumps = self.public_outputs(job_id)
        self.assertNotIn(split_fragments(STEP)[0], stream + dumps)
        self.assertNotIn("partial_text", stream + dumps)

    def test_schema_invalid_complete_stream_is_not_normalized_and_never_shows_probability(self):
        uncalibrated = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                        "solution_candidate": "2", "confidence": 0.95}
        self.open_stream([
            [*split_fragments(uncalibrated), {"type": "result"}],
            [*split_fragments(NEED_PLAN), {"type": "result"}],
            [*split_fragments(PLAN), {"type": "result"}],
            [*split_fragments(STEP), {"type": "result"}],
            [*split_fragments(VERDICT), {"type": "result"}],
            [*split_fragments({"final_response": "2"}), {"type": "result"}],
            [*split_fragments(ACCEPT), {"type": "result"}],
        ], SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16))
        job_id = self.create_job()
        failed = self.terminal(job_id)
        self.assertEqual("failed", failed["status"], failed)
        recovery = failed["result"]["solver"]["recovery"]
        # ALIGN-04: the complete streamed package that fails the strict schema
        # is a known protocol failure, never an unknown remote outcome.
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("explore", recovery["protocol_failures"][0]["role"])
        self.assertEqual("invalid_role_schema", recovery["protocol_failures"][0]["error_category"])
        # The streamed complete package never became a normalized candidate.
        self.assertEqual([], failed["result"]["solver"]["candidate_history"])
        stream, dumps = self.public_outputs(job_id)
        # A raw-text '0.95' scan misfires on wall-clock fields (an ISO timestamp
        # like ...T06:47:20.9537650Z contains '0.95'); the leak check walks the
        # parsed public output instead.
        assert_no_uncalibrated_probability(self, stream, dumps)
        # The known failure ends dispatch honestly; no retry decision applies.
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        self.assertEqual(1, len(self.outbound))

    def test_process_exit_mid_stream_keeps_unknown_and_requires_explicit_new_identity(self):
        import subprocess
        import sys

        from showcase.flask_app import create_app
        from tests.star_recovery_worker import config, stream_transport

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run(
                [sys.executable, "-m", "tests.star_recovery_worker", directory, "stream_exit"],
                capture_output=True, timeout=60)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            self.assertEqual(1, len((folder / "requests.jsonl").read_text().splitlines()))
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "showcase.adapters.requests.post", side_effect=stream_transport(folder, "after")):
                app = create_app(config(folder))
                try:
                    self.app = app
                    self.client = app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    failed = self.terminal(job_id)
                    self.assertEqual("failed", failed["status"], failed)
                    recovery = failed["result"]["solver"]["recovery"]
                    self.assertEqual("needs_review", recovery["status"])
                    self.assertEqual(1, len(recovery["unknown_calls"]))
                    old_id = recovery["unknown_calls"][0]["call_id"]
                    original = failed["result"]["budget"]
                    rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                                headers=self.headers())
                    self.assertEqual(409, rejected.status_code)
                    self.assertEqual("star_retry_decision_required", rejected.get_json()["error"])
                    self.assertEqual(1, len((folder / "requests.jsonl").read_text().splitlines()))
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={
                        "retry_call": {"call_id": old_id, "new_call_id": str(uuid.uuid4())}},
                        headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    final = self.terminal(job_id)
                    self.assertEqual("succeeded", final["status"], final)
                    self.assertEqual(11, len((folder / "requests.jsonl").read_text().splitlines()))
                    budget = final["result"]["budget"]
                    self.assertEqual(original["deadline_at"], budget["deadline_at"])
                    self.assertEqual(1, budget["unknown_attempts"])
                    self.assertEqual(11, budget["logical_calls"])
                    self.assertEqual(11, budget["http_attempts"])
                    stream, dumps = self.public_outputs(job_id)
                    self.assertIn("stream_metrics", stream + dumps)
                    # The interrupted fragment text never reaches any public output.
                    self.assertNotIn('"assessment": "NE', stream + dumps)
                    self.assertNotIn("partial_text", stream + dumps)
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        app.extensions[name].close()
