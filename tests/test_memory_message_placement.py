"""Current advisory bodies have one untrusted final-user location on the wire."""

import json
import math
import os
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter, _normalize_message
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.intern_port import InternModelPort
from showcase.solver_harness.intern_schemas import response_schema

MEMORY = {
    "schema": "population-memory-injection-v1", "status": "available",
    "authority": "advisory_only", "review_status": "requires_current_run_review",
    "observations": [{"record_id": "placement-observation", "outcome": "unknown",
                      "use": "diagnostic_only", "content": {"summary": "Synthetic hint"}}],
}


def advisory_bodies(value):
    if isinstance(value, dict):
        found = [value["population_memory_advisory"]] if "population_memory_advisory" in value else []
        return found + [body for item in value.values() for body in advisory_bodies(item)]
    if isinstance(value, list):
        return [body for item in value for body in advisory_bodies(item)]
    return []


class MemoryMessagePlacementTest(unittest.TestCase):
    def prepare(self, *, skills, sessions):
        harness = self.enterContext(SolverHarness(config={"features": {
            "skills": skills, "persistent_sessions": sessions}}))
        run = harness.solve("Prove x + x = 2*x.", {"run_id": "placement-fixture"})
        harness._population_memory_enabled = True
        with patch("showcase.solver_harness.faithful_memory_injection.load_population_memory",
                   return_value=deepcopy(MEMORY)):
            prepared = harness.prepare_request(run, {"role": "meta", "problem": "Prove x + x = 2*x."})
        return harness, run, prepared

    def messages(self, request):
        return [_normalize_message(message) for message in
                InternModelPort()._messages(request, response_schema(request))]

    def test_current_body_is_identical_once_in_final_user_for_all_feature_combinations(self):
        for skills, sessions in ((False, False), (False, True), (True, False), (True, True)):
            with self.subTest(skills=skills, persistent_sessions=sessions):
                _, _, prepared = self.prepare(skills=skills, sessions=sessions)
                before = deepcopy(prepared)
                messages = self.messages(prepared)
                self.assertEqual("user", messages[-1]["role"])
                context = json.loads(messages[-1]["content"])
                self.assertEqual(MEMORY, context.get("population_memory_advisory"))
                self.assertEqual([MEMORY], advisory_bodies(context))
                for message in messages[:-1]:
                    if message["content"].startswith("{"):
                        self.assertEqual([], advisory_bodies(json.loads(message["content"])))
                self.assertEqual(before, prepared)

    def test_only_nested_memory_is_removed_and_unrelated_context_is_unchanged(self):
        _, _, prepared = self.prepare(skills=True, sessions=False)
        prepared["role_context"] = {"state": {
            "population_memory_advisory": deepcopy(MEMORY), "accepted_results": ["current-proof"]}}
        prepared["prompt_layers"].append({"kind": "unrelated", "notes": ["preserve"]})
        before = deepcopy(prepared)
        messages = self.messages(prepared)
        for layer, message in zip(before["prompt_layers"], messages[1:-1]):
            expected = deepcopy(layer)
            expected.get("state", {}).pop("population_memory_advisory", None)
            self.assertEqual(expected, json.loads(message["content"]))
        self.assertEqual({"state": {"accepted_results": ["current-proof"]}},
                         json.loads(messages[-1]["content"])["role_context"])
        self.assertEqual(before, prepared)

    def test_legacy_nested_only_body_survives_without_current_top_level_body(self):
        for skills, sessions in ((True, False), (False, True)):
            with self.subTest(skills=skills, sessions=sessions):
                _, _, prepared = self.prepare(skills=skills, sessions=sessions)
                prepared.pop("population_memory_advisory")
                before = deepcopy(prepared)
                messages = self.messages(prepared)
                bodies = [body for message in messages if message["content"].startswith("{")
                          for body in advisory_bodies(json.loads(message["content"]))]
                self.assertEqual([MEMORY], bodies)
                self.assertEqual(before, prepared)

    def test_reprepare_removes_revoked_bodies_and_memory_bearing_old_history(self):
        for disabled in (False, True):
            with self.subTest(disabled=disabled):
                harness, run, prepared = self.prepare(skills=True, sessions=False)
                prepared["session_history"] = [
                    {"request": {"population_memory_advisory": deepcopy(MEMORY)},
                     "response": {"reason": "OLD_MEMORY_DERIVED_REASON"}},
                    {"request": {"call_id": "ordinary"}, "response": {"text": "ordinary dialogue"}},
                ]
                prepared["session_history_summary"] = "OLD_MEMORY_DERIVED_REASON"
                harness._population_memory_enabled = not disabled
                with patch("showcase.solver_harness.faithful_memory_injection.load_population_memory",
                           return_value={"observations": []}):
                    revoked = harness.prepare_request(run, prepared)
                messages = self.messages(revoked)
                serialized = json.dumps(messages)
                self.assertNotIn("placement-observation", serialized)
                self.assertNotIn("Synthetic hint", serialized)
                self.assertNotIn("OLD_MEMORY_DERIVED_REASON", serialized)
                self.assertIn("ordinary dialogue", serialized)

    def test_exact_memory_cost_matches_admitted_serialized_body_delta(self):
        _, _, prepared = self.prepare(skills=True, sessions=False)
        plain = deepcopy(prepared)
        plain.pop("population_memory_advisory")
        for layer in plain["prompt_layers"]:
            layer.get("state", {}).pop("population_memory_advisory", None)
        costs, admitted = [], []
        prepared["_population_memory_cost_observer"] = lambda cost, _: costs.append(cost)
        reply = {"decision": "CONTINUE", "reason_summary": "Continue independently",
                 "plan_summary": "", "forbidden_directions": [], "reusable_results": [],
                 "trace_back_to": None}
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {"content": json.dumps(reply)},
                                                  "finish_reason": "stop"}], "usage": {}}
        with patch.dict(os.environ, {"INTERN_API_KEY": "unit-test-token", "INTERN_MODEL": "intern-s2",
                                     "INTERN_API_BASE": "https://api.example.test/v1/chat/completions"}):
            port = InternModelPort(adapter=InternModelAdapter(
                client=InternChatClient(timeout=2, retry=1, thinking_mode=False), thinking_mode=False))
            with patch("llm_client.requests.post", return_value=response) as post:
                for request in (prepared, plain):
                    request["_context_admission"] = lambda body, *_: admitted.append(body)
                    port.complete(request)
                bodies = [call.kwargs["data"] for call in post.call_args_list]
        self.assertEqual(admitted, bodies)
        self.assertEqual(2, len(bodies))
        delta = len(bodies[0]) - len(bodies[1])
        self.assertGreater(delta, 0)
        self.assertEqual(1, len(costs))
        self.assertEqual(delta, costs[0]["additional_utf8_bytes"])
        self.assertEqual(math.ceil(delta / 3), costs[0]["estimated_tokens"])
        self.assertEqual(["placement-observation"], costs[0]["record_ids"])
        self.assertEqual("estimated", costs[0]["status"])
        self.assertNotIn("Synthetic hint", json.dumps(costs[0]))
