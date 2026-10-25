"""ALIGN-04: fully received but protocol-illegal responses are known failures.

A provider response that arrived completely (finish_reason recorded, usage
known) but failed JSON/schema validation must never be reported as an
unknown remote outcome. It is a known protocol failure that bounded repair
may continue or that ends dispatch honestly; genuine network unknowns keep
their human-review gate with zero automatic resend.
"""

import json
import os
import threading
import time
import unittest
import uuid

import requests

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import (ACCEPT, RawProviderContent, StarJobFixture,
                                        assert_no_uncalibrated_probability)
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

KNOWN_USAGE = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
CALL_USAGE = {**KNOWN_USAGE, "reasoning_tokens": None, "cached_tokens": None}
IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")
TWO_STEPS = {"version": 1, "steps": [*PLAN["steps"], {
    "step_id": "conclude", "title": "Conclude", "objective": "State the sum",
    "depends_on": ["sum"],
}]}


class StarProtocolFailureTest(StarJobFixture, unittest.TestCase):
    def open_plan(self, replies, *, limit=16, **config):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=limit, max_http_attempts=limit), **config)
        job_id = self.create_job()
        return job_id

    def timeline(self, job_id):
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return [json.loads(line[6:]) for line in stream.splitlines()
                if line.startswith("data: ")]

    def test_complete_invalid_json_is_a_known_protocol_failure_never_unknown(self):
        # The provider finished the reasoner response (finish_reason=stop, usage
        # known) but the body is not JSON. The Job must name the known protocol
        # failure; it must not list an unknown call or wait for human review.
        # The step executor owns one bounded format repair, so the run only ends
        # after the repair reply fails the same way.
        job_id = self.open_plan([NEED_PLAN, PLAN, RawProviderContent("not json"),
                                 RawProviderContent("still not json")])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("safe", recovery["status"])
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"reasoner"},
                         {item["role"] for item in recovery["protocol_failures"]})
        self.assertEqual({"invalid_json"},
                         {item["error_category"] for item in recovery["protocol_failures"]})
        self.assertEqual("stop", recovery["protocol_failures"][0]["finish_reason"])
        self.assertEqual(CALL_USAGE, recovery["protocol_failures"][0]["usage"])
        self.assertEqual(1, sum(item["repair_attempts"] for item in recovery["protocol_failures"]))
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual("TERMINAL", job["result"]["solver"]["phase"])
        events = self.timeline(job_id)
        terminal = [event for event in events
                    if event.get("solver_event_type") == "protocol_failure_unrepaired"]
        self.assertEqual(1, len(terminal))
        self.assertEqual("reasoner", terminal[0]["role"])
        self.assertEqual("invalid_json", terminal[0]["error_category"])
        # The known failure ends dispatch: no automatic resend, no new request.
        self.assertEqual(4, len(self.outbound))
        budget = job["result"]["budget"]
        self.assertEqual(4, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertEqual({"prompt_tokens": 28, "completion_tokens": 12, "total_tokens": 40},
                         budget["provider_known"])
        # The failed response body never reaches public outputs.
        public = json.dumps([job, self.report(job_id),
                             self.client.get(f"/api/runs/{job_id}/evidence").get_json()])
        self.assertNotIn("not json", public)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        recorded = [event for event in evidence["timeline"]
                    if event.get("solver_event_type") == "protocol_failure_unrepaired"]
        self.assertEqual(1, len(recorded))
        self.assertEqual("reasoner", recorded[0]["role"])
        self.assertEqual("invalid_json", recorded[0]["error_category"])

    def test_planner_invalid_json_repairs_once_with_new_identity_and_completes(self):
        job_id = self.open_plan([NEED_PLAN, RawProviderContent("not json"), PLAN, STEP,
                                 VERDICT, {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(7, len(self.outbound))
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("planner", failure["role"])
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(CALL_USAGE, failure["usage"])
        self.assertEqual(1, failure["repair_attempts"])
        # The repair is an independent new action: a second planner call with a
        # new identity, dispatched under the same original Run and deadline.
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(1, planners[1]["repair_attempt"])
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertAlmostEqual(1100, budget["deadline_at"] - budget["started_at"], delta=5)
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "plan_parse_failed"]
        self.assertEqual(1, len(repairs))

    def test_planner_repair_exhaustion_stops_dispatch_with_explicit_exit(self):
        job_id = self.open_plan([NEED_PLAN, RawProviderContent("{"),
                                 RawProviderContent("not json")])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual(["explore", "planner", "planner"],
                         [request["role"] for request in self.outbound])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"planner"}, {item["role"] for item in recovery["protocol_failures"]})
        self.assertEqual(1, sum(item["repair_attempts"] for item in recovery["protocol_failures"]))
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        budget = job["result"]["budget"]
        self.assertEqual(3, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_invalid_escape_in_complete_reply_is_parsed_and_continues(self):
        # Live ALIGN-10 batches (5f25cd6f/ad2329a6): the model's complete
        # reply embeds code whose strings carry single backslashes ("\\d",
        # Windows paths) — a well-formed JSON object except for invalid
        # escapes. The port rescues exactly this class by re-parsing with the
        # invalid escapes doubled; the strict schema still applies afterwards
        # and unfixable bodies remain known protocol failures.
        need_plan_bad_escape = (
            '{"assessment": "NEED_PLAN", "worked": [], "failed": [], '
            '"candidates": ["parity DP over \\d ranges and path C:\\Users"], '
            '"solution_candidate": null, "tool_request": null}')
        job_id = self.open_plan([RawProviderContent(need_plan_bad_escape), PLAN, STEP,
                                 VERDICT, {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        planner = next(request for request in self.outbound if request["role"] == "planner")
        self.assertEqual("NEED_PLAN", planner["exploration_findings"][0]["assessment"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["protocol_failures"])
        self.assertEqual([], recovery["unknown_calls"])

    def test_mixed_escapes_preserve_text_without_format_reask(self):
        raw = (r'{"assessment":"NEED_PLAN","worked":[],"failed":[],'
               r'"candidates":["regex \\d+ and path C:\Users"],'
               r'"solution_candidate":null,"tool_request":null}')
        job_id = self.open_plan([RawProviderContent(raw), PLAN, STEP, VERDICT,
                                 {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(6, len(self.outbound))
        planner = next(item for item in self.outbound if item["role"] == "planner")
        self.assertEqual([r"regex \d+ and path C:\Users"],
                         planner["exploration_findings"][0]["candidates"])
        self.assertEqual([], job["result"]["solver"]["recovery"]["protocol_failures"])
        self.assertEqual([], job["result"]["solver"]["recovery"]["unknown_calls"])
        self.assertEqual(60, job["result"]["budget"]["provider_known"]["total_tokens"])
        self.assertEqual("2", job["result"]["final_response"])
        # This limited fixture does not claim a full reference proof acceptance.
        self.assertEqual("needs_review", job["result"]["verification"]["acceptance"])
        self.assertEqual("same_artifact", job["result"]["verification"]["binding"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertIn("2", json.dumps(evidence))

    def test_explore_invalid_json_repairs_once_with_new_identity_and_completes(self):
        # Live ALIGN-10 batches repeatedly delivered complete explore replies
        # whose embedded code strings broke strict JSON (finish_reason=stop).
        # The explore entry now owns the same bounded format repair the planner
        # has: one fresh identity, same Run and deadline, honest exit if the
        # repair reply fails too.
        broken = RawProviderContent(
            '{"assessment": "NEED_PLAN", "worked": [], "failed": [], '
            '"candidates": ["parity DP"], "solution_candidate": null, '
            '"tool_request": null, "note": "unbalanced')
        job_id = self.open_plan([broken, NEED_PLAN, PLAN, STEP, VERDICT,
                                 {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        explores = [request for request in self.outbound if request["role"] == "explore"]
        self.assertEqual(2, len(explores), self.outbound)
        self.assertTrue(explores[1]["call_id"].endswith(":repair-1"), explores[1]["call_id"])
        self.assertIn("strict JSON", explores[1]["repair_instruction"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("safe", recovery["status"])
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("explore", failure["role"])
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(1, failure["repair_attempts"])
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "explore_parse_failed"]
        self.assertEqual(1, len(repairs))
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_reasoner_invalid_json_repairs_once_with_new_identity_and_completes(self):
        # ALIGN-10 round-2: the step executor gets the same gated bounded format
        # repair as the planner and the explore entry; a fresh reasoner identity
        # may salvage the step report instead of losing the whole run.
        job_id = self.open_plan([NEED_PLAN, PLAN, RawProviderContent("not json"), STEP,
                                 VERDICT, {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        reasoners = [request for request in self.outbound if request["role"] == "reasoner"]
        self.assertEqual(2, len(reasoners), self.outbound)
        self.assertTrue(reasoners[1]["call_id"].endswith(":repair-1"), reasoners[1]["call_id"])
        self.assertIn("strict JSON", reasoners[1]["repair_instruction"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("reasoner", failure["role"])
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual(1, failure["repair_attempts"])
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "reasoner_parse_failed"]
        self.assertEqual(1, len(repairs))
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_step_verifier_invalid_json_repairs_once_with_new_identity_and_completes(self):
        job_id = self.open_plan([NEED_PLAN, PLAN, STEP, RawProviderContent("not json"),
                                 VERDICT, {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        verifiers = [request for request in self.outbound if request["role"] == "step_verifier"]
        self.assertEqual(2, len(verifiers), self.outbound)
        self.assertTrue(verifiers[1]["call_id"].endswith(":repair-1"), verifiers[1]["call_id"])
        self.assertIn("strict JSON", verifiers[1]["repair_instruction"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("step_verifier", recovery["protocol_failures"][0]["role"])
        self.assertEqual(1, recovery["protocol_failures"][0]["repair_attempts"])
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "step_review_parse_failed"]
        self.assertEqual(1, len(repairs))
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_final_whole_review_invalid_json_repairs_once_with_new_identity(self):
        # Live ALIGN-10 batch ...-6a1828b2 died here: the whole reviewer echoed
        # the schema definition instead of a verdict. The finalization review
        # now owns one bounded repair with a fresh identity.
        job_id = self.open_plan([NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"},
                                 RawProviderContent("not json"), ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        reviews = [request for request in self.outbound
                   if request["role"] == "whole_solution_verifier"]
        self.assertEqual(2, len(reviews), self.outbound)
        self.assertTrue(reviews[1]["call_id"].endswith(":repair-1"), reviews[1]["call_id"])
        self.assertIn("never the schema definition", reviews[1]["repair_instruction"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("whole_solution_verifier", recovery["protocol_failures"][0]["role"])
        self.assertEqual(1, recovery["protocol_failures"][0]["repair_attempts"])
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "finalization_parse_failed"]
        self.assertEqual(1, len(repairs))
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertEqual("same_artifact", self.report(job_id)["checks"]["binding"])

    def test_explore_fast_path_whole_review_invalid_repairs_once_and_completes(self):
        from tests.star_product_support import POLISH, SOLVED

        job_id = self.open_plan([SOLVED, POLISH, RawProviderContent("not json"), ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        reviews = [request for request in self.outbound
                   if request["role"] == "whole_solution_verifier"]
        self.assertEqual(2, len(reviews), self.outbound)
        self.assertTrue(reviews[1]["call_id"].endswith(":repair-1"), reviews[1]["call_id"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("whole_solution_verifier", recovery["protocol_failures"][0]["role"])
        self.assertEqual(1, recovery["protocol_failures"][0]["repair_attempts"])
        events = self.timeline(job_id)
        repairs = [event for event in events
                   if event.get("solver_event_type") == "solution_review_parse_failed"]
        self.assertEqual(1, len(repairs))
        budget = job["result"]["budget"]
        self.assertEqual(4, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_explore_repair_exhaustion_stops_dispatch_with_explicit_exit(self):
        job_id = self.open_plan([RawProviderContent("{"), RawProviderContent("not json")])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual(["explore", "explore"],
                         [request["role"] for request in self.outbound])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"explore"}, {item["role"] for item in recovery["protocol_failures"]})
        self.assertEqual(1, sum(item["repair_attempts"] for item in recovery["protocol_failures"]))
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        budget = job["result"]["budget"]
        self.assertEqual(2, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_streamed_complete_schema_invalid_is_protocol_failure_never_unknown(self):
        # A complete streamed package that carries an uncalibrated probability
        # fails the strict provider schema: known protocol failure, no
        # normalization, no human unknown-review detour. The explore entry now
        # owns one bounded format repair, so the invalid reply is followed by a
        # single repair dispatch; when that reply fails the same way the run
        # still ends honestly with zero further dispatch.
        uncalibrated = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                        "solution_candidate": "2", "confidence": 0.95}
        job_id = self.open_plan([uncalibrated, uncalibrated, NEED_PLAN, PLAN, STEP, VERDICT,
                                 {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"explore"}, {item["role"] for item in recovery["protocol_failures"]})
        self.assertEqual({"invalid_role_schema"},
                         {item["error_category"] for item in recovery["protocol_failures"]})
        self.assertEqual("stop", recovery["protocol_failures"][0]["finish_reason"])
        self.assertEqual(CALL_USAGE, recovery["protocol_failures"][0]["usage"])
        self.assertEqual(1, sum(item["repair_attempts"] for item in recovery["protocol_failures"]))
        # The streamed complete package never became a normalized candidate.
        self.assertEqual([], job["result"]["solver"]["candidate_history"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        dumps = json.dumps([job, self.report(job_id),
                            self.client.get(f"/api/runs/{job_id}/evidence").get_json()])
        assert_no_uncalibrated_probability(self, stream, dumps)
        # The run ended honestly; resuming it is refused without any new request.
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        self.assertEqual(2, len(self.outbound))

    def test_unknown_outcome_keeps_human_gate_and_zero_automatic_resend(self):
        # The boundary stays closed: a mid-call network timeout remains an
        # unknown outcome needing an explicit new-identity decision.
        job_id = self.open_plan([NEED_PLAN, PLAN, requests.Timeout("connection lost"), STEP,
                                 VERDICT, {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("needs_review", recovery["status"])
        self.assertEqual(1, len(recovery["unknown_calls"]))
        self.assertEqual([], recovery["protocol_failures"])
        old_id = recovery["unknown_calls"][0]["call_id"]
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        self.assertEqual("star_retry_decision_required", rejected.get_json()["error"])
        self.assertEqual(3, len(self.outbound))
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={"retry_call": {
            "call_id": old_id, "new_call_id": str(uuid.uuid4())}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(7, len(self.outbound))
        budget = final["result"]["budget"]
        self.assertEqual(1, budget["unknown_attempts"])
        self.assertEqual(job["result"]["budget"]["deadline_at"], budget["deadline_at"])


class StarProtocolFenceTest(StarJobFixture, unittest.TestCase):
    """Repair-window fences: budget exhaustion, deadline and cancel stop dispatch."""

    def open_plan(self, replies, **limits):
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(**limits))
        return self.create_job()

    def test_model_budget_exhaustion_stops_protocol_repair_without_dispatch(self):
        # The repair bound is also bounded by the shared ledger: once the model
        # budget is spent, the repair attempt stops before any new dispatch.
        job_id = self.open_plan([NEED_PLAN, RawProviderContent("not json"), PLAN, STEP,
                                 VERDICT, {"final_response": "2"}, ACCEPT],
                                max_model_calls=2, max_http_attempts=2)
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual(2, len(self.outbound))
        self.assertEqual(["explore", "planner"], [r["role"] for r in self.outbound])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("safe", recovery["status"])
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("planner", recovery["protocol_failures"][0]["role"])
        self.assertEqual(0, recovery["protocol_failures"][0]["repair_attempts"])
        self.assertEqual("partial_budget_exhausted", job["result"]["solver"]["status"])
        self.assertEqual(2, job["result"]["budget"]["http_attempts"])
        self.assertEqual(2, job["result"]["budget"]["logical_calls"])
        self.assertIn("Hard budget exhausted", job["result"]["final_response"])

    def test_expired_deadline_stops_protocol_path_without_further_dispatch(self):
        # A response that straddles the deadline is discarded by the S3 control
        # fence before it can be parsed: no math commit and no re-dispatch, the
        # ledger keeps the real usage, and the original deadline is not reset.
        def slow_invalid(_context):
            time.sleep(1.1)
            return RawProviderContent("not json")

        job_id = self.open_plan([NEED_PLAN, slow_invalid, PLAN, STEP, VERDICT,
                                 {"final_response": "2"}, ACCEPT],
                                max_model_calls=8, max_http_attempts=8,
                                max_runtime_seconds=1)
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("run_deadline_exhausted", job["error"])
        self.assertEqual(2, len(self.outbound))
        self.assertEqual(["explore", "planner"], [r["role"] for r in self.outbound])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual(1, len(recovery["unknown_calls"]))
        self.assertEqual("planner", recovery["unknown_calls"][0]["role"])
        self.assertEqual([], recovery["protocol_failures"])
        rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, rejected.status_code)
        self.assertEqual(2, len(self.outbound))
        budget = job["result"]["budget"]
        self.assertAlmostEqual(1, budget["deadline_at"] - budget["started_at"], delta=0.2)
        self.assertIsNotNone(budget["ended_at"])
        self.assertEqual({"prompt_tokens": 14, "completion_tokens": 6, "total_tokens": 20},
                         budget["provider_known"])
        self.assertEqual(0, budget["unknown_attempts"])

    def test_cancel_during_protocol_repair_stops_math_and_preserves_ledger(self):
        # Cancel lands while the repair response is in flight: the S3 control
        # fence discards it like any late result, nothing further is
        # dispatched, and the frozen ledger keeps the original deadline.
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def paused_repair(_context):
            entered.set()
            release.wait(5)
            return PLAN

        job_id = self.open_plan([NEED_PLAN, RawProviderContent("not json"), paused_repair,
                                 STEP, VERDICT, {"final_response": "2"}, ACCEPT],
                                max_model_calls=16, max_http_attempts=16)
        self.assertTrue(entered.wait(5))
        self.cancel(job_id)
        release.set()
        job = self.terminal(job_id)
        self.assertEqual("canceled", job["status"], job)
        self.assertEqual(3, len(self.outbound))
        time.sleep(0.2)
        self.assertEqual(3, len(self.outbound))
        budget = job["result"]["budget"]
        self.assertIsNotNone(budget["ended_at"])
        self.assertAlmostEqual(1100, budget["deadline_at"] - budget["started_at"], delta=5)
        self.assertEqual(3, budget["http_attempts"])
        self.assertEqual({"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
                         budget["provider_known"])
        recovery = job["result"]["solver"]["recovery"]
        # The original failure stays a known protocol failure; the in-flight
        # repair response was discarded by the cancel fence as an unknown.
        self.assertEqual(1, len(recovery["protocol_failures"]))
        self.assertEqual("planner", recovery["protocol_failures"][0]["role"])
        self.assertEqual(1, recovery["protocol_failures"][0]["repair_attempts"])
        self.assertEqual(1, len(recovery["unknown_calls"]))
        self.assertEqual("planner", recovery["unknown_calls"][0]["role"])
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, response.status_code)


@unittest.skipUnless(IMAGE, "requires independently validated local Docker image ID")
class StarFullReferenceProtocolFailureTest(StarJobFixture, unittest.TestCase):
    """ALIGN-AC-12/13 hold at the full reference preset with real isolated readiness."""

    def open_full(self, replies):
        self.open_star(replies, SHOWCASE_STAR_FULL_ENABLED=True,
                       SHOWCASE_STAR_PYTHON_IMAGE_ID=IMAGE)

    def submit(self):
        return self.client.post("/api/agent/jobs", json={
            "message": "Factor x^2-1.", "session_id": self.session,
            "solver_mode": "star_reference",
        }, headers=self.headers())

    def test_full_reference_reasoner_invalid_json_is_known_failure_and_ends_dispatch(self):
        # The reasoner owns one bounded format repair, so the honest end needs
        # the repair reply to fail the same way (ALIGN-10 round 2).
        self.open_full([NEED_PLAN, TWO_STEPS, STEP, VERDICT,
                        RawProviderContent("not json"), RawProviderContent("still not json")])
        job_id = self.submit().get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("safe", recovery["status"])
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(2, len(recovery["protocol_failures"]))
        self.assertEqual({"reasoner"}, {item["role"] for item in recovery["protocol_failures"]})
        failure = recovery["protocol_failures"][0]
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(CALL_USAGE, failure["usage"])
        self.assertEqual(1, sum(item["repair_attempts"] for item in recovery["protocol_failures"]))
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual("protocol_failure_unrepaired", job["error"])
        self.assertEqual(6, len(self.outbound))
        self.assertEqual(6, job["result"]["budget"]["http_attempts"])
        self.assertEqual(0, job["result"]["budget"]["unknown_attempts"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        terminal = [json.loads(line[6:]) for line in stream.splitlines()
                    if line.startswith("data: ")
                    and json.loads(line[6:]).get("solver_event_type") == "protocol_failure_unrepaired"]
        self.assertEqual(1, len(terminal))
        self.assertEqual("reasoner", terminal[0]["role"])
        self.assertEqual("invalid_json", terminal[0]["error_category"])

    def test_full_reference_planner_invalid_json_repairs_with_new_identity(self):
        self.open_full([NEED_PLAN, RawProviderContent("not json"), PLAN, STEP, VERDICT,
                        {"final_response": "x^2-1=(x-1)(x+1)."}, ACCEPT])
        job_id = self.submit().get_json()["job_id"]
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(7, len(self.outbound))
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("planner", failure["role"])
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual(1, failure["repair_attempts"])
        planners = [request for request in self.outbound if request["role"] == "planner"]
        self.assertEqual(2, len(planners))
        self.assertEqual(1, planners[1]["repair_attempt"])
        budget = job["result"]["budget"]
        self.assertEqual(7, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertEqual(48, budget["limits"]["max_model_calls"])
        self.assertAlmostEqual(1100, budget["deadline_at"] - budget["started_at"], delta=5)
        self.assertEqual("completed_llm_reviewed", job["result"]["solver"]["status"])


if __name__ == "__main__":
    unittest.main()
