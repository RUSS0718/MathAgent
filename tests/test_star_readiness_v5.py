"""Independent contract tests for the proposed #97 v5 registration."""

import copy
import hashlib
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.run_star_readiness_97 import _build_adapter
from showcase import star_readiness_registration as registration_module
from showcase.run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.run_control import RunStopped
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_coordinator import StarReadinessCoordinator, _claim_live_registration
from showcase.star_readiness_registration import (
    STOP_ON,
    adapt_draft,
    authorize_live_registration,
    digest,
    registration,
)
from showcase.star_readiness_v5 import (
    V5_AUTHORIZATION_SCOPE,
    V5_DRAFT_VERSION,
    V5_MODEL,
    V5_PREVIOUS_DRAFT_SHA256,
    V5_QUESTION_SPECS,
    V5_ROUND_LIMITS,
    V5_RUN_LIMITS,
)

SOURCE = {"revision": "a" * 40, "source_sha256": "b" * 64, "dirty_status": True}
TEST_V5_QUESTION_TEXTS = ("Compute 2 + 2.", "Compute 2 + 3.")
TEST_V5_QUESTION_SPECS = tuple(
    (question_id, source, question_type, hashlib.sha256(text.encode()).hexdigest())
    for (question_id, source, question_type, _hash), text in zip(
        V5_QUESTION_SPECS, TEST_V5_QUESTION_TEXTS
    )
)


def v5_draft():
    """Build a fresh v5 draft from its immutable sample and budget contract."""
    return {
        "budget_status": "proposed_unapproved",
        "dirty_status": True,
        "enforcement": "not_implemented",
        "evidence_types": ["scripted", "fault_injection", "live", "replay"],
        "execution_authorized": False,
        "model": copy.deepcopy(V5_MODEL),
        "original_batch": "unchanged_not_counted",
        "previous_draft_sha256": V5_PREVIOUS_DRAFT_SHA256,
        "question_encoding": "UTF-8 exact text with LF separators, no trailing newline",
        "questions": [
            {
                "id": question_id,
                "prompt_sha256": prompt_sha256,
                "source": source,
                "text": text,
                "type": question_type,
            }
            for (question_id, source, question_type, prompt_sha256), text in zip(
                TEST_V5_QUESTION_SPECS, TEST_V5_QUESTION_TEXTS
            )
        ],
        "round_limits": copy.deepcopy(V5_ROUND_LIMITS),
        "runner_qualification": "not_implemented",
        "schedule": [
            {
                "attempts": 1,
                "limits": copy.deepcopy(limits),
                "question": question_id,
                "transport": "nonstream",
            }
            for (question_id, *_), limits in zip(TEST_V5_QUESTION_SPECS, V5_RUN_LIMITS)
        ],
        "source_identity": {"revision": "c" * 40, "source_sha256": "d" * 64},
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(STOP_ON),
        "version": V5_DRAFT_VERSION,
    }


