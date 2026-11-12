"""Public collaboration projections never expose private model reports."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.workbench_projection import collaboration_fields
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_challenge import CHALLENGE, HIDDEN_ARGUMENT, STEP_ACCEPT
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN


class WorkbenchContractTests(unittest.TestCase):
    def state(self):
        return {"run_id": "run-test", "run_salt": "salt", "plan_version": 1,
                "attempt_index": 0, "state_revision": 5, "current_step": "private-id",
                "plan": {"steps": [{"step_id": "private-id"}]}}

    def test_thread_and_message_identity(self):
        state = self.state()
        a = collaboration_fields({"event_id": "a", "type": "step_reviewed",
                                  "verdict": "CHALLENGE"}, state)
        b = collaboration_fields({"event_id": "b", "type": "challenge_replied",
                                  "argument": "PRIVATE"}, state)
        self.assertEqual(a["thread_id"], b["thread_id"])
        self.assertNotEqual(a["message_id"], b["message_id"])
        self.assertEqual(b["step_label"], "步骤 1")
        self.assertNotIn("PRIVATE", json.dumps(b))
        self.assertNotIn("private-id", json.dumps(b))
        state["attempt_index"] = 1
        self.assertNotEqual(a["thread_id"], collaboration_fields(
            {"event_id": "a", "type": "step_reviewed", "verdict": "CHALLENGE"}, state)["thread_id"])

    def test_rollback_reports_only_known_changes(self):
        state = self.state()
        state["attempt_index"] = 1
        state["failure_records"] = [{"kind": "trace_back", "attempt_index": 0,
                                     "archived_steps": {"private-id": {"report": "PRIVATE"}}}]
        result = collaboration_fields({"event_id": "c", "type": "trace_back_applied",
                                       "trace_back_to": 1}, state)
        self.assertEqual(result["changes"][0]["op"], "del")
        self.assertFalse(any(row["op"] == "add" for row in result["changes"]))
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_non_collaboration_has_no_payload(self):
        self.assertIsNone(collaboration_fields({"type": "model_response"}, self.state()))

    def test_meta_continue_closes_originating_attempt_thread(self):
        state = self.state()
        before = collaboration_fields({"event_id": "a", "type": "step_reviewed", "verdict": "CHALLENGE"}, state)
        state["attempt_index"] = 1
        after = collaboration_fields({"event_id": "b", "type": "meta_decided", "attempt_index": 1,
                                      "decision": {"decision": "CONTINUE"}}, state)
        self.assertEqual(before["thread_id"], after["thread_id"])
        self.assertEqual(after["thread_status"], "decided")


class WorkbenchPublicJobTests(StarJobFixture, unittest.TestCase):
    def test_authenticated_job_stream_has_shared_thread_and_real_report_answer(self):
        self.open_star([NEED_PLAN, PLAN, STEP, CHALLENGE,
                        {"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False},
                        STEP_ACCEPT, {"final_response": "2"}, ACCEPT],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        run_id = self.create_job()
        self.assertEqual(self.terminal(run_id)["status"], "succeeded")
        text = self.client.get(f"/api/agent/jobs/{run_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
        messages = [event["workbench"] for event in events if "workbench" in event]
        self.assertEqual([item["kind"] for item in messages], ["challenge", "reply"])
        self.assertEqual(messages[0]["thread_id"], messages[1]["thread_id"])
        self.assertNotIn(HIDDEN_ARGUMENT, text)
        final = next(event for event in events if event["type"] == "final_result")
        self.assertEqual(len(final["evidence_chain"]), 1)
        self.assertEqual(self.report(run_id)["answer"], "2")
