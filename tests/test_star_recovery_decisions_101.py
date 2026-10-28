"""F09: public Jobs require a committed, current Meta ruling, including on replay."""

import json
import unittest
from copy import deepcopy
from unittest.mock import patch

import requests

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import SolverHarness
from showcase.tools import ToolRegistry
from tests.star_product_support import StarJobFixture
from tests.test_star_product_guidance_consumption import REPLIES
from tests.test_star_product_replan_decision import RULING_ABORT, RULING_FIRST, star_replier
from tests.test_star_product_tools import FEATURES, VERDICT


class RecoveryDecision101Test(StarJobFixture, unittest.TestCase):
    def run_ruling(self, change, *, audit=False, replan=False, change_history=False):
        """Inject a damaged checkpoint at the public event boundary, then observe Job."""
        original = SolverHarness.commit_event
        injected = []

        def commit(harness, run_id, *, expected_revision, event, state_updates=None):
            kind = "meta_decided" if replan else "meta_guidance_decided"
            key = "meta_decision" if replan else "meta_guidance_decision"
            if event["type"] == kind and not injected:
                updates = deepcopy(state_updates)
                change(updates[key], expected_revision)
                if change_history:
                    change(updates["meta_interventions"][-1], expected_revision)
                injected.append(expected_revision + 1)
                result = original(harness, run_id, expected_revision=expected_revision,
                                  event=event, state_updates=updates)
                if audit:
                    result = original(harness, run_id, expected_revision=result["state_revision"],
                                      event={"event_id": "recovery-audit-101", "type": "call_audit"})
                return result
            result = original(harness, run_id, expected_revision=expected_revision,
                              event=event, state_updates=state_updates)
            return result

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        rulings = {1: RULING_FIRST}
        replier = star_replier(rulings, {("a2", 0)})

        def answer(context):
            value = replier(context)
            if context["role"] == "meta" and context.get("guidance_request") is None:
                rulings[1] = RULING_ABORT
            return value

        replies = [answer] * 64 if replan else list(REPLIES)
        self.open_star(replies, SHOWCASE_STAR_REGISTRY=registry,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=28, max_http_attempts=28))
        with patch.object(SolverHarness, "commit_event", commit):
            job_id = self.create_job()
            final = self.terminal(job_id)
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        events = [json.loads(line[6:]) for line in stream.splitlines()
                  if line.startswith("data: ")]
        self.assertEqual(1, len(injected))
        return job_id, final, events

    def test_missing_decision_revision_cannot_authorize_traceback(self):
        _, final, events = self.run_ruling(lambda decision, _: decision.pop("decided_at_revision"))
        self.assertEqual([], [event for event in events
                              if event.get("solver_event_type") == "trace_back_applied"])
        self.assertEqual("failed", final["status"])
        self.assertEqual(6, final["result"]["budget"]["http_attempts"])

    def assert_rejected(self, change, **options):
        _, final, events = self.run_ruling(change, **options)
        self.assertEqual([], [event for event in events if event.get("solver_event_type")
                              in {"trace_back_applied", "plan_archived", "plan_replaced"}])
        self.assertEqual("failed", final["status"])

    def test_future_revision_cannot_authorize_traceback(self):
        self.assert_rejected(lambda decision, rev: decision.update(decided_at_revision=rev + 2),
                             change_history=True)

    def test_non_decision_revision_cannot_authorize_traceback(self):
        self.assert_rejected(lambda decision, rev: decision.update(decided_at_revision=rev),
                             change_history=True)

    def test_changed_target_cannot_borrow_a_genuine_ruling_revision(self):
        self.assert_rejected(lambda decision, _: decision.update(trace_back_to=2))

    def test_boolean_revision_cannot_authorize_traceback(self):
        self.assert_rejected(lambda decision, _: decision.update(decided_at_revision=True))

    def test_forged_approval_cannot_archive_or_dispatch_replacement_plan(self):
        self.assert_rejected(lambda decision, _: decision.pop("decided_at_revision"), replan=True)
        self.assertEqual(1, sum(item["role"] == "planner" for item in self.outbound))

    def test_audit_after_current_ruling_still_allows_single_consumption(self):
        _, final, events = self.run_ruling(lambda *_: None, audit=True)
        self.assertEqual("succeeded", final["status"], final)
        applied = [event for event in events
                   if event.get("solver_event_type") == "trace_back_applied"]
        self.assertEqual([(1, "meta_guidance"), (2, "meta")],
                         [(event["trace_back_to"], event["triggered_by"]) for event in applied])
        self.assertEqual(2, sum(item["role"] == "meta" for item in self.outbound))

    def test_unknown_meta_after_saved_progress_requires_review_without_redispatch(self):
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        self.open_star([*REPLIES[:3], VERDICT, REPLIES[4], requests.Timeout("unknown Meta")],
                       SHOWCASE_STAR_REGISTRY=registry,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=28, max_http_attempts=28),
                       SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True})
        job_id = self.create_job()
        before = self.terminal(job_id)
        self.assertEqual("failed", before["status"])
        meta = self.outbound[-1]
        self.assertEqual("meta", meta["role"])
        self.assertEqual({"current_step": "s2", "phase": "STEP_VERIFY"}, meta["progress"])
        self.assertEqual([], meta["allowed_tools"])
        recovery = before["result"]["solver"]["recovery"]
        self.assertEqual("needs_review", recovery["status"])
        self.assertEqual("meta", recovery["unknown_calls"][0]["role"])
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                    headers=self.headers())
        self.assertEqual(409, response.status_code)
        after = self.job(job_id)
        self.assertEqual(before["result"]["budget"], after["result"]["budget"])
        self.assertEqual(recovery, after["result"]["solver"]["recovery"])
        self.assertEqual(6, len(self.outbound))


if __name__ == "__main__":
    unittest.main()