class StarReadinessV5Test(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("showcase.star_readiness_registration.V5_QUESTION_SPECS",
                                TEST_V5_QUESTION_SPECS))

    def test_v5_adapter_freezes_increased_wait_limits_without_changing_call_budgets(self):
        manifest = adapt_draft(v5_draft(), current_source=SOURCE)

        self.assertEqual(V5_DRAFT_VERSION, manifest["draft_version"])
        self.assertEqual(600, manifest["model"]["request_timeout_seconds"])
        self.assertEqual(4800, manifest["round_limits"]["wall_seconds"])
        self.assertEqual([900, 3600], [entry["limits"]["wall_seconds"]
                                      for entry in manifest["schedule"]])
        for key in ("charged_tokens", "http_attempts", "logical_calls", "problem_tool_calls"):
            self.assertEqual(registration_module.ROUND_LIMITS[key], manifest["round_limits"][key])
        for index, existing_limits in enumerate(registration_module.RUN_LIMITS):
            for key in ("charged_tokens", "http_attempts", "logical_calls", "problem_tool_calls"):
                with self.subTest(run=index, limit=key):
                    self.assertEqual(
                        existing_limits[key], manifest["schedule"][index]["limits"][key]
                    )
        self.assertFalse(manifest["execution_authorized"])
        self.assertEqual("draft_not_dispatchable", manifest["status"])

    def test_registration_rejects_timeout_and_wall_clock_drift(self):
        manifest = adapt_draft(v5_draft(), current_source=SOURCE)
        mutations = []

        changed_timeout = copy.deepcopy(manifest)
        changed_timeout["model"]["request_timeout_seconds"] = 601
        mutations.append(changed_timeout)

        changed_run_wall = copy.deepcopy(manifest)
        changed_run_wall["schedule"][1]["limits"]["wall_seconds"] = 3601
        mutations.append(changed_run_wall)

        changed_round_wall = copy.deepcopy(manifest)
        changed_round_wall["round_limits"]["wall_seconds"] = 4801
        mutations.append(changed_round_wall)

        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    registration(changed, expected_sha256=digest(changed), current_source=SOURCE)

    def test_v5_live_authorization_is_version_scoped_and_one_time(self):
        loopback = adapt_draft(v5_draft(), current_source=SOURCE)
        live = authorize_live_registration(
            loopback,
            expected_sha256=digest(loopback),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-28",
        )
        self.assertEqual(V5_AUTHORIZATION_SCOPE, live["authorization_scope"])
        self.assertEqual("authorized_live", live["status"])

        with tempfile.TemporaryDirectory() as directory:
            with patch("showcase.star_readiness_coordinator.ARTIFACTS", Path(directory)):
                _claim_live_registration(digest(live), V5_DRAFT_VERSION)
                with self.assertRaisesRegex(ValueError, "already_consumed"):
                    _claim_live_registration(digest(live), V5_DRAFT_VERSION)

    def test_coordinator_uses_the_manifest_round_wall_clock(self):
        manifest = adapt_draft(v5_draft(), current_source=SOURCE)
        clock = [1000.0]

        def verify_source():
            clock[0] += 120
            return SOURCE

        class Archive:
            def __init__(self, _path):
                self.result = None

            def put(self, _name, _value):
                pass

            def finish(self, result):
                self.result = result

        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(StarReadinessCoordinator, "_check_execution_profile"),
                patch("showcase.star_readiness_coordinator.current_source_identity",
                      side_effect=verify_source),
                patch("showcase.star_readiness_coordinator.ARTIFACTS", Path(directory)),
                patch("showcase.star_readiness_coordinator.ExperimentArchive", Archive),
                patch("showcase.star_readiness_coordinator.ExperimentRunPolicy",
                      return_value=SimpleNamespace()) as policy,
                patch("showcase.star_readiness_coordinator.ExperimentServer") as server_factory,
                patch("showcase.star_readiness_coordinator.validate_server_configuration",
                      return_value={}),
                patch("showcase.star_readiness_coordinator.admit_next_run",
                      return_value="round_wall_seconds_insufficient") as admit,
                patch("showcase.star_readiness_coordinator.time.monotonic",
                      side_effect=lambda: clock[0]),
                patch("showcase.star_readiness_coordinator.time.time",
                      side_effect=lambda: clock[0]),
            ):
                server_factory.return_value.preflight.return_value = {
                    "available": True,
                    "identity": {"run_id": "preflight-run"},
                    "budget": {"tool_calls": 1, "http_attempts": 0},
                }
                coordinator = StarReadinessCoordinator(
                    "unused",
                    adapters={"nonstream": SimpleNamespace()},
                    manifest=manifest,
                    manifest_sha256=digest(manifest),
                )
                result = coordinator.run()

        self.assertEqual("round_wall_seconds_insufficient", result["stop_reason"])
        self.assertEqual(4680, admit.call_args.kwargs["remaining_seconds"])
        policy.assert_called_once_with(5800.0)
        self.assertEqual(600, server_factory.call_args.kwargs["request_timeout_seconds"])

    def test_adapter_uses_registered_timeout_without_dispatching(self):
        environment = {
            "INTERN_API_KEY": "test-only-not-a-real-key",
            "INTERN_API_BASE": "https://chat.intern-ai.org.cn/api/v1/chat/completions",
            "INTERN_MODEL": "intern-s2",
        }
        with patch.dict("os.environ", environment):
            adapter = _build_adapter({
                "model": copy.deepcopy(V5_MODEL),
                "provider_endpoint": environment["INTERN_API_BASE"],
            })

        self.assertEqual(600, adapter._get_client().timeout)
        self.assertEqual(600, adapter.client_timeout)

    def test_server_accepts_registered_v5_timeout_and_rejects_later_drift(self):
        from tests.star_experiment_support import LoopbackProvider

        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        adapter = provider.adapters()["nonstream"]
        adapter._get_client().timeout = 600
        with tempfile.TemporaryDirectory() as directory:
            server = ExperimentServer(
                Path(directory), "nonstream", adapter, ExperimentRunPolicy(10**10), "scripted",
                request_timeout_seconds=600,
            )
            try:
                server.check_conditions()
                adapter._get_client().timeout = 601
                with self.assertRaisesRegex(ValueError, "experiment_conditions_mismatch"):
                    server.check_conditions()
            finally:
                server.close()
        self.assertEqual([], provider.requests)

    def test_v5_nonstream_http_wait_obeys_run_and_round_deadlines_without_resend(self):
        for limiting_deadline in ("run", "round"):
            with self.subTest(limiting_deadline=limiting_deadline):
                release = threading.Event()
                received = []

                class Handler(BaseHTTPRequestHandler):
                    def log_message(self, *_args):
                        pass

                    def do_POST(self):
                        received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                        release.wait(2)
                        body = json.dumps({
                            "model": "intern-s2", "choices": [{
                                "message": {"content": "late fixture"}, "finish_reason": "stop"}],
                            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
                        }).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)

                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
                threading.Thread(target=server.serve_forever, daemon=True).start()
                self.addCleanup(server.server_close)
                self.addCleanup(server.shutdown)
                self.addCleanup(release.set)
                with patch.dict("os.environ", {"INTERN_API_KEY": "fixture-only",
                                               "INTERN_MODEL": "intern-s2"}):
                    adapter = _build_adapter({"model": V5_MODEL,
                                              "provider_endpoint": "https://chat.intern-ai.org.cn/api/v1/chat/completions"})
                client = adapter._get_client()
                client.api_base = f"http://127.0.0.1:{server.server_port}"
                client.provider_endpoint_only, client.loopback_only = False, True
                ledger = RunBudgetLedger()
                self.addCleanup(ledger.close)
                policy = ExperimentRunPolicy(time.time() + (0.08 if limiting_deadline == "round" else 10))
                limits = {
                    "max_model_calls": 12,
                    "max_http_attempts": 16,
                    "max_tool_calls": 3,
                    "max_tokens": 65536,
                    "max_runtime_seconds": 3600,
                }
                if limiting_deadline == "run":
                    limits["max_runtime_seconds"] = 0.08
                policy.prepare(limits)
                budget = ledger.ensure("deadline-fixture", policy.budget(), deadline_at=policy.deadline_at)
                original_deadline = budget.snapshot()["deadline_at"]
                started = time.monotonic()
                with bind_budget(budget), self.assertRaisesRegex(RunStopped, "run_deadline_exhausted"):
                    adapter.complete([{"role": "user", "content": "fixture"}], metadata={"role": "explore"})
                self.assertLess(time.monotonic() - started, 1)
                self.assertEqual(600, ledger.attempts("deadline-fixture")[0]["requests_timeout_seconds"])
                self.assertEqual(1, budget.snapshot()["http_attempts"])
                self.assertEqual(1, budget.snapshot()["unknown_attempts"])
                self.assertGreater(budget.snapshot()["reserved_tokens"], 0)
                ledger.ensure("deadline-fixture", RunBudgetLimits(), deadline_at=time.time() + 3600)
                self.assertEqual(original_deadline, budget.snapshot()["deadline_at"])
                release.set()
                until = time.monotonic() + 1
                while budget.snapshot()["unknown_attempts"] and time.monotonic() < until:
                    time.sleep(0.01)
                self.assertEqual(0, budget.snapshot()["unknown_attempts"])
                self.assertEqual(5, budget.snapshot()["charged_tokens"])
                self.assertEqual(1, len(received))
                self.assertFalse(received[0].get("stream", False))


if __name__ == "__main__":
    unittest.main()
