"""Public streaming activity projection contracts for CP-02."""

import unittest

from showcase.solver_harness import SolverHarness
from showcase.evidence import EvidencePackExporter


CONFIG = {
    "max_model_calls": 3,
    "features": {"stream_recovery": True, "stream_activity": True},
}


class StreamingActivityTest(unittest.TestCase):
    def test_activity_is_persisted_as_redacted_call_events(self):
        class Port:
            def complete(self, request):
                observe = request["activity_observer"]
                observe({
                    "kind": "response_headers",
                    "at": "2026-11-01T00:00:01Z",
                })
                observe({
                    "kind": "reasoning",
                    "at": "2026-11-01T00:00:02Z",
                    "reasoning_chars": 12,
                    "text": "private reasoning must not escape",
                })
                observe({
                    "kind": "content",
                    "at": "2026-11-01T00:00:03Z",
                    "content_bytes": 4,
                    "text": "private json fragment",
                })
                return {"assessment": "NEED_PLAN"}

        with SolverHarness(config=CONFIG, model_port=Port()) as harness:
            result = harness.solve("question", {"run_id": "activity"})

        call = next(iter(result["state"]["calls"].values()))
        metrics = call["stream_metrics"]
        self.assertEqual("2026-11-01T00:00:01Z", metrics["response_headers_at"])
        self.assertEqual("2026-11-01T00:00:02Z", metrics["first_reasoning_at"])
        self.assertEqual("2026-11-01T00:00:03Z", metrics["first_content_at"])
        self.assertEqual(12, metrics["reasoning_chars"])
        self.assertEqual(4, metrics["content_bytes"])
        activity_events = [event for event in result["events"] if event["type"] == "call_activity"]
        self.assertTrue(activity_events)
        for event in activity_events:
            self.assertNotIn("text", event)
            self.assertNotIn("reasoning", event)

    def test_disconnect_keeps_activity_and_stops_without_retry(self):
        class Port:
            def __init__(self):
                self.calls = 0

            def complete(self, request):
                self.calls += 1
                request["activity_observer"]({
                    "kind": "content",
                    "at": "2026-11-01T00:00:04Z",
                    "content_bytes": 7,
                })

                def stream():
                    yield {"type": "text_delta", "text": "partial"}
                    raise TimeoutError("disconnect")

                return stream()

        port = Port()
        with SolverHarness(config=CONFIG, model_port=port) as harness:
            result = harness.solve("question", {"run_id": "disconnect"})
            again = harness.solve("question", {"run_id": "disconnect"})

        call = next(iter(result["state"]["calls"].values()))
        self.assertEqual("unknown_outcome", call["status"])
        self.assertEqual("2026-11-01T00:00:04Z", call["stream_metrics"]["first_content_at"])
        self.assertEqual(result, again)
        self.assertEqual(1, port.calls)

    def test_evidence_pack_keeps_stream_metrics_without_stream_text(self):
        pack = EvidencePackExporter().export(
            {"run_id": "evidence", "status": "running", "final_response": ""},
            events=[{
                "type": "call_activity",
                "stream_metrics": {
                    "first_event_at": "2026-11-01T00:00:01Z",
                    "reasoning_chars": 3,
                },
                "text": "private stream text",
            }],
        )
        timeline = pack["timeline"][0]
        self.assertEqual(3, timeline["stream_metrics"]["reasoning_chars"])
        self.assertNotIn("text", timeline)

    def test_activity_observer_is_not_part_of_call_identity_on_recovery(self):
        class Port:
            def __init__(self):
                self.calls = 0

            def complete(self, request):
                self.calls += 1
                return {"value": "done"}

        port = Port()
        with SolverHarness(config=CONFIG) as harness:
            result = harness.solve("question", {"run_id": "stream-identity"})
            run = harness.get_run(result["run_id"])
            request = {
                "run_id": result["run_id"],
                "role": "reasoner",
                "call_id": "same-call",
                "problem": "question",
            }
            first = harness.dispatch(run, port.complete, request)
            recovered = harness.get_run(result["run_id"])
            second = harness.dispatch(recovered, port.complete, request)

        self.assertEqual(first, second)
        self.assertEqual(1, port.calls)
