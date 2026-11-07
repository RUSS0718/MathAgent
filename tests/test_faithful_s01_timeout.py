"""S01 stream lifecycle behavior through the adapter, budget, and Job seams."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from showcase.adapters import AdapterError, InternStreamAdapter
from showcase.request_transport import DeadlineNotSubmitted
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.run_service import RunService
from showcase.solver_harness import SolverHarness
from showcase.workspace import WorkspaceService

STREAM_POLICY = {
    "policy_version": "faithful-stream-v1",
    "soft_prompt_seconds": 1200,
    "effective_idle_seconds": 30,
}


class VirtualClock:
    def __init__(self, initial: float | None = None) -> None:
        self.value = time.time() if initial is None else initial

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def data_packet(value: dict) -> bytes:
    return ("data: " + json.dumps(value, separators=(",", ":")) + "\n\n").encode()


def content_packet(text: str) -> bytes:
    return data_packet({"choices": [{"delta": {"content": text}}]})


def identified_content_packet(event_id: str, text: str) -> bytes:
    return f"id: {event_id}\n".encode() + content_packet(text)


def usage_packet() -> bytes:
    return data_packet({"choices": [], "usage": {
        "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
    }})


class FaithfulStreamTimeoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = VirtualClock()
        self.ledger = RunBudgetLedger()
        self.addCleanup(self.ledger.close)
        self.response = requests.Response()
        self.response.status_code = 200
        self.client = SimpleNamespace(
            api_base="http://127.0.0.1:1/chat/completions",
            authorization="Bearer synthetic",
            model="intern-s2-test",
            timeout=180,
            retry=1,
            thinking_mode=False,
            loopback_only=True,
        )
        self.adapter = InternStreamAdapter(self.client, max_tokens=64)

    def budget(self, seconds: float = 1500.0, attempts: int = 12):
        return self.ledger.ensure(
            f"s01-run-{uuid.uuid4().hex}",
            RunBudgetLimits(
                max_model_calls=2,
                max_http_attempts=attempts,
                max_tool_calls=0,
                max_tokens=10_000,
                max_runtime_seconds=seconds,
            ),
            stream_timeout_policy=STREAM_POLICY,
        )

    def run_stream(self, budget, transport, *, activity=None):
        with (
            patch("showcase.adapters.time.time", self.clock),
            patch("showcase.request_transport.response_events", side_effect=transport),
            bind_budget(budget),
        ):
            return list(self.adapter.stream_complete(
                [{"role": "user", "content": "synthetic"}],
                metadata={"role": "explore", "activity_observer": activity.append if isinstance(activity, list) else activity},
            ))

    def _advance_and_tick(self, clock, kwargs, seconds: float) -> None:
        clock.advance(seconds)
        soft_deadline = kwargs.get("soft_deadline_at")
        if soft_deadline is not None and clock() >= soft_deadline:
            kwargs["on_soft_deadline"]()
        deadlines = [kwargs["deadline"]]
        idle_deadline = kwargs.get("effective_idle_deadline")
        if callable(idle_deadline):
            idle_deadline = idle_deadline()
            if idle_deadline is not None:
                deadlines.append(idle_deadline)
        if clock() >= min(deadlines):
            raise requests.ReadTimeout("synthetic virtual deadline")

    def test_live_stream_runs_1300_seconds_and_emits_one_soft_prompt(self):
        budget = self.budget()
        started = self.clock()
        observed = []
        transport_args = {}

        def transport(_url, **kwargs):
            transport_args.update(kwargs)
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", content_packet("part-0")
            for index in range(1, 42):
                self._advance_and_tick(self.clock, kwargs, 29)
                yield "bytes", content_packet(f"part-{index}")
            self._advance_and_tick(self.clock, kwargs, 10)
            self.assertEqual(1200, self.clock() - started)
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", content_packet("part-42")
            for index, interval in enumerate((29, 29, 29, 12), start=43):
                self._advance_and_tick(self.clock, kwargs, interval)
                yield "bytes", content_packet(f"part-{index}")
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None

        result = self.run_stream(budget, transport, activity=observed)[-1]

        self.assertEqual("success", result["attempts"][0]["status"])
        self.assertEqual(1300, self.clock() - started)
        warnings = [item for item in observed if item.get("kind") == "soft_timeout_warning"]
        self.assertEqual(1, len(warnings))
        self.assertEqual(1200, warnings[0]["elapsed_seconds"])
        self.assertIsInstance(transport_args["deadline"], (int, float))
        self.assertGreater(transport_args["timeout"][1], 1300)
        self.assertEqual(180, transport_args["timeout"][0])
        self.assertIsNone(result["attempts"][0]["requests_timeout_seconds"])

    def test_first_effective_delta_can_arrive_after_client_timeout(self):
        budget = self.budget()
        started = self.clock()

        def transport(_url, **kwargs):
            yield "headers", self.response
            for _ in range(6):
                self._advance_and_tick(self.clock, kwargs, 30)
                yield "bytes", b": heartbeat\n\n"
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", content_packet("late first delta")
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None

        result = self.run_stream(budget, transport)[-1]

        self.assertEqual("success", result["attempts"][0]["status"])
        self.assertEqual("late first delta", result["text"])
        self.assertEqual(181, self.clock() - started)

    def test_heartbeat_usage_role_and_duplicate_delta_do_not_refresh_idle(self):
        budget = self.budget()

        def transport(_url, **kwargs):
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1)
            first = identified_content_packet("event-1", "partial")
            yield "bytes", first
            self._advance_and_tick(self.clock, kwargs, 10)
            yield "bytes", b": keepalive\n\n"
            self._advance_and_tick(self.clock, kwargs, 10)
            yield "bytes", usage_packet()
            self._advance_and_tick(self.clock, kwargs, 9)
            yield "bytes", first
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", b": keepalive\n\n"

        with self.assertRaises(AdapterError) as caught:
            self.run_stream(budget, transport)

        self.assertEqual("timeout", caught.exception.category)
        attempt = caught.exception.request_attempts[0]
        self.assertEqual(5, attempt["usage"]["total_tokens"])
        self.assertEqual(len("partial"), attempt["content_bytes"])
        self.assertEqual(1, budget.snapshot()["unresolved_attempts"])
        self.assertGreater(budget.snapshot()["reserved_tokens"], 0)

    def test_identical_unidentified_deltas_are_both_streamed_and_refresh_idle(self):
        budget = self.budget()

        def transport(_url, **kwargs):
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", content_packet("same")
            self._advance_and_tick(self.clock, kwargs, 28)
            yield "bytes", content_packet("same")
            self._advance_and_tick(self.clock, kwargs, 29)
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None

        chunks = self.run_stream(budget, transport)
        deltas = [item["text"] for item in chunks if item.get("type") == "text_delta"]
        result = chunks[-1]

        self.assertEqual(["same", "same"], deltas)
        self.assertEqual("samesame", result["text"])
        self.assertEqual(result["text"], "".join(deltas))

    def test_same_explicit_sse_id_and_data_are_deduplicated(self):
        budget = self.budget()

        def transport(_url, **kwargs):
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1)
            packet = identified_content_packet("event-1", "once")
            yield "bytes", packet
            self._advance_and_tick(self.clock, kwargs, 29)
            yield "bytes", packet
            self._advance_and_tick(self.clock, kwargs, 1)

        chunks = []
        with patch("showcase.adapters.time.time", self.clock), patch(
            "showcase.request_transport.response_events", side_effect=transport
        ), bind_budget(budget), self.assertRaises(AdapterError) as caught:
            for chunk in self.adapter.stream_complete(
                [{"role": "user", "content": "synthetic"}], metadata={"role": "explore"}
            ):
                chunks.append(chunk)

        self.assertEqual("timeout", caught.exception.category)
        self.assertEqual(["once"], [chunk["text"] for chunk in chunks])
        self.assertEqual(4, caught.exception.request_attempts[0]["content_bytes"])

    def test_real_transport_drains_queued_eof_before_expired_idle_deadline(self):
        budget = self.budget()
        self.client.loopback_only = False
        reader_closed = threading.Event()

        class CompletedResponse:
            status_code = 200

            def iter_content(self, chunk_size=1):
                yield content_packet("final delta") + b"data: [DONE]\n\n"

            def raise_for_status(self):
                return None

            def close(self):
                reader_closed.set()

        response = CompletedResponse()
        with patch("showcase.adapters.time.time", self.clock), bind_budget(budget), patch(
            "showcase.request_transport.requests.post", return_value=response
        ):
            stream = self.adapter.stream_complete(
                [{"role": "user", "content": "synthetic"}], metadata={"role": "explore"}
            )
            first = next(stream)
            self.assertEqual({"type": "text_delta", "text": "final delta"}, first)
            self.assertTrue(reader_closed.wait(1))
            self.clock.advance(31)
            remaining = list(stream)

        self.assertEqual("final delta", remaining[-1]["text"])
        self.assertEqual("success", remaining[-1]["attempts"][-1]["status"])

    def test_real_transport_still_fails_when_effective_idle_expires(self):
        budget = self.budget()
        self.client.loopback_only = False
        unblock_reader = threading.Event()
        reader_closed = threading.Event()
        self.addCleanup(unblock_reader.set)

        class StalledResponse:
            status_code = 200

            def iter_content(self, chunk_size=1):
                yield content_packet("partial")
                unblock_reader.wait()

            def raise_for_status(self):
                return None

            def close(self):
                reader_closed.set()
                unblock_reader.set()

        response = StalledResponse()
        with patch("showcase.adapters.time.time", self.clock), bind_budget(budget), patch(
            "showcase.request_transport.requests.post", return_value=response
        ):
            stream = self.adapter.stream_complete(
                [{"role": "user", "content": "synthetic"}], metadata={"role": "explore"}
            )
            first = next(stream)
            self.assertEqual("partial", first["text"])
            self.clock.advance(31)
            with self.assertRaises(AdapterError) as caught:
                next(stream)
            unblock_reader.set()
            self.assertTrue(reader_closed.wait(1))

        self.assertEqual("timeout", caught.exception.category)

    def test_connect_timeout_and_retry_after_429_have_initialized_usage(self):
        for failure_kind in ("connect", "429"):
            with self.subTest(failure_kind=failure_kind):
                self.clock = VirtualClock()
                ledger = RunBudgetLedger()
                self.addCleanup(ledger.close)
                budget = ledger.ensure(
                    f"s01-{failure_kind}",
                    RunBudgetLimits(max_model_calls=2, max_http_attempts=4,
                                    max_tool_calls=0, max_tokens=10_000,
                                    max_runtime_seconds=100),
                    stream_timeout_policy=STREAM_POLICY,
                )
                attempts = []

                def transport(_url, **kwargs):
                    attempts.append(True)
                    if len(attempts) == 1 and failure_kind == "connect":
                        raise requests.ConnectTimeout("synthetic pre-send timeout")
                    if len(attempts) == 1:
                        response = requests.Response()
                        response.status_code = 429
                        response.headers["Retry-After"] = "0"
                        raise requests.HTTPError("synthetic rate limit", response=response)
                    yield "headers", self.response
                    yield "bytes", content_packet("recovered")
                    yield "bytes", b"data: [DONE]\n\n"
                    yield "complete", None

                with patch("showcase.adapters.time.time", self.clock), patch(
                    "showcase.adapters.time.sleep", self.clock.advance
                ), bind_budget(budget), patch(
                    "showcase.request_transport.response_events", side_effect=transport
                ):
                    result = list(self.adapter.stream_complete(
                        [{"role": "user", "content": "synthetic"}],
                        metadata={"role": "explore"},
                    ))[-1]

                self.assertEqual(2, len(attempts))
                self.assertEqual("success", result["attempts"][-1]["status"])
                self.assertEqual("recovered", result["text"])

    def test_frozen_policy_surfaces_only_soft_warning_when_stream_activity_is_off(self):
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure(
            "s01-audit-run",
            RunBudgetLimits(max_model_calls=3, max_http_attempts=3,
                            max_tool_calls=0, max_runtime_seconds=100),
            stream_timeout_policy=STREAM_POLICY,
        )

        class Port:
            def complete(self, request):
                return {"assessment": "NEED_PLAN"}

        with SolverHarness(
            config={"max_model_calls": 3, "features": {
                "stream_activity": False, "stream_recovery": True,
            }},
        ) as harness:
            harness.solve("synthetic question", {"run_id": "s01-audit-run"})
            run = harness.get_run("s01-audit-run")

            def warn(request):
                request["activity_observer"]({
                    "kind": "soft_timeout_warning",
                    "elapsed_seconds": 1200,
                    "policy_version": STREAM_POLICY["policy_version"],
                    "text": "must not persist",
                })
                return {"assessment": "NEED_PLAN"}

            with bind_budget(budget):
                harness.dispatch(run, warn, {
                    "run_id": "s01-audit-run",
                    "role": "reasoner",
                    "call_id": "s01-warning-call",
                    "problem": "synthetic question",
                })
            result = harness.get_run("s01-audit-run")

        warnings = [
            event for event in result["events"]
            if event.get("activity_kind") == "soft_timeout_warning"
        ]
        self.assertEqual(1, len(warnings))
        self.assertEqual({
            "elapsed_seconds": 1200,
            "policy_version": STREAM_POLICY["policy_version"],
        }, warnings[0]["stream_timeout_warning"])
        self.assertNotIn("text", warnings[0])
        self.assertNotIn("stream_metrics", next(iter(result["state"]["calls"].values())))

    def test_run_deadline_wins_and_post_completion_processing_uses_run_deadline(self):
        run_limited = self.budget(seconds=20)
        def expires_at_run_deadline(_url, **kwargs):
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1)
            yield "bytes", content_packet("partial")
            self._advance_and_tick(self.clock, kwargs, 20)

        with self.assertRaises(AdapterError) as caught:
            self.run_stream(run_limited, expires_at_run_deadline)
        self.assertEqual("timeout", caught.exception.category)
        self.assertEqual(1, run_limited.snapshot()["unknown_attempts"])

        self.clock = VirtualClock()
        post_complete = self.budget()

        def slow_after_complete(_url, **kwargs):
            yield "headers", self.response
            self._advance_and_tick(self.clock, kwargs, 1000)
            yield "bytes", content_packet("done")
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None
            self._advance_and_tick(self.clock, kwargs, 181)

        result = self.run_stream(post_complete, slow_after_complete)[-1]
        self.assertEqual("success", result["attempts"][0]["status"])
        self.assertEqual("done", result["text"])

    def test_retry_budget_allows_more_than_three_confirmed_not_sent_attempts(self):
        budget = self.budget(seconds=100, attempts=6)
        attempts = []
        started = self.clock()

        def transport(_url, **kwargs):
            attempts.append(True)
            if len(attempts) <= 4:
                raise DeadlineNotSubmitted("confirmed not sent")
            yield "headers", self.response
            yield "bytes", content_packet("recovered")
            yield "bytes", b"data: [DONE]\n\n"
            yield "complete", None

        with patch("showcase.adapters.time.time", self.clock), patch(
            "showcase.adapters.time.sleep", self.clock.advance
        ), bind_budget(budget), patch(
            "showcase.request_transport.response_events", side_effect=transport
        ):
            result = list(self.adapter.stream_complete(
                [{"role": "user", "content": "synthetic"}], metadata={"role": "explore"}
            ))[-1]

        self.assertEqual(5, len(attempts))
        self.assertEqual("success", result["attempts"][-1]["status"])
        self.assertEqual(15, self.clock() - started)

    def test_same_idempotency_key_restores_job_policy_across_server_config_change(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "workspace.sqlite"
            run_service = RunService(database_path=database)
            first = WorkspaceService(
                database,
                worker_enabled=False,
                connection=run_service._store._connection,
                stream_timeout_policy_version=STREAM_POLICY["policy_version"],
            )
            session_id = first.create_session("user-1")
            key = str(uuid.uuid4())
            limits = RunBudgetLimits(max_runtime_seconds=1800)
            job, existing = first.create_job(
                user_id="user-1",
                session_id=session_id,
                problem="synthetic problem",
                idempotency_key=key,
                budget_limits=limits,
            )
            first.close()

            second = WorkspaceService(
                database, worker_enabled=False, connection=run_service._store._connection
            )
            try:
                recovered, replayed = second.create_job(
                    user_id="user-1",
                    session_id=session_id,
                    problem="synthetic problem",
                    idempotency_key=key,
                    budget_limits=limits,
                )
                self.assertFalse(existing)
                self.assertTrue(replayed)
                self.assertEqual(job["job_id"], recovered["job_id"])
                public_job = second.get_job(recovered["job_id"], "user-1")
                self.assertEqual(STREAM_POLICY, public_job["result"]["stream_timeout_policy"])
                self.assertEqual(STREAM_POLICY, second.budget_ledger.stream_timeout_policy(recovered["job_id"]))
                self.assertEqual(0, second.budget_ledger.snapshot(recovered["job_id"])["logical_calls"])
            finally:
                second.close()
                run_service.close()

    def test_stream_timeout_policy_is_disabled_for_new_jobs_by_default(self):
        run_service = RunService()
        service = WorkspaceService(
            connection=run_service._store._connection,
            worker_enabled=False,
        )
        try:
            session_id = service.create_session("user-1")
            job, existing = service.create_job(
                user_id="user-1",
                session_id=session_id,
                problem="synthetic problem",
                idempotency_key=str(uuid.uuid4()),
                budget_limits=RunBudgetLimits(max_runtime_seconds=1800),
            )
            projected = service.get_job(job["job_id"], "user-1")
            self.assertFalse(existing)
            self.assertNotIn("stream_timeout_policy", projected["result"])
            self.assertIsNone(service.budget_ledger.stream_timeout_policy(job["job_id"]))
            self.assertNotIn("stream_timeout_policy", service.budget_ledger.snapshot(job["job_id"]))
        finally:
            service.close()
            run_service.close()


if __name__ == "__main__":
    unittest.main()
