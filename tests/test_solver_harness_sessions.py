"""Persistent session behavior through solve/get_run."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, ScriptedVerifierPort, SolverHarness

PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "x", "objective": "prove"}]}
CHALLENGE = {
    "goal_gate": "PARTIAL",
    "logic_gate": "UNCERTAIN",
    "verdict": "CHALLENGE",
    "objection": "boundary",
}
ACCEPT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT"}


class SessionsTest(unittest.TestCase):
    def test_challenge_restores_distinct_role_histories(self):
        model = ScriptedModelPort([{"argument": "initial"}, {"argument": "reply"}])
        verifier = ScriptedVerifierPort([CHALLENGE, ACCEPT])
        with SolverHarness(
            model_port=model,
            verifier_port=verifier,
            config={"max_model_calls": 4, "features": {"persistent_sessions": True}},
        ) as harness:
            result = harness.solve("prove", {"run_id": "sessions", "plan": PLAN})
            self.assertEqual(result, harness.get_run("sessions"))
        self.assertEqual(model.requests[0]["session_key"], model.requests[1]["session_key"])
        self.assertEqual("initial", model.requests[1]["session_history"][0]["response"]["argument"])
        self.assertEqual(
            "CHALLENGE", verifier.requests[1]["session_history"][0]["response"]["verdict"]
        )
        self.assertNotEqual(model.requests[0]["session_key"], verifier.requests[0]["session_key"])
        self.assertEqual(2, len(result["state"]["session_registry"]))

    def test_recreation_continues_meta_history_and_completed_run_is_idempotent(self):
        config = {"max_model_calls": 4, "features": {"persistent_sessions": True}}

        def decision(action):
            return {
                "decision": action,
                "reason_summary": "reason",
                "plan_summary": "plan",
                "forbidden_directions": [],
                "reusable_results": [],
                "trace_back_to": None,
            }

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "run.db"
            with SolverHarness(
                database_path=database,
                config=config,
                meta_port=ScriptedModelPort([decision("CONTINUE")]),
            ) as harness:
                first = harness.solve("prove", {"run_id": "recover", "meta_trigger": "blocked"})
                first = harness.commit_event(
                    "recover",
                    expected_revision=first["state_revision"],
                    event={"event_id": "next-plan", "type": "plan_changed"},
                    state_updates={"plan_version": 2},
                )
            model = ScriptedModelPort([decision("ABORT")])
            with SolverHarness(database_path=database, config=config, meta_port=model) as harness:
                final = harness.solve("prove", {"run_id": "recover", "meta_trigger": "blocked"})
                self.assertEqual(
                    "CONTINUE", model.requests[0]["session_history"][0]["response"]["decision"]
                )
                self.assertEqual(
                    final, harness.solve("prove", {"run_id": "recover", "meta_trigger": "blocked"})
                )
                self.assertEqual(final, harness.get_run("recover"))
            self.assertGreater(model.requests[0]["state_revision"], first["state_revision"])
            self.assertEqual(1, len(model.requests))

    def test_latest_authorized_context_copies_input_and_filters_invalid_facts(self):
        requests = []

        class Observer:
            def complete(self, request):
                requests.append(request)
                request["role_context"]["state"]["confirmed_failures_ledger"].clear()
                request["step"]["objective"] = "tampered"
                return {"argument": "proof"}

        config = {"max_model_calls": 3, "features": {"persistent_sessions": True}}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "run.db"
            with SolverHarness(config=config, database_path=database) as harness:
                run = harness.solve("prove", {"run_id": "latest"})
                harness.commit_event(
                    "latest",
                    expected_revision=run["state_revision"],
                    event={"event_id": "seed", "type": "seed"},
                    state_updates={
                        "phase": "PLAN",
                        "confirmed_failures_ledger": [{"reason": "forbidden"}],
                        "verified_results_ledger": [
                            {"result_id": "bad", "invalidated": True},
                            {"result_id": "good"},
                        ],
                    },
                )
            with SolverHarness(
                config=config, database_path=database, model_port=Observer()
            ) as harness:
                result = harness.solve("prove", {"run_id": "latest", "plan": PLAN})
                self.assertEqual("prove", PLAN["steps"][0]["objective"])
                self.assertEqual(
                    [{"reason": "forbidden"}], result["state"]["confirmed_failures_ledger"]
                )
                self.assertEqual(
                    [{"result_id": "good"}],
                    requests[0]["role_context"]["state"]["verified_results_ledger"],
                )

    def test_restored_identity_conflict_is_rejected_before_model_call(self):
        config = {"max_model_calls": 4, "features": {"persistent_sessions": True}}
        with SolverHarness(
            config=config, model_port=ScriptedModelPort([{"assessment": "UNSOLVED"}])
        ) as harness:
            run = harness.solve("prove", {"run_id": "identity"})
            registry = run["state"]["session_registry"]
            next(iter(registry.values()))["problem_hash"] = "foreign"
            harness.commit_event(
                "identity",
                expected_revision=run["state_revision"],
                event={"event_id": "conflict", "type": "conflict"},
                state_updates={"session_registry": registry},
            )
            with self.assertRaisesRegex(ValueError, "session identity"):
                harness.get_run("identity")

    def test_new_attempt_archives_reasoner_and_new_steps_split_verifier_sessions(self):
        model = ScriptedModelPort([{"argument": "one"}, {"argument": "two"}, {"argument": "retry"}])
        verifier = ScriptedVerifierPort([ACCEPT, ACCEPT, ACCEPT])
        config = {"max_model_calls": 8, "features": {"persistent_sessions": True}}
        plan = {
            "version": 1,
            "steps": [*PLAN["steps"], {"step_id": "s2", "title": "y", "objective": "next"}],
        }
        with SolverHarness(config=config, model_port=model, verifier_port=verifier) as harness:
            first = harness.solve("prove", {"run_id": "attempts", "plan": plan})
            self.assertEqual(model.requests[0]["session_key"], model.requests[1]["session_key"])
            self.assertEqual([], verifier.requests[1]["session_history"])
            self.assertNotEqual(
                verifier.requests[0]["session_key"], verifier.requests[1]["session_key"]
            )
            harness.commit_event(
                "attempts",
                expected_revision=first["state_revision"],
                event={"event_id": "replan-test", "type": "replan"},
                state_updates={
                    "phase": "PLAN",
                    "attempt_index": 1,
                    "current_step": None,
                    "steps": {},
                },
            )
            second = harness.solve("prove", {"run_id": "attempts", "plan": {**PLAN, "version": 2}})
            self.assertNotEqual(model.requests[0]["session_key"], model.requests[2]["session_key"])
            self.assertEqual([], model.requests[2]["session_history"])
            self.assertIn(model.requests[0]["session_key"], second["state"]["session_registry"])

    def test_replan_dispatch_uses_rescued_ledger_and_archives_invalid_facts(self):
        config = {"max_model_calls": 3, "features": {"persistent_sessions": True}}
        safe = {
            "result_id": "safe",
            "source": "independent",
            "dependencies": [],
            "evidence_level": "tool_verified",
        }
        bad = {"result_id": "bad", "source": "s1", "dependencies": []}
        decision = {
            "decision": "APPROVE_REPLAN",
            "reason_summary": "route failed",
            "plan_summary": "new",
            "forbidden_directions": ["forbidden"],
            "reusable_results": ["safe"],
            "trace_back_to": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "run.db"
            with SolverHarness(config=config, database_path=database) as harness:
                run = harness.solve("prove", {"run_id": "replan"})
                harness.commit_event(
                    "replan",
                    expected_revision=run["state_revision"],
                    event={"event_id": "seed", "type": "seed"},
                    state_updates={
                        "phase": "META_DECIDE",
                        "plan": PLAN,
                        "plan_version": 1,
                        "current_step": "s1",
                        "accepted_results": [safe, bad],
                        "verified_results_ledger": [safe, bad],
                    },
                )
            model = ScriptedModelPort([{**PLAN, "version": 2}, {"argument": "new"}])
            with SolverHarness(
                config=config,
                database_path=database,
                model_port=model,
                meta_port=ScriptedModelPort([decision]),
            ) as harness:
                result = harness.solve("prove", {"run_id": "replan"})
                self.assertEqual(result, harness.get_run("replan"))
            self.assertEqual(
                ["safe"],
                [
                    item["result_id"]
                    for item in model.requests[0]["role_context"]["state"][
                        "verified_results_ledger"
                    ]
                ],
            )
            self.assertTrue(model.requests[1]["role_context"]["state"]["confirmed_failures_ledger"])
