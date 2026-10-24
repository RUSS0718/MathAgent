"""ALIGN-04: fully received but protocol-illegal responses are known failures.

A provider response that arrived completely (finish_reason recorded, usage
known) but failed JSON/schema validation must never be reported as an
unknown remote outcome. It is a known protocol failure that bounded repair
may continue or that ends dispatch honestly; genuine network unknowns keep
their human-review gate with zero automatic resend.
"""

import json
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
        job_id = self.open_plan([NEED_PLAN, PLAN, RawProviderContent("not json"), VERDICT,
                                 {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual("safe", recovery["status"])
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("reasoner", failure["role"])
        self.assertEqual("invalid_json", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(CALL_USAGE, failure["usage"])
        self.assertEqual(0, failure["repair_attempts"])
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual("TERMINAL", job["result"]["solver"]["phase"])
        events = self.timeline(job_id)
        terminal = [event for event in events
                    if event.get("solver_event_type") == "protocol_failure_unrepaired"]
        self.assertEqual(1, len(terminal))
        self.assertEqual("reasoner", terminal[0]["role"])
        self.assertEqual("invalid_json", terminal[0]["error_category"])
        # The known failure ends dispatch: no automatic resend, no new request.
        self.assertEqual(3, len(self.outbound))
        budget = job["result"]["budget"]
        self.assertEqual(3, budget["http_attempts"])
        self.assertEqual(0, budget["unknown_attempts"])
        self.assertEqual({"prompt_tokens": 21, "completion_tokens": 9, "total_tokens": 30},
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

    def test_streamed_complete_schema_invalid_is_protocol_failure_never_unknown(self):
        # A complete streamed package that carries an uncalibrated probability
        # fails the strict provider schema: known protocol failure, no
        # normalization, no human unknown-review detour, zero further dispatch.
        uncalibrated = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                        "solution_candidate": "2", "confidence": 0.95}
        job_id = self.open_plan([uncalibrated, NEED_PLAN, PLAN, STEP, VERDICT,
                                 {"final_response": "2"}, ACCEPT])
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"], job)
        recovery = job["result"]["solver"]["recovery"]
        self.assertEqual([], recovery["unknown_calls"])
        self.assertEqual("safe", recovery["status"])
        self.assertEqual(1, len(recovery["protocol_failures"]))
        failure = recovery["protocol_failures"][0]
        self.assertEqual("explore", failure["role"])
        self.assertEqual("invalid_role_schema", failure["error_category"])
        self.assertEqual("stop", failure["finish_reason"])
        self.assertEqual(CALL_USAGE, failure["usage"])
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
        self.assertEqual(1, len(self.outbound))

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


if __name__ == "__main__":
    unittest.main()
