"""Offline behavior contracts for persisted automatic ProblemSpec intake."""

import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from showcase.solver_harness import ScriptedVerifierPort, SolverHarness

PROBLEM = "Find all real solutions of x^2 = 1."
SPEC = {
    "specification_version": 1, "original_problem": PROBLEM, "domain": "real numbers",
    "quantifiers": ["all real x"], "assumptions": ["x^2 = 1"],
    "directions": [], "output_requirements": ["all real solutions"],
    "root_obligations": [
        {"obligation_type": "enumeration", "statement": "List all real roots of x^2 = 1."},
        {"obligation_type": "completeness", "statement": "Prove that no other real roots exist."},
    ], "auxiliary_goals": [],
}
CONFIG = {"max_model_calls": 6, "features": {
    "auto_problem_spec": True, "problem_spec": True, "final_generation": True,
    "final_solution_review": True, "star_routing": True, "persistent_sessions": True,
    "stream_recovery": True, "skills": True,
}}
SOLVED = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
          "solution_candidate": "x = -1 or x = 1, since (x-1)(x+1)=0."}
POLISH = {"solution_candidate": SOLVED["solution_candidate"]}
ACCEPT = {"verdict": "ACCEPT", "reason": "Both roots and completeness are established."}


class IntakePort:
    """Record explicit model operations without creating a provider client."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(deepcopy(request))
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return deepcopy(reply)


class AutoIntakeTest(unittest.TestCase):
    def test_serial_graph_and_progress_are_preserved_through_intake(self):
        config = {**CONFIG, "features": {**CONFIG["features"], "serial_routes": True,
                                         "proof_graph": True, "progress_scheduling": True}}
        port = IntakePort([SPEC, SOLVED, POLISH])
        with SolverHarness(config=config, model_port=port,
                           verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
            run = harness.solve(PROBLEM, {"run_id": "serial-auto-intake"})
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])
        self.assertTrue(run["state"]["progress_policy"]["enabled"])
        self.assertEqual("serial-aprs-v1", run["state"]["route_policy"]["policy_version"])
        self.assertTrue(run["state"]["proof_graph_policy"]["enabled"])
        self.assertEqual(["enumeration", "completeness"],
                         [root["obligation_type"] for root in run["state"]["problem_spec"]["root_obligations"]])

    def test_process_exit_after_dispatch_does_not_reissue_on_restart(self):
        class ProcessExit(BaseException):
            pass

        def crash_after_dispatch(run, event):
            if event["type"] == "call_audit" and event.get("outcome") == "dispatched":
                raise ProcessExit()

        with TemporaryDirectory() as folder:
            path = Path(folder) / "intake.sqlite3"
            port = IntakePort([])
            with SolverHarness(database_path=path, config=CONFIG, model_port=port,
                               event_observer=crash_after_dispatch) as harness:
                with self.assertRaises(ProcessExit):
                    harness.solve(PROBLEM, {"run_id": "inflight-intake"})
            with SolverHarness(database_path=path, config=CONFIG, model_port=port) as harness:
                run = harness.solve(PROBLEM, {"run_id": "inflight-intake"})
            self.assertEqual([], port.requests)
            self.assertEqual("interrupted", run["state"]["status"])
            self.assertEqual("unknown_outcome", run["state"]["calls"]["inflight-intake:problem-intake:1"]["status"])

    def test_intake_role_has_a_strict_provider_schema(self):
        from showcase.solver_harness.intern_schemas import response_schema
        from showcase.tool_schemas import schema_error

        schema = response_schema({"role": "problem_intake"})
        self.assertIsNone(schema_error(SPEC, schema))
        self.assertIsNotNone(schema_error({**SPEC, "invented": "field"}, schema))

    def test_provided_spec_bypasses_intake(self):
        port = IntakePort([SOLVED, POLISH])
        with SolverHarness(config=CONFIG, model_port=port,
                           verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
            run = harness.solve(PROBLEM, {"run_id": "supplied", "problem_spec": SPEC})
        self.assertEqual(["explore", "explore_polish"], [r["role"] for r in port.requests])
        self.assertNotIn("problem_intake", run["state"])
        self.assertEqual(3, run["state"]["counters"]["model_calls"])

    def test_wrong_original_problem_is_rejected_before_solving(self):
        port = IntakePort([{**SPEC, "original_problem": "Find integer solutions instead."}])
        with SolverHarness(config=CONFIG, model_port=port) as harness:
            run = harness.solve(PROBLEM, {"run_id": "wrong-problem"})
        self.assertEqual("TERMINAL", run["state"]["phase"])
        self.assertEqual("problem_spec_original_problem_mismatch", run["state"]["result_reason"])
        self.assertNotIn("problem_spec", run["state"])
        self.assertEqual(["problem_intake"], [r["role"] for r in port.requests])

    def test_invalid_spec_terminates_without_fallback_or_repeat(self):
        port = IntakePort([{**SPEC, "root_obligations": []}])
        with SolverHarness(config=CONFIG, model_port=port) as harness:
            run = harness.solve(PROBLEM, {"run_id": "invalid-spec"})
            repeated = harness.solve(PROBLEM, {"run_id": "invalid-spec"})
        self.assertEqual("TERMINAL", run["state"]["phase"])
        self.assertEqual("problem_intake_invalid_spec", run["state"]["result_reason"])
        self.assertEqual(run, repeated)
        self.assertNotIn("problem_spec", run["state"])
        self.assertEqual(1, len(port.requests))

    def test_unknown_is_not_reissued_after_restart_and_explicit_retry_can_complete(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "intake.sqlite3"
            first = IntakePort([TimeoutError("remote completion unknown")])
            with SolverHarness(database_path=path, config=CONFIG, model_port=first) as harness:
                interrupted = harness.solve(PROBLEM, {"run_id": "intake-unknown"})
            call_id = "intake-unknown:problem-intake:1"
            self.assertEqual("unknown_outcome", interrupted["state"]["calls"][call_id]["status"])
            port = IntakePort([SPEC, SOLVED, POLISH])
            with SolverHarness(database_path=path, config=CONFIG, model_port=port,
                               verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
                recovered = harness.solve(PROBLEM, {"run_id": "intake-unknown"})
                self.assertEqual("interrupted", recovered["state"]["status"])
                self.assertEqual([], port.requests)
                result = harness.solve(PROBLEM, {"run_id": "intake-unknown", "retry_call": {
                    "call_id": call_id, "new_call_id": "intake-explicit-retry",
                }})
            self.assertEqual("completed_llm_reviewed", result["state"]["status"])
            self.assertEqual("unknown_outcome", result["state"]["calls"][call_id]["status"])
            self.assertEqual(call_id, result["state"]["calls"]["intake-explicit-retry"]["retry_of_internal"])
            self.assertEqual(5, result["state"]["counters"]["model_calls"])

    def test_completed_response_is_consumed_after_crash_without_another_intake(self):
        class ProcessExit(BaseException):
            pass

        def crash_after_response(run, event):
            if (event["type"] == "call_audit" and event.get("outcome") == "completed"):
                raise ProcessExit()

        with TemporaryDirectory() as folder:
            path = Path(folder) / "intake.sqlite3"
            with SolverHarness(database_path=path, config=CONFIG, model_port=IntakePort([SPEC]),
                               event_observer=crash_after_response) as harness:
                with self.assertRaises(ProcessExit):
                    harness.solve(PROBLEM, {"run_id": "completed-intake"})
            port = IntakePort([SOLVED, POLISH])
            with SolverHarness(database_path=path, config=CONFIG, model_port=port,
                               verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
                run = harness.solve(PROBLEM, {"run_id": "completed-intake"})
            self.assertEqual(["explore", "explore_polish"], [r["role"] for r in port.requests])
            self.assertEqual("completed_llm_reviewed", run["state"]["status"])
            self.assertEqual(4, run["state"]["counters"]["model_calls"])

    def test_generated_spec_is_persisted_before_explore_and_simple_answer_still_shortcuts(self):
        port = IntakePort([SPEC, SOLVED, POLISH])
        snapshots = []
        with SolverHarness(config=CONFIG, model_port=port,
                           verifier_port=ScriptedVerifierPort([ACCEPT]),
                           event_observer=lambda run, event: snapshots.append(deepcopy(run))) as harness:
            run = harness.solve(PROBLEM, {"run_id": "auto-spec"})
            restored = harness.get_run("auto-spec", problem=PROBLEM)
        self.assertEqual("SETUP", snapshots[0]["state"]["phase"])
        self.assertNotIn("problem_spec", snapshots[0]["state"])
        self.assertEqual(["problem_intake", "explore", "explore_polish"],
                         [request["role"] for request in port.requests])
        self.assertEqual(PROBLEM, port.requests[1]["problem_spec"]["original_problem"])
        self.assertEqual(["enumeration", "completeness"],
                         [item["obligation_type"] for item in restored["state"]["problem_spec"]["root_obligations"]])
        self.assertEqual("completed_llm_reviewed", run["state"]["status"])
        self.assertEqual(4, run["state"]["counters"]["model_calls"])
        self.assertEqual("completed", run["state"]["calls"]["auto-spec:problem-intake:1"]["status"])
        self.assertEqual(1, len(run["state"]["specification_history"]))


if __name__ == "__main__":
    unittest.main()
