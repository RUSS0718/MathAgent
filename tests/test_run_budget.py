from __future__ import annotations

import os
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline, PipelineBudget
from showcase.tools import ToolRegistry


class Response:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": "2"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class RunBudgetContractTest(unittest.TestCase):
    def test_synchronous_run_blocks_unmetered_and_exhausted_transports(self):
        from showcase.adapters import InternAgentAdapter
        from showcase.run_service import RunService

        class UnsupportedClient:
            calls = 0

            def chat(self, messages, *, temperature, max_tokens):
                self.calls += 1
                return "2"

        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}))
        unsupported = UnsupportedClient()
        cases = [
            (InternChatClient(retry=1), PipelineBudget(max_model_calls=0)),
            (InternChatClient(retry=1), PipelineBudget(max_http_attempts=0)),
            (InternChatClient(retry=1), PipelineBudget(max_tokens=0)),
            (unsupported, PipelineBudget()),
        ]
        for transport, limits in cases:
            with self.subTest(limits=limits, transport=type(transport).__name__), tempfile.TemporaryDirectory() as directory:
                service = RunService(
                    agent=InternAgentAdapter(InternModelAdapter(transport, max_tokens=256)),
                    run_budget_limits=limits,
                )
                app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": directory}, service=service)
                try:
                    with patch("llm_client.requests.post", return_value=Response()) as post:
                        client = app.test_client()
                        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                        run = client.post("/api/runs", json={"problem": "1+1"}, headers={"X-CSRF-Token": csrf}).get_json()
                        self.assertEqual("FAILED", run["status"])
                        evidence = client.get(f"/api/runs/{run['run_id']}/evidence").get_json()
                        self.assertEqual(0, evidence["budget"]["http_attempts"])
                        self.assertEqual(0, post.call_count)
                        self.assertEqual(0, unsupported.calls)
                finally:
                    for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        app.extensions[key].close()

    def run_job(self, *, budget=None, responses=None, pipeline_factory=None, registry=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "fake-key"}))
        post = self.enterContext(
            patch("llm_client.requests.post", side_effect=responses, return_value=Response())
        )
        self.enterContext(patch("llm_client.time.sleep"))
        pipeline = LiveAgentPipeline(
            InternModelAdapter(InternChatClient(retry=2), max_tokens=256),
            registry or ToolRegistry(),
            budget=budget,
        )
        if pipeline_factory:
            pipeline = pipeline_factory(pipeline.model)
        app = create_app(
            {
                "TESTING": True,
                "SHOWCASE_MODE": "live",
                "SHOWCASE_DATA_DIR": directory.name,
                "SHOWCASE_LIVE_PIPELINE": pipeline,
            }
        )
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(app.extensions[key].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        job_id = client.post(
            "/api/agent/jobs", json={"message": "1+1", "session_id": session}, headers=headers
        ).get_json()["job_id"]
        for _ in range(300):
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.01)
        report = client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        evidence = client.get(f"/api/runs/{job_id}/evidence").get_json()
        return job, report, evidence, post

    def test_provider_usage_settles_reservations_in_persisted_report(self):
        job, report, evidence, post = self.run_job()
        self.assertEqual("succeeded", job["status"])
        ledger = report["budget"]
        self.assertEqual(3, ledger["logical_calls"])
        self.assertEqual(3, ledger["http_attempts"])
        self.assertEqual(
            {"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
            ledger["provider_known"],
        )
        self.assertEqual(0, ledger["reserved_tokens"])
        self.assertEqual(0, ledger["unknown_attempts"])
        self.assertIsNone(ledger["cost"])
        self.assertEqual(ledger, evidence["budget"])
        self.assertEqual(3, post.call_count)

    def test_retry_timeout_keeps_unknown_reservation_and_consumes_attempt_budget(self):
        from requests import Timeout

        job, report, _evidence, post = self.run_job(
            budget=PipelineBudget(max_http_attempts=1),
            responses=[Timeout("private"), Response()],
        )
        self.assertEqual("failed", job["status"])
        self.assertEqual(1, post.call_count)
        ledger = report["budget"]
        self.assertEqual(1, ledger["logical_calls"])
        self.assertEqual(1, ledger["http_attempts"])
        self.assertEqual(1, ledger["unknown_attempts"])
        self.assertEqual(1, ledger["unresolved_attempts"])
        self.assertGreaterEqual(ledger["reserved_tokens"], 256)
        self.assertIsNone(ledger["provider_known"]["total_tokens"])

    def test_input_plus_output_reservation_blocks_dispatch_before_http(self):
        job, report, _evidence, post = self.run_job(budget=PipelineBudget(max_tokens=256))
        self.assertEqual("failed", job["status"])
        self.assertEqual(0, post.call_count)
        self.assertEqual(0, report["budget"]["http_attempts"])

    def test_missing_usage_is_not_free_and_exhausts_next_reservation(self):
        class MissingUsage(Response):
            def json(self):
                result = super().json()
                del result["usage"]
                return result

        job, report, _evidence, post = self.run_job(
            budget=PipelineBudget(max_tokens=850),
            responses=[MissingUsage(), Response(), Response()],
        )
        self.assertEqual("failed", job["status"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, report["budget"]["unknown_attempts"])
        self.assertGreater(report["budget"]["reserved_tokens"], 256)
        self.assertIsNone(report["budget"]["provider_known"]["prompt_tokens"])

    def test_same_run_workers_and_reopened_ledger_share_attempt_limit(self):
        import sqlite3
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from showcase.adapters import AdapterError
        from showcase.run_budget import (
            RunBudgetLedger,
            RunBudgetLimits,
            bind_budget,
            current_budget,
        )

        class ParallelPipeline:
            budget = PipelineBudget(max_http_attempts=1)

            def __init__(self, model):
                self.model = model

            def run(self, run_id, problem, **_kwargs):
                original = current_budget()
                database = original.ledger.connection.execute("PRAGMA database_list").fetchone()[2]
                barrier = threading.Barrier(2)

                def worker():
                    connection = sqlite3.connect(database, check_same_thread=False)
                    try:
                        ledger = RunBudgetLedger(connection)
                        # Reopening with larger limits must retain the first Run contract.
                        handle = ledger.ensure(run_id, RunBudgetLimits(max_http_attempts=99))
                        barrier.wait(timeout=2)
                        with bind_budget(handle):
                            try:
                                self.model.complete([{"role": "user", "content": problem}])
                                return "sent"
                            except AdapterError:
                                return "blocked"
                    finally:
                        connection.close()

                with ThreadPoolExecutor(max_workers=2) as executor:
                    results = list(executor.map(lambda _: worker(), range(2)))
                return {
                    "status": "COMPLETED",
                    "final_response": ",".join(sorted(results)),
                    "budget": original.snapshot(),
                }

        job, report, _evidence, post = self.run_job(pipeline_factory=ParallelPipeline)
        self.assertEqual("succeeded", job["status"])
        self.assertEqual("blocked,sent", report["answer"])
        self.assertEqual(1, post.call_count)
        self.assertEqual(1, report["budget"]["http_attempts"])
        self.assertEqual(1, report["budget"]["limits"]["max_http_attempts"])

    def test_budget_limits_reject_invalid_or_unbounded_values(self):
        for field, value in [
            ("max_tokens", -1),
            ("max_tokens", True),
            ("max_http_attempts", 1.5),
            ("max_model_calls", float("inf")),
            ("max_runtime_seconds", float("nan")),
        ]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                PipelineBudget(**{field: value})

    def test_tool_dispatch_uses_shared_run_ledger(self):
        class ToolResponse(Response):
            def json(self):
                result = super().json()
                result["choices"] = [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "calculate", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ]
                return result

        calls = []
        registry = ToolRegistry()
        registry.register("calculate", lambda _arguments: calls.append("called") or 2)
        job, report, _evidence, post = self.run_job(
            budget=PipelineBudget(max_tool_calls=0),
            registry=registry,
            responses=[Response(), ToolResponse(), Response(), Response()],
        )
        self.assertEqual("failed", job["status"])
        self.assertEqual([], calls)
        self.assertEqual(2, post.call_count)
        self.assertEqual(0, report["budget"]["tool_calls"])

    def test_known_partial_usage_keeps_unknown_fields_and_reservation(self):
        class PartialUsage(Response):
            def json(self):
                result = super().json()
                result["usage"] = {"prompt_tokens": 7}
                return result

        job, report, _evidence, _post = self.run_job(responses=[PartialUsage()] * 3)
        self.assertEqual("succeeded", job["status"])
        ledger = report["budget"]
        self.assertEqual(21, ledger["provider_known"]["prompt_tokens"])
        self.assertIsNone(ledger["provider_known"]["total_tokens"])
        self.assertEqual(768, ledger["reserved_tokens"])
        self.assertEqual(3, ledger["provider_unknown_fields"]["completion_tokens"])

    def test_expired_utc_run_deadline_blocks_http(self):
        job, report, _evidence, post = self.run_job(budget=PipelineBudget(max_runtime_seconds=0))
        self.assertEqual("failed", job["status"])
        self.assertEqual(0, post.call_count)
        self.assertEqual(report["budget"]["started_at"], report["budget"]["deadline_at"])

    def test_successful_retry_uses_one_logical_call_and_two_attempts(self):
        from requests import ConnectTimeout

        job, report, _evidence, post = self.run_job(
            responses=[ConnectTimeout("private"), Response(), Response(), Response()]
        )
        self.assertEqual("succeeded", job["status"])
        self.assertEqual(4, post.call_count)
        self.assertEqual(3, report["budget"]["logical_calls"])
        self.assertEqual(4, report["budget"]["http_attempts"])
        self.assertEqual(0, report["budget"]["unresolved_attempts"])
        self.assertEqual(0, report["budget"]["reserved_tokens"])

    def test_langgraph_run_and_resume_keep_the_same_persisted_budget(self):
        from pathlib import Path

        from showcase.adapters import InternAgentAdapter
        from showcase.graph import LangGraphExecutionLoop
        from showcase.run_service import RunService

        class ToolResponse(Response):
            def json(self):
                result = super().json()
                result["choices"] = [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "calculate", "arguments": "{}"},
                                }
                            ],
                        },
                    }
                ]
                return result

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"INTERN_API_KEY": "fake"}),
            patch("llm_client.requests.post", return_value=ToolResponse()) as post,
        ):
            registry = ToolRegistry()
            registry.register("calculate", lambda _arguments: 2)
            model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256)
            database = Path(directory) / "runs.sqlite3"
            service = RunService(
                database_path=database,
                execution_loop=LangGraphExecutionLoop(InternAgentAdapter(model), registry),
                run_budget_limits=PipelineBudget(max_model_calls=1),
            )
            app = create_app(
                {"TESTING": True, "SHOWCASE_DATA_DIR": directory},
                service=service,
                database_path=database,
            )
            try:
                client = app.test_client()
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                response = client.post(
                    "/api/runs", json={"problem": "1+1"}, headers={"X-CSRF-Token": csrf}
                )
                self.assertEqual(201, response.status_code)
                run_id = response.get_json()["run_id"]
                report = client.get(f"/api/runs/{run_id}/report").get_json()["report"]
                self.assertEqual(1, report["budget"]["logical_calls"])
                self.assertEqual(1, report["budget"]["http_attempts"])
                self.assertEqual(1, report["budget"]["tool_calls"])
                service.resume_run(run_id)
                resumed = client.get(f"/api/runs/{run_id}/evidence").get_json()["budget"]
                self.assertEqual(1, post.call_count)
                self.assertEqual(1, resumed["logical_calls"])
                self.assertEqual(report["budget"]["deadline_at"], resumed["deadline_at"])
            finally:
                for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                    app.extensions[key].close()
