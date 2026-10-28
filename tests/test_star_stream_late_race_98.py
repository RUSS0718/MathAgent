"""Issue #98: stream timeout and late-response settlement must not race."""

import json
import os
import sqlite3
import threading
import time
import unittest
from unittest.mock import patch

import requests

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudgetLedger
from showcase.star_experiment_policy import ExperimentRunPolicy
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


def completed_sse():
    packet = {"choices": [{"delta": {"content": json.dumps(SOLVED)},
              "finish_reason": "stop"}], "usage": {"prompt_tokens": 7,
              "completion_tokens": 3, "total_tokens": 10}}
    return ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()


class StreamLateRaceTest(StarJobFixture, unittest.TestCase):
    def open_stream(self, strict=True, **config):
        with patch.dict(os.environ, {"INTERN_API_KEY": "offline-placeholder"}):
            adapter = InternStreamAdapter(InternChatClient(timeout=2, retry=3), max_tokens=256)
        self.open_star([], SHOWCASE_STAR_ADAPTER=adapter,
                       SHOWCASE_STAR_FEATURES={"strict_completion": strict}, **config)

    def test_timeout_does_not_overwrite_inflight_late_success(self):
        self.open_stream()
        late_entered, release, callback_finished = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        sends = []
        original = RunBudgetLedger.settle

        class Reply:
            status_code = 200

        def pause_success(ledger, run_id, attempt_id, event):
            if event.get("status") == "success":
                late_entered.set()
                if not release.wait(3):
                    raise AssertionError("late settlement was not released")
            return original(ledger, run_id, attempt_id, event)

        def transport(_url, *, on_late_response, **_kwargs):
            sends.append(True)

            def late():
                try:
                    on_late_response(Reply(), completed_sse(), .01, .2, True)
                finally:
                    callback_finished.set()

            threading.Thread(target=late, daemon=True).start()
            if not late_entered.wait(2):
                raise AssertionError("late response did not reach settlement")
            raise requests.ReadTimeout("offline deadline")
            yield  # This boundary is an iterator even on timeout.

        with (patch("showcase.request_transport.response_events", side_effect=transport),
              patch.object(RunBudgetLedger, "settle", pause_success)):
            job_id = self.create_job()
            job = self.terminal(job_id)
            self.assertEqual("failed", job["status"])
            self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
            self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
            original_id = job["result"]["request_attempts"][0]["attempt_id"]
            release.set()
            self.assertTrue(callback_finished.wait(2))
            settled = self.job(job_id)
        self.assertEqual("failed", settled["status"])
        self.assertEqual(job["result"]["solver"], settled["result"]["solver"])
        self.assertEqual([True], sends)
        self.assertEqual(original_id, settled["result"]["request_attempts"][0]["attempt_id"])
        self.assertEqual("success", settled["result"]["request_attempts"][0]["status"])
        self.assertEqual(10, settled["result"]["budget"]["provider_known"]["total_tokens"])
        self.assertEqual(0, settled["result"]["budget"]["unresolved_attempts"])
        self.assertEqual(0, settled["result"]["budget"]["reserved_tokens"])

    def test_partial_late_usage_before_timeout_keeps_unknown_reservation(self):
        self.open_stream()
        sends = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            sends.append(True)
            partial = completed_sse().replace(b"data: [DONE]\n\n", b"")
            on_late_response(Reply(), partial, .01, .2, False)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job = self.terminal(self.create_job())
        self.assertEqual([True], sends)
        self.assertEqual("failed", job["status"])
        self.assertEqual("needs_review", job["result"]["solver"]["recovery"]["status"])
        attempt = job["result"]["request_attempts"][0]
        budget = job["result"]["budget"]
        self.assertEqual("unknown", attempt["status"])
        self.assertEqual(10, budget["provider_known"]["total_tokens"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
    def test_invalid_incomplete_late_stream_remains_unknown_after_timeout(self):
        self.open_stream()

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            partial = b"data: {broken\n\n" + completed_sse().replace(b"data: [DONE]\n\n", b"")
            on_late_response(Reply(), partial, .01, .2, False)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job = self.terminal(self.create_job())
        attempt = job["result"]["request_attempts"][0]
        budget = job["result"]["budget"]
        self.assertEqual("unknown", attempt["status"])
        self.assertEqual("invalid_response", attempt["error_category"])
        self.assertEqual(10, budget["provider_known"]["total_tokens"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
    def test_late_invalid_sse_is_error_but_preserves_later_known_usage(self):
        self.open_stream()
        callbacks = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            job = self.terminal(job_id)
            callbacks[0](Reply(), b"data: {broken\n\n" + completed_sse(), .01, .2, True)
            settled = self.job(job_id)
        attempt = settled["result"]["request_attempts"][0]
        self.assertEqual(job["status"], settled["status"])
        self.assertEqual("error", attempt["status"])
        self.assertEqual("invalid_response", attempt["error_category"])
        self.assertEqual(10, settled["result"]["budget"]["provider_known"]["total_tokens"])
        self.assertEqual(1, settled["result"]["budget"]["unresolved_attempts"])
    def test_non_strict_late_stream_without_done_matches_connectivity_failure(self):
        self.open_stream(strict=False)
        callbacks = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            job = self.terminal(job_id)
            partial = completed_sse().replace(b"data: [DONE]\n\n", b"")
            callbacks[0](Reply(), partial, .01, .2, True)
            settled = self.job(job_id)
        attempt = settled["result"]["request_attempts"][0]
        budget = settled["result"]["budget"]
        self.assertEqual(job["status"], settled["status"])
        self.assertEqual("error", attempt["status"])
        self.assertEqual("connectivity", attempt["error_category"])
        self.assertEqual(10, budget["provider_known"]["total_tokens"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
    def test_job_read_keeps_budget_and_attempts_on_same_ledger_version(self):
        self.open_stream()
        callbacks = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            self.terminal(job_id)
            service = self.app.extensions["showcase_workspace_service"]
            original_events = service.store.events
            invoked = []

            def events_and_late(*args, **kwargs):
                events = original_events(*args, **kwargs)
                if not invoked:
                    invoked.append(True)
                    callbacks[0](Reply(), completed_sse(), .01, .2, True)
                return events

            with patch.object(service.store, "events", side_effect=events_and_late):
                observed = self.job(job_id)["result"]
            final = self.job(job_id)["result"]
        self.assertEqual([True], invoked)
        unresolved = observed["budget"]["unresolved_attempts"]
        attempt = observed["request_attempts"][0]
        self.assertIn((unresolved, attempt["status"]), [(1, "error"), (0, "success")])
        self.assertEqual(0, final["budget"]["unresolved_attempts"])
        self.assertEqual("success", final["request_attempts"][0]["status"])
    def test_job_read_does_not_mix_later_new_attempt_events_with_old_budget(self):
        self.open_stream()
        self.replies.extend([SOLVED, POLISH, ACCEPT])
        first_post, release, second_event = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        service = self.app.extensions["showcase_workspace_service"]
        original_post = self.post.side_effect
        original_view = service.budget_ledger.view
        job_ids = []

        def post(*args, **kwargs):
            if not first_post.is_set():
                first_post.set()
                if not release.wait(5):
                    raise AssertionError("first request not released")
            elif not second_event.is_set():
                # The fake transport publishes the already-reserved second attempt.
                _, attempts = original_view(job_ids[0])
                service.store.append_event(job_ids[0], {"type": "request_attempt", "attempt": attempts[-1]})
                second_event.set()
            return original_post(*args, **kwargs)

        self.post.side_effect = post
        job_id = self.create_job()
        job_ids.append(job_id)
        self.assertTrue(first_post.wait(2))

        def view_then_advance(run_id):
            snapshot = original_view(run_id)
            release.set()
            if not second_event.wait(5):
                raise AssertionError("second attempt event not published")
            return snapshot

        with patch.object(service.budget_ledger, "view", side_effect=view_then_advance):
            observed = self.job(job_id)["result"]
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        self.assertEqual(1, observed["budget"]["http_attempts"])
        self.assertEqual(1, len(observed["request_attempts"]))
        self.assertTrue(second_event.is_set())
    def test_run_read_does_not_mix_later_new_attempt_events_with_old_budget(self):
        self.open_stream()
        self.replies.extend([SOLVED, POLISH, ACCEPT])
        first_post, release, second_event = (threading.Event() for _ in range(3))
        self.addCleanup(release.set)
        service = self.app.extensions["showcase_workspace_service"]
        original_post = self.post.side_effect
        run_service = self.app.extensions["showcase_run_service"]
        original_view = run_service._budget_ledger.view
        job_ids = []

        def post(*args, **kwargs):
            if not first_post.is_set():
                first_post.set()
                if not release.wait(5):
                    raise AssertionError("first request not released")
            elif not second_event.is_set():
                # The fake transport publishes the already-reserved second attempt.
                _, attempts = original_view(job_ids[0])
                service.store.append_event(job_ids[0], {"type": "request_attempt", "attempt": attempts[-1]})
                second_event.set()
            return original_post(*args, **kwargs)

        self.post.side_effect = post
        job_id = self.create_job()
        job_ids.append(job_id)
        self.assertTrue(first_post.wait(2))

        def view_then_advance(run_id):
            snapshot = original_view(run_id)
            release.set()
            if not second_event.wait(5):
                raise AssertionError("second attempt event not published")
            return snapshot

        with patch.object(run_service._budget_ledger, "view", side_effect=view_then_advance):
            response = self.client.get(f"/api/runs/{job_id}")
            self.assertEqual(200, response.status_code)
            observed = response.get_json()["result"]
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"])
        self.assertEqual(1, observed["budget"]["http_attempts"])
        self.assertEqual(1, len(observed["request_attempts"]))
        self.assertTrue(second_event.is_set())
    def test_run_read_keeps_budget_and_attempts_on_same_ledger_version(self):
        self.open_stream()
        callbacks = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            self.terminal(job_id)
            service = self.app.extensions["showcase_run_service"]
            original_events = service._store.get_events
            invoked = []

            def events_and_late(*args, **kwargs):
                events = original_events(*args, **kwargs)
                if not invoked:
                    invoked.append(True)
                    callbacks[0](Reply(), completed_sse(), .01, .2, True)
                return events

            with patch.object(service._store, "get_events", side_effect=events_and_late):
                response = self.client.get(f"/api/runs/{job_id}")
                self.assertEqual(200, response.status_code)
                observed = response.get_json()["result"]
            final = self.client.get(f"/api/runs/{job_id}").get_json()["result"]
        self.assertEqual([True], invoked)
        unresolved = observed["budget"]["unresolved_attempts"]
        attempt = observed["request_attempts"][0]
        self.assertIn((unresolved, attempt["status"]), [(1, "error"), (0, "success")])
        self.assertEqual(0, final["budget"]["unresolved_attempts"])
        self.assertEqual("success", final["request_attempts"][0]["status"])
    def test_late_sqlite_lock_is_retried_without_another_provider_request(self):
        policy = ExperimentRunPolicy(time.time() + 8, phase_deadline_at=time.time() + 1.2)
        self.open_stream(SHOWCASE_STAR_EXPERIMENT_POLICY=policy)
        release_body, lock_released, first_failure = (threading.Event() for _ in range(3))
        self.addCleanup(release_body.set)
        self.addCleanup(lock_released.set)
        original_settle = RunBudgetLedger.settle
        tries = []

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def iter_content(self, chunk_size=1):
                if not release_body.wait(3):
                    raise AssertionError("body not released")
                yield completed_sse()

            def close(self):
                pass

        def locked_settle(ledger, run_id, attempt_id, event):
            if event.get("status") == "success":
                tries.append(True)
                if not lock_released.is_set():
                    first_failure.set()
                    raise sqlite3.OperationalError("database is locked")
            return original_settle(ledger, run_id, attempt_id, event)

        self.post.side_effect = lambda *_args, **_kwargs: Reply()
        with patch.object(RunBudgetLedger, "settle", locked_settle):
            job_id = self.create_job()
            job = self.terminal(job_id)
            self.assertEqual(1, job["result"]["budget"]["unresolved_attempts"])
            release_body.set()
            self.assertTrue(first_failure.wait(2))
            lock_released.set()
            settled = self.wait_for(lambda: (value if (value := self.job(job_id))
                ["result"]["budget"]["unresolved_attempts"] == 0 else None))
        self.assertGreaterEqual(len(tries), 2)
        self.assertEqual(1, self.post.call_count)
        self.assertEqual(job["status"], settled["status"])
        self.assertEqual("success", settled["result"]["request_attempts"][0]["status"])
    def test_concurrent_duplicate_late_reports_settle_original_attempt_once(self):
        self.open_stream()
        callbacks = []

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            before = self.terminal(job_id)
            barrier = threading.Barrier(5)
            failures = []

            def late():
                try:
                    barrier.wait(2)
                    callbacks[0](Reply(), completed_sse(), .01, .2, True)
                except Exception as exc:
                    failures.append(exc)

            workers = [threading.Thread(target=late, daemon=True) for _ in range(4)]
            for worker in workers:
                worker.start()
            barrier.wait(2)
            for worker in workers:
                worker.join(3)
                self.assertFalse(worker.is_alive())
            after = self.job(job_id)
        self.assertEqual([], failures)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(1, after["result"]["budget"]["http_attempts"])
        self.assertEqual(10, after["result"]["budget"]["provider_known"]["total_tokens"])
        self.assertEqual(0, after["result"]["budget"]["unresolved_attempts"])
        self.assertEqual(before["result"]["request_attempts"][0]["attempt_id"],
                         after["result"]["request_attempts"][0]["attempt_id"])
    def test_persistent_sqlite_lock_stops_retry_and_keeps_original_unknown(self):
        self.open_stream()
        callbacks = []
        sends = []
        tries = []
        original_settle = RunBudgetLedger.settle

        class Reply:
            status_code = 200

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            sends.append(True)
            raise requests.ReadTimeout("offline deadline")
            yield

        def locked_settle(ledger, run_id, attempt_id, event):
            if event.get("status") == "success":
                tries.append(True)
                raise sqlite3.OperationalError("database is locked")
            return original_settle(ledger, run_id, attempt_id, event)

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            before = self.terminal(job_id)
            with (patch.object(RunBudgetLedger, "settle", locked_settle),
                  self.assertLogs("showcase.run_budget_late", level="WARNING") as logs):
                worker = threading.Thread(target=callbacks[0], args=(
                    Reply(), completed_sse(), .01, .2, True), daemon=True)
                worker.start()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "retry must be bounded")
            after = self.job(job_id)
        self.assertEqual([True], sends)
        self.assertGreaterEqual(len(tries), 1)
        self.assertLessEqual(len(tries), 4)
        self.assertTrue(any("unresolved" in line for line in logs.output))
        self.assertEqual(before["result"]["request_attempts"], after["result"]["request_attempts"])
        self.assertEqual(1, after["result"]["budget"]["unresolved_attempts"])
        self.assertEqual(before["result"]["budget"]["reserved_tokens"],
                         after["result"]["budget"]["reserved_tokens"])
    def test_old_run_late_reply_cannot_change_new_run(self):
        self.open_stream()
        self.replies.extend([SOLVED, POLISH, ACCEPT])
        from showcase.request_transport import response_events as real_events

        callbacks = []
        sends = []

        class Reply:
            status_code = 200

        def transport(url, *, on_late_response, **kwargs):
            sends.append(True)
            if len(sends) == 1:
                callbacks.append(on_late_response)
                raise requests.ReadTimeout("old arm deadline")
            yield from real_events(url, on_late_response=on_late_response, **kwargs)

        with patch("showcase.request_transport.response_events", side_effect=transport):
            old_id = self.create_job()
            old_before = self.terminal(old_id)
            new_id = self.create_job()
            new_before = self.terminal(new_id)
            self.assertEqual("failed", old_before["status"])
            self.assertEqual("succeeded", new_before["status"])
            self.assertNotEqual(old_id, new_id)
            callbacks[0](Reply(), completed_sse(), .01, .2, True)
            old_after, new_after = self.job(old_id), self.job(new_id)
        self.assertEqual(old_before["status"], old_after["status"])
        self.assertEqual(old_before["result"]["solver"], old_after["result"]["solver"])
        self.assertEqual(old_before["result"]["request_attempts"][0]["attempt_id"],
                         old_after["result"]["request_attempts"][0]["attempt_id"])
        self.assertEqual("success", old_after["result"]["request_attempts"][0]["status"])
        self.assertEqual(new_before["status"], new_after["status"])
        self.assertEqual(new_before["result"], new_after["result"])
        self.assertEqual(4, len(sends))
        self.assertEqual(3, self.post.call_count)
    def test_late_503_with_valid_sse_is_not_success(self):
        self.open_stream()
        callbacks, sends = [], []

        class Reply:
            status_code = 503

        def transport(_url, *, on_late_response, **_kwargs):
            callbacks.append(on_late_response)
            sends.append(True)
            raise requests.ReadTimeout("offline deadline")
            yield

        with patch("showcase.request_transport.response_events", side_effect=transport):
            job_id = self.create_job()
            job = self.terminal(job_id)
            original_id = job["result"]["request_attempts"][0]["attempt_id"]
            callbacks[0](Reply(), completed_sse(), .01, .2, True)
            settled = self.job(job_id)
        attempt = settled["result"]["request_attempts"][0]
        budget = settled["result"]["budget"]
        self.assertEqual([True], sends)
        self.assertEqual("failed", settled["status"])
        self.assertEqual(job["result"]["solver"], settled["result"]["solver"])
        self.assertEqual(original_id, attempt["attempt_id"])
        self.assertEqual(503, attempt["http_status"])
        self.assertEqual("error", attempt["status"])
        self.assertEqual("http_status", attempt["error_category"])
        self.assertEqual(10, budget["provider_known"]["total_tokens"])
        self.assertEqual(1, budget["unresolved_attempts"])
        self.assertEqual(budget["local_input_estimate"] + 256, budget["reserved_tokens"])
        self.assertEqual(budget["reserved_tokens"], budget["charged_tokens"])


if __name__ == "__main__":
    unittest.main()
