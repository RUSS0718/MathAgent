"""Trace-back contracts through solve/get_run."""

import unittest

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}
TRACE = {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "TRACE_BACK", "trace_back_to": 1}
PLAN = {
    "version": 1,
    "steps": [
        {"step_id": "s1", "title": "first", "objective": "derive"},
        {"step_id": "s2", "title": "second", "objective": "finish", "depends_on": ["s1"]},
    ],
}


class TracebackTest(unittest.TestCase):
    def test_traceback_archives_and_restarts_with_new_identity(self):
        snapshots = []

        class ObservedModel(ScriptedModelPort):
            def complete(self, request):
                if len(self.requests) == 2:
                    snapshots.append(harness.get_run(request["run_id"]))
                return super().complete(request)

        model = ObservedModel(
            [
                {"argument": "old first"},
                {"argument": "old second"},
                {"argument": "new first"},
                {"argument": "new second"},
            ]
        )
        with SolverHarness(
            model_port=model,
            verifier_port=ScriptedVerifierPort([ACCEPT, TRACE, ACCEPT, ACCEPT]),
            config={"max_model_calls": 8},
        ) as harness:
            result = harness.solve("prove", {"run_id": "back", "plan": PLAN})
            self.assertEqual(result, harness.get_run("back"))
        self.assertEqual("FINAL_GENERATE", result["state"]["phase"])
        reset = snapshots[0]["state"]
        self.assertEqual(1, reset["attempt_index"])
        self.assertEqual("s1", reset["current_step"])
        self.assertEqual([], reset["accepted_results"])
        failure = reset["failure_records"][0]
        self.assertEqual("trace_back", failure["kind"])
        self.assertEqual("old first", failure["archived_steps"]["s1"]["report"]["argument"])
        self.assertEqual("TRACE_BACK", failure["archived_steps"]["s2"]["verification"]["verdict"])
        self.assertNotEqual(model.requests[0]["call_id"], model.requests[2]["call_id"])
        self.assertNotEqual(model.requests[0]["session_key"], model.requests[2]["session_key"])
        self.assertIn("trace_back_applied", [event["type"] for event in snapshots[0]["events"]])

    def test_invalid_target_escalates_without_guessing(self):
        for target in (None, True, 0, 3, "1"):
            with self.subTest(target=target):
                model = ScriptedModelPort([{"argument": "pending"}])
                with SolverHarness(
                    model_port=model,
                    verifier_port=ScriptedVerifierPort([{**TRACE, "trace_back_to": target}]),
                    config={"max_model_calls": 4},
                ) as harness:
                    result = harness.solve("prove", {"plan": PLAN})
                    self.assertEqual(result, harness.get_run(result["run_id"]))
                self.assertEqual("META_DECIDE", result["state"]["phase"])
                self.assertEqual(0, result["state"]["attempt_index"])
                self.assertEqual("s1", result["state"]["current_step"])
                self.assertEqual(
                    "INVALID_TRACE_BACK_TARGET", result["state"]["meta_interventions"][0]["trigger"]
                )
                self.assertEqual(1, len(model.requests))

    def test_challenge_history_is_archived_before_retry(self):
        challenge = {
            "goal_gate": "PARTIAL",
            "logic_gate": "UNCERTAIN",
            "verdict": "CHALLENGE",
            "objection": "justify",
        }
        with SolverHarness(
            model_port=ScriptedModelPort(
                [
                    {"argument": "old"},
                    {"argument": "reply"},
                    {"argument": "new"},
                    {"argument": "next"},
                ]
            ),
            verifier_port=ScriptedVerifierPort([challenge, TRACE, ACCEPT, ACCEPT]),
            config={"max_model_calls": 8},
        ) as harness:
            result = harness.solve("prove", {"plan": PLAN})
        archived = result["state"]["failure_records"][0]["archived_steps"]["s1"]
        self.assertEqual("reply", archived["report"]["argument"])
        self.assertEqual("TRACE_BACK", archived["challenge_history"][0]["verdict"]["verdict"])
        self.assertNotIn("challenge_history", result["state"]["steps"]["s1"])

    def test_result_dependencies_invalidate_transitively_and_rescue_evidence(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.db"
            config = {"max_model_calls": 2}
            with SolverHarness(database_path=path, config=config) as harness:
                run = harness.solve("prove", {"run_id": "dependencies"})
                harness.commit_event(
                    "dependencies",
                    expected_revision=run["state_revision"],
                    event={"event_id": "fixtures", "type": "fixture_loaded"},
                    state_updates={
                        "accepted_results": [
                            {"statement": "orphan invalid", "dependencies": [],
                             "evidence_level": "candidate"},
                            {
                                "result_id": "r1",
                                "source": "s1",
                                "statement": "bad",
                                "evidence_level": "llm_reviewed",
                            },
                            {
                                "result_id": "r2",
                                "source": "other",
                                "dependencies": ["r1"],
                                "statement": "dependent",
                            },
                            {
                                "result_id": "r3",
                                "source": "other",
                                "dependencies": ["r2"],
                                "statement": "transitive",
                            },
                            {
                                "result_id": "missing",
                                "source": "unknown",
                                "statement": "missing metadata",
                            },
                            {
                                "result_id": "unknown",
                                "source": "other",
                                "dependencies": ["absent"],
                                "statement": "unknown dependency",
                            },
                            {
                                "result_id": "safe",
                                "dependencies": [],
                                "source": "independent",
                                "statement": "safe",
                                "evidence_level": "tool_verified",
                            },
                        ]
                    },
                )
            with SolverHarness(
                database_path=path,
                config=config,
                model_port=ScriptedModelPort([{}]),
                verifier_port=ScriptedVerifierPort([TRACE]),
            ) as harness:
                result = harness.solve("prove", {"run_id": "dependencies", "plan": PLAN})
                self.assertEqual(result, harness.get_run("dependencies"))
        state = result["state"]
        self.assertEqual(["safe"], [r["result_id"] for r in state["accepted_results"]])
        failure = state["failure_records"][0]
        self.assertEqual(
            [None, "r1", "r2", "r3", "missing", "unknown"],
            [r.get("result_id") for r in failure["invalidated_results"]],
        )
        self.assertEqual("tool_verified", failure["rescued_results"][0]["evidence_level"])
        self.assertEqual("STEP_EXECUTE", state["phase"])

    def test_repeated_tracebacks_preserve_each_archive(self):
        trace = {
            **TRACE,
            "reason": "unsupported route",
            "forbidden_directions": ["reuse old argument"],
        }
        model = ScriptedModelPort(
            [{"argument": value} for value in ("old", "retry", "fresh", "end")]
        )
        with SolverHarness(
            model_port=model,
            verifier_port=ScriptedVerifierPort([trace, trace, ACCEPT, ACCEPT]),
            config={"max_model_calls": 8},
        ) as harness:
            result = harness.solve("prove", {"plan": PLAN})
        state = result["state"]
        self.assertEqual(2, state["attempt_index"])
        self.assertEqual(
            ["old", "retry"],
            [
                failure["archived_steps"]["s1"]["report"]["argument"]
                for failure in state["failure_records"]
            ],
        )
        self.assertEqual(state["failure_records"], state["confirmed_failures_ledger"])
        self.assertEqual("unsupported route", state["failure_records"][0]["reason"])
        self.assertEqual(
            ["reuse old argument"], model.requests[2]["failure_records"][0]["forbidden_directions"]
        )
