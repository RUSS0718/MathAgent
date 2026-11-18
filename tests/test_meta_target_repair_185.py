"""Meta action/target mismatches reach the existing bounded wire repair."""

import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.intern_schemas import response_schema
from showcase.tool_schemas import schema_error
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_guidance import PLAIN, PLAN_V2, REPLAN_RULING, guidance
from tests.test_star_product_tools import FEATURES, NEED_PLAN, PLAN, VERDICT


class MetaTargetRepairTest(StarJobFixture, unittest.TestCase):
    def test_wire_schema_requires_target_only_for_traceback(self):
        for request, reply, field, trace in (
            ({"role": "meta"}, REPLAN_RULING, "decision", "TRACE_BACK"),
            ({"role": "meta", "guidance_request": {"failure_type": "stuck"}},
             guidance("replan"), "action_type", "trace_back"),
        ):
            schema = response_schema(request)
            with self.subTest(field=field):
                self.assertIsNone(schema_error(reply, schema))
                self.assertIsNotNone(schema_error({**reply, "trace_back_to": 2}, schema))
                self.assertIsNotNone(schema_error({**reply, field: trace}, schema))
                self.assertIsNone(schema_error({**reply, field: trace, "trace_back_to": 1}, schema))
                for target in (0, -1, True, 1.0):
                    self.assertIsNotNone(schema_error({**reply, field: trace,
                                                       "trace_back_to": target}, schema))
                self.assertIsNotNone(schema_error({**reply, "unexpected": True}, schema))

    def test_optional_memory_decisions_remain_valid_in_both_meta_forms(self):
        memory = {"authority": "advisory_only", "observations": [{"record_id": "advice"}]}
        decision = [{"record_id": "advice", "decision": "reject", "reason": "not relevant"}]
        for request, reply in (
            ({"role": "meta"}, REPLAN_RULING),
            ({"role": "meta", "guidance_request": {"failure_type": "stuck"}}, guidance("replan")),
        ):
            with self.subTest(request=request):
                schema = response_schema({**request, "population_memory_advisory": memory})
                self.assertIsNone(schema_error({**reply, "memory_decisions": decision}, schema))
                self.assertIsNotNone(schema_error({**reply, "memory_decisions": decision,
                                                   "trace_back_to": 2}, schema))
                self.assertIsNotNone(schema_error({**reply, "memory_decisions": [
                    {**decision[0], "record_id": "foreign"}]}, schema))

    def run_public_replan(self, *, second_invalid=False):
        invalid = {**REPLAN_RULING, "trace_back_to": 2}
        replies = [NEED_PLAN, PLAN, {**PLAIN, "blocked": True}, guidance("replan"), invalid,
                   invalid if second_invalid else REPLAN_RULING]
        if not second_invalid:
            replies.extend([PLAN_V2, PLAIN, VERDICT, {"final_response": "2"}, ACCEPT])
        self.open_star(replies, stream_chunk_size=4096,
                       SHOWCASE_STAR_FEATURES={**FEATURES, "local_code_tool": False,
                                              "meta_guidance": True},
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                           max_model_calls=14, max_http_attempts=14, max_tool_calls=0))
        job_id = self.create_job()
        final = self.terminal(job_id, timeout=20)
        rulings = [r for r in self.outbound if r["role"] == "meta" and not r.get("guidance_request")]
        self.assertEqual(2, len(rulings))
        original, repair = rulings
        self.assertEqual(original["call_id"] + ":repair-1", repair["call_id"])
        for key in ("run_id", "plan_version", "pending_replan_request", "allowed_tools"):
            self.assertEqual(original[key], repair[key])
        self.assertIn("trace_back_to", repair["repair_instruction"])
        self.assertEqual(0, final["result"]["budget"]["unresolved_attempts"])
        return final, self.report(job_id)

    def test_replan_target_mismatch_repairs_once_and_reaches_reviewed_delivery(self):
        final, report = self.run_public_replan()
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("accepted", report["semantics"]["whole_review"])
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        planners = [r for r in self.outbound if r["role"] == "planner"]
        self.assertEqual([1, 2], [r["plan_version"] for r in planners])
        self.assertEqual(11, len(self.outbound))

    def test_second_target_mismatch_stops_without_planner_or_third_repair(self):
        final, _ = self.run_public_replan(second_invalid=True)
        self.assertEqual("failed", final["status"])
        self.assertEqual(6, len(self.outbound))
        self.assertEqual(1, sum(r["role"] == "planner" for r in self.outbound))
