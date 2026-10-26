"""Spec #87 simulated matrix via real HTTP, public Job, SQLite/S3 and Docker."""

import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from showcase.star_experiment import ExperimentCoordinator
from showcase.star_experiment_gates import qualify
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.star_experiment_registration import E1, registration
from showcase.star_experiment_scoring import admit
from showcase.star_experiment_server import ExperimentServer
from tests.star_experiment_support import LoopbackProvider, independent_review, saved_batch


class ExperimentPublicJobTest(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.folder = Path(folder)
        saved_batch(self.folder / "e0")
        self.qualification = qualify(self.folder / "e0", original_runner_version="fixture-v0", evidence_kind="scripted")
        self.assertTrue(self.qualification.valid, self.qualification.report)

    def execute(self, scenario="matrix", reviewer=independent_review):
        self.provider = LoopbackProvider(scenario)
        self.addCleanup(self.provider.close)
        coordinator = ExperimentCoordinator(self.folder / "round", adapters=self.provider.adapters(),
                                            qualification=self.qualification)
        self.coordinator = coordinator
        return coordinator.run(reviewer)

    def test_first_unknown_stops_all_later_dispatch_and_preserves_reservation(self):
        called = []
        result = self.execute("unknown", reviewer=lambda *args: called.append(args))
        self.assertEqual("unknown_outcome", result["stop_reason"], result)
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual(1, len(self.provider.requests), "No automatic resend or next Run")
        self.assertGreater(result["usage"]["reserved_tokens"], 8192)
        self.assertEqual(1, result["usage"]["unresolved_attempts"])
        self.assertIsNone(result["cost"])
        self.assertEqual(3, result["preflights"])
        self.assertEqual([], called, "An unknown stops immediately without waiting for mathematical review")

    def test_matrix_runs_all_ten_in_order_and_has_natural_nonfastpath(self):
        result = self.execute()
        self.assertEqual("completed", result["stop_reason"], result)
        self.assertEqual(10, result["executed_runs"])
        self.assertEqual(12, result["preflights"])
        self.assertEqual(36, result["usage"]["logical_calls"])
        self.assertEqual(36, len(self.provider.requests))
        self.assertEqual(2, result["usage"]["tool_calls"])
        self.assertEqual(14, result["tools_including_environment"])
        self.assertTrue(result["natural_nonfastpath"])
        self.assertEqual(["multiply", "multiply", "fractions", "fractions",
                          "digit_cancel", "sharp", "partitions", "digit_cancel", "sharp", "partitions"],
                         list(self.provider.run_keys.values()))
        for index, record in enumerate(result["runs"]):
            bundle = json.loads((self.folder / "round" / f"run-{index:02d}.json").read_text(encoding="utf-8"))
            budget = bundle["report"]["budget"]
            for field in ("max_model_calls", "max_http_attempts", "max_tool_calls", "max_tokens", "max_runtime_seconds"):
                self.assertEqual(record["entry"]["limits"][field], budget["limits"][field])
            self.assertEqual(bundle["report"]["semantics"], bundle["evidence"]["semantics"])
        self.assertTrue(all(r["score"]["e1_gate"] for r in result["runs"][:4]))
        messages = json.dumps([w["messages"] for w, c in self.provider.requests if c["role"] == "explore"], ensure_ascii=False)
        self.assertNotIn("deterministic-test-reviewer", messages)
        self.assertNotIn("190569291", messages)
        before = (self.folder / "round/result.json").read_bytes()
        with self.assertRaises(FileExistsError):
            ExperimentCoordinator(self.folder / "round", adapters=self.provider.adapters(),
                                  qualification=self.qualification).run(independent_review)
        self.assertEqual(before, (self.folder / "round/result.json").read_bytes())
        hashes = json.loads((self.folder / "round/hashes.json").read_text(encoding="utf-8"))
        for name, expected in hashes.items():
            self.assertEqual(expected, hashlib.sha256((self.folder / "round" / name).read_bytes()).hexdigest())
        for wire, _ in self.provider.requests:
            self.assertEqual("intern-s2", wire["model"])
            self.assertEqual(8192, wire["max_tokens"])
            self.assertEqual(.2, wire["temperature"])
            self.assertTrue(wire["thinking_mode"])

    def test_e1_known_token_efficiency_failure_stops_e2(self):
        result = self.execute("inefficient")
        self.assertEqual("e1_gate_failed", result["stop_reason"], result)
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual(3, len(self.provider.requests))
        self.assertTrue(result["runs"][0]["score"]["flow_complete"])

    def test_e2_mathematical_reject_is_honest_unsolved_not_transport_failure(self):
        result = self.execute("math_reject")
        self.assertEqual("e2_gate_failed", result["stop_reason"], result)
        self.assertEqual(8, result["executed_runs"], "Stop as soon as a class can no longer meet its gate")
        rejected = [r for r in result["runs"] if r["entry"]["question"] == "digit_cancel"]
        self.assertTrue(all(not r["score"]["flow_complete"] and not r["score"]["unknown"] for r in rejected))
        self.assertTrue(all(not r["score"]["protocol_defect"] for r in rejected))

    def test_natural_all_fastpath_does_not_claim_nonfastpath(self):
        result = self.execute("all_fast")
        self.assertEqual("completed", result["stop_reason"], result)
        self.assertFalse(result["natural_nonfastpath"])
        self.assertEqual("not_covered", result["mechanisms"]["live_replan"])

    def test_invalid_independent_review_cannot_pass_e1(self):
        def wrong_binding(key, question, bundle):
            review = independent_review(key, question, bundle)
            review["answer_sha256"] = "another-answer"
            return review
        result = self.execute(reviewer=wrong_binding)
        self.assertEqual("e1_gate_failed", result["stop_reason"], result)
        self.assertEqual("undecided", result["runs"][0]["score"]["mathematics"])

    def test_modified_qualification_refuses_before_any_provider_or_preflight(self):
        self.qualification.report["skips"] = 1
        result = self.execute()
        self.assertEqual(0, len(self.provider.requests))
        self.assertEqual(0, result["preflights"])
        self.assertNotEqual("completed", result["stop_reason"])

    def test_cancel_while_independent_review_waits_stops_waiting(self):
        completed = threading.Event()

        def waiting_review(key, question, bundle):
            threading.Timer(.05, self.coordinator.cancel).start()
            time.sleep(.6)
            completed.set()
            return independent_review(key, question, bundle)

        result = self.execute(reviewer=waiting_review)
        self.assertEqual("canceled", result["stop_reason"], result)
        self.assertFalse(completed.is_set(), "Review waiting must honor the round cancellation")
        self.assertEqual(1, result["executed_runs"])

    def test_known_protocol_defect_stops_after_bounded_repair_without_unknown(self):
        result = self.execute("protocol")
        self.assertEqual("product_protocol_defect", result["stop_reason"], result)
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual(2, result["usage"]["logical_calls"])
        self.assertEqual(2, result["usage"]["http_attempts"])
        self.assertEqual(0, result["usage"]["unknown_attempts"])

    def test_review_failure_keeps_run_and_consumption_in_terminal_archive(self):
        def broken_review(*args):
            raise RuntimeError("private detail must not enter public failure")
        result = self.execute(reviewer=broken_review)
        self.assertEqual("experiment_defect:ValueError", result["stop_reason"], result)
        self.assertEqual(1, result["executed_runs"])
        self.assertEqual(3, result["usage"]["logical_calls"])
        self.assertTrue((self.folder / "round/run-00.json").exists())
        self.assertNotIn("private detail", (self.folder / "round/failure.json").read_text())


class RoundAdmissionTest(unittest.TestCase):
    def test_full_next_run_envelope_counts_charged_unknown_and_all_dimensions(self):
        from showcase.star_experiment_registration import E2
        used = dict(logical_calls=0, http_attempts=0, tool_calls=0, charged_tokens=0)
        for field, value in [("logical_calls", 85), ("http_attempts", 113),
                             ("tool_calls", 20), ("charged_tokens", 458753)]:
            with self.subTest(field=field):
                self.assertEqual("round_" + field + "_insufficient", admit({**used, field: value}, E2, 0, 2))
        self.assertEqual("round_deadline_exhausted", admit(used, E2, 4800, 2))
        self.assertEqual("environment_budget_exhausted", admit(used, E2, 0, 12))
        self.assertIsNone(admit(used, E2, 4799, 2))  # Run gets only the remaining second in S3.


class ExperimentDeadlineJobTest(unittest.TestCase):
    def test_per_run_total_deadline_starts_before_its_job_preflight(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        provider = LoopbackProvider("all_fast")
        self.addCleanup(provider.close)
        policy = ExperimentRunPolicy(time.time() + 3600)
        server = ExperimentServer(Path(folder), "nonstream", provider.adapters()["nonstream"], policy, "scripted")
        self.addCleanup(server.close)
        started = time.time()
        policy.prepare(E1)
        job_id = server.dispatch(registration()["questions"]["multiply"])
        bundle = server.collect(job_id, policy.deadline_at)
        self.assertEqual("succeeded", bundle["job"]["status"])
        self.assertLessEqual(bundle["report"]["budget"]["deadline_at"], started + 300,
                             "Per-Run total limit must include its Job preflight")
        self.assertEqual(300, bundle["report"]["budget"]["limits"]["max_runtime_seconds"])

    def test_problem_tools_are_separate_from_environment_preflights(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        policy = ExperimentRunPolicy(time.time() + 60)
        from showcase.star_experiment_registration import E2
        policy.prepare(E2)
        server = ExperimentServer(Path(folder), "nonstream", provider.adapters()["nonstream"], policy, "scripted")
        self.addCleanup(server.close)
        job_id = server.dispatch(registration()["questions"]["digit_cancel"])
        bundle = server.collect(job_id, policy.deadline_at)
        self.assertEqual("succeeded", bundle["job"]["status"])
        self.assertEqual(1, bundle["report"]["budget"]["tool_calls"], "Real problem computation belongs to S3")
        self.assertEqual(1, server.preflight()["budget"]["tool_calls"], "Environment probe has its own S3 identity")
        self.assertEqual("docker_isolated", bundle["job"]["result"]["tool_results"][0]["receipt"]["source"])

    def test_s3_deadline_never_exceeds_round_absolute_deadline_after_preflight(self):
        class SlowAdmissionPolicy(ExperimentRunPolicy):
            def remaining(self):
                remaining = super().remaining()
                time.sleep(.02)  # Model scheduling delay between reading remaining time and S3 admission.
                return remaining

        folder = self.enterContext(tempfile.TemporaryDirectory())
        provider = LoopbackProvider("all_fast")
        self.addCleanup(provider.close)
        policy = SlowAdmissionPolicy(time.time() + 30)
        policy.prepare(E1)
        server = ExperimentServer(Path(folder), "nonstream", provider.adapters()["nonstream"], policy, "scripted")
        self.addCleanup(server.close)
        job_id = server.dispatch(registration()["questions"]["multiply"])
        bundle = server.collect(job_id, policy.deadline_at)
        self.assertEqual("succeeded", bundle["job"]["status"])
        self.assertLessEqual(bundle["report"]["budget"]["deadline_at"], policy.deadline_at,
                             "Preflight and admission delay must not extend the round deadline")
        self.assertLessEqual(server.preflight()["budget"]["deadline_at"], policy.deadline_at,
                             "Environment preflight must also retain the round absolute deadline")
