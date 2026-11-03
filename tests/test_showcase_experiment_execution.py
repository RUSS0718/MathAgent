from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.experiment_manifest import manifest_digest
from showcase.experiment_runner import read_status
from showcase.experiment_sources import StaticModelConfigAdapter
from tests.test_showcase_experiment_cli import (
    MockTransportAdapter,
    _manifest,
    _ServerAppliedConfig,
)


class _Authorization:
    def __init__(self, manifest_sha256, evidence_kind, run_id):
        self.manifest_sha256 = manifest_sha256
        self.evidence_kind = evidence_kind
        self.run_id = run_id
        self.used = False

    def authorize(self, manifest_sha256, evidence_kind, run_id):
        allowed = (
            not self.used
            and manifest_sha256 == self.manifest_sha256
            and evidence_kind == self.evidence_kind
            and run_id == self.run_id
        )
        self.used = True
        return allowed


class _JobAdapter:
    def __init__(
        self, observations=None, *, ambiguous=False, observer_only=False, resume_response=None
    ):
        self.observations = list(observations or [])
        self.ambiguous = ambiguous
        self.observer_only = observer_only
        self.resume_response = resume_response
        self.submissions = 0
        self.resume_submissions = 0
        self.resume_preflight_inputs = []
        self.wait_deadlines = []
        self.lookup_inputs = []
        self.jobs = {}
        self.resume_actions = {}
        self._next_job = 0
        self._digests = {}
        self.dispatch_inputs = []

    def validate_runtime_contract(self, _manifest):
        return True

    def create_session(self, _run_id):
        return "session-safe"

    def request_digest(self, sample, session_id, *, budget_limits, deadline_at):
        value = f"{sample['id']}:{session_id}".encode()
        return hashlib.sha256(value).hexdigest()

    def find_by_idempotency_key(self, key, request_digest):
        self.lookup_inputs.append((key, request_digest))
        return list(self.jobs.get(key, []))

    def create_job(self, sample, session_id, key, *, budget_limits, deadline_at):
        self.submissions += 1
        self.dispatch_inputs.append((dict(budget_limits), deadline_at))
        if self.ambiguous:
            raise TimeoutError("transport details must not be recorded")
        self._next_job += 1
        job_id = f"job-{self._next_job}"
        digest = self.request_digest(
            sample,
            session_id,
            budget_limits=budget_limits,
            deadline_at=deadline_at,
        )
        self._digests[key] = digest
        self.jobs[key] = [{"job_id": job_id, "request_digest": digest}]
        return {"job_id": job_id}

    def wait_for_job(self, job_id, deadline_at):
        self.wait_deadlines.append(deadline_at)
        if self.observations:
            observed = self.observations.pop(0)
        else:
            observed = {"status": "succeeded"}
        return _snapshot(observed, deadline_at)

    def resume_preflight(self, job_id, expected_deadline_at, *, intent=None):
        self.resume_preflight_inputs.append(intent)
        if self.resume_response is not None:
            return dict(self.resume_response)
        matches = self.find_by_idempotency_key(intent["idempotency_key"], intent["request_digest"])
        if len(matches) != 1 or matches[0].get("job_id") != job_id:
            return {"observer_only": True, "safe_to_resume": False}
        budget = dict(_snapshot({}, expected_deadline_at)["budget"])
        budget["limits"] = dict(self.dispatch_inputs[-1][0])
        budget["deadline_at"] = expected_deadline_at
        record = matches[0]
        return {
            "safe_to_resume": True,
            "observer_only": self.observer_only,
            "unknown_actions": 0,
            "orphan_tool_actions": 0,
            "job_id": job_id,
            "request_digest": record["request_digest"],
            "status": "running",
            "ledger_consistent": True,
            "deadline_at": expected_deadline_at,
            "budget": budget,
        }

    def resume_request_digest(self, job_id):
        return hashlib.sha256(f"resume:{job_id}".encode()).hexdigest()

    def find_resume_by_idempotency_key(self, key):
        return list(self.resume_actions.get(key, []))

    def resume_job(self, job_id, key):
        self.resume_submissions += 1
        digest = self.resume_request_digest(job_id)
        self.resume_actions[key] = [{"job_id": job_id, "request_digest": digest}]
        return {"job_id": job_id}


class _CrashAtDispatchAdapter(_JobAdapter):
    def create_job(self, sample, session_id, key, *, budget_limits, deadline_at):
        self.submissions += 1
        self.dispatch_inputs.append((dict(budget_limits), deadline_at))
        raise SystemExit("simulated process death at dispatch boundary")


