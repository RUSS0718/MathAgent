"""Public plan and attempt history from real ProblemSpec Job transitions."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_faithful_s03_job import FEATURES, REPLIES, SPEC
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_traceback import PROPOSE, TRACE, report


class FaithfulS05HistoryTest(StarJobFixture, unittest.TestCase):
    def open_job(self, replies):
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES={**FEATURES, "context_pack": False},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12,
            ),
        )
        created = self.client.post(
            "/api/agent/jobs",
            json={
                "message": SPEC["original_problem"],
                "session_id": self.session,
                "solver_mode": "star_limited",
                "problem_spec": SPEC,
            },
            headers=self.headers(),
        )
        self.assertEqual(202, created.status_code, created.get_json())
        return created.get_json()["job_id"]

    @staticmethod
    def plan(version, step_id):
        return {
            "version": version,
            "steps": [{
                "step_id": step_id,
                "title": "Evaluate",
                "objective": "Prove the value",
                "obligation_ids": ["root:value"],
                "auxiliary_goal_ids": [],
            }],
        }

    @staticmethod
    def accepted_review():
        return {
            **REPLIES[3],
            "obligation_evidence": [{
                "obligation_id": "root:value",
                "evidence_category": "universal_proof",
                "claim_indexes": [0],
            }],
        }

    def test_public_history_contains_traceback_retry_attempt_from_real_job(self):
        claim = {"statement": "1+1=2", "label": "hard-verify"}
        job_id = self.open_job([
            REPLIES[0],
            self.plan(1, "prove-value"),
            report("first attempt", claims=[claim]),
            {**TRACE, "trace_back_to": 1},
            report("retried attempt", claims=[claim]),
            self.accepted_review(),
            REPLIES[4],
            ACCEPT,
        ])
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)

        progress = self.report(job_id)["solver"]["solver"]["progress"]

        self.assertEqual(1, progress["root_obligations"]["covered"])
        self.assertEqual([
            {"plan_version": 1, "attempt_index": 0, "status": "retried",
             "step_count": 1, "outcome": "trace_back"},
            {"plan_version": 1, "attempt_index": 1, "status": "current",
             "step_count": 1, "outcome": None},
        ], progress["plan_history"])
        self.assertNotIn("PRIVATE_ROOT_STATEMENT", str(progress))

    def test_public_history_contains_archived_plan_from_real_replan_job(self):
        claim = {"statement": "1+1=2", "label": "hard-verify"}
        decision = {
            **META_ABORT,
            "decision": "APPROVE_REPLAN",
            "reason_summary": "Old plan needs a fresh attempt",
            "forbidden_directions": ["old route"],
            "reusable_results": [],
        }
        job_id = self.open_job([
            REPLIES[0],
            self.plan(1, "prove-value"),
            report("first attempt", claims=[claim]),
            PROPOSE,
            decision,
            self.plan(2, "fresh-value"),
            report("replanned attempt", claims=[claim]),
            self.accepted_review(),
            REPLIES[4],
            ACCEPT,
        ])
        terminal = self.terminal(job_id)
        self.assertEqual("succeeded", terminal["status"], terminal)
        event_stream = self.client.get(
            f"/api/agent/jobs/{job_id}/events"
        ).get_data(as_text=True)
        events = [
            json.loads(line[6:]) for line in event_stream.splitlines()
            if line.startswith("data: ")
        ]
        self.assertTrue(any(
            event.get("solver_event_type") == "plan_archived"
            for event in events
        ))

        progress = self.report(job_id)["solver"]["solver"]["progress"]

        self.assertEqual(1, progress["root_obligations"]["covered"])
        self.assertEqual("satisfied", progress["root_obligations"]["items"][0]["status"])
        self.assertEqual([
            {"plan_version": 1, "attempt_index": 0, "status": "archived",
             "step_count": 1, "outcome": "replan"},
            {"plan_version": 2, "attempt_index": 1, "status": "current",
             "step_count": 1, "outcome": None},
        ], progress["plan_history"])
        self.assertNotIn("PRIVATE_ROOT_STATEMENT", str(progress))
