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
    def test_tool_ceiling_allows_verifier_to_review_success_or_denial(self):
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
                self.assertEqual(1, len(verifier.requests))
                self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
                self.assertEqual("ACCEPTED", result["state"]["steps"]["s1"]["status"])
                self.assertEqual(limit, len(tool.requests))
                receipt = verifier.requests[0]["report"]["tool_receipts"][0]
                self.assertEqual(bool(limit), receipt["executed"])
                self.assertEqual("success" if limit else "not_executed", receipt["status"])
                if not limit:
                    self.assertEqual("tool_call_budget_exhausted", receipt["reason"])

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

        from tests.test_solver_harness_replan import DECISION, ReplanTest

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

    def test_paired_reexplore_flag_changes_actual_delegation_branch(self):
        import tempfile
        from pathlib import Path

        from tests.test_solver_harness_replan import DECISION

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
