"""Continuous Challenge evidence through the public STAR Job contract."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT

HIDDEN_ARGUMENT = "private hidden reasoning must stay out of public events"
CHALLENGE = {
    "goal_gate": "PARTIAL",
    "logic_gate": "UNCERTAIN",
    "verdict": "CHALLENGE",
    "objection": "Check the sign of the boundary term.",
}
META_ABORT = {
    "decision": "ABORT",
    "reason_summary": "The step did not resolve the boundary term.",
    "plan_summary": "",
    "forbidden_directions": [],
    "reusable_results": [],
    "trace_back_to": None,
}
META_CONTINUE = {
    "decision": "CONTINUE",
    "reason_summary": "Continue with the recorded objection history.",
    "plan_summary": "Resolve the equality case explicitly.",
    "forbidden_directions": [],
    "reusable_results": [],
    "trace_back_to": None,
}
STEP_ACCEPT = {**VERDICT, "verdict": "ACCEPT", "objection": ""}


class StarProductChallengeTest(StarJobFixture, unittest.TestCase):
    def run_challenge(self, replies, *, budget=16):
        self.open_star(
            replies,
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=budget, max_http_attempts=budget
            ),
        )
        job_id = self.create_job()
        job = self.terminal(job_id)
        events = [
            json.loads(line[6:])
            for line in self.client.get(f"/api/agent/jobs/{job_id}/events")
            .get_data(as_text=True)
            .splitlines()
            if line.startswith("data: ")
        ]
        return job_id, job, events

    def test_three_rounds_keep_latest_history_and_accept_only_after_verifier(self):
        objections = [
            "Check the sign of the boundary term.",
            "Now check the equality case.",
            "The equality case still needs justification.",
        ]
        replies = [NEED_PLAN, PLAN, STEP, {**CHALLENGE, "objection": objections[0]}]
        for index in range(3):
            replies.append({"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False})
            replies.append(
                STEP_ACCEPT if index == 2 else {**CHALLENGE, "objection": objections[index + 1]}
            )
        replies.extend([{"final_response": "2"}, ACCEPT])

        job_id, job, events = self.run_challenge(replies)

        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(
            ["explore", "planner", "reasoner", "step_verifier",
             "reasoner", "step_verifier", "reasoner", "step_verifier",
             "reasoner", "step_verifier", "final_generator", "whole_solution_verifier"],
            [request["role"] for request in self.outbound],
        )
        challenged_reasoners = [
            request for request in self.outbound
            if request["role"] == "reasoner" and request.get("round")
        ]
        self.assertEqual([1, 2, 3], [request["round"] for request in challenged_reasoners])
        self.assertEqual([[], [1], [1, 2]], [
            [item["round"] for item in request["challenge_history"]]
            for request in challenged_reasoners
        ])
        self.assertEqual(objections, [request["objection"] for request in challenged_reasoners])
        for request in challenged_reasoners:
            context = request["role_context"]
            self.assertEqual(request["state_revision"], context["state_revision"])
            self.assertGreater(context["state_revision"], 0)
            self.assertEqual("sum", context["state"]["current_step"])
            self.assertEqual("CHALLENGE", context["state"]["phase"])
        challenged_verifiers = [
            request for request in self.outbound
            if request["role"] == "step_verifier" and request.get("round")
        ]
        self.assertEqual([1, 2, 3], [request["round"] for request in challenged_verifiers])
        self.assertEqual([[1], [1, 2], [1, 2, 3]], [
            [item["round"] for item in request["challenge_history"]]
            for request in challenged_verifiers
        ])
        for request in challenged_verifiers:
            self.assertEqual(
                request["state_revision"], request["role_context"]["state_revision"]
            )
            self.assertEqual("STEP_VERIFY", request["role_context"]["state"]["phase"])
        revisions = [request["state_revision"] for request in self.outbound]
        self.assertTrue(all(left < right for left, right in zip(revisions, revisions[1:])))

        reviews = [
            event for event in events
            if event.get("solver_event_type") == "step_reviewed"
        ]
        self.assertEqual(4, len(reviews))
        self.assertEqual(1, sum(event.get("verdict") == "ACCEPT" for event in reviews))
        self.assertEqual(
            objections,
            [event.get("objection_summary") for event in reviews if event.get("verdict") == "CHALLENGE"],
        )
        self.assertTrue(all(event.get("role") == "step_verifier" for event in reviews))
        self.assertTrue(all(event.get("usage", {}).get("total_tokens") == 10 for event in reviews))
        reasoner_events = [
            event for event in events
            if event.get("solver_event_type") == "challenge_replied"
        ]
        self.assertEqual(3, len(reasoner_events))
        self.assertTrue(all(event.get("role") == "reasoner" for event in reasoner_events))
        self.assertTrue(all(event.get("usage", {}).get("total_tokens") == 10 for event in reasoner_events))
        serialized_events = json.dumps(events, ensure_ascii=False)
        self.assertNotIn(HIDDEN_ARGUMENT, serialized_events)
        self.assertNotIn("original_problem", serialized_events)
        self.assertEqual(job_id, job["result"]["solver"]["run_id"])

        report = self.report(job_id)
        self.assertEqual("star_limited", report["solver_mode"] if "solver_mode" in report else report["solver"]["solver_mode"])
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual(job_id, evidence["evidence_id"])
        self.assertEqual("fault_injection", evidence["solver"]["evidence_kind"])
        self.assertTrue(any(item.get("solver_event_type") == "challenge_replied" for item in evidence["timeline"]))

    def test_round_limit_escalates_once_and_meta_abort_controls_the_job(self):
        replies = [NEED_PLAN, PLAN, STEP, CHALLENGE]
        for _ in range(3):
            replies.extend([{"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE])
        replies.append(META_ABORT)

        job_id, job, events = self.run_challenge(replies, budget=11)

        self.assertEqual("failed", job["status"], job)
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual(["meta"], [request["role"] for request in self.outbound[-1:]])
        self.assertEqual(3, len([
            request for request in self.outbound
            if request["role"] == "reasoner" and request.get("round")
        ]))
        escalation = next(
            event for event in events
            if event.get("solver_event_type") == "challenge_stalemate"
        )
        self.assertEqual("round_limit_reached", escalation.get("upgrade_reason"))
        decision = next(
            event for event in events
            if event.get("solver_event_type") == "meta_decided"
        )
        self.assertEqual("ABORT", decision.get("decision"))
        self.assertEqual("meta", decision.get("role"))
        self.assertEqual("round_limit_reached", decision.get("upgrade_reason"))
        self.assertEqual(job_id, self.client.get(f"/api/runs/{job_id}").get_json()["run_id"])
        self.assertNotIn(HIDDEN_ARGUMENT, json.dumps(events, ensure_ascii=False))

    def test_meta_continue_dispatches_with_the_same_step_history(self):
        replies = [NEED_PLAN, PLAN, STEP, CHALLENGE]
        for _ in range(3):
            replies.extend([{"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE])
        replies.extend([
            META_CONTINUE,
            {"argument": "Continued proof", "claims": [], "blocked": False},
            STEP_ACCEPT,
            {"final_response": "2"},
            ACCEPT,
        ])

        job_id, job, events = self.run_challenge(replies, budget=16)

        self.assertEqual("succeeded", job["status"], job)
        meta = next(request for request in self.outbound if request["role"] == "meta")
        self.assertEqual("challenge_round_limit", meta["trigger"])
        self.assertEqual(3, len(meta["role_context"]["state"]["steps"]["sum"]["challenge_history"]))
        resumed = [
            request for request in self.outbound
            if request["role"] == "reasoner" and not request.get("round")
            and request.get("challenge_history")
        ]
        self.assertEqual(1, len(resumed))
        self.assertEqual([1, 2, 3], [
            item["round"] for item in resumed[0]["challenge_history"]
        ])
        self.assertEqual(CHALLENGE["objection"], resumed[0]["objection"])
        decision = next(
            event for event in events if event.get("solver_event_type") == "meta_decided"
        )
        self.assertEqual("CONTINUE", decision.get("decision"))
        self.assertEqual("round_limit_reached", decision.get("upgrade_reason"))
        self.assertEqual(1, sum(
            event.get("verdict") == "ACCEPT"
            for event in events if event.get("solver_event_type") == "step_reviewed"
        ))

    def test_invalid_meta_accept_does_not_accept_or_dispatch_more_work(self):
        replies = [NEED_PLAN, PLAN, STEP, CHALLENGE]
        for _ in range(3):
            replies.extend([{"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE])
        replies.append({**META_ABORT, "decision": "ACCEPT"})

        job_id, job, events = self.run_challenge(replies, budget=16)

        self.assertEqual("failed", job["status"], job)
        # ALIGN-04: the meta reply with an out-of-schema decision arrived
        # completely, so it is a known protocol failure that ends dispatch
        # honestly instead of an interrupted unknown awaiting review.
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual("meta", self.outbound[-1]["role"])
        self.assertEqual(11, len(self.outbound))
        self.assertEqual(1, sum(request["role"] == "meta" for request in self.outbound))
        self.assertFalse(any(event.get("verdict") == "ACCEPT" for event in events))
        self.assertEqual("unknown", job["result"]["verification"]["status"])
        self.assertNotIn(HIDDEN_ARGUMENT, json.dumps(events, ensure_ascii=False))

    def test_meta_cannot_trace_back_to_a_nonexistent_step(self):
        replies = [NEED_PLAN, PLAN, STEP, CHALLENGE]
        for _ in range(3):
            replies.extend([{"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE])
        replies.append({**META_ABORT, "decision": "TRACE_BACK", "trace_back_to": 2})

        _, job, events = self.run_challenge(replies, budget=16)

        self.assertEqual("failed", job["status"], job)
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual(11, len(self.outbound))
        self.assertFalse(any(event.get("verdict") == "ACCEPT" for event in events))
        invalid = next(event for event in events if event.get("solver_event_type") == "meta_invalid")
        self.assertEqual("meta", invalid.get("role"))
        self.assertEqual("round_limit_reached", invalid.get("upgrade_reason"))

    def test_meta_continuation_cannot_reset_the_round_or_meta_limits(self):
        replies = [NEED_PLAN, PLAN, STEP, CHALLENGE]
        for _ in range(3):
            replies.extend([{"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False}, CHALLENGE])
        replies.extend([
            META_CONTINUE,
            {"argument": HIDDEN_ARGUMENT, "claims": [], "blocked": False},
            CHALLENGE,
        ])

        job_id, job, events = self.run_challenge(replies, budget=16)

        self.assertEqual("failed", job["status"], job)
        self.assertEqual("partial_aborted", job["result"]["solver"]["status"])
        self.assertEqual(1, len([request for request in self.outbound if request["role"] == "meta"]))
        self.assertEqual(3, len([
            request for request in self.outbound
            if request["role"] == "reasoner" and request.get("round")
        ]))
        self.assertEqual(["reasoner", "step_verifier"], [
            request["role"] for request in self.outbound[-2:]
        ])
        stopped = next(
            event for event in events
            if event.get("solver_event_type") == "challenge_escalation_stopped"
        )
        self.assertEqual("meta_escalation_limit_reached", stopped.get("upgrade_reason"))
        self.assertEqual("controller", stopped.get("role"))
        self.assertNotIn(HIDDEN_ARGUMENT, json.dumps(events, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
