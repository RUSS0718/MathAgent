"""Public Skill protocol injection and role-history isolation."""

import json
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_tools import FEATURES, NEED_PLAN, PLAN, STEP, VERDICT

PLAIN = {"argument": "Addition", "claims": [], "blocked": False}
GUIDANCE = {
    "action_type": "retry_different_method",
    "specific_task": "USE_ADDITION_SENTINEL",
    "use_pure_reasoning": True,
    "trace_back_to": None,
    "rationale": "Avoid blocked method",
}


class StarSkillContextTest(StarJobFixture, unittest.TestCase):
    def protocol_from(self, request, protocol_id):
        messages = self.outbound_messages[self.outbound.index(request)]
        layer = next(
            json.loads(message["content"])
            for message in messages
            if '"kind": "protocols"' in message["content"]
        )
        protocol = next(item for item in layer["protocols"] if item["id"] == protocol_id)
        self.assertEqual("1", protocol["version"])
        self.assertTrue(protocol["instructions"].strip())
        self.assertTrue(protocol["trigger"].strip())
        self.assertTrue(protocol["permissions"])
        return protocol

    def test_counterexample_protocol_is_injected_for_actual_challenge(self):
        challenged = {
            **VERDICT,
            "verdict": "CHALLENGE",
            "logic_gate": "FAIL",
            "objection": "Check the boundary case",
        }
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        self.open_star(
            [NEED_PLAN, PLAN, STEP, challenged, PLAIN, VERDICT, {"final_response": "2"}, ACCEPT],
            SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": False, "skills": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=18, max_http_attempts=18),
            SHOWCASE_STAR_REGISTRY=registry,
        )
        job_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])

        explore = next(item for item in self.outbound if item["role"] == "explore")
        self.assertIn("exploration-protocol", explore["active_skill_ids"])
        self.assertEqual(
            ["read_state", "read_ledger"],
            self.protocol_from(explore, "exploration-protocol")["permissions"],
        )
        initial_reasoner = next(item for item in self.outbound if item["role"] == "reasoner")
        self.assertIn("verification-tag-protocol", initial_reasoner["active_skill_ids"])
        self.protocol_from(initial_reasoner, "verification-tag-protocol")

        challenge = next(
            item for item in self.outbound
            if item["role"] == "reasoner" and item.get("round") == 1
        )
        self.assertIn("construct-counterexamples", challenge["active_skill_ids"])
        self.assertIn("verification-tag-protocol", challenge["active_skill_ids"])
        self.assertEqual(
            ["read_ledger"],
            self.protocol_from(challenge, "construct-counterexamples")["permissions"],
        )
        self.protocol_from(challenge, "verification-tag-protocol")
        verifier = next(item for item in self.outbound if item["role"] == "step_verifier")
        self.assertIn("verifier-review-protocol", verifier["active_skill_ids"])
        self.assertIn("verification-tag-protocol", verifier["active_skill_ids"])
        self.protocol_from(verifier, "verifier-review-protocol")
        self.protocol_from(verifier, "verification-tag-protocol")

        reasoners = [item for item in self.outbound if item["role"] == "reasoner"]
        verifiers = [item for item in self.outbound if item["role"] == "step_verifier"]
        self.assertEqual(reasoners[0]["session_key"], challenge["session_key"])
        self.assertEqual(2, len(verifiers))
        self.assertEqual(verifiers[0]["session_key"], verifiers[1]["session_key"])
        challenge_messages = self.outbound_messages[self.outbound.index(challenge)]
        challenge_context = json.loads(challenge_messages[-1]["content"])
        self.assertEqual(1, len(challenge_context["session_history"]))
        self.assertEqual("reasoner", challenge_context["session_history"][0]["request"]["role"])
        projection = next(
            json.loads(message["content"])
            for message in challenge_messages
            if '"kind": "projection"' in message["content"]
        )
        self.assertEqual(challenge_context["state_revision"], projection["state_revision"])
        self.assertEqual(1, len(verifiers[1]["session_history"]))
        protocol_messages = json.dumps(challenge_messages, ensure_ascii=False)
        self.assertIn("Check smallest admissible instances", protocol_messages)

        events = [
            json.loads(line[6:])
            for line in self.client.get(f"/api/agent/jobs/{job_id}/events")
            .get_data(as_text=True)
            .splitlines()
            if line.startswith("data: ")
        ]
        challenge_event = next(
            event for event in events if event.get("solver_event_type") == "challenge_replied"
        )
        self.assertIn("construct-counterexamples", challenge_event["active_skill_ids"])
        self.assertTrue(self.client.get(f"/api/runs/{job_id}/evidence").get_json()["timeline"])

    def test_role_history_and_current_projection_are_isolated_between_public_runs(self):
        registry = ToolRegistry()
        registry.register("polynomial_check", lambda _args: None)
        self.open_star(
            [
                NEED_PLAN, PLAN, {**PLAIN, "blocked": True}, GUIDANCE,
                STEP, VERDICT, {"final_response": "2"}, ACCEPT,
                NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT,
            ],
            SHOWCASE_STAR_FEATURES={**FEATURES, "meta_guidance": True, "skills": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=18, max_http_attempts=18),
            SHOWCASE_STAR_REGISTRY=registry,
        )
        first_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(first_id)["status"])
        second_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(second_id)["status"])
        second_requests = [
            (item, messages)
            for item, messages in zip(self.outbound, self.outbound_messages)
            if item.get("run_id") == second_id
        ]
        self.assertTrue(second_requests)
        for item, messages in second_requests:
            self.assertEqual(second_id, item["run_id"])
            self.assertNotIn("USE_ADDITION_SENTINEL", json.dumps(messages, ensure_ascii=False))
            context = json.loads(messages[-1]["content"])
            self.assertNotIn(
                "USE_ADDITION_SENTINEL",
                json.dumps(context.get("session_history", []), ensure_ascii=False),
            )
            projection = next(
                json.loads(message["content"])
                for message in messages
                if message["role"] == "system" and '"kind": "projection"' in message["content"]
            )
            self.assertEqual(context["state_revision"], projection["state_revision"])


if __name__ == "__main__":
    unittest.main()