def _snapshot(overrides, deadline_at):
    budget = {
        "logical_calls": 1,
        "http_attempts": 1,
        "tool_calls": 0,
        "charged_tokens": 10,
        "wall_time_seconds": 1.0,
        "unknown_attempts": 0,
        "unresolved_attempts": 0,
        "unknown_tool_calls": 0,
    }
    value = {
        "status": "succeeded",
        "ledger_consistent": True,
        "transport_known": True,
        "transport": {
            "policy": "stream_first",
            "profile_set_fingerprint": "c" * 64,
            "calls": [{"call_id": "explore", "profile_fingerprint": "d" * 64}],
        },
        "budget": budget,
        "deadline_at": deadline_at,
    }
    value.update(copy.deepcopy(overrides))
    return value


def _context(manifest, job_adapter):
    digest = manifest_digest(manifest)
    source = manifest["source_identity"]
    return {
        "current_source": source,
        "trusted_model_config": StaticModelConfigAdapter(manifest["model"]),
        "server_model_config": _ServerAppliedConfig(manifest),
        "sample_resolver": type(
            "Resolver",
            (),
            {
                "hashes": lambda _self, sample: {
                    "input_sha256": sample["input_sha256"],
                    "text_sha256": sample["text_sha256"],
                }
            },
        )(),
        "transport_adapter": MockTransportAdapter(),
        "authorization": _Authorization(digest, manifest["evidence_kind"], "run-serial"),
        "job_adapter_factory": lambda: job_adapter,
    }


def _context_for_run(manifest, job_adapter, run_id):
    context = _context(manifest, job_adapter)
    context["authorization"] = _Authorization(
        manifest_digest(manifest), manifest["evidence_kind"], run_id
    )
    return context


def _two_sample_manifest(source):
    manifest = _manifest(source)
    second = dict(manifest["samples"][0], id="sample-02")
    manifest["samples"].append(second)
    manifest["batch_limits"] = {
        "runs": 2,
        "logical_calls": 4,
        "http_attempts": 4,
        "tool_calls": 2,
        "charged_tokens": 8192,
        "wall_seconds": 240,
    }
    manifest["authorization"]["execution_authorized"] = True
    return manifest


