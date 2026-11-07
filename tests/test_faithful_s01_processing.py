"""Public Job evidence for known local stream processing failures."""

from __future__ import annotations

import json
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN

POLICY_VERSION = "faithful-stream-v1"


class FaithfulS01ProcessingAcceptance(StarJobFixture, unittest.TestCase):
    """Keep completed remote streams distinct from incomplete remote outcomes."""

    def open_stream(self, replies, *, freeze_policy, **config):
        adapter = config.pop(
            "SHOWCASE_STAR_ADAPTER",
            InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
        )
        features = {"stream_activity": True, "strict_completion": True}
        features.update(config.pop("SHOWCASE_STAR_FEATURES", {}))
        self.open_star(
            replies,
            SHOWCASE_STAR_ADAPTER=adapter,
            SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION=(POLICY_VERSION if freeze_policy else None),
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_runtime_seconds=120),
            SHOWCASE_STAR_FEATURES=features,
            **config,
        )

    def run_eof_local_assembly_timeout(self, *, freeze_policy):
        from showcase.request_attempts import record_attempts

        class ReasonerStreamAdapter(InternStreamAdapter):
            def stream_complete(self, messages, *, metadata=None):
                if (metadata or {}).get("role") != "reasoner":
                    response = self.complete(messages, metadata=metadata)
                    yield {
                        "type": "result",
                        "text": response.text,
                        "usage": response.usage,
                        "finish_reason": response.finish_reason,
                        "model": response.model_id,
                        "attempts": response.request_attempts,
                    }
                    return
                yield from super().stream_complete(messages, metadata=metadata)

        deadline = time.time() + 4.5
        run_policy = ExperimentRunPolicy(time.time() + 12, phase_deadline_at=deadline)
        registry = ToolRegistry()
        executed = []
        registry.register("polynomial_check", lambda arguments: executed.append(arguments) or 2)
        self.open_stream(
            [NEED_PLAN, PLAN, STEP],
            freeze_policy=freeze_policy,
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_ADAPTER=ReasonerStreamAdapter(
                InternChatClient(retry=1), max_tokens=256
            ),
            SHOWCASE_STAR_EXPERIMENT_POLICY=run_policy,
            SHOWCASE_STAR_REGISTRY=registry,
        )
        entered, release, returned = threading.Event(), threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original_record = record_attempts

        def slow_record(events, metadata=None):
            if (metadata or {}).get("role") == "reasoner" and not entered.is_set():
                entered.set()
                if not release.wait(10):
                    raise AssertionError("completed stream assembly was not released")
                try:
                    return original_record(events, metadata)
                finally:
                    returned.set()
            return original_record(events, metadata)

        with patch("showcase.adapters.record_attempts", side_effect=slow_record):
            job_id = self.create_job()
            self.assertTrue(entered.wait(5), self.job(job_id))
            terminal = self.terminal(job_id, timeout=8)
            self.assertEqual("failed", terminal["status"])
            solver_before = terminal["result"]["solver"]
            events_before = self.client.get(
                f"/api/agent/jobs/{job_id}/events"
            ).get_data(as_text=True)
            release.set()
            self.assertTrue(returned.wait(3))
            settled = self.job(job_id)
            events_after = self.client.get(
                f"/api/agent/jobs/{job_id}/events"
            ).get_data(as_text=True)

        self.assertEqual("failed", settled["status"])
        self.assertEqual(solver_before, settled["result"]["solver"])
        self.assertEqual(events_before, events_after)
        self.assertEqual([], executed)
        self.assertEqual(3, len(self.outbound))
        return settled, job_id

    def test_frozen_complete_stream_local_assembly_failure_is_not_unknown(self):
        settled, job_id = self.run_eof_local_assembly_timeout(freeze_policy=True)
        recovery = settled["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("needs_review", recovery["status"])
        self.assertEqual(1, len(recovery["processing_failures"]))
        failure = recovery["processing_failures"][0]
        self.assertEqual("local_processing_timeout", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(10, failure["usage"]["total_tokens"])
        reasoner_attempt = next(
            attempt for attempt in settled["result"]["request_attempts"]
            if attempt["role"] == "reasoner"
        )
        self.assertEqual(POLICY_VERSION,
                         reasoner_attempt["call_policy_evidence"]["policy_version"])
        self.assertEqual("success", reasoner_attempt["status"])
        self.assertEqual("known", reasoner_attempt["metering_status"])
        self.assertEqual(0, settled["result"]["budget"]["unresolved_attempts"])
        rejected = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
        )
        self.assertEqual(409, rejected.status_code)
        self.assertEqual("star_processing_failure_requires_new_job",
                         rejected.get_json()["error"])
        self.assertEqual(3, len(self.outbound))

    def test_legacy_complete_stream_timeout_keeps_unknown_dto_shape(self):
        settled, _ = self.run_eof_local_assembly_timeout(freeze_policy=False)
        recovery = settled["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["unknown_calls"]))
        self.assertEqual({"status", "unknown_calls", "unknown_tools", "retries",
                          "protocol_failures"}, set(recovery))

    def test_frozen_incomplete_stream_parser_timeout_remains_unknown(self):
        class ReasonerOnlyStreamAdapter(InternStreamAdapter):
            def stream_complete(self, messages, *, metadata=None):
                if (metadata or {}).get("role") != "reasoner":
                    response = self.complete(messages, metadata=metadata)
                    yield {"type": "result", "text": response.text,
                           "usage": response.usage, "finish_reason": response.finish_reason,
                           "model": response.model_id, "attempts": response.request_attempts}
                    return
                yield from super().stream_complete(messages, metadata=metadata)

        deadline = time.time() + 4.5
        run_policy = ExperimentRunPolicy(time.time() + 12, phase_deadline_at=deadline)
        adapter = ReasonerOnlyStreamAdapter(InternChatClient(timeout=4, retry=1), max_tokens=256)
        self.open_stream(
            [NEED_PLAN, PLAN, STEP],
            freeze_policy=True,
            SHOWCASE_STAR_ADAPTER=adapter,
            SHOWCASE_STAR_EXPERIMENT_POLICY=run_policy,
            SHOWCASE_STAR_FEATURES={**FEATURES, "stream_activity": True,
                                    "strict_completion": True},
        )
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def loads(value, *args, **kwargs):
            if isinstance(value, str) and '"delta"' in value and self.post.call_count >= 3:
                entered.set()
                if not release.wait(10):
                    raise AssertionError("stream parser was not released")
            return json.loads(value, *args, **kwargs)

        with patch("showcase.adapters.json", SimpleNamespace(loads=loads, dumps=json.dumps)):
            job_id = self.create_job()
            self.assertTrue(entered.wait(5), self.job(job_id))
            failed = self.terminal(job_id)
            self.assertEqual("failed", failed["status"])
            release.set()
            self.wait_for(lambda: self.job(job_id)["result"]["budget"]["unresolved_attempts"] == 0)

        settled = self.job(job_id)
        recovery = settled["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["unknown_calls"]))
        self.assertNotIn("processing_failures", recovery)
        reasoner_attempt = next(
            attempt for attempt in settled["result"]["request_attempts"]
            if attempt["role"] == "reasoner"
        )
        self.assertEqual(POLICY_VERSION,
                         reasoner_attempt["call_policy_evidence"]["policy_version"])
        self.assertEqual(3, len(self.outbound))


if __name__ == "__main__":
    unittest.main()
