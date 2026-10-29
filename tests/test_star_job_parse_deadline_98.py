"""Public Job stays terminal while a metered JSON parser finishes late."""

import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_star_product_tools import FEATURES, NEED_PLAN, PLAN, STEP


def arm_parser_deadline(policy):
    # Start the registered window after fixture setup, before submitting any
    # Job. Never move an active Run's deadline to make a late parser pass.
    started = time.time()
    policy.round_deadline_at = started + 10
    policy.phase_deadline_at = started + 2.5


class JobParseDeadlineTest(StarJobFixture, unittest.TestCase):
    def test_slow_fixture_setup_does_not_consume_parser_deadline(self):
        original_open = self.open_star

        def delayed_open(*args, **kwargs):
            original_open(*args, **kwargs)
            time.sleep(2.75)

        with patch.object(self, "open_star", side_effect=delayed_open):
            self.test_blocked_late_tool_reply_only_settles_original_attempt()

    def test_blocked_late_tool_reply_only_settles_original_attempt(self):
        policy = ExperimentRunPolicy(time.time() + 10)
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        self.open_star([NEED_PLAN, PLAN, STEP], SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_REGISTRY=registry, SHOWCASE_STAR_FEATURES=FEATURES)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def loads(value, *args, **kwargs):
            if isinstance(value, (bytes, bytearray)) and b"polynomial_check" in value:
                entered.set()
                if not release.wait(10):
                    raise AssertionError("parser not released")
            return json.loads(value, *args, **kwargs)

        with patch("llm_client.json", SimpleNamespace(loads=loads, dumps=json.dumps)):
            arm_parser_deadline(policy)
            job_id = self.create_job()
            self.assertTrue(entered.wait(5))
            before = self.terminal(job_id)
            self.assertFalse(release.is_set())
            self.assertEqual("failed", before["status"])
            self.assertEqual(1, before["result"]["budget"]["unresolved_attempts"])
            self.assertGreater(before["result"]["budget"]["reserved_tokens"], 0)
            self.assertEqual(0, before["result"]["budget"]["tool_calls"])
            self.assertEqual([], executed)
            attempt_id = before["result"]["request_attempts"][-1]["attempt_id"]
            self.assertEqual(3, self.post.call_count)
            release.set()
            after = self.wait_for(lambda: (job if (job := self.job(job_id))["result"]
                ["budget"]["unresolved_attempts"] == 0 else None))
        self.assertEqual("failed", after["status"])
        self.assertEqual(before["result"]["solver"], after["result"]["solver"])
        self.assertEqual(before["result"].get("final_response"), after["result"].get("final_response"))
        self.assertEqual(attempt_id, after["result"]["request_attempts"][-1]["attempt_id"])
        self.assertEqual("success", after["result"]["request_attempts"][-1]["status"])
        self.assertEqual(10, after["result"]["request_attempts"][-1]["usage"]["total_tokens"])
        self.assertEqual(0, after["result"]["budget"]["tool_calls"])
        self.assertEqual([], executed)
        self.assertEqual(3, self.post.call_count)


    def test_blocked_stream_event_finishes_job_before_late_parser_release(self):
        import os

        from llm_client import InternChatClient
        from showcase.adapters import InternStreamAdapter

        policy = ExperimentRunPolicy(time.time() + 10)
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=4, retry=1), max_tokens=256)
        self.open_star([NEED_PLAN, PLAN, STEP], SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_ADAPTER=adapter, SHOWCASE_STAR_REGISTRY=registry,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "strict_completion": True})
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def loads(value, *args, **kwargs):
            if isinstance(value, str) and '"delta"' in value and self.post.call_count >= 3:
                entered.set()
                if not release.wait(10):
                    raise AssertionError("stream parser not released")
            return json.loads(value, *args, **kwargs)

        with patch("showcase.adapters.json", SimpleNamespace(loads=loads, dumps=json.dumps)):
            arm_parser_deadline(policy)
            job_id = self.create_job()
            self.assertTrue(entered.wait(5))
            before = self.terminal(job_id)
            self.assertFalse(release.is_set())
            self.assertEqual("failed", before["status"])
            self.assertEqual(1, before["result"]["budget"]["unresolved_attempts"])
            self.assertGreater(before["result"]["budget"]["reserved_tokens"], 0)
            self.assertEqual(0, before["result"]["budget"]["tool_calls"])
            self.assertEqual([], executed)
            self.assertEqual(3, self.post.call_count)
            attempt_id = before["result"]["request_attempts"][-1]["attempt_id"]
            release.set()
            after = self.wait_for(lambda: (job if (job := self.job(job_id))["result"]
                ["budget"]["unresolved_attempts"] == 0 else None))
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["result"]["solver"], after["result"]["solver"])
        self.assertEqual(before["result"].get("final_response"), after["result"].get("final_response"))
        self.assertEqual(attempt_id, after["result"]["request_attempts"][-1]["attempt_id"])
        self.assertEqual("success", after["result"]["request_attempts"][-1]["status"])
        self.assertEqual(10, after["result"]["request_attempts"][-1]["usage"]["total_tokens"])
        self.assertEqual(0, after["result"]["budget"]["tool_calls"])
        self.assertEqual([], executed)
        self.assertEqual(3, self.post.call_count)
    def test_late_stream_assembly_does_not_publish_after_terminal_job(self):
        import os

        from llm_client import InternChatClient
        from showcase.adapters import InternStreamAdapter
        from showcase.request_attempts import record_attempts

        policy = ExperimentRunPolicy(time.time() + 10)
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=4, retry=1), max_tokens=256)
        self.open_star([NEED_PLAN, PLAN, STEP], SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_ADAPTER=adapter, SHOWCASE_STAR_REGISTRY=registry,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "strict_completion": True})
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def slow_record(events, metadata=None):
            if (metadata or {}).get("role") == "reasoner" and not entered.is_set():
                entered.set()
                if not release.wait(10):
                    raise AssertionError("stream assembly not released")
                records = record_attempts(events, metadata)
                returned.set()
                return records
            return record_attempts(events, metadata)

        with patch("showcase.adapters.record_attempts", side_effect=slow_record):
            arm_parser_deadline(policy)
            job_id = self.create_job()
            self.assertTrue(entered.wait(5))
            before = self.terminal(job_id)
            self.assertFalse(release.is_set())
            self.assertEqual("failed", before["status"])
            self.assertEqual(0, before["result"]["budget"]["unresolved_attempts"])
            self.assertEqual(0, before["result"]["budget"]["tool_calls"])
            before_events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
            release.set()
            self.assertTrue(returned.wait(3))
            after = self.job(job_id)
            after_events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["result"]["solver"], after["result"]["solver"])
        self.assertEqual(before["result"]["request_attempts"], after["result"]["request_attempts"])
        self.assertEqual(before_events, after_events)
        self.assertEqual([], executed)
        self.assertEqual(3, self.post.call_count)
    def test_blocked_tool_normalization_does_not_continue_the_job(self):
        from showcase.adapters import parse_tool_requests

        policy = ExperimentRunPolicy(time.time() + 10)
        executed = []
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: executed.append(args) or 2)
        self.open_star([NEED_PLAN, PLAN, STEP], SHOWCASE_STAR_EXPERIMENT_POLICY=policy,
                       SHOWCASE_STAR_REGISTRY=registry, SHOWCASE_STAR_FEATURES=FEATURES)
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def parse(text, *args, **kwargs):
            if isinstance(text, str) and "polynomial_check" in text:
                entered.set()
                if not release.wait(10):
                    raise AssertionError("tool normalization not released")
                returned.set()
            return parse_tool_requests(text, *args, **kwargs)

        with patch("showcase.adapters.parse_tool_requests", side_effect=parse):
            arm_parser_deadline(policy)
            job_id = self.create_job()
            self.assertTrue(entered.wait(5))
            before = self.terminal(job_id)
            self.assertFalse(release.is_set())
            self.assertEqual("failed", before["status"])
            self.assertEqual(0, before["result"]["budget"]["unresolved_attempts"])
            self.assertEqual(0, before["result"]["budget"]["tool_calls"])
            self.assertEqual([], executed)
            self.assertEqual(3, self.post.call_count)
            release.set()
            self.assertTrue(returned.wait(3))
            after = self.job(job_id)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["result"]["solver"], after["result"]["solver"])
        self.assertEqual(before["result"].get("final_response"), after["result"].get("final_response"))
        self.assertEqual(0, after["result"]["budget"]["tool_calls"])
        self.assertEqual([], executed)
        self.assertEqual(3, self.post.call_count)
if __name__ == "__main__":
    unittest.main()
