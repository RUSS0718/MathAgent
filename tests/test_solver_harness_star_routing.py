"""Opt-in STAR v1.2 routing through public solve and adapter boundaries."""

import unittest

from tests.test_solver_harness_review_fixes import PLAN

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness


class StarRoutingTest(unittest.TestCase):
    def test_star_solved_polishes_same_explore_session_before_fresh_review(self):
        model = ScriptedModelPort(
            [
                {"assessment": "SOLVED", "solution_candidate": "draft"},
                {"solution_candidate": "polished"},
            ]
        )
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(
            config={"features": {"star_routing": True}, "max_model_calls": 3},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve("public")
        self.assertEqual("polished", result["state"]["final_response"])
        self.assertEqual(["explore", "explore_polish"], [r["role"] for r in model.requests])
        self.assertEqual(model.requests[0]["session_key"], model.requests[1]["session_key"])
        self.assertNotEqual(model.requests[1]["session_key"], verifier.requests[0]["session_key"])

    def test_star_partial_meta_chooses_plan_instead_of_fixed_retry(self):
        model = ScriptedModelPort([{"assessment": "PARTIALLY_SOLVED", "worked": ["bound"]}])
        meta = ScriptedModelPort([{"decision": "PLAN", "reason": "need structure"}])
        with SolverHarness(
            config={"features": {"star_routing": True}, "max_model_calls": 3},
            model_port=model,
            meta_port=meta,
        ) as harness:
            result = harness.solve("public")
        self.assertEqual("PLAN", result["state"]["phase"])
        self.assertEqual(1, len(model.requests))
        self.assertEqual("partial_exploration", meta.requests[0]["action"])

    def test_star_invalid_initial_plan_repairs_once_then_terminates(self):
        for second, reason in [
            ({"version": 1, "steps": []}, "PLAN_INVALID"),
            (None, "PARSE_ERROR"),
        ]:
            with self.subTest(reason=reason):

                class Port(ScriptedModelPort):
                    def complete(self, request):
                        if (
                            request["role"] == "planner"
                            and len([r for r in self.requests if r["role"] == "planner"]) == 1
                            and second is None
                        ):
                            self.requests.append(dict(request))
                            raise ValueError("parse")
                        return super().complete(request)

                model = Port(
                    [{"assessment": "NEED_PLAN"}, {"version": 1, "steps": []}, second or {}]
                )
                with SolverHarness(
                    config={
                        "features": {"star_routing": True, "final_generation": True},
                        "max_model_calls": 5,
                    },
                    model_port=model,
                ) as harness:
                    result = harness.solve("public")
                self.assertEqual(2, len([r for r in model.requests if r["role"] == "planner"]))
                self.assertEqual("TERMINAL", result["state"]["phase"])
                self.assertEqual(reason, result["state"]["result_reason"])

    def test_star_hint_modes_route_preplan_and_validate_missing_hint(self):
        for mode in ("none", "meta_auto", "user_hint"):
            with self.subTest(mode=mode):
                meta = ScriptedModelPort([{"hint": "factor"}])
                model = ScriptedModelPort(
                    [{"assessment": "NEED_PLAN"}, {"final_response": "unused"}]
                )
                with SolverHarness(
                    config={
                        "features": {"star_routing": True},
                        "hint_mode": mode,
                        "max_model_calls": 3,
                    },
                    model_port=model,
                    meta_port=meta,
                ) as harness:
                    result = harness.solve(
                        "public", {"user_hint": "try factoring"} if mode == "user_hint" else {}
                    )
                self.assertEqual(1 if mode == "meta_auto" else 0, len(meta.requests))
                expected = (
                    "factor"
                    if mode == "meta_auto"
                    else "try factoring"
                    if mode == "user_hint"
                    else None
                )
                self.assertEqual(expected, result["state"].get("preplan_hint"))

    def test_star_replacement_plan_repairs_once_and_records_reason(self):
        from tests.test_solver_harness_replan import DECISION, ReplanTest

        from showcase.storage import SQLiteStore

        for repaired in (True, False):
            with self.subTest(repaired=repaired):
                store = SQLiteStore(":memory:")
                config = {"features": {"star_routing": True}, "max_model_calls": 3}
                with SolverHarness(store=store, config=config) as seed:
                    ReplanTest().seed(seed)
                model = ScriptedModelPort(
                    [
                        {"version": 2, "steps": []},
                        {**PLAN, "version": 2} if repaired else {"version": 2, "steps": []},
                    ]
                )
                with SolverHarness(
                    store=store,
                    config=config,
                    model_port=model,
                    meta_port=ScriptedModelPort([DECISION]),
                ) as harness:
                    result = harness.solve("prove", {"run_id": "r"})
                self.assertEqual(2, len(model.requests))
                if repaired:
                    self.assertEqual(2, result["state"]["plan_version"])
                else:
                    self.assertEqual("PLAN_INVALID", result["state"]["result_reason"])
                    self.assertEqual("TERMINAL", result["state"]["phase"])

    def test_star_retry_decision_and_persistent_polish_session_are_real(self):
        model = ScriptedModelPort(
            [
                {"assessment": "PARTIALLY_SOLVED"},
                {"assessment": "SOLVED", "solution_candidate": "draft"},
                {"solution_candidate": "polished"},
            ]
        )
        meta = ScriptedModelPort([{"decision": "RETRY", "reason": "one useful route"}])
        verifier = ScriptedVerifierPort([{"verdict": "ACCEPT"}])
        with SolverHarness(
            config={
                "features": {"star_routing": True, "persistent_sessions": True},
                "max_model_calls": 5,
            },
            model_port=model,
            meta_port=meta,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve("public")
        self.assertEqual("polished", result["state"]["final_response"])
        self.assertEqual(model.requests[1]["session_key"], model.requests[2]["session_key"])
        self.assertEqual(1, len(model.requests[2]["session_history"]))
        self.assertNotEqual(model.requests[2]["session_key"], verifier.requests[0]["session_key"])

    def test_star_polish_checks_budget_and_missing_hint_rejected_before_model(self):
        model = ScriptedModelPort([{"assessment": "SOLVED", "solution_candidate": "draft"}])
        verifier = ScriptedVerifierPort([])
        with SolverHarness(
            config={"features": {"star_routing": True}, "max_model_calls": 1},
            model_port=model,
            verifier_port=verifier,
        ) as harness:
            result = harness.solve("public")
        self.assertEqual(1, len(model.requests))
        self.assertEqual([], verifier.requests)
        self.assertEqual("partial_budget_exhausted", result["state"]["status"])
        model = ScriptedModelPort([])
        with SolverHarness(
            config={"features": {"star_routing": True}, "hint_mode": "user_hint"}, model_port=model
        ) as harness:
            with self.assertRaisesRegex(ValueError, "user_hint_required"):
                harness.solve("public")
        self.assertEqual([], model.requests)

    def test_star_streamed_intern_plan_schema_failure_repairs_with_audits_retained(self):
        import json

        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort

        class Client:
            def __init__(self):
                self.replies = [
                    {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
                    {"version": 1, "steps": []},
                    PLAN,
                ]

            def chat(self, messages, **kwargs):
                return {"content": json.dumps(self.replies.pop(0)), "finish_reason": "stop"}

        port = InternModelPort(InternModelAdapter(Client()))
        with SolverHarness(
            config={
                "features": {
                    "star_routing": True,
                    "final_generation": True,
                    "stream_recovery": True,
                },
                "max_model_calls": 3,
            },
            model_port=port,
        ) as harness:
            result = harness.solve("public")
        self.assertEqual(3, len(port.invocations))
        self.assertEqual(PLAN, result["state"].get("plan"))
        self.assertTrue(
            any(
                c.get("error_category") == "invalid_role_schema"
                for c in result["state"]["calls"].values()
            )
        )
