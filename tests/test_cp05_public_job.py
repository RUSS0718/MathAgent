"""Public Job acceptance contracts for CP-05 checkpoint integration."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import tempfile
import time
import unittest
import uuid
import requests
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.test_star_product_planning import FEATURES as PLAN_FEATURES, STEP, VERDICT
import tests.test_star_product_streaming_recovery as streaming_support
from tests.test_star_product_tools import NEED_PLAN
from showcase.solver_harness.intern_schemas import response_schema


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


PLAN = {
    "version": 1,
    "steps": [{"step_id": "s1", "title": "proof", "objective": "derive the result"}],
}


def planner_checkpoint(status="YIELD", marker="planner-draft", *, gaps=None, version=1):
    return {
        "protocol_version": version,
        "checkpoint_id": marker,
        "status": status,
        "objective": "derive the result",
        "dependencies": ["known fact"],
        "evidence": [marker],
        "gaps": ["close the implication"] if gaps is None else gaps,
        "next_action": "close the implication",
    }


def reasoner_checkpoint(status="YIELD", marker="reasoner-draft", *, blocked=False):
    return {
        "checkpoint": {
            "protocol_version": 1,
            "checkpoint_id": marker,
            "status": status,
            "objective": "derive the result",
            "argument": marker,
            "claims": [{"statement": marker, "label": "hard-verify"}],
            "blocked": blocked,
            "dependencies": [],
            "evidence": [marker],
            "gaps": ["close the implication"] if status == "YIELD" else [],
            "next_action": "close the implication",
        }
    }


class _JsonResponse:
    status_code = 200

    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(self.value)}}],
            "model": "intern-s2",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class CP05PublicJobTest(unittest.TestCase):
    def open_app(self, replies, *, features=None, budget=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.requests = []
        self.messages = []
        remaining = list(replies)

        def post(*_args, **kwargs):
            payload = json.loads(kwargs["data"])
            context = json.loads(payload["messages"][-1]["content"])
            self.requests.append(context)
            self.messages.append(payload["messages"])
            return _JsonResponse(remaining.pop(0))

        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        self.enterContext(patch("llm_client.requests.post", side_effect=post))
        app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": str(Path(directory.name) / "showcase"),
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_FEATURES": features or {
                "final_generation": True,
                "final_solution_review": True,
                "meta_guidance": True,
                "planner_checkpoints": True,
                "reasoner_checkpoints": True,
            },
            "SHOWCASE_STAR_BUDGET": budget or RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=0
            ),
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                InternChatClient(retry=1), max_tokens=256
            ),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(app.extensions[name].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        return client, headers, session

    def run_public_job(self, replies, *, features):
        client, headers, session = self.open_app(replies, features=features)
        created = client.post(
            "/api/agent/jobs",
            json={"message": "prove the result", "session_id": session, "solver_mode": "star_limited"},
            headers=headers,
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        job = self.wait_for_terminal(client, job_id)
        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        evidence = client.get(f"/api/runs/{job_id}/evidence").get_json()
        events = client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return {
            "job": job,
            "report": report,
            "evidence": evidence,
            "events": events,
            "requests": list(self.requests),
            "messages": list(self.messages),
        }

    def wait_for_terminal(self, client, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.01)
        self.fail("CP-05 public Job did not reach a terminal state")

    def test_non_stream_checkpoint_job_covers_handoff_meta_and_final_review(self):
        replies = [
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": planner_checkpoint()},
            {"checkpoint": planner_checkpoint("FINAL", "planner-final", gaps=[]), "plan": PLAN},
            reasoner_checkpoint(blocked=True),
            {
                "action_type": "retry_different_method",
                "specific_task": "close the implication symbolically",
                "use_pure_reasoning": True,
                "trace_back_to": None,
                "rationale": "the first route is blocked",
            },
            reasoner_checkpoint("FINAL", "reasoner-final"),
            {
                "goal_gate": "YES",
                "logic_gate": "PASS",
                "verdict": "ACCEPT",
                "objection": "",
            },
            {"final_response": "The result follows from the accepted proof."},
            {"verdict": "ACCEPT", "reason": "The complete candidate is consistent."},
        ]
        client, headers, session = self.open_app(replies)
        created = client.post(
            "/api/agent/jobs",
            json={"message": "prove the result", "session_id": session, "solver_mode": "star_limited"},
            headers=headers,
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        job = self.wait_for_terminal(client, job_id)

        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(
            [
                "explore",
                "planner",
                "planner",
                "reasoner",
                "meta",
                "reasoner",
                "step_verifier",
                "final_generator",
                "whole_solution_verifier",
            ],
            [request["role"] for request in self.requests],
        )
        self.assertTrue(job["result"]["solver"]["progress"]["steps"][0]["reported"])
        self.assertEqual("completed", job["result"]["solver"]["semantics"]["execution"])
        self.assertEqual("accepted", job["result"]["solver"]["semantics"]["whole_review"])
        self.assertEqual("The result follows from the accepted proof.", job["result"]["final_response"])
        evidence = client.get(f"/api/runs/{job_id}/evidence").get_json()

        runtime_entries = [
            event for event in evidence["timeline"]
            if event.get("role") and event.get("prompt_fingerprint")
        ]
        self.assertTrue(runtime_entries)
        expected_prompt_fingerprints = {}
        for request, messages in zip(self.requests, self.messages):
            expected_prompt_fingerprints.setdefault(request["role"], set()).add(
                fingerprint(messages)
            )
        actual_prompt_fingerprints = {}
        for event in runtime_entries:
            actual_prompt_fingerprints.setdefault(event["role"], set()).add(
                event["prompt_fingerprint"]
            )
        self.assertEqual(expected_prompt_fingerprints, actual_prompt_fingerprints)
        self.assertIn("final_generator", actual_prompt_fingerprints)
        self.assertTrue(all(
            all(value == "unavailable" for value in event["stream_activity"].values())
            for event in runtime_entries
        ))
        self.assertEqual(
            {fingerprint(response_schema(request)) for request in self.requests},
            {event["schema_fingerprint"] for event in runtime_entries},
        )
        self.assertEqual(
            {fingerprint("prove the result")},
            {event["input_fingerprint"] for event in runtime_entries},
        )
        self.assertEqual(
            {fingerprint(request) for request in self.requests},
            {fingerprint(json.loads(messages[-1]["content"])) for messages in self.messages},
        )

        raw_call_ids = {request["call_id"] for request in self.requests}
        public_call_ids = {
            attempt["solver_call_id"] for attempt in job["result"]["request_attempts"]
        }
        self.assertTrue(public_call_ids)
        self.assertTrue(all(call_id.startswith("solver_call_") for call_id in public_call_ids))
        self.assertTrue(raw_call_ids.isdisjoint(public_call_ids))

        stream = client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("checkpoint_status", stream)
        self.assertIn("meta_guidance_decided", stream)
        self.assertNotIn("prove the result", stream)
        self.assertNotIn("close the implication symbolically", stream)

    def test_public_job_stops_on_repeated_empty_planner_yield_after_one_format_repair(self):
        client, headers, session = self.open_app([
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": planner_checkpoint(gaps=[])},
            {"checkpoint": planner_checkpoint(gaps=[])},
        ])
        created = client.post(
            "/api/agent/jobs",
            json={"message": "prove the result", "session_id": session, "solver_mode": "star_limited"},
            headers=headers,
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job = self.wait_for_terminal(client, created.get_json()["job_id"])

        self.assertEqual("failed", job["status"], job)
        self.assertEqual(["explore", "planner", "planner"], [request["role"] for request in self.requests])
        first, repair = self.requests[1:]
        self.assertEqual(first["call_id"] + ":repair-1", repair["call_id"])
        self.assertEqual(first["checkpoint_round"], repair["checkpoint_round"])
        self.assertTrue(repair["format_repair"])
        self.assertEqual("protocol_failure_unrepaired", job["result"]["solver"]["result_reason"])
        self.assertEqual(3, len(job["result"]["request_attempts"]))

    def test_public_planner_rejects_invalid_progress_and_budget_before_continuation(self):
        cases = (
            (
                "invalid_version",
                [
                    {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                    {"checkpoint": planner_checkpoint(version=0)},
                ],
                None,
                ["explore", "planner"],
                "partial_aborted",
            ),
            (
                "no_progress",
                [
                    {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                    {"checkpoint": planner_checkpoint()},
                    {"checkpoint": planner_checkpoint()},
                ],
                None,
                ["explore", "planner", "planner"],
                "partial_aborted",
            ),
            (
                "budget",
                [
                    {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                    {"checkpoint": planner_checkpoint()},
                ],
                RunBudgetLimits(max_model_calls=2, max_http_attempts=2, max_tool_calls=0),
                ["explore", "planner"],
                "partial_budget_exhausted",
            ),
        )
        for name, replies, budget, roles, status in cases:
            with self.subTest(case=name):
                client, headers, session = self.open_app(replies, budget=budget)
                created = client.post(
                    "/api/agent/jobs",
                    json={"message": "prove the result", "session_id": session,
                          "solver_mode": "star_limited"},
                    headers=headers,
                )
                self.assertEqual(202, created.status_code, created.get_json())
                job = self.wait_for_terminal(client, created.get_json()["job_id"])
                self.assertEqual("failed", job["status"], job)
                self.assertEqual(status, job["result"]["solver"]["status"], job)
                self.assertEqual(roles, [request["role"] for request in self.requests])

    def test_control_and_checkpoint_candidate_share_public_job_contract(self):
        control = self.run_public_job(
            [
                {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                PLAN,
                {"argument": "accepted proof", "claims": [], "blocked": False},
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
                {"final_response": "The result follows from the accepted proof."},
                {"verdict": "ACCEPT", "reason": "The complete candidate is consistent."},
            ],
            features={"final_generation": True, "final_solution_review": True},
        )
        candidate = self.run_public_job(
            [
                {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                {"checkpoint": planner_checkpoint()},
                {"checkpoint": planner_checkpoint("FINAL", "planner-final", gaps=[]), "plan": PLAN},
                reasoner_checkpoint(blocked=True),
                {
                    "action_type": "retry_different_method",
                    "specific_task": "close the implication symbolically",
                    "use_pure_reasoning": True,
                    "trace_back_to": None,
                    "rationale": "the first route is blocked",
                },
                reasoner_checkpoint("FINAL", "reasoner-final"),
                {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""},
                {"final_response": "The result follows from the accepted proof."},
                {"verdict": "ACCEPT", "reason": "The complete candidate is consistent."},
            ],
            features={
                "final_generation": True,
                "final_solution_review": True,
                "meta_guidance": True,
                "planner_checkpoints": True,
                "reasoner_checkpoints": True,
            },
        )

        self.assertEqual(
            ["explore", "planner", "reasoner", "step_verifier", "final_generator",
             "whole_solution_verifier"],
            [request["role"] for request in control["requests"]],
        )
        self.assertEqual(
            ["explore", "planner", "planner", "reasoner", "meta", "reasoner",
             "step_verifier", "final_generator", "whole_solution_verifier"],
            [request["role"] for request in candidate["requests"]],
        )
        self.assertEqual(6, control["job"]["result"]["budget"]["logical_calls"])
        self.assertEqual(6, control["job"]["result"]["budget"]["http_attempts"])
        self.assertEqual(9, candidate["job"]["result"]["budget"]["logical_calls"])
        self.assertEqual(9, candidate["job"]["result"]["budget"]["http_attempts"])
        for run in (control, candidate):
            job, report, evidence = run["job"], run["report"], run["evidence"]
            self.assertEqual("succeeded", job["status"])
            self.assertEqual("completed", job["result"]["solver"]["semantics"]["execution"])
            self.assertEqual("accepted", job["result"]["solver"]["semantics"]["whole_review"])
            self.assertEqual("The result follows from the accepted proof.", job["result"]["final_response"])
            self.assertEqual(job["result"]["final_response"], report["answer"])
            self.assertEqual(report["answer"], evidence["report"]["answer"])
            self.assertEqual(report["semantics"], evidence["semantics"])
            self.assertEqual(report["checks"], evidence["verification"])
            self.assertEqual(report["budget"], evidence["budget"])
            self.assertEqual(report["request_attempts"], evidence["request_attempts"])
            self.assertEqual(0, job["result"]["budget"]["tool_calls"])

    def test_checkpoint_feature_switch_is_rejected_only_when_unknown_and_disabled_path_stays_legacy(self):
        from showcase.run_budget import RunBudgetLimits
        from showcase.star_product_config import limited_config

        disabled = limited_config(RunBudgetLimits(3, 3, 0))
        self.assertNotIn("planner_checkpoints", disabled["features"])
        self.assertNotIn("reasoner_checkpoints", disabled["features"])
        enabled = limited_config(
            RunBudgetLimits(3, 3, 0),
            {"planner_checkpoints": True, "reasoner_checkpoints": True},
        )
        self.assertTrue(enabled["features"]["planner_checkpoints"])
        self.assertTrue(enabled["features"]["reasoner_checkpoints"])
        with self.assertRaisesRegex(ValueError, "star_features_invalid"):
            limited_config(RunBudgetLimits(3, 3, 0), {"unknown_checkpoint": True})


class CP05DocumentationContractTest(unittest.TestCase):
    def test_handoff_document_records_scope_and_evidence_boundary(self):
        document = Path("docs/evals/showcase-cp05-checkpoint-handoff.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "CP-01..CP-04",
            "#112",
            "loopback",
            "replay",
            "provider-live",
            "unknown",
            "not_run",
            "deadline",
            "脱敏",
            "静默",
            "无正文",
            "缺 usage",
            "断流",
            "取消",
            "迟到",
        ):
            self.assertIn(marker, document)
        self.assertNotIn("INTERN_API_KEY", document)
        self.assertNotIn("Obey this exact response schema", document)


class CP05StreamingMatrixTest(StarJobFixture, unittest.TestCase):
    """CP-05 public Job stream outcomes using the existing SSE fixture."""

    def open_stream(self, plans, **config):
        return streaming_support.StarStreamingRecoveryTest.open_stream(self, plans, **config)

    def plan_for(self, replies):
        return streaming_support.StarStreamingRecoveryTest.plan_for(self, replies)

    @staticmethod
    def plan_without_usage(replies):
        return [
            [*streaming_support.split_fragments(reply), {"type": "result", "usage": {}}]
            for reply in replies
        ]

    def test_public_stream_matrix(self):
        features = {**PLAN_FEATURES, "stream_activity": True}
        plan = {"version": 1, "steps": [
            {"step_id": "sum", "title": "Add", "objective": "Compute 1+1"}
        ]}

        with self.subTest(case="normal"):
            self.open_stream(
                self.plan_for([NEED_PLAN, plan, STEP, VERDICT,
                               {"final_response": "2"}, {"verdict": "ACCEPT"}]),
                SHOWCASE_STAR_FEATURES=features,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            )
            result = self.terminal(self.create_job())
            self.assertEqual("succeeded", result["status"], result)
            self.assertEqual(0, result["result"]["budget"]["unknown_attempts"])

        with self.subTest(case="empty_body"):
            self.open_stream(
                [[{"type": "result"}]],
                SHOWCASE_STAR_FEATURES=features,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4),
            )
            result = self.terminal(self.create_job())
            self.assertEqual("failed", result["status"], result)
            failures = result["result"]["solver"]["recovery"]["protocol_failures"]
            self.assertEqual("empty_response", failures[0]["error_category"])

        with self.subTest(case="missing_usage"):
            self.open_stream(
                self.plan_without_usage([NEED_PLAN, plan, STEP, VERDICT,
                                         {"final_response": "2"}, {"verdict": "ACCEPT"}]),
                SHOWCASE_STAR_FEATURES=features,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8),
            )
            result = self.terminal(self.create_job())
            self.assertEqual("succeeded", result["status"], result)
            self.assertTrue(all(
                attempt["usage"]["total_tokens"] is None
                and attempt["metering_status"] == "unknown"
                for attempt in result["result"]["request_attempts"]
            ))

        with self.subTest(case="disconnect"):
            self.open_stream([
                [*streaming_support.split_fragments(NEED_PLAN), {"type": "result"}],
                [*streaming_support.split_fragments(plan), {"type": "result"}],
                [streaming_support.split_fragments(STEP)[0], requests.Timeout("disconnect")],
            ], SHOWCASE_STAR_FEATURES=features,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
            result = self.terminal(self.create_job())
            self.assertEqual("failed", result["status"], result)
            recovery = result["result"]["solver"]["recovery"]
            self.assertEqual("needs_review", recovery["status"])
            self.assertEqual(1, len(recovery["unknown_calls"]))

        with self.subTest(case="cancel"):
            entered, release = threading.Event(), threading.Event()
            self.addCleanup(release.set)

            def block(_context):
                entered.set()
                release.wait(3)
                return {"type": "result"}

            self.open_stream([[block]], SHOWCASE_STAR_FEATURES=features,
                             SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=4, max_http_attempts=4))
            job_id = self.create_job()
            self.assertTrue(entered.wait(3))
            self.assertEqual("canceled", self.cancel(job_id)["status"])
            release.set()
            self.assertEqual("canceled", self.terminal(job_id)["status"])

        with self.subTest(case="late"):
            from tests.test_star_stream_late_race_98 import StreamLateRaceTest, completed_sse

            StreamLateRaceTest.open_stream(self)
            callbacks = []

            class Reply:
                status_code = 200

            def transport(_url, *, on_late_response, **_kwargs):
                callbacks.append(on_late_response)
                raise requests.ReadTimeout("deadline")
                yield

            with patch("showcase.request_transport.response_events", side_effect=transport):
                job_id = self.create_job()
                before = self.terminal(job_id)
                before_solver = before["result"]["solver"]
                attempt_id = before["result"]["request_attempts"][0]["attempt_id"]
                callbacks[0](Reply(), completed_sse(), .01, .2, True)
                after = self.job(job_id)
            self.assertEqual("failed", before["status"])
            self.assertEqual(before_solver, after["result"]["solver"])
            self.assertEqual(attempt_id, after["result"]["request_attempts"][0]["attempt_id"])
            self.assertEqual("success", after["result"]["request_attempts"][0]["status"])
            self.assertEqual(10, after["result"]["request_attempts"][0]["usage"]["total_tokens"])


if __name__ == "__main__":
    unittest.main()
