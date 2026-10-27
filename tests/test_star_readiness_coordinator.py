"""Public behavior tests for the one-shot scripted #97 readiness batch."""

import hashlib
import json
import os
import tempfile
import time
import unittest
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from showcase import star_readiness_registration as readiness_registration
from showcase.star_acceptance import evaluate_delivery
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_configuration import validate_server_configuration
from showcase.star_readiness_coordinator import StarReadinessCoordinator, _claim_live_registration
from showcase.star_readiness_runtime import cleanup_runtime_storage
from tests.star_experiment_support import LoopbackProvider

SOURCE = {"revision": "a" * 40, "source_sha256": "b" * 64, "dirty_status": True}
QUESTION_TEXTS = (
    ("simple-01", "https://example.test/simple", "simple_fastpath", "Compute 2 + 2."),
    ("multi-01", "https://example.test/multi", "public_multistep", "Compute 2 + 3."),
)
QUESTION_SPECS = tuple(
    (question_id, source, question_type, hashlib.sha256(text.encode("utf-8")).hexdigest())
    for question_id, source, question_type, text in QUESTION_TEXTS
)


def frozen_manifest():
    """Create a locally frozen registration using the production schema validator."""
    draft = {
        "budget_status": "proposed_unapproved",
        "dirty_status": True,
        "enforcement": "not_implemented",
        "evidence_types": ["scripted", "fault_injection", "live", "replay"],
        "execution_authorized": False,
        "model": deepcopy(readiness_registration.MODEL),
        "original_batch": "unchanged_not_counted",
        "previous_draft_sha256": "c" * 64,
        "question_encoding": "UTF-8 exact text with LF separators, no trailing newline",
        "questions": [
            {"id": question_id, "source": source, "type": question_type,
             "text": text, "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}
            for question_id, source, question_type, text in QUESTION_TEXTS
        ],
        "round_limits": deepcopy(readiness_registration.ROUND_LIMITS),
        "runner_qualification": "not_implemented",
        "schedule": [
            {"attempts": 1, "limits": deepcopy(limits), "question": question_id,
             "transport": "nonstream"}
            for (question_id, _, _, _), limits in zip(
                QUESTION_TEXTS, readiness_registration.RUN_LIMITS
            )
        ],
        "source_identity": {"revision": SOURCE["revision"],
                             "source_sha256": SOURCE["source_sha256"]},
        "status": "draft_not_dispatchable",
        "stop_on": deepcopy(readiness_registration.STOP_ON),
        "version": readiness_registration.DRAFT_VERSION,
    }
    return readiness_registration.adapt_draft(draft, current_source=SOURCE)


class ScriptedServer:
    """In-memory scripted server that never sends a provider request."""

    instances = []
    scenario = "success"
    events = []
    clock_jump = None

    def __init__(self, path, transport, adapter, policy, evidence_kind,
                 *, refresh_preflight_each_call=False, late_usage_evidence_dir=None):
        self.path, self.transport, self.adapter = path, transport, adapter
        self.policy, self.evidence_kind = policy, evidence_kind
        self.dispatched = []
        self.accepted_job_ids = []
        self.preflight_count = 0
        self.collected_deadlines = []
        self.collected_cancellations = []
        type(self).instances.append(self)

    def check_conditions(self):
        return None

    def preflight(self):
        self.preflight_count += 1
        type(self).events.append("preflight")
        available = not (
            self.scenario == "startup_preflight_failure" and self.preflight_count == 1
            or self.scenario == "post_dispatch_preflight_failure" and self.preflight_count == 2
        )
        return {
            "available": available,
            "identity": {"run_id": f"preflight-{self.preflight_count}"},
            "budget": {"tool_calls": 1, "http_attempts": 0},
        }

    def dispatch(self, question, *, idempotency_key=None):
        type(self).events.append("dispatch")
        self.dispatched.append(question["prompt"])
        job_id = f"job-{len(self.dispatched)}"
        self.accepted_job_ids.append(job_id)
        if self.scenario == "dispatch_response_lost":
            raise TimeoutError("fixture_dispatch_response_lost")
        return job_id

    def resolve_dispatch(self, idempotency_key):
        return self.accepted_job_ids[-1] if self.accepted_job_ids else None

    def collect(self, job_id, deadline_at, *, canceled=lambda: False):
        self.collected_deadlines.append((deadline_at, self.policy.round_deadline_at))
        if self.scenario == "collection_failure":
            raise ValueError("fixture_collection_failure")
        if self.scenario == "clock_rollback_during_collect":
            type(self).clock_jump()
            self.collected_cancellations.append(canceled())
        return make_bundle(
            job_id,
            unknown=self.scenario == "unknown",
            missing_usage=self.scenario == "missing_usage",
            failed=self.scenario == "failed",
            evidence_mismatch=self.scenario == "evidence_mismatch",
            protocol_failed=self.scenario == "protocol_failed",
        )

    def provenance(self, job_id):
        self.provenance_calls = getattr(self, "provenance_calls", []) + [job_id]
        return {}, []

    def close(self):
        return None


def make_bundle(job_id, *, unknown=False, missing_usage=False, failed=False,
                evidence_mismatch=False, protocol_failed=False):
    """Build a consistent public Job/Run/report/Evidence bundle."""
    semantics = {
        "transport": "unknown" if unknown else "complete",
        "execution": "completed",
        "whole_review": "accepted",
        "binding": "same_artifact",
    }
    budget = {
        "charged_tokens": 17,
        "http_attempts": 1,
        "logical_calls": 1,
        "provider_known": {"total_tokens": None if unknown or missing_usage else 17},
        "reserved_tokens": 8192 if unknown else 0,
        "tool_calls": 0,
        "unknown_attempts": int(unknown),
        "unknown_tool_calls": 0,
        "unresolved_attempts": int(unknown),
    }
    result = {"final_response": "fixture answer"}
    if protocol_failed:
        result["solver"] = {"recovery": {"protocol_failures": 1}}
    verification = {}
    attempts = []
    return {
        "job": {"job_id": job_id, "status": "failed" if failed else "succeeded",
                "result": result},
        "report": {
            "answer": "fixture answer",
            "budget": deepcopy(budget),
            "checks": deepcopy(verification),
            "request_attempts": deepcopy(attempts),
            "semantics": {**semantics, **({"transport": "mismatch"} if evidence_mismatch else {})},
        },
        "evidence": {
            "budget": deepcopy(budget),
            "request_attempts": deepcopy(attempts),
            "run": {"run_id": job_id},
            "semantics": deepcopy(semantics),
            "verification": deepcopy(verification),
        },
        "run": {"run_id": job_id},
    }


class StarReadinessCoordinatorTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch("showcase.star_readiness_coordinator.ARTIFACTS",
                                self.folder / "artifacts"))
        ScriptedServer.instances = []
        ScriptedServer.events = []
        ScriptedServer.scenario = "success"
        ScriptedServer.clock_jump = None
        self.source = patch(
            "showcase.star_readiness_coordinator.current_source_identity", return_value=SOURCE
        )
        self.source_mock = self.source.start()
        self.addCleanup(self.source.stop)
        self.server = patch(
            "showcase.star_readiness_coordinator.ExperimentServer", ScriptedServer
        )
        self.server.start()
        self.addCleanup(self.server.stop)
        self.delivery = patch(
            "showcase.star_readiness_coordinator.evaluate_delivery",
            return_value={"review_bound": True, "reason": "fastpath_no_step_proofs",
                          "proof_delivered": False},
        )
        self.delivery_mock = self.delivery.start()
        self.addCleanup(self.delivery.stop)
        self.configuration = patch(
            "showcase.star_readiness_coordinator.validate_server_configuration",
            side_effect=lambda _server, expected: deepcopy(expected),
        )
        self.configuration_mock = self.configuration.start()
        self.addCleanup(self.configuration.stop)
        self.question_specs = patch(
            "showcase.star_readiness_registration.QUESTION_SPECS", QUESTION_SPECS
        )
        self.question_specs.start()
        self.addCleanup(self.question_specs.stop)
        self.enterContext(patch("showcase.star_readiness_registration.V4_QUESTION_SPECS",
                                QUESTION_SPECS))
        self.manifest = frozen_manifest()
        self.coordinator = StarReadinessCoordinator(
            self.folder / "round",
            adapters={"nonstream": SimpleNamespace(_get_client=lambda: SimpleNamespace(
                loopback_only=True, api_base="http://127.0.0.1:43123"))},
            manifest=self.manifest,
            manifest_sha256=readiness_registration.digest(self.manifest),
        )

    def test_dispatches_each_registered_question_once_and_archives_bundle_and_result(self):
        result = self.coordinator.run()

        self.assertEqual("completed", result["stop_reason"])
        self.assertEqual(2, result["executed_runs"])
        self.assertEqual([item[3] for item in QUESTION_TEXTS], ScriptedServer.instances[0].dispatched)
        self.assertEqual(3, self.source_mock.call_count, "startup plus a source check per dispatch")
        self.assertEqual(["preflight", "preflight", "dispatch", "preflight", "dispatch"],
                         ScriptedServer.events)
        self.assertEqual(2, len(ScriptedServer.instances[0].provenance_calls))
        runtime_path = Path(ScriptedServer.instances[0].path)
        self.assertFalse(runtime_path.is_relative_to(self.folder / "round"))
        self.assertFalse(runtime_path.exists(), "raw Job storage must be removed after the run")
        self.assertEqual(2, self.delivery_mock.call_count)
        self.assertEqual(34, result["usage"]["charged_tokens"])
        self.assertEqual(0, result["usage"]["reserved_tokens"])
        self.assertEqual([], result["unresolved_dispatches"])
        self.assertEqual("complete", result["runtime_storage_cleanup"])
        for name in ("intent-00.json", "run-00.json", "intent-01.json", "run-01.json",
                     "result.json", "hashes.json"):
            self.assertTrue((self.folder / "round" / name).is_file(), name)
        archived = json.loads((self.folder / "round" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual("completed", archived["stop_reason"])
        archive_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.folder / "round").glob("*.json")
        )
        self.assertNotIn(QUESTION_TEXTS[0][3], archive_text)
        self.assertNotIn("fixture answer", archive_text)

    def test_settled_success_with_lost_dispatch_response_is_archived_without_redispatch(self):
        ScriptedServer.scenario = "dispatch_response_lost"

        with patch("showcase.star_readiness_coordinator.time.time", return_value=1_000.0):
            with patch("showcase.star_readiness_coordinator.cleanup_runtime_storage",
                       wraps=cleanup_runtime_storage) as cleanup:
                result = self.coordinator.run()

        self.assertEqual("dispatch_response_recovered", result["stop_reason"])
        self.assertEqual("TimeoutError", result["failure_type"])
        self.assertEqual(1, result["attempted_runs"])
        self.assertEqual(1, result["executed_runs"])
        self.assertTrue(result["usage"]["usage_complete"])
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertEqual(0, result["usage"]["reserved_tokens"])
        self.assertEqual([], result["unresolved_dispatches"])
        self.assertEqual([], result["uncollected"])
        self.assertEqual(["multi-01"], result["unexecuted"])
        self.assertEqual(["job-1"], ScriptedServer.instances[0].accepted_job_ids)
        self.assertEqual(["job-1"], cleanup.call_args.args[1])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertEqual("complete", result["runtime_storage_cleanup"])
        self.assertFalse(Path(ScriptedServer.instances[0].path).exists())
        run = json.loads((self.folder / "round" / "run-00.json").read_text(encoding="utf-8"))
        self.assertEqual({"job_id": "job-1", "status": "succeeded"}, run["job"])
        self.assertEqual("job-1", run["run"]["run_id"])
        self.assertEqual("job-1", run["evidence_identity"]["run_id"])
        self.assertTrue(all(run["bundle_invariants"].values()))
        self.assertEqual(17, run["budget"]["provider_known"]["total_tokens"])
        self.assertTrue((self.folder / "round" / "delivery-00.json").is_file())
        dispatch = json.loads((self.folder / "round" / "dispatch-00.json").read_text(encoding="utf-8"))
        self.assertEqual({"job_id": "job-1", "recovered_from_store": True,
                          "status": "response_recovered"}, dispatch)
        archived = json.loads((self.folder / "round" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["unresolved_dispatches"], archived["unresolved_dispatches"])
        archive_text = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (self.folder / "round").glob("*.json")
        )
        self.assertNotIn(QUESTION_TEXTS[0][3], archive_text)
        self.assertIn("job-1", archive_text)

    def test_failed_job_with_lost_dispatch_response_is_archived_without_redispatch(self):
        ScriptedServer.scenario = "dispatch_response_lost"
        with patch.object(ScriptedServer, "collect", return_value=make_bundle("job-1", failed=True)) as collect:
            result = self.coordinator.run()

        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual(1, len(ScriptedServer.instances[0].dispatched))
        self.assertEqual("job-1", collect.call_args.args[0])
        self.assertEqual(1, collect.call_count)
        self.assertEqual([], result["uncollected"])
        self.assertEqual([], result["unresolved_dispatches"])
        self.assertTrue(result["usage"]["usage_complete"])
        run = json.loads((self.folder / "round" / "run-00.json").read_text(encoding="utf-8"))
        self.assertEqual({"job_id": "job-1", "status": "failed"}, run["job"])
        self.assertEqual("job-1", run["evidence_identity"]["run_id"])
        self.assertEqual(17, run["budget"]["charged_tokens"])
        self.assertTrue((self.folder / "round" / "delivery-00.json").is_file())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertEqual("complete", result["runtime_storage_cleanup"])

    def _assert_recovered_dispatch_retained(self, result):
        """Require the original dispatch identity and reservation to survive failed recovery."""
        self.assertEqual("retained", result["runtime_storage_cleanup"], result)
        runtime = self.folder / "artifacts" / result["runtime_storage_path"]
        self.assertTrue(runtime.is_dir())
        retention = json.loads((runtime / "retention.json").read_text(encoding="utf-8"))
        self.assertEqual(["job-1"], retention["run_ids"])
        pending, = result["unresolved_dispatches"]
        self.assertEqual("job-1", pending["job_id"])
        self.assertEqual("pending_settlement", pending["status"])
        self.assertEqual({**self.manifest["schedule"][0]["limits"], "deadline_at": 1300.0},
                         pending["reserved_budget"])
        intent = json.loads((self.coordinator.path / "intent-00.json").read_text(encoding="utf-8"))
        self.assertEqual(intent["idempotency_key"], pending["idempotency_key"])
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertEqual(0, result["usage"]["charged_tokens"])
        self.assertEqual([{"index": 0, "job_id": "job-1"}], result["uncollected"])
        self.assertEqual(1, len(ScriptedServer.instances[-1].dispatched))
        self.assertFalse((self.coordinator.path / "intent-01.json").exists())
        archived = json.loads((self.coordinator.path / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["unresolved_dispatches"], archived["unresolved_dispatches"])
        self.assertFalse(archived["usage"]["usage_complete"])

    def test_recovered_dispatch_retains_runtime_and_reservation_when_collection_or_archive_fails(self):
        from showcase.star_experiment_archive import ExperimentArchive

        original_put = ExperimentArchive.put
        faults = {
            "collect": (ScriptedServer, "collect"),
            "run_record": ("showcase.star_readiness_coordinator.run_record",),
            "provenance": (ScriptedServer, "provenance"),
            "delivery": ("showcase.star_readiness_coordinator.evaluate_delivery",),
            "delivery_record": ("showcase.star_readiness_coordinator.delivery_record",),
        }
        for fault in (*faults, "dispatch-00.json", "run-00.json", "delivery-00.json"):
            with self.subTest(fault=fault), ExitStack() as resources:
                self.coordinator.path = self.folder / fault
                ScriptedServer.scenario = "dispatch_response_lost"
                resources.enter_context(patch("showcase.star_readiness_coordinator.time.time",
                                              return_value=1000.0))
                if fault in faults:
                    target = faults[fault]
                    inject = patch if len(target) == 1 else patch.object
                    resources.enter_context(inject(*target, side_effect=OSError("fixture_recovery_failed")))
                else:
                    def fail_archive(archive, name, value):
                        if name == fault:
                            raise OSError("fixture_archive_failed")
                        return original_put(archive, name, value)
                    resources.enter_context(patch.object(ExperimentArchive, "put", fail_archive))
                result = self.coordinator.run()

                self.assertEqual("failure", result["stop_reason"])
                self.assertEqual("OSError", result["failure_type"])
                self._assert_recovered_dispatch_retained(result)

    def test_recovered_dispatch_rejects_wrong_job_identity_without_settling_or_cleaning(self):
        for component in ("job", "run", "evidence"):
            with self.subTest(component=component):
                self.coordinator.path = self.folder / component
                ScriptedServer.scenario = "dispatch_response_lost"
                bundle = make_bundle("job-1")
                if component == "job":
                    bundle[component]["job_id"] = "wrong-job"
                elif component == "run":
                    bundle[component]["run_id"] = "wrong-job"
                else:
                    bundle[component]["run"]["run_id"] = "wrong-job"
                with (
                    patch("showcase.star_readiness_coordinator.time.time", return_value=1000.0),
                    patch.object(ScriptedServer, "collect", return_value=bundle),
                ):
                    result = self.coordinator.run()

                self.assertEqual("evidence_mismatch", result["stop_reason"])
                self._assert_recovered_dispatch_retained(result)

    def test_recovered_dispatch_keeps_unknown_and_hard_limit_stop_contracts(self):
        for scenario in ("unknown", "hard_limit"):
            with self.subTest(scenario=scenario):
                self.coordinator.path = self.folder / scenario
                ScriptedServer.scenario = "dispatch_response_lost"
                bundle = make_bundle("job-1", unknown=scenario == "unknown")
                if scenario == "hard_limit":
                    for key in ("report", "evidence"):
                        bundle[key]["budget"]["logical_calls"] = 6
                with patch.object(ScriptedServer, "collect", return_value=bundle) as collect:
                    result = self.coordinator.run()

                self.assertEqual("unknown_transport" if scenario == "unknown" else "hard_limit",
                                 result["stop_reason"])
                self.assertEqual(1, len(ScriptedServer.instances[-1].dispatched))
                self.assertEqual(1, collect.call_count)
                self.assertTrue((self.coordinator.path / "run-00.json").is_file())
                self.assertFalse((self.coordinator.path / "intent-01.json").exists())
                self.assertEqual(scenario != "unknown", result["usage"]["usage_complete"])
                if scenario == "unknown":
                    self.assertEqual("pending_settlement", result["unresolved_dispatches"][0]["status"])
                    self.assertEqual("job-1", result["unresolved_dispatches"][0]["job_id"])
                    self.assertEqual(8192, result["usage"]["reserved_tokens"])
                else:
                    self.assertEqual([], result["unresolved_dispatches"])

    def test_persisted_terminal_job_is_archived_before_settled_runtime_is_cleaned(self):
        """Lose the public POST receipt after the real local Job and S3 ledger settle."""
        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        original_dispatch = ExperimentServer.dispatch

        def preflight(server):
            server.preflight_count += 1
            return {"available": True, "identity": {"run_id": f"probe-{server.preflight_count}"},
                    "budget": {"tool_calls": 1, "http_attempts": 0}}

        for failed in (False, True):
            with self.subTest(failed=failed):
                accepted = []
                posts = []
                original_post = ExperimentServer.post

                def post(server, path, payload, **kwargs):
                    posts.append(path)
                    return original_post(server, path, payload, **kwargs)

                def respond(context):
                    if failed:
                        return {"assessment": "INVALID"}
                    return {
                        "explore": {"assessment": "SOLVED", "worked": [], "failed": [],
                                    "candidates": [], "solution_candidate": "4"},
                        "explore_polish": {"solution_candidate": "4"},
                        "whole_solution_verifier": {"verdict": "ACCEPT", "reason": "Addition"},
                    }[context["role"]]

                def lose_response(server, question, **kwargs):
                    job_id = original_dispatch(server, question, **kwargs)
                    bundle = server.collect(job_id, time.time() + 10)
                    accepted.append(bundle)
                    raise TimeoutError("fixture_response_lost_after_settlement")

                provider.respond = respond
                adapter = provider.adapters()["nonstream"]
                adapter._get_client().loopback_only = True
                coordinator = StarReadinessCoordinator(
                    self.folder / ("persisted-failure" if failed else "persisted-success"),
                    adapters={"nonstream": adapter}, manifest=self.manifest,
                    manifest_sha256=readiness_registration.digest(self.manifest),
                )
                with (
                    patch("showcase.star_readiness_coordinator.ExperimentServer", ExperimentServer),
                    patch("showcase.star_product_readiness.isolated_readiness",
                          return_value={"available": True}),
                    patch.object(ExperimentServer, "preflight", preflight),
                    patch.object(ExperimentServer, "post", post),
                    patch.object(ExperimentServer, "dispatch", lose_response),
                    patch("showcase.star_readiness_coordinator.evaluate_delivery", evaluate_delivery),
                ):
                    result = coordinator.run()

                self.assertEqual("protocol_failure" if failed else "dispatch_response_recovered",
                                 result["stop_reason"], result)
                self.assertEqual("TimeoutError", result["failure_type"], result)
                self.assertEqual(1, len(accepted), result)
                self.assertEqual("failed" if failed else "succeeded", accepted[0]["job"]["status"])
                self.assertEqual(0, accepted[0]["report"]["budget"]["unresolved_attempts"])
                self.assertEqual(0, accepted[0]["report"]["budget"]["reserved_tokens"])
                self.assertEqual(1, posts.count("/api/agent/jobs"))
                self.assertEqual(1, result["attempted_runs"])
                self.assertEqual([], result["uncollected"])
                self.assertEqual([], result["unresolved_dispatches"])
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertEqual("complete", result["runtime_storage_cleanup"])
                archived = json.loads((coordinator.path / "run-00.json").read_text(encoding="utf-8"))
                self.assertEqual(accepted[0]["job"]["job_id"], archived["job"]["job_id"])
                self.assertEqual(accepted[0]["report"]["budget"]["charged_tokens"],
                                 archived["budget"]["charged_tokens"])
                self.assertTrue(archived["request_attempts"])
                self.assertTrue(all(archived["bundle_invariants"].values()))
                self.assertTrue((coordinator.path / "delivery-00.json").is_file())
                self.assertFalse((coordinator.path / "intent-01.json").exists())

    def test_unrecoverable_dispatch_retains_runtime_and_key_for_manual_reconciliation(self):
        ScriptedServer.scenario = "dispatch_response_lost"
        for outcome in (None, OSError("fixture_store_unavailable")):
            with self.subTest(outcome=outcome):
                self.coordinator.path = self.folder / ("not-found" if outcome is None else "error")
                with patch.object(ScriptedServer, "resolve_dispatch", side_effect=[outcome]):
                    result = self.coordinator.run()
                unresolved = result["unresolved_dispatches"][0]
                self.assertIsNone(unresolved["job_id"])
                self.assertTrue(unresolved["idempotency_key"])
                self.assertEqual("pending_settlement", unresolved["status"])
                self.assertEqual("retained", result["runtime_storage_cleanup"])
                runtime = self.folder / "artifacts" / result["runtime_storage_path"]
                self.assertTrue(runtime.is_dir())
                self.assertTrue((runtime / "retention.json").is_file())
                self.assertEqual(1, len(ScriptedServer.instances[-1].dispatched))

    def test_later_lost_dispatch_retains_full_reservation_and_prior_observed_usage(self):
        now = [1_000.0]
        original_dispatch = ScriptedServer.dispatch
        original_collect = ScriptedServer.collect

        def dispatch_with_second_response_lost(server, question, **kwargs):
            if server.dispatched:
                server.scenario = "dispatch_response_lost"
                now[0] += 50  # Waiting for a response must not extend the original deadline.
            return original_dispatch(server, question, **kwargs)

        def collect_with_elapsed_time(server, *args, **kwargs):
            bundle = original_collect(server, *args, **kwargs)
            now[0] += 300
            return bundle

        with (patch("showcase.star_readiness_coordinator.time.time", side_effect=lambda: now[0]),
              patch("showcase.star_readiness_coordinator.time.monotonic",
                    side_effect=lambda: now[0]),
              patch.object(ScriptedServer, "dispatch", dispatch_with_second_response_lost),
              patch.object(ScriptedServer, "collect", collect_with_elapsed_time),
              patch.object(ScriptedServer, "resolve_dispatch", return_value=None)):
            result = self.coordinator.run()

        self.assertEqual("unknown_dispatch_outcome", result["stop_reason"])
        self.assertEqual(2, result["attempted_runs"])
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual([item[3] for item in QUESTION_TEXTS], ScriptedServer.instances[0].dispatched)
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertEqual(1, result["usage"]["logical_calls"])
        self.assertEqual(1, result["usage"]["http_attempts"])
        self.assertEqual(0, result["usage"]["problem_tool_calls"])
        intent = json.loads((self.folder / "round" / "intent-01.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [{"index": 1, "question_id": "multi-01", "status": "pending_settlement",
              "job_id": None, "idempotency_key": intent["idempotency_key"],
              "reserved_budget": {"charged_tokens": 65536, "logical_calls": 12,
                                  "http_attempts": 16, "problem_tool_calls": 3,
                                  "wall_seconds": 600, "deadline_at": 1_900.0}}],
            result["unresolved_dispatches"],
        )
        archived = json.loads((self.folder / "round" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual(result["usage"], archived["usage"])
        self.assertEqual(result["unresolved_dispatches"], archived["unresolved_dispatches"])
        self.assertFalse((self.folder / "round" / "run-01.json").exists())

    def test_startup_preflight_only_consumes_batch_deadline(self):
        now = [1_000.0]
        original_preflight = ScriptedServer.preflight

        def preflight_with_startup_delay(server):
            observed = original_preflight(server)
            if server.preflight_count == 1:
                now[0] += 120
            return observed

        with (patch("showcase.star_readiness_coordinator.time.time", side_effect=lambda: now[0]),
              patch.object(ScriptedServer, "preflight", preflight_with_startup_delay)):
            result = self.coordinator.run()

        self.assertEqual("completed", result["stop_reason"])
        self.assertEqual([(1_420.0, 1_900.0), (1_720.0, 1_900.0)],
                         ScriptedServer.instances[0].collected_deadlines)
        self.assertEqual(3, result["preflights"])
        self.assertEqual(0, result["usage"]["problem_tool_calls"])

    def test_system_clock_rollback_does_not_restore_batch_admission_time(self):
        wall_now = [10_000.0]
        monotonic_now = [100.0]
        original_preflight = ScriptedServer.preflight

        def preflight_with_clock_rollback(server):
            observed = original_preflight(server)
            if server.preflight_count == 1:
                wall_now[0] -= 1_000
                monotonic_now[0] += 650
            return observed

        with (patch("showcase.star_readiness_coordinator.time.time",
                    side_effect=lambda: wall_now[0]),
              patch("showcase.star_readiness_coordinator.time.monotonic",
                    side_effect=lambda: monotonic_now[0]),
              patch.object(ScriptedServer, "preflight", preflight_with_clock_rollback)):
            result = self.coordinator.run()

        self.assertEqual("round_wall_seconds_insufficient", result["stop_reason"])
        self.assertEqual(1, result["preflights"])
        self.assertEqual([], ScriptedServer.instances[0].dispatched)
        self.assertEqual([], ScriptedServer.instances[0].collected_deadlines)
        self.assertEqual(10_900.0, ScriptedServer.instances[0].policy.round_deadline_at)

    def test_system_clock_rollback_does_not_extend_server_wait_past_run_deadline(self):
        wall_now = [10_000.0]
        monotonic_now = [100.0]
        ScriptedServer.scenario = "clock_rollback_during_collect"
        ScriptedServer.instances = []

        def roll_back_wall_clock():
            wall_now[0] -= 500
            monotonic_now[0] += 301

        ScriptedServer.clock_jump = roll_back_wall_clock
        with (patch("showcase.star_readiness_coordinator.time.time",
                    side_effect=lambda: wall_now[0]),
              patch("showcase.star_readiness_coordinator.time.monotonic",
                    side_effect=lambda: monotonic_now[0])):
            result = self.coordinator.run()

        self.assertEqual([True], ScriptedServer.instances[0].collected_cancellations)
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual("round_wall_seconds_insufficient", result["stop_reason"])
        self.assertEqual(10_300.0, ScriptedServer.instances[0].collected_deadlines[0][0])
        self.assertEqual(10_900.0, ScriptedServer.instances[0].policy.round_deadline_at)

    def test_unknown_transport_stops_before_second_dispatch_and_preserves_reserved_usage(self):
        ScriptedServer.scenario = "unknown"

        result = self.coordinator.run()

        self.assertEqual("unknown_transport", result["stop_reason"])
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertEqual(8192, result["usage"]["reserved_tokens"])
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertTrue((self.folder / "round" / "run-00.json").is_file())
        self.assertTrue((self.folder / "round" / "result.json").is_file())

    def test_missing_provider_usage_stops_before_second_dispatch(self):
        ScriptedServer.scenario = "missing_usage"

        result = self.coordinator.run()

        self.assertEqual("usage_unknown", result["stop_reason"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

    def test_failed_run_stops_before_second_dispatch(self):
        ScriptedServer.scenario = "failed"

        result = self.coordinator.run()

        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertTrue((self.folder / "round" / "run-00.json").is_file())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

    def test_collection_failure_retains_job_identity_and_marks_usage_incomplete(self):
        ScriptedServer.scenario = "collection_failure"

        result = self.coordinator.run()

        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual([{"index": 0, "job_id": "job-1"}], result["uncollected"])
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertEqual([], result["unresolved_dispatches"])
        self.assertEqual("retained", result["runtime_storage_cleanup"])
        runtime = self.folder / "artifacts" / result["runtime_storage_path"]
        self.assertTrue(runtime.is_dir())
        self.assertEqual(["job-1"], json.loads(
            (runtime / "retention.json").read_text(encoding="utf-8"))["run_ids"])

    def test_normal_dispatch_retains_runtime_when_run_or_delivery_archive_fails(self):
        from showcase.star_experiment_archive import ExperimentArchive

        original_put = ExperimentArchive.put
        faults = {
            "provenance": (ScriptedServer, "provenance"),
            "evaluate_delivery": ("showcase.star_readiness_coordinator.evaluate_delivery",),
            "delivery_record": ("showcase.star_readiness_coordinator.delivery_record",),
        }
        for fault in ("run_record", "run_archive", *faults, "delivery_archive"):
            with self.subTest(fault=fault), ExitStack() as resources:
                self.coordinator.path = self.folder / fault
                if fault == "run_record":
                    resources.enter_context(patch("showcase.star_readiness_coordinator.run_record",
                                                  side_effect=OSError("fixture_record_failed")))
                elif fault in faults:
                    target = faults[fault]
                    inject = patch if len(target) == 1 else patch.object
                    resources.enter_context(inject(
                        *target, side_effect=OSError("fixture_delivery_failed"),
                    ))
                else:
                    archive_name = "run-00.json" if fault == "run_archive" else "delivery-00.json"
                    def fail_archive(archive, name, value):
                        if name == archive_name:
                            raise OSError("fixture_archive_failed")
                        return original_put(archive, name, value)
                    resources.enter_context(patch.object(ExperimentArchive, "put", fail_archive))
                result = self.coordinator.run()

                self.assertEqual("failure", result["stop_reason"])
                self.assertEqual("OSError", result["failure_type"])
                self.assertEqual([], result["unresolved_dispatches"])
                self.assertEqual([], result["runs"])
                self.assertEqual([{"index": 0, "job_id": "job-1"}], result["uncollected"])
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertEqual("retained", result["runtime_storage_cleanup"])
                runtime = self.folder / "artifacts" / result["runtime_storage_path"]
                self.assertTrue(runtime.is_dir())
                retention = json.loads((runtime / "retention.json").read_text(encoding="utf-8"))
                self.assertEqual("job_archive_incomplete", retention["reason"])
                self.assertEqual(["job-1"], retention["run_ids"])
                self.assertEqual(1, len(ScriptedServer.instances[-1].dispatched))
                self.assertFalse((self.coordinator.path / "intent-01.json").exists())

    def test_inconsistent_evidence_stops_before_second_dispatch(self):
        ScriptedServer.scenario = "evidence_mismatch"

        result = self.coordinator.run()

        self.assertEqual("evidence_mismatch", result["stop_reason"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertFalse((self.folder / "round" / "run-00.json").exists())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

    def test_normal_dispatch_rejects_wrong_job_before_archiving_or_counting_usage(self):
        with patch.object(ScriptedServer, "collect", return_value=make_bundle("wrong-job")):
            result = self.coordinator.run()

        self.assertEqual("evidence_mismatch", result["stop_reason"])
        self.assertEqual(0, result["usage"]["charged_tokens"])
        self.assertEqual(0, result["usage"]["http_attempts"])
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertEqual([{"index": 0, "job_id": "job-1"}], result["uncollected"])
        self.assertEqual("retained", result["runtime_storage_cleanup"])
        self.assertTrue((self.folder / "artifacts" / result["runtime_storage_path"]).is_dir())
        self.assertFalse((self.folder / "round" / "run-00.json").exists())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertEqual(1, len(ScriptedServer.instances[-1].dispatched))

    def test_protocol_failure_has_a_distinct_stop_reason(self):
        ScriptedServer.scenario = "protocol_failed"

        result = self.coordinator.run()

        self.assertEqual("protocol_failure", result["stop_reason"])
        self.assertEqual(1, result["executed_runs"])
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

    def test_failed_startup_preflight_is_counted_and_prevents_dispatch(self):
        ScriptedServer.scenario = "startup_preflight_failure"

        result = self.coordinator.run()

        self.assertEqual("preflight_evidence_mismatch", result["stop_reason"])
        self.assertEqual(1, result["preflights"])
        self.assertEqual([], ScriptedServer.instances[0].dispatched)
        self.assertTrue((self.folder / "round" / "preflight-00.json").is_file())

    def test_failed_run_preflight_prevents_current_and_later_dispatch(self):
        ScriptedServer.scenario = "post_dispatch_preflight_failure"

        result = self.coordinator.run()

        self.assertEqual("preflight_evidence_mismatch", result["stop_reason"])
        self.assertEqual(2, result["preflights"])
        self.assertEqual([], ScriptedServer.instances[0].dispatched)
        self.assertTrue((self.folder / "round" / "preflight-01.json").is_file())
        self.assertFalse((self.folder / "round" / "intent-00.json").exists())

    def test_source_drift_at_dispatch_stops_without_dispatch(self):
        self.source_mock.side_effect = [SOURCE, {**SOURCE, "revision": "d" * 40}]

        result = self.coordinator.run()

        self.assertEqual("source_identity_mismatch", result["stop_reason"])
        self.assertEqual([], ScriptedServer.instances[0].dispatched)
        self.assertFalse((self.folder / "round" / "intent-00.json").exists())

    def test_runtime_configuration_drift_stops_before_second_dispatch(self):
        configuration = self.manifest["reference_configuration"]
        self.configuration_mock.side_effect = [configuration, configuration, ValueError("drift")]

        result = self.coordinator.run()

        self.assertEqual("configuration_mismatch", result["stop_reason"])
        self.assertEqual(1, result["executed_runs"])
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())
        self.assertTrue((self.folder / "round" / "configuration-00.json").exists())

    def test_rejects_non_loopback_or_non_loopback_only_client(self):
        bad_clients = (
            SimpleNamespace(loopback_only=False, api_base="http://127.0.0.1:43123"),
            SimpleNamespace(loopback_only=True, api_base="http://localhost:43123"),
        )
        for client in bad_clients:
            with self.subTest(client=client):
                with self.assertRaises(ValueError):
                    StarReadinessCoordinator(
                        self.folder / "rejected",
                        adapters={"nonstream": SimpleNamespace(_get_client=lambda: client)},
                        manifest=self.manifest,
                        manifest_sha256=readiness_registration.digest(self.manifest),
                    )

    def test_live_mode_requires_live_manifest_and_strict_registered_endpoint(self):
        client = SimpleNamespace(
            loopback_only=False,
            provider_endpoint_only=True,
            api_base="https://chat.intern-ai.org.cn/api/v1/chat/completions",
            authorization="Bearer configured",
        )
        with self.assertRaisesRegex(ValueError, "live_authorization_required"):
            StarReadinessCoordinator(
                self.folder / "unauthorized-live",
                adapters={"nonstream": SimpleNamespace(_get_client=lambda: client)},
                manifest=self.manifest,
                manifest_sha256=readiness_registration.digest(self.manifest),
                evidence_kind="live",
            )

        live_manifest = readiness_registration.authorize_live_registration(
            self.manifest,
            expected_sha256=readiness_registration.digest(self.manifest),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-27",
        )
        coordinator = StarReadinessCoordinator(
            self.folder / "authorized-live",
            adapters={"nonstream": SimpleNamespace(_get_client=lambda: client)},
            manifest=live_manifest,
            manifest_sha256=readiness_registration.digest(live_manifest),
            evidence_kind="live",
        )
        self.assertEqual("live", coordinator.evidence_kind)

        client.api_base = "https://attacker.example/v1/chat/completions"
        with self.assertRaisesRegex(ValueError, "live_provider_invalid"):
            StarReadinessCoordinator(
                self.folder / "endpoint-drift",
                adapters={"nonstream": SimpleNamespace(_get_client=lambda: client)},
                manifest=live_manifest,
                manifest_sha256=readiness_registration.digest(live_manifest),
                evidence_kind="live",
            )

    def test_live_manifest_can_only_be_run_once_across_archive_directories(self):
        live_manifest = readiness_registration.authorize_live_registration(
            self.manifest,
            expected_sha256=readiness_registration.digest(self.manifest),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-27",
        )
        manifest_sha256 = readiness_registration.digest(live_manifest)
        client = SimpleNamespace(
            loopback_only=False,
            provider_endpoint_only=True,
            api_base="https://chat.intern-ai.org.cn/api/v1/chat/completions",
            authorization="Bearer fixture",
        )
        adapters = {"nonstream": SimpleNamespace(_get_client=lambda: client)}

        with patch(
            "showcase.star_readiness_coordinator.ARTIFACTS",
            self.folder / "claims",
        ):
            first = StarReadinessCoordinator(
                self.folder / "live-round-1",
                adapters=adapters,
                manifest=live_manifest,
                manifest_sha256=manifest_sha256,
                evidence_kind="live",
            )
            self.assertEqual("completed", first.run()["stop_reason"])
            dispatches_after_first = ScriptedServer.events.count("dispatch")

            second = StarReadinessCoordinator(
                self.folder / "live-round-2",
                adapters=adapters,
                manifest=live_manifest,
                manifest_sha256=manifest_sha256,
                evidence_kind="live",
            )
            second_result = second.run()

        self.assertEqual("failure", second_result["stop_reason"])
        self.assertEqual("ValueError", second_result["failure_type"])
        self.assertEqual(dispatches_after_first, ScriptedServer.events.count("dispatch"))
        self.assertTrue((self.folder / "live-round-2" / "result.json").is_file())

    def test_live_draft_cannot_be_consumed_again_with_new_source_or_authorization_date(self):
        live_manifest = readiness_registration.authorize_live_registration(
            self.manifest,
            expected_sha256=readiness_registration.digest(self.manifest),
            current_source=SOURCE,
            explicit_authorization=True,
            authorization_date="2026-10-27",
        )
        client = SimpleNamespace(
            loopback_only=False, provider_endpoint_only=True,
            api_base="https://chat.intern-ai.org.cn/api/v1/chat/completions",
            authorization="Bearer fixture",
        )
        adapters = {"nonstream": SimpleNamespace(_get_client=lambda: client)}
        with patch("showcase.star_readiness_coordinator.ARTIFACTS", self.folder / "claims"):
            first = StarReadinessCoordinator(
                self.folder / "first", adapters=adapters, manifest=live_manifest,
                manifest_sha256=readiness_registration.digest(live_manifest), evidence_kind="live",
            )
            self.assertEqual("completed", first.run()["stop_reason"])
            for field, value in (
                ("authorization_date", "2026-10-28"),
                ("source_identity", {**SOURCE, "revision": "e" * 40, "source_sha256": "f" * 64}),
            ):
                with self.subTest(field=field):
                    changed = {**live_manifest, field: value}
                    self.source_mock.return_value = changed["source_identity"]
                    second = StarReadinessCoordinator(
                        self.folder / field, adapters=adapters, manifest=changed,
                        manifest_sha256=readiness_registration.digest(changed), evidence_kind="live",
                    )
                    self.assertEqual("failure", second.run()["stop_reason"])
                    self.assertEqual(2, ScriptedServer.events.count("dispatch"))

    def test_historical_v2_hash_consumption_marker_is_still_honored(self):
        marker = self.folder / "artifacts" / "issue-97-prereg" / (
            readiness_registration.V2_LIVE_MANIFEST_SHA256 + ".consumed"
        )
        marker.parent.mkdir(parents=True)
        marker.write_text("historical consumption\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "already_consumed"):
            _claim_live_registration(readiness_registration.V2_LIVE_MANIFEST_SHA256,
                                     readiness_registration.V2_DRAFT_VERSION)
        self.assertEqual("historical consumption\n", marker.read_text(encoding="utf-8"))

    def test_future_draft_version_requires_separate_live_enablement(self):
        with self.assertRaisesRegex(ValueError, "live_draft_version_invalid"):
            _claim_live_registration("a" * 64, "issue-97-nonstream-draft-v5")
        self.assertFalse((self.folder / "artifacts" / "issue-97-prereg").exists())

    def test_v4_consumption_is_independent_of_v3_and_cannot_be_reset_by_changing_hash(self):
        _claim_live_registration("a" * 64, readiness_registration.V3_DRAFT_VERSION)
        _claim_live_registration("b" * 64, readiness_registration.V4_DRAFT_VERSION)

        markers = self.folder / "artifacts" / "issue-97-prereg"
        self.assertEqual("a" * 64 + "\n", (markers / (
            readiness_registration.V3_DRAFT_VERSION + ".consumed")).read_text(encoding="utf-8"))
        self.assertEqual("b" * 64 + "\n", (markers / (
            readiness_registration.V4_DRAFT_VERSION + ".consumed")).read_text(encoding="utf-8"))
        for manifest_hash in ("b" * 64, "c" * 64):
            with self.subTest(manifest_hash=manifest_hash):
                with self.assertRaisesRegex(ValueError, "already_consumed"):
                    _claim_live_registration(manifest_hash, readiness_registration.V4_DRAFT_VERSION)
        self.assertEqual(2, len(list(markers.glob("*.consumed"))))

    @unittest.skipUnless(
        os.environ.get("RUN_STAR_READINESS_DOCKER_INTEGRATION") == "1",
        "requires a Docker-enabled environment; set RUN_STAR_READINESS_DOCKER_INTEGRATION=1",
    )
    def test_real_experiment_server_runs_both_jobs_through_loopback_provider(self):
        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        adapters = provider.adapters()
        adapters["nonstream"]._get_client().loopback_only = True
        original_respond = provider.respond

        def respond(context):
            serialized = json.dumps(context, ensure_ascii=False)
            question_id = "multi-01" if "2 + 3" in serialized else "simple-01"
            provider.run_keys.setdefault(context["run_id"], question_id)
            answer = "5" if question_id == "multi-01" else "4"
            role = context["role"]
            if role == "explore":
                if question_id == "multi-01":
                    return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
                return {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                        "solution_candidate": answer}
            if role == "explore_polish":
                return {"solution_candidate": answer}
            if role == "planner":
                return {"version": 1, "steps": [{"step_id": "derive", "title": "Compute",
                        "objective": "Derive the registered result"}]}
            if role == "reasoner":
                claim = {"statement": answer, "label": "easy-verify"}
                if question_id == "multi-01":
                    code = "print(2 + 3)\n"
                    claim["tool_request"] = {"tool": "python_math", "arguments": {"code": code},
                                              "scope": "finite_computation",
                                              "expected_output": "5\n"}
                return {"argument": f"A direct derivation gives {answer}.", "claims": [claim],
                        "blocked": False}
            if role == "step_verifier":
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": ""}
            if role == "final_generator":
                return {"final_response": f"Final answer: {answer}"}
            if role == "whole_solution_verifier":
                return {"verdict": "ACCEPT", "reason": "The registered result is supported"}
            return original_respond(context)

        provider.respond = respond
        coordinator = StarReadinessCoordinator(
            self.folder / "integrated-round",
            adapters={"nonstream": adapters["nonstream"]},
            manifest=self.manifest,
            manifest_sha256=readiness_registration.digest(self.manifest),
        )

        with (patch("showcase.star_readiness_coordinator.ExperimentServer", ExperimentServer),
              patch("showcase.star_readiness_coordinator.validate_server_configuration",
                    validate_server_configuration),
              patch("showcase.star_readiness_coordinator.evaluate_delivery", evaluate_delivery)):
            result = coordinator.run()

        self.assertEqual("completed", result["stop_reason"], result)
        self.assertEqual(2, result["executed_runs"])
        self.assertEqual(2, len(provider.run_keys))
        self.assertGreater(len(provider.requests), 0)
        self.assertEqual(3, result["preflights"])
        self.assertEqual(3, len({
            json.loads(path.read_text(encoding="utf-8"))["identity"]["run_id"]
            for path in (self.folder / "integrated-round").glob("preflight-*.json")
        }))
        self.assertGreater(result["usage"]["logical_calls"], 0)
        self.assertGreater(result["usage"]["charged_tokens"], 0)
        self.assertEqual(1, result["usage"]["problem_tool_calls"])
        self.assertTrue((self.folder / "integrated-round" / "run-00.json").is_file())
        self.assertTrue((self.folder / "integrated-round" / "run-01.json").is_file())
        self.assertFalse(any(path.is_dir() for path in (self.folder / "integrated-round").iterdir()))

    def test_existing_archive_directory_is_rejected_without_overwriting(self):
        self.coordinator.path.mkdir()
        sentinel = self.coordinator.path / "keep.txt"
        sentinel.write_text("existing", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            self.coordinator.run()

        self.assertEqual("existing", sentinel.read_text(encoding="utf-8"))
        self.assertFalse((self.coordinator.path / "result.json").exists())
        self.assertEqual([], ScriptedServer.instances)


if __name__ == "__main__":
    unittest.main()
