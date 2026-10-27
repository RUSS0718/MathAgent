"""Public behavior tests for the one-shot scripted #97 readiness batch."""

import hashlib
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from showcase import star_readiness_registration as readiness_registration
from showcase.star_acceptance import evaluate_delivery
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_configuration import validate_server_configuration
from showcase.star_readiness_coordinator import StarReadinessCoordinator
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

    def __init__(self, path, transport, adapter, policy, evidence_kind):
        self.path, self.transport, self.adapter = path, transport, adapter
        self.policy, self.evidence_kind = policy, evidence_kind
        self.dispatched = []
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

    def dispatch(self, question):
        type(self).events.append("dispatch")
        self.dispatched.append(question["prompt"])
        return f"job-{len(self.dispatched)}"

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
        self.assertEqual(["preflight", "dispatch", "preflight", "dispatch", "preflight"],
                         ScriptedServer.events)
        self.assertEqual(2, len(ScriptedServer.instances[0].provenance_calls))
        self.assertEqual(2, self.delivery_mock.call_count)
        self.assertEqual(34, result["usage"]["charged_tokens"])
        self.assertEqual(0, result["usage"]["reserved_tokens"])
        for name in ("intent-00.json", "run-00.json", "intent-01.json", "run-01.json",
                     "result.json", "hashes.json"):
            self.assertTrue((self.folder / "round" / name).is_file(), name)
        archived = json.loads((self.folder / "round" / "result.json").read_text(encoding="utf-8"))
        self.assertEqual("completed", archived["stop_reason"])

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

    def test_inconsistent_evidence_stops_before_second_dispatch(self):
        ScriptedServer.scenario = "evidence_mismatch"

        result = self.coordinator.run()

        self.assertEqual("evidence_mismatch", result["stop_reason"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertTrue((self.folder / "round" / "run-00.json").is_file())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

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

    def test_failed_post_dispatch_preflight_is_counted_and_current_job_is_collected(self):
        ScriptedServer.scenario = "post_dispatch_preflight_failure"

        result = self.coordinator.run()

        self.assertEqual("preflight_evidence_mismatch", result["stop_reason"])
        self.assertEqual(2, result["preflights"])
        self.assertEqual([QUESTION_TEXTS[0][3]], ScriptedServer.instances[0].dispatched)
        self.assertTrue((self.folder / "round" / "run-00.json").is_file())
        self.assertFalse((self.folder / "round" / "intent-01.json").exists())

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
        self.assertGreater(result["usage"]["logical_calls"], 0)
        self.assertGreater(result["usage"]["charged_tokens"], 0)
        self.assertEqual(1, result["usage"]["problem_tool_calls"])
        self.assertTrue((self.folder / "integrated-round" / "run-00.json").is_file())
        self.assertTrue((self.folder / "integrated-round" / "run-01.json").is_file())

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
