"""Review regressions through public solve and adapter transport seams."""

import unittest

from showcase.solver_harness import (
    ScriptedModelPort,
    ScriptedToolPort,
    ScriptedVerifierPort,
    SolverHarness,
)

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "compute", "objective": "compute"}]}


class ReviewFixTest(unittest.TestCase):
    def test_tool_hard_budget_stops_verifier_and_enters_terminal_best_effort(self):
        for limit in (0, 1):
            with self.subTest(limit=limit):
                model = ScriptedModelPort(
                    [
                        {
                            "argument": "candidate",
                            "claims": [
                                {
                                    "statement": "2+2=4",
                                    "label": "easy-verify",
                                    "tool_request": {
                                        "tool": "polynomial_check",
                                        "arguments": {},
                                        "scope": "finite_computation",
                                    },
                                }
                            ],
                        }
                    ]
                )
                verifier = ScriptedVerifierPort(
                    [{"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}]
                )
                tool = ScriptedToolPort([{"status": "success", "output": 4, "exit_code": 0}])
                with SolverHarness(
                    config={
                        "features": {"local_code_tool": True, "best_effort": True},
                        "allowed_tools": ["polynomial_check"],
                        "max_tool_calls": limit,
                        "max_model_calls": 5,
                    },
                    model_port=model,
                    verifier_port=verifier,
                    tool_port=tool,
                ) as harness:
                    result = harness.solve("2+2", {"plan": PLAN})
                self.assertEqual([], verifier.requests)
                self.assertEqual("TERMINAL", result["state"]["phase"])
                self.assertEqual("partial_budget_exhausted", result["state"]["status"])
                self.assertEqual(limit, len(tool.requests))
                self.assertEqual(
                    "tool_call_budget_exhausted", result["state"]["budget"]["exhaustion_reason"]
                )

    def test_intern_meta_delegation_uses_tasks_schema(self):
        import json

        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort

        class Client:
            def chat(self, messages, **kwargs):
                return {
                    "content": json.dumps(
                        {
                            "tasks": [
                                {
                                    "prompt": "check boundary",
                                    "permitted_tools": [],
                                    "timeout_seconds": 1,
                                }
                            ]
                        }
                    ),
                    "finish_reason": "stop",
                }

        result = InternModelPort(InternModelAdapter(Client()), original_problem="public").complete(
            {"role": "meta", "action": "delegate_research_task"}
        )
        self.assertEqual("check boundary", result["tasks"][0]["prompt"])

    def test_intern_research_timeout_reaches_existing_http_transport(self):
        import json

        from showcase.adapters import InternModelAdapter
        from showcase.solver_harness.intern_port import InternModelPort

        class Client:
            timeout = 30

            def __init__(self):
                self.timeout_seen = None

            def chat(self, messages, timeout_seconds=None, **kwargs):
                self.timeout_seen = timeout_seconds
                return {"content": json.dumps({"findings": ["bounded"]}), "finish_reason": "stop"}

        client = Client()
        port = InternModelPort(InternModelAdapter(client), original_problem="public")
        port.complete({"role": "researcher", "timeout_seconds": 1})
        self.assertEqual(1, client.timeout_seen)

    def test_research_timeout_and_failed_reply_are_not_complete(self):
        import time

        from test_solver_harness_replan import DECISION, ReplanTest

        from showcase.storage import SQLiteStore

        class ResearchPort(ScriptedModelPort):
            def __init__(self, mode):
                super().__init__([])
                self.mode = mode

            def complete(self, request):
                self.requests.append(dict(request))
                if request["role"] == "meta":
                    return {
                        "tasks": [
                            {"prompt": "bounded", "permitted_tools": [], "timeout_seconds": 1}
                        ]
                    }
                if request["role"] == "researcher":
                    if self.mode == "timeout":
                        time.sleep(1.1)
                        return {"findings": ["late; never consume"]}
                    raise RuntimeError("provider failed")
                return {**PLAN, "version": 2}

        for mode in ("timeout", "failed"):
            for audit in (False, True):
                with self.subTest(mode=mode, audit=audit):
                    store = SQLiteStore(":memory:")
                    config = {
                        "max_model_calls": 4,
                        "features": {"reexplore_after_replan": True, "stream_recovery": audit},
                    }
                    with SolverHarness(store=store, config=config) as seed:
                        ReplanTest().seed(seed)
                    with SolverHarness(
                        store=store,
                        config=config,
                        model_port=ResearchPort(mode),
                        meta_port=ScriptedModelPort([DECISION]),
                    ) as harness:
                        result = harness.solve("prove", {"run_id": "r"})
                    task = result["state"]["reexploration_tasks"][0]
                    self.assertEqual(
                        "unknown_outcome" if mode == "timeout" else "failed", task["status"]
                    )
                    self.assertIsNone(task["output_ref"])
                    self.assertFalse(
                        any(
                            "late; never consume" in str(item)
                            for item in result["state"].get("reexploration_findings", [])
                        )
                    )
                    if audit:
                        self.assertTrue(
                            any(
                                record["status"] == "unknown_outcome"
                                for record in result["state"]["calls"].values()
                            )
                        )

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

    def test_paired_reexplore_flag_changes_actual_delegation_branch(self):
        import tempfile
        from pathlib import Path

        from test_solver_harness_replan import DECISION

        from showcase.solver_harness.paired import PairedRunner

        class Port(ScriptedModelPort):
            def complete(self, request):
                self.requests.append(dict(request))
                if request["role"] == "meta":
                    return {
                        "tasks": [
                            {"prompt": "boundary", "permitted_tools": [], "timeout_seconds": 1}
                        ]
                    }
                if request["role"] == "researcher":
                    return {"findings": ["possible route"]}
                if request["role"] == "planner":
                    return {**PLAN, "version": 2}
                return {"argument": "bound", "claims": []}

        model_a, model_b = Port([]), Port([])
        base = {
            "max_model_calls": 8,
            "max_tool_calls": 0,
            "max_total_duration_seconds": 30,
            "features": {"reexplore_after_replan": False},
        }

        def ports(model):
            return {
                "source": "scripted",
                "model_port": model,
                "verifier_port": ScriptedVerifierPort(
                    [{"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "PROPOSE_REPLAN"}]
                ),
                "meta_port": ScriptedModelPort([DECISION]),
            }

        conditions = {
            "models": {
                r: {"model_id": "scripted", "revision": "fixture"}
                for r in ("reasoner", "verifier", "meta")
            },
            "transport": {
                "max_output_tokens": 100,
                "timeout_seconds": 3,
                "physical_attempts_per_call": 1,
            },
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            result = runner.run_pair(
                "public",
                control_config=base,
                variant_config={**base, "features": {"reexplore_after_replan": True}},
                conditions=conditions,
                control_ports=ports(model_a),
                variant_ports=ports(model_b),
                strategy_feature="reexplore_after_replan",
                metadata={"plan": PLAN},
            )
        self.assertFalse(any(r["role"] == "researcher" for r in model_a.requests))
        self.assertTrue(any(r["role"] == "researcher" for r in model_b.requests))
        self.assertIn("reexplore_after_replan", result["manifest"]["strategy_feature"])

    def test_restricted_pair_records_profile_skips_and_dispatches_no_research_or_tool(self):
        import tempfile
        from pathlib import Path

        from showcase.solver_harness.paired import PairedRunner

        tools = [ScriptedToolPort([]), ScriptedToolPort([])]
        models = [
            ScriptedModelPort([{"assessment": "NEED_PLAN"}]),
            ScriptedModelPort([{"assessment": "NEED_PLAN"}]),
        ]
        base = {
            "profile": "restricted-pure-reasoning",
            "max_model_calls": 2,
            "max_tool_calls": 0,
            "max_total_duration_seconds": 30,
            "features": {
                "skills": False,
                "local_code_tool": False,
                "reexplore_after_replan": False,
            },
        }
        conditions = {
            "models": {"reasoner": {"model_id": "scripted", "revision": "fixture"}},
            "transport": {
                "max_output_tokens": 100,
                "timeout_seconds": 3,
                "physical_attempts_per_call": 1,
            },
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            PairedRunner(database_path=Path(directory) / "pair.db") as runner,
        ):
            report = runner.run_pair(
                "public",
                control_config=base,
                variant_config={**base, "features": {**base["features"], "skills": True}},
                conditions=conditions,
                control_ports={
                    "source": "scripted",
                    "model_port": models[0],
                    "tool_port": tools[0],
                },
                variant_ports={
                    "source": "scripted",
                    "model_port": models[1],
                    "tool_port": tools[1],
                },
            )
        for name, tool, model in zip(("control", "variant"), tools, models):
            self.assertEqual(
                "restricted-pure-reasoning", report["manifest"]["configs"][name]["profile"]
            )
            self.assertEqual(
                "disabled_by_profile", report["arms"][name]["feature_skips"]["local_code_tool"]
            )
            self.assertEqual(
                "disabled_by_profile",
                report["arms"][name]["feature_skips"]["reexplore_after_replan"],
            )
            self.assertEqual([], tool.requests)
            self.assertFalse(any(r["role"] == "researcher" for r in model.requests))
            self.assertEqual(1, len(model.requests))

    def test_star_replacement_plan_repairs_once_and_records_reason(self):
        from test_solver_harness_replan import DECISION, ReplanTest

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
