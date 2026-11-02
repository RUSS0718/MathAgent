"""Streaming interruption and retry contracts through solve/get_run."""

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import ScriptedModelPort, SolverHarness

CONFIG = {"max_model_calls": 4, "features": {"stream_recovery": True, "persistent_sessions": True}}
PLAN = {"version": 1, "steps": [{"step_id": "s1", "title": "proof", "objective": "prove"}]}


class InterruptedPort:
    def __init__(self):
        self.requests = []

    def complete(self, request):
        self.requests.append(request)

        def chunks():
            yield {"type": "text_delta", "text": "partial proof"}
            raise TimeoutError("connection lost")

        return chunks()


class StreamingTest(unittest.TestCase):
    def test_partial_output_survives_restart_and_requires_explicit_new_retry_call(self):
        port = InterruptedPort()
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "runs.db"
            with SolverHarness(database_path=database, config=CONFIG, model_port=port) as harness:
                interrupted = harness.solve("prove", {"run_id": "stream", "plan": PLAN})
                self.assertEqual("interrupted", interrupted["state"]["status"])
                call_id = port.requests[0]["call_id"]
                call = interrupted["state"]["calls"][call_id]
                self.assertEqual("unknown_outcome", call["status"])
                self.assertEqual("partial proof", call["partial_text"])
                self.assertIsNone(call["usage"])
                self.assertEqual([], interrupted["state"]["accepted_results"])
            retry = ScriptedModelPort([{"argument": "complete proof"}])
            with SolverHarness(database_path=database, config=CONFIG, model_port=retry) as harness:
                self.assertEqual(interrupted, harness.get_run("stream"))
                self.assertEqual(interrupted, harness.solve("prove", {"run_id": "stream"}))
                self.assertEqual([], retry.requests)
                metadata = {
                    "run_id": "stream",
                    "retry_call": {"call_id": call_id, "new_call_id": "controlled-retry"},
                }
                recovered = harness.solve("prove", metadata)
                self.assertEqual("recovered_pending_validation", recovered["state"]["status"])
                self.assertEqual("controlled-retry", retry.requests[0]["call_id"])
                self.assertEqual([], recovered["state"]["accepted_results"])
                self.assertEqual(recovered, harness.solve("prove", metadata))
                self.assertEqual(1, len(retry.requests))

    def test_tool_error_and_structured_exception_keep_unverified_partial_output(self):
        class ToolErrorPort:
            def complete(self, request):
                return iter(
                    [
                        {"type": "text_delta", "text": "unfinished"},
                        {"type": "tool_error", "error": "failed"},
                    ]
                )

        class StructuredErrorPort:
            def complete(self, request):
                error = TimeoutError("timeout")
                error.partial_text = "exception partial"
                raise error

        for port, status, partial in [
            (ToolErrorPort(), "tool_error", "unfinished"),
            (StructuredErrorPort(), "unknown_outcome", "exception partial"),
        ]:
            with (
                self.subTest(status=status),
                SolverHarness(config=CONFIG, model_port=port) as harness,
            ):
                result = harness.solve("prove", {"plan": PLAN})
                call = next(iter(result["state"]["calls"].values()))
                self.assertEqual(status, call["status"])
                self.assertEqual(partial, call["partial_text"])
                self.assertIsNone(call["usage"])
                self.assertEqual([], result["state"]["accepted_results"])

    def test_completed_stream_is_validated_and_completed_solve_is_idempotent(self):
        class CompletePort:
            def __init__(self):
                self.count = 0

            def complete(self, request):
                self.count += 1
                snapshot = harness.get_run(request["run_id"])
                self_status = snapshot["state"]["calls"][request["call_id"]]["status"]
                if self_status != "dispatched":
                    raise AssertionError("call not audited before emit")
                return iter(
                    [
                        {"type": "text_delta", "text": "candidate"},
                        {
                            "result": {"assessment": "SOLVED", "solution_candidate": "42"},
                            "usage": {"output_tokens": 5},
                        },
                    ]
                )

        class AcceptPort:
            def verify(self, request):
                return {"verdict": "ACCEPT"}

        port = CompletePort()
        with SolverHarness(config=CONFIG, model_port=port, verifier_port=AcceptPort()) as harness:
            result = harness.solve("question", {"run_id": "done"})
            self.assertEqual("TERMINAL", result["state"]["phase"])
            self.assertEqual(result, harness.solve("question", {"run_id": "done"}))
            self.assertEqual(1, port.count)
            call = next(
                value for value in result["state"]["calls"].values() if value["role"] == "explore"
            )
            self.assertEqual({"output_tokens": 5}, call["usage"])
            with self.assertRaisesRegex(ValueError, "terminal run is frozen"):
                harness.commit_event(
                    "done",
                    expected_revision=result["state_revision"],
                    event={"event_id": "late", "type": "late"},
                    state_updates={"phase": "PLAN"},
                )

    def test_late_response_cannot_overwrite_terminal_snapshot(self):
        class LatePort:
            def complete(self, request):
                snapshot = harness.get_run(request["run_id"])
                harness.commit_event(
                    request["run_id"],
                    expected_revision=snapshot["state_revision"],
                    event={"event_id": "stop", "type": "operator_stop"},
                    state_updates={
                        "phase": "TERMINAL",
                        "status": "partial_aborted",
                        "final_response": "Stopped",
                    },
                )
                return {"assessment": "SOLVED", "solution_candidate": "late answer"}

        with SolverHarness(config=CONFIG, model_port=LatePort()) as harness:
            result = harness.solve("question", {"run_id": "late"})
            self.assertEqual("Stopped", result["state"]["final_response"])
            self.assertEqual("partial_aborted", result["state"]["status"])
            self.assertEqual(
                "ignored_late_response", next(iter(result["state"]["calls"].values()))["status"]
            )

    def test_each_stream_fragment_is_checkpointed_before_next_chunk(self):
        class Port:
            def complete(self, request):
                def chunks():
                    yield {"type": "text_delta", "text": "checkpoint"}
                    snapshot = harness.get_run(request["run_id"])
                    saved = snapshot["state"]["calls"][request["call_id"]]
                    self_test.assertEqual("checkpoint", saved["partial_text"])
                    yield {"result": {"assessment": "NEED_PLAN"}}

                return chunks()

        self_test = self
        with SolverHarness(config=CONFIG, model_port=Port()) as harness:
            result = harness.solve("question", {"run_id": "checkpoint"})
            self.assertEqual("PLAN", result["state"]["phase"])

    def test_prior_process_inflight_stream_becomes_unknown_without_retry(self):
        class ProcessCrash(BaseException):
            pass

        class CrashPort:
            def complete(self, request):
                def chunks():
                    yield {"type": "text_delta", "text": "saved partial"}
                    raise ProcessCrash()

                return chunks()

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "crash.db"
            with SolverHarness(
                config=CONFIG, database_path=database, model_port=CrashPort()
            ) as harness:
                with self.assertRaises(ProcessCrash):
                    harness.solve("question", {"run_id": "crash"})
            model = ScriptedModelPort([{"assessment": "SOLVED"}])
            with SolverHarness(
                config=CONFIG, database_path=database, model_port=model
            ) as recovered:
                result = recovered.get_run("crash")
                self.assertEqual(
                    "unknown_outcome", next(iter(result["state"]["calls"].values()))["status"]
                )
                self.assertEqual(
                    "saved partial", next(iter(result["state"]["calls"].values()))["partial_text"]
                )
                self.assertEqual(result, recovered.solve("question", {"run_id": "crash"}))
                self.assertEqual([], model.requests)

    def test_verifier_and_meta_streams_share_interruption_audit_without_acceptance(self):
        class Verifier:
            def verify(self, request):
                error = TimeoutError()
                error.partial_text = "verifier partial"
                raise error

        with SolverHarness(
            config=CONFIG,
            model_port=ScriptedModelPort([{"argument": "candidate"}]),
            verifier_port=Verifier(),
        ) as harness:
            result = harness.solve("prove", {"plan": PLAN})
            self.assertEqual("interrupted", result["state"]["status"])
            self.assertEqual([], result["state"]["accepted_results"])
            self.assertIn(
                "step_verifier", [call["role"] for call in result["state"]["calls"].values()]
            )
        with SolverHarness(config=CONFIG, meta_port=InterruptedPort()) as harness:
            result = harness.solve("prove", {"meta_trigger": "blocked"})
            self.assertEqual("interrupted", result["state"]["status"])
            self.assertEqual("meta", next(iter(result["state"]["calls"].values()))["role"])
