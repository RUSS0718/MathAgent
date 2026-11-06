"""Regression contract for complete provider generation errors at the Intern port."""

import hashlib
import json
import unittest
from types import SimpleNamespace

from showcase.adapters import AdapterError, ModelResponse
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from showcase.solver_harness.intern_schemas import response_schema
from showcase.stream_preference import StreamProfile

VALID_EXPLORE = {
    "assessment": "UNKNOWN",
    "worked": [],
    "failed": [],
    "candidates": [],
}
INVALID_BODY = "provider returned a complete non-JSON error body"
ENDPOINT = "http://127.0.0.1:5000/api/v1/chat/completions"
HARNESS_CONFIG = {"features": {"star_routing": True, "stream_recovery": True}}


class FakeCompleteAdapter:
    model_id = "offline-intern"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete(self, _messages, *, metadata=None):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        return ModelResponse(
            text=item[0],
            finish_reason=item[1],
            usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            model_id=self.model_id,
        )


class FakeStreamAdapter(FakeCompleteAdapter):
    model_id = "offline-intern"
    temperature = 0.2
    max_tokens = 256
    thinking_mode = None

    def __init__(self, responses):
        super().__init__(responses)
        self.client = SimpleNamespace(
            model=self.model_id, api_base=ENDPOINT, loopback_only=True
        )

    def _get_client(self):
        return self.client

    def stream_complete(self, _messages, *, metadata=None):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, BaseException):
            raise item
        text, finish_reason = item
        yield {"type": "text_delta", "text": text}
        yield {
            "type": "result",
            "text": text,
            "finish_reason": finish_reason,
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            "model": self.model_id,
            "attempts": [],
        }


def streaming_port(adapter):
    schema = response_schema({"role": "explore"})
    fingerprint = hashlib.sha256(
        json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    profile = StreamProfile(
        endpoint=ENDPOINT,
        model=adapter.model_id,
        temperature=adapter.temperature,
        max_tokens=adapter.max_tokens,
        thinking_mode=adapter.thinking_mode,
        messages_schema=(("system", ("content", "role")), ("user", ("content", "role"))),
        evidence_kind="controlled_test",
        status="controlled_test",
        schema_fingerprint=fingerprint,
        payload_keys=frozenset({"model", "messages", "stream", "temperature", "max_tokens"}),
    )
    return InternModelPort(adapter, transport_policy="stream_first", stream_profiles=(profile,))


class ProviderGenerationError127Test(unittest.TestCase):
    def test_late_provider_error_does_not_replace_existing_terminal_state(self):
        class CancellingAdapter(FakeCompleteAdapter):
            def complete(self, messages, *, metadata=None):
                latest = harness.get_run("late-provider-error")
                harness.commit_event(
                    latest["run_id"], expected_revision=latest["state_revision"],
                    event={"event_id": "user-cancel", "type": "user_cancelled"},
                    state_updates={"phase": "TERMINAL", "status": "canceled",
                                   "final_response": "Canceled by user."},
                )
                return super().complete(messages, metadata=metadata)

        adapter = CancellingAdapter([(INVALID_BODY, "error")])
        with SolverHarness(model_port=InternModelPort(adapter), config=HARNESS_CONFIG) as harness:
            run = harness.solve("offline probe", {"run_id": "late-provider-error"})
        self.assertEqual("canceled", run["state"]["status"])
        self.assertEqual("Canceled by user.", run["state"]["final_response"])
        self.assertEqual(1, adapter.calls)

    def test_error_finish_reason_overrides_arbitrary_and_valid_json_bodies(self):
        valid = json.dumps(VALID_EXPLORE)
        for transport in ("nonstream", "stream"):
            for body in (INVALID_BODY, valid):
                with self.subTest(transport=transport, body=body[:20]):
                    adapter = (
                        FakeStreamAdapter([(body, "error")])
                        if transport == "stream"
                        else FakeCompleteAdapter([(body, "error")])
                    )
                    port = streaming_port(adapter) if transport == "stream" else InternModelPort(adapter)

                    with self.assertRaises(InternPortError) as caught:
                        response = port.complete({"role": "explore", "problem": "offline probe"})
                        if transport == "stream":
                            list(response)

                    self.assertEqual("provider_generation_error", caught.exception.category)
                    self.assertEqual(1, len(port.invocations))
                    self.assertEqual("error", port.invocations[0]["finish_reason"])
                    self.assertEqual("provider_generation_error", port.invocations[0]["error_category"])

    def test_harness_records_complete_generation_error_without_format_repair(self):
        for transport in ("nonstream", "stream"):
            with self.subTest(transport=transport):
                adapter = (
                    FakeStreamAdapter([(INVALID_BODY, "error")])
                    if transport == "stream"
                    else FakeCompleteAdapter([(INVALID_BODY, "error")])
                )
                port = streaming_port(adapter) if transport == "stream" else InternModelPort(adapter)
                with SolverHarness(model_port=port, config=HARNESS_CONFIG) as harness:
                    run = harness.solve("offline probe", {"run_id": f"provider-error-{transport}"})

                calls = list(run["state"]["calls"].values())
                self.assertEqual(1, adapter.calls)
                self.assertEqual(1, len(calls))
                self.assertEqual("provider_failed", calls[0]["status"])
                self.assertEqual("provider_generation_error", calls[0]["error_category"])
                self.assertEqual("provider_generation_error", run["state"]["result_reason"])
                self.assertEqual("TERMINAL", run["state"]["phase"])

    def test_stop_invalid_json_keeps_one_repair_and_stream_disconnect_stays_unknown(self):
        adapter = FakeCompleteAdapter([(INVALID_BODY, "stop"), (INVALID_BODY, "stop")])
        port = InternModelPort(adapter)
        with SolverHarness(model_port=port, config=HARNESS_CONFIG) as harness:
            repaired = harness.solve("offline probe", {"run_id": "stop-invalid-json"})
        self.assertEqual(2, adapter.calls)
        self.assertEqual(
            {"invalid_json"},
            {call["error_category"] for call in repaired["state"]["calls"].values()},
        )

        adapter = FakeStreamAdapter([AdapterError("offline_disconnect")])
        port = streaming_port(adapter)
        with SolverHarness(model_port=port, config=HARNESS_CONFIG) as harness:
            interrupted = harness.solve("offline probe", {"run_id": "stream-disconnect"})
        calls = list(interrupted["state"]["calls"].values())
        self.assertEqual(1, adapter.calls)
        self.assertEqual(1, len(calls))
        self.assertEqual("unknown_outcome", calls[0]["status"])