class ExperimentExecutionTest(unittest.TestCase):
    def test_timeout_status_persists_safe_stream_timing_from_job_events(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }

        class TimingAdapter(_JobAdapter):
            def execution_events(self, _job_id, *, after_id=0):
                if after_id:
                    return []
                return [{
                    "id": 1,
                    "event": "solver_progress",
                    "summary": "Solver progress recorded",
                    "stream_activity": {
                        "first_content_at": "2026-11-03T00:00:01Z",
                        "last_content_at": "2026-11-03T00:00:09Z",
                        "status": "streaming",
                        "content_bytes": 24,
                    },
                }]

            def wait_for_job(self, job_id, deadline_at):
                super().wait_for_job(job_id, deadline_at)
                now[0] = deadline_at + 0.5
                return _snapshot({"status": "running"}, deadline_at)

        manifest = _manifest(source)
        adapter = TimingAdapter()
        now = [1000.0]
        with tempfile.TemporaryDirectory() as temporary:
            with patch("showcase.experiment_execution.time.time", side_effect=lambda: now[0]):
                result = run_batch(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id="run-timeout-stream-timing",
                    output_root=temporary,
                    context=_context_for_run(manifest, adapter, "run-timeout-stream-timing"),
                )
            saved = read_status("run-timeout-stream-timing", output_root=temporary)

        self.assertEqual("stopped", result["phase"])
        self.assertEqual("hard_limit", result["stop_reason"])
        self.assertEqual(1, result["event_cursor"])
        self.assertEqual(result["log_tail"], saved["log_tail"])
        self.assertEqual(
            "2026-11-03T00:00:09Z",
            saved["log_tail"][-1]["stream_activity"]["last_content_at"],
        )

    def test_polling_error_persists_only_safe_observer_error_fields(self):
        from showcase.cli import CliError
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }

        class PollingErrorAdapter(_JobAdapter):
            def wait_for_job(self, _job_id, _deadline_at):
                raise CliError("network_error", 504)

        manifest = _manifest(source)
        adapter = PollingErrorAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-polling-error",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-polling-error"),
            )
            saved = read_status("run-polling-error", output_root=temporary)

        self.assertEqual("stopped", result["phase"])
        self.assertEqual("unknown_job_status", result["stop_reason"])
        self.assertEqual({"code": "network_error", "http_status": 504}, saved["observer_error"])

    def test_nonzero_provider_retry_is_rejected_before_adapter_construction(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["model"]["retry"] = 1
        adapter = _JobAdapter()
        context = _context_for_run(manifest, adapter, "run-retry-disabled")
        factory_calls = []
        context["job_adapter_factory"] = lambda: factory_calls.append(True) or adapter

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "experiment_retry_unsupported"):
                run_batch(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id="run-retry-disabled",
                    output_root=temporary,
                    context=context,
                )

        self.assertEqual(0, adapter.submissions)
        self.assertEqual([], factory_calls)

    def test_runs_and_full_run_budget_are_reserved_before_next_sample_post(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _two_sample_manifest(source)
        manifest["batch_limits"]["runs"] = 1
        adapter = _JobAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            limited_runs = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-count-reservation",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-count-reservation"),
            )
        self.assertEqual("hard_limit", limited_runs["stop_reason"])
        self.assertEqual(1, limited_runs["completed"])
        self.assertEqual(1, adapter.submissions)

        manifest = _two_sample_manifest(source)
        manifest["batch_limits"]["logical_calls"] = 3
        adapter = _JobAdapter(
            [
                {
                    "budget": {
                        "logical_calls": 2,
                        "http_attempts": 2,
                        "tool_calls": 0,
                        "charged_tokens": 10,
                        "wall_time_seconds": 1.0,
                        "unknown_attempts": 0,
                        "unresolved_attempts": 0,
                        "unknown_tool_calls": 0,
                    }
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temporary:
            limited_quota = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-budget-reservation",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-budget-reservation"),
            )
        self.assertEqual("hard_limit", limited_quota["stop_reason"])
        self.assertEqual(1, limited_quota["completed"])
        self.assertEqual(1, adapter.submissions)

    def test_resume_without_persisted_session_stops_without_creating_another(self):
        from showcase.experiment_execution import resume_batch, run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)

        class SessionResponseLostAdapter(_JobAdapter):
            def __init__(self):
                super().__init__()
                self.session_creations = 0

            def create_session(self, _run_id):
                self.session_creations += 1
                if self.session_creations == 1:
                    raise SystemExit("session POST accepted before local persistence")
                return f"session-{self.session_creations}"

        adapter = SessionResponseLostAdapter()
        digest = manifest_digest(manifest)
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SystemExit):
                run_batch(
                    manifest,
                    expected_sha256=digest,
                    run_id="run-session-crash",
                    output_root=temporary,
                    context=_context_for_run(manifest, adapter, "run-session-crash"),
                )

            result = resume_batch(
                "run-session-crash",
                expected_sha256=digest,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-session-crash"),
            )

        self.assertEqual("stopped", result["phase"])
        self.assertEqual("unknown_session", result["stop_reason"])
        self.assertEqual(1, adapter.session_creations)
        self.assertEqual(0, adapter.submissions)

    def test_unapproved_evidence_kind_cannot_reach_job_adapter(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        for evidence_kind in ("live", "arbitrary"):
            manifest = _manifest(source)
            manifest["evidence_kind"] = evidence_kind
            digest = manifest_digest(manifest)
            adapter = _JobAdapter()
            with (
                self.subTest(evidence_kind=evidence_kind),
                tempfile.TemporaryDirectory() as temporary,
            ):
                with self.assertRaisesRegex(ValueError, "experiment_evidence_kind_unavailable"):
                    run_batch(
                        manifest,
                        expected_sha256=digest,
                        run_id=f"run-{evidence_kind}",
                        output_root=temporary,
                        context=_context_for_run(manifest, adapter, f"run-{evidence_kind}"),
                    )
            self.assertEqual(0, adapter.submissions)

    def test_run_dispatches_samples_serially_and_persists_redacted_status(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _two_sample_manifest(source)
        adapter = _JobAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-serial",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-serial"),
            )
            saved = read_status("run-serial", output_root=temporary)

        self.assertEqual("completed", result["phase"])
        self.assertEqual(2, result["completed"])
        self.assertEqual(2, adapter.submissions)
        self.assertTrue(
            all(limits == manifest["run_limits"] for limits, _ in adapter.dispatch_inputs)
        )
        self.assertTrue(all(item[1] == saved["deadline_at"] for item in adapter.dispatch_inputs))
        self.assertEqual(2, saved["completed"])
        self.assertNotIn("x+1=2", str(saved))
        self.assertEqual(
            {
                "logical_calls": 2,
                "http_attempts": 2,
                "tool_calls": 0,
                "charged_tokens": 20,
                "wall_seconds": 2.0,
            },
            saved["usage"],
        )
        self.assertEqual(2, len(saved["run_records"]))
        self.assertEqual(
            {
                "sample_id",
                "job_id",
                "idempotency_key",
                "request_digest",
                "deadline_at",
                "session_id",
            },
            set(saved["run_records"][0]),
        )
        self.assertEqual("job-1", saved["run_records"][0]["job_id"])
        self.assertNotIn("x+1=2", str(saved["run_records"]))
        self.assertFalse((Path(temporary) / "run-serial" / "dispatch_intent.json").exists())

    def test_run_persists_actual_safe_execution_event_tail(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        adapter = _JobAdapter()
        adapter.execution_events = lambda _job_id, *, after_id=0: [
            {"id": 1, "event": "queued", "summary": "Job queued"},
            {"id": 2, "event": "final_result", "summary": "private provider response"},
            {"id": 3, "event": "untrusted event code", "summary": "private prompt"},
        ]

        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-event-tail",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-event-tail"),
            )
            saved = read_status("run-event-tail", output_root=temporary)

        expected_tail = [
            {"event": "queued", "summary": "Job queued"},
            {"event": "final_result", "summary": "Final result recorded"},
        ]
        self.assertEqual(expected_tail, result["log_tail"])
        self.assertEqual(expected_tail, saved["log_tail"])
        self.assertNotIn("private provider response", str(saved))
        self.assertNotIn("private prompt", str(saved))

    def test_run_persists_safe_events_while_job_is_still_being_polled(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        expected_tail = [{"event": "running", "summary": "Job started"}]

        class ProgressAdapter(_JobAdapter):
            def wait_for_job_with_progress(self, job_id, deadline_at, *, on_progress):
                on_progress()
                self.status_during_wait = read_status(
                    "run-event-progress", output_root=temporary
                )
                return _snapshot({"status": "succeeded"}, deadline_at)

        adapter = ProgressAdapter()
        adapter.execution_events = lambda _job_id, *, after_id=0: (
            [{"id": 1, "event": "running", "summary": "private prompt"}]
            if after_id == 0
            else []
        )

        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-event-progress",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-event-progress"),
            )

        self.assertEqual("completed", result["phase"])
        self.assertEqual(expected_tail, adapter.status_during_wait["log_tail"])
        self.assertNotIn("private prompt", str(adapter.status_during_wait))

    def test_run_resets_event_cursor_for_each_job_in_a_batch(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _two_sample_manifest(source)
        adapter = _JobAdapter()
        events_by_job = {
            job_id: [
                {"id": 1, "event": "queued", "summary": "Job queued"},
                {"id": 2, "event": "final_result", "summary": "Final result recorded"},
            ]
            for job_id in ("job-1", "job-2")
        }
        adapter.execution_events = lambda job_id, *, after_id=0: [
            event for event in events_by_job[job_id] if event["id"] > after_id
        ]

        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-event-cursor-per-job",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-event-cursor-per-job"),
            )

        self.assertEqual(2, result["completed"])
        self.assertEqual(
            [
                {"event": "queued", "summary": "Job queued"},
                {"event": "final_result", "summary": "Final result recorded"},
                {"event": "queued", "summary": "Job queued"},
                {"event": "final_result", "summary": "Final result recorded"},
            ],
            result["log_tail"],
        )

    def test_resume_clears_intent_after_completed_record_was_saved(self):
        from showcase.experiment_execution import resume_batch, run_batch
        from showcase.experiment_execution_state import save_execution_status

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        adapter = _JobAdapter()
        manifest_hash = manifest_digest(manifest)
        with tempfile.TemporaryDirectory() as temporary:
            initial = run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-intent-cleanup",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-intent-cleanup"),
            )
            run_dir = Path(temporary) / "run-intent-cleanup"
            status = read_status("run-intent-cleanup", output_root=temporary)
            intent = {
                "index": 0,
                "sample_id": "sample-01",
                "session_id": status["run_records"][0]["session_id"],
                "idempotency_key": status["run_records"][0]["idempotency_key"],
                "request_digest": status["run_records"][0]["request_digest"],
                "deadline_at": status["run_records"][0]["deadline_at"],
            }
            (run_dir / "dispatch_intent.json").write_text(json.dumps(intent), encoding="utf-8")
            status.update(phase="running", stop_reason=None)
            save_execution_status(run_dir, status)
            resumed = resume_batch(
                "run-intent-cleanup",
                expected_sha256=manifest_hash,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-intent-cleanup"),
            )

        self.assertEqual("completed", resumed["phase"])
        self.assertEqual(initial["run_records"], resumed["run_records"])
        self.assertEqual(1, adapter.submissions)

    def test_ambiguous_dispatch_stops_without_retry_or_next_sample(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _two_sample_manifest(source)
        adapter = _JobAdapter(ambiguous=True)
        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-unknown",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-unknown"),
            )

        self.assertEqual("stopped", result["phase"])
        self.assertEqual("unknown_dispatch", result["stop_reason"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(0, result["completed"])

    def test_resume_after_process_death_with_intent_and_no_job_does_not_post_again(self):
        from showcase.experiment_execution import resume_batch, run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest_hash = manifest_digest(manifest)
        adapter = _CrashAtDispatchAdapter()
        context = _context_for_run(manifest, adapter, "run-crash-boundary")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(SystemExit):
                run_batch(
                    manifest,
                    expected_sha256=manifest_hash,
                    run_id="run-crash-boundary",
                    output_root=temporary,
                    context=context,
                )

            resumed = resume_batch(
                "run-crash-boundary",
                expected_sha256=manifest_hash,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-crash-boundary"),
            )

        self.assertEqual("stopped", resumed["phase"])
        self.assertEqual("unknown_dispatch", resumed["stop_reason"])
        self.assertEqual(1, adapter.submissions)

    def test_ledger_defect_and_batch_hard_limit_stop_before_next_sample(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        for name, observation, expected in (
            ("ledger", {"ledger_consistent": False}, "ledger_or_binding_defect"),
            (
                "usage",
                {
                    "budget": {
                        "logical_calls": 1,
                        "http_attempts": 1,
                        "tool_calls": 0,
                        "charged_tokens": 10,
                        "wall_time_seconds": 1.0,
                        "unknown_attempts": 1,
                        "unresolved_attempts": 0,
                        "unknown_tool_calls": 0,
                    }
                },
                "incomplete_or_unresolved_usage",
            ),
        ):
            manifest = _two_sample_manifest(source)
            adapter = _JobAdapter([observation])
            with tempfile.TemporaryDirectory() as temporary:
                result = run_batch(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id=f"run-{name}",
                    output_root=temporary,
                    context=_context_for_run(manifest, adapter, f"run-{name}"),
                )
            self.assertEqual(expected, result["stop_reason"])
            self.assertEqual(1, adapter.submissions)

        manifest = _two_sample_manifest(source)
        manifest["batch_limits"]["logical_calls"] = 1
        manifest_hash = manifest_digest(manifest)
        adapter = _JobAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-limit",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-limit"),
            )
        self.assertEqual("hard_limit", result["stop_reason"])
        self.assertEqual(0, result["completed"])
        self.assertEqual(0, adapter.submissions)

    def test_running_job_at_run_deadline_stops_with_hard_limit_and_keeps_identity(self):
        from unittest.mock import patch

        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _two_sample_manifest(source)
        now = [1_000.0]

        class StillRunningAdapter(_JobAdapter):
            def wait_for_job(self, job_id, deadline_at):
                observation = super().wait_for_job(job_id, deadline_at)
                now[0] = deadline_at + 0.5
                observation["status"] = "running"
                return observation

        adapter = StillRunningAdapter()
        with tempfile.TemporaryDirectory() as temporary:
            with patch("showcase.experiment_execution.time.time", side_effect=lambda: now[0]):
                result = run_batch(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id="run-deadline-still-running",
                    output_root=temporary,
                    context=_context_for_run(manifest, adapter, "run-deadline-still-running"),
                )
            intent = json.loads(
                (Path(temporary) / "run-deadline-still-running" / "dispatch_intent.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual("stopped", result["phase"])
        self.assertEqual("hard_limit", result["stop_reason"])
        self.assertEqual("job-1", result["current_job_id"])
        self.assertEqual(intent["deadline_at"], result["run_records"][0]["deadline_at"])
        self.assertEqual(adapter.wait_deadlines[0], intent["deadline_at"])
        self.assertEqual(manifest["run_limits"], adapter.dispatch_inputs[0][0])
        self.assertEqual(0, result["current_index"])
        self.assertEqual(0, result["completed"])
        self.assertEqual(1, adapter.submissions)

    def test_resume_reuses_original_job_and_does_not_repeat_dispatch(self):
        from showcase.experiment_execution import resume_batch, run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["authorization"]["execution_authorized"] = True
        adapter = _JobAdapter([{"status": "running"}, {"status": "succeeded"}])
        manifest_hash = manifest_digest(manifest)
        with tempfile.TemporaryDirectory() as temporary:
            first = run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-resume",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-resume"),
            )
            resumed = resume_batch(
                "run-resume",
                expected_sha256=manifest_hash,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-resume"),
            )

        self.assertEqual("running", first["phase"])
        self.assertEqual("completed", resumed["phase"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(1, resumed["completed"])

    def test_resume_attaches_to_existing_job_without_resume_action(self):
        from showcase.experiment_execution import resume_batch, run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest_hash = manifest_digest(manifest)
        adapter = _JobAdapter([{"status": "running"}, {"status": "succeeded"}], observer_only=True)
        with tempfile.TemporaryDirectory() as temporary:
            run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-observer-resume",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-observer-resume"),
            )
            original = read_status("run-observer-resume", output_root=temporary)
            resumed = resume_batch(
                "run-observer-resume",
                expected_sha256=manifest_hash,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-observer-resume"),
            )

        self.assertEqual("completed", resumed["phase"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(0, adapter.resume_submissions)
        self.assertEqual(original["deadline_at"], resumed["deadline_at"])
        self.assertEqual(adapter.wait_deadlines[0], adapter.wait_deadlines[1])
        self.assertEqual(
            next(iter(adapter.jobs)),
            adapter.resume_preflight_inputs[0]["idempotency_key"],
        )
        self.assertEqual(
            adapter.jobs[next(iter(adapter.jobs))][0]["request_digest"],
            adapter.resume_preflight_inputs[0]["request_digest"],
        )

    def test_resume_unknown_state_fails_closed_without_resume_action(self):
        from showcase.experiment_execution import resume_batch, run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest_hash = manifest_digest(manifest)
        adapter = _JobAdapter(
            [{"status": "running"}],
            resume_response={
                "safe_to_resume": False,
                "observer_only": False,
            },
        )
        with tempfile.TemporaryDirectory() as temporary:
            run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-unknown-resume",
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-unknown-resume"),
            )
            resumed = resume_batch(
                "run-unknown-resume",
                expected_sha256=manifest_hash,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, "run-unknown-resume"),
            )

        self.assertEqual("stopped", resumed["phase"])
        self.assertEqual("resume_review_required", resumed["stop_reason"])
        self.assertEqual(0, adapter.resume_submissions)

    def test_manifest_flag_alone_and_changed_or_reused_grants_fail_closed(self):
        from showcase.experiment_execution import run_batch

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["authorization"]["execution_authorized"] = True
        manifest_hash = manifest_digest(manifest)
        adapter = _JobAdapter()
        context = _context_for_run(manifest, adapter, "run-auth")
        context["authorization"] = _Authorization("f" * 64, "scripted", "run-auth")

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "experiment_invocation_authorization_required"):
                run_batch(
                    manifest,
                    expected_sha256=manifest_hash,
                    run_id="run-auth",
                    output_root=temporary,
                    context=context,
                )
            self.assertEqual(0, adapter.submissions)

            grant = _Authorization(manifest_hash, "scripted", "run-auth")
            context["authorization"] = grant
            changed = dict(manifest, evidence_kind="reviewed")
            with self.assertRaisesRegex(ValueError, "experiment_evidence_kind_unavailable"):
                run_batch(
                    changed,
                    expected_sha256=manifest_digest(changed),
                    run_id="run-auth",
                    output_root=temporary,
                    context=context,
                )
            result = run_batch(
                manifest,
                expected_sha256=manifest_hash,
                run_id="run-auth",
                output_root=temporary,
                context=context,
            )
            self.assertEqual("completed", result["phase"])
            self.assertEqual(1, adapter.submissions)
            with self.assertRaisesRegex(ValueError, "experiment_invocation_authorization_required"):
                run_batch(
                    manifest,
                    expected_sha256=manifest_hash,
                    run_id="run-auth",
                    output_root=temporary,
                    context=context,
                )
        self.assertEqual(1, adapter.submissions)


if __name__ == "__main__":
    unittest.main()
