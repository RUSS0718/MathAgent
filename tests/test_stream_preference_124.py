"""Issue #124 per-call streaming preference contracts; offline only."""

import hashlib
import json
import unittest
from types import SimpleNamespace

from showcase.stream_preference import StreamProfile


def _schema_fingerprint(role):
    from showcase.solver_harness.intern_schemas import response_schema

    schema = response_schema({"role": role})
    return hashlib.sha256(json.dumps(
        schema, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


class StreamPreferenceSelectorTest(unittest.TestCase):
    def _adapter(self, *, endpoint="http://127.0.0.1:5000/api/v1/chat/completions"):
        client = SimpleNamespace(
            api_base=endpoint,
            model="intern-s2",
            thinking_mode=True,
            loopback_only=True,
        )
        return SimpleNamespace(
            _get_client=lambda: client,
            model_id="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            stream_complete=lambda *_args, **_kwargs: iter(()),
        )

    def test_stream_first_without_live_profile_rejects_before_dispatch(self):
        from showcase.stream_preference import select_transport

        client = SimpleNamespace(
                api_base="https://chat.intern-ai.org.cn/api/v1/chat/completions",
                model="intern-s2",
                thinking_mode=True,
                loopback_only=False,
        )
        adapter = SimpleNamespace(
            _get_client=lambda: client,
            model_id="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
        )

        decision = select_transport(
            adapter,
            [{"role": "user", "content": "synthetic"}],
            policy="stream_first",
        )

        self.assertEqual("reject", decision["transport"])
        self.assertEqual("provider_profile_unverified", decision["reason"])
        self.assertEqual("not_verified", decision["evidence_kind"])
        self.assertTrue(decision["new_run_required"])

    def test_injected_provider_live_claim_cannot_authorize_streaming(self):
        from showcase.stream_preference import select_transport

        endpoint = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
        adapter = self._adapter(endpoint=endpoint)
        adapter._get_client().loopback_only = False
        messages = [{"role": "user", "content": "synthetic"}]
        injected_claim = StreamProfile(
            endpoint=endpoint,
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(("user", ("content", "role")),),
            evidence_kind="provider_live",
            status="provider_live_verified",
        )

        decision = select_transport(
            adapter, messages, policy="stream_first", profiles=(injected_claim,),
        )

        self.assertEqual("reject", decision["transport"])
        self.assertEqual("provider_profile_unverified", decision["reason"])
        self.assertEqual("not_verified", decision["evidence_kind"])
        self.assertTrue(decision["new_run_required"])

    def test_matching_controlled_profile_selects_stream_before_dispatch(self):
        from showcase.stream_preference import select_transport

        messages = [
            {"role": "system", "content": "schema"},
            {"role": "user", "content": "synthetic"},
        ]
        profile = StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(
                ("system", ("content", "role")),
                ("user", ("content", "role")),
            ),
            evidence_kind="controlled_test",
            status="controlled_test",
        )

        decision = select_transport(
            self._adapter(), messages, policy="stream_first", profiles=(profile,)
        )

        self.assertEqual("stream", decision["transport"])
        self.assertEqual("profile_match", decision["reason"])
        self.assertEqual("controlled_test", decision["evidence_kind"])
        self.assertEqual(64, len(decision["profile_set_fingerprint"]))
        self.assertEqual(64, len(decision["profile_fingerprint"]))

    def test_different_response_schema_does_not_match_registered_stream_profile(self):
        from showcase.stream_preference import select_transport

        messages = [{"role": "user", "content": "synthetic"}]
        profile = StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2", temperature=0.2, max_tokens=256,
            thinking_mode=True,
            messages_schema=(("user", ("content", "role")),),
            evidence_kind="controlled_test", status="controlled_test",
            schema_fingerprint="schema-a",
        )

        decision = select_transport(
            self._adapter(), messages, policy="stream_first", profiles=(profile,),
            schema_fingerprint="schema-b",
        )

        self.assertEqual("reject", decision["transport"])
        self.assertEqual("provider_profile_unverified", decision["reason"])
        self.assertTrue(decision["new_run_required"])

    def test_native_tools_reject_stream_first_and_require_separate_run(self):
        from showcase.stream_preference import select_transport

        adapter = self._adapter()
        decision = select_transport(
            adapter,
            [{"role": "user", "content": "synthetic"}],
            policy="stream_first",
            native_tools=True,
            profiles=(StreamProfile(
                endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
                model="intern-s2", temperature=0.2, max_tokens=256,
                thinking_mode=True,
                messages_schema=(("user", ("content", "role")),),
                evidence_kind="controlled_test", status="controlled_test",
            ),),
        )

        self.assertEqual("reject", decision["transport"])
        self.assertEqual("provider_native_tools_unsupported_with_stream", decision["reason"])
        self.assertEqual("documented", decision["evidence_kind"])
        self.assertEqual("native_tools_require_nonstream", decision["capability_limit"])
        self.assertTrue(decision["new_run_required"])

    def test_legacy_policy_remains_an_explicit_nonstream_compatible_choice(self):
        from showcase.stream_preference import select_transport

        decision = select_transport(
            self._adapter(), [{"role": "user", "content": "synthetic"}], policy="legacy"
        )

        self.assertEqual("legacy", decision["transport"])
        self.assertIsNone(decision["reason"])

    def test_legacy_policy_rejects_unverified_stream_activity(self):
        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        class Adapter:
            model_id = "intern-s2"

            def __init__(self):
                self.stream_calls = 0
                self.nonstream_calls = 0

            def complete(self, *_args, **_kwargs):
                self.nonstream_calls += 1
                raise AssertionError("unverified stream activity must not fall back")

            def stream_complete(self, *_args, **_kwargs):
                self.stream_calls += 1
                return iter(())

        adapter = Adapter()
        decisions = []
        port = InternModelPort(
            adapter,
            streaming=True,
            transport_policy="legacy",
            transport_choice_observer=lambda decision, _request:
                decisions.append(decision) or True,
        )

        with self.assertRaises(InternPortError) as raised:
            port.complete({
                "role": "explore", "problem": "synthetic", "run_id": "legacy-unverified-stream",
            })

        self.assertEqual("stream_first_policy_required", raised.exception.category)
        self.assertEqual(0, adapter.stream_calls)
        self.assertEqual(0, adapter.nonstream_calls)
        self.assertEqual("reject", decisions[0]["transport"])
        self.assertEqual("stream_first_policy_required", decisions[0]["reason"])
        self.assertTrue(decisions[0]["new_run_required"])

    def test_missing_stream_adapter_rejects_without_nonstream_dispatch(self):
        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        class Adapter:
            model_id = "intern-s2"
            temperature = 0.2
            max_tokens = 256
            thinking_mode = True

            def __init__(self):
                self.completions = 0
                self.client = SimpleNamespace(
                    api_base="http://127.0.0.1:5000/api/v1/chat/completions",
                    model="intern-s2", thinking_mode=True, loopback_only=True,
                )

            def _get_client(self):
                return self.client

            def complete(self, *_args, **_kwargs):
                self.completions += 1
                raise AssertionError("reject must not dispatch nonstream")

        adapter = Adapter()
        profile = StreamProfile(
            endpoint=adapter.client.api_base,
            model="intern-s2", temperature=0.2, max_tokens=256,
            thinking_mode=True,
            messages_schema=(("system", ("content", "role")),
                             ("user", ("content", "role"))),
            evidence_kind="controlled_test", status="controlled_test",
            schema_fingerprint=_schema_fingerprint("explore"),
        )
        port = InternModelPort(
            adapter, original_problem="public input", transport_policy="stream_first",
            stream_profiles=(profile,),
        )

        with self.assertRaises(InternPortError) as raised:
            port.complete({"role": "explore", "problem": "public input"})

        self.assertEqual("stream_adapter_unavailable", raised.exception.category)
        self.assertEqual(0, adapter.completions)

    def test_one_run_rejects_native_tools_after_a_stream_choice(self):
        import json

        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        class Adapter:
            model_id = "intern-s2"
            temperature = 0.2
            max_tokens = 256
            thinking_mode = True

            def __init__(self):
                self.client = SimpleNamespace(
                    api_base="http://127.0.0.1:5000/api/v1/chat/completions",
                    model="intern-s2", thinking_mode=True, loopback_only=True,
                )
                self.nonstream_calls = 0
                self.stream_calls = 0

            def _get_client(self):
                return self.client

            def complete(self, *_args, **_kwargs):
                self.nonstream_calls += 1
                raise AssertionError("a Run cannot change from stream to nonstream")

            def stream_complete(self, *_args, **_kwargs):
                self.stream_calls += 1
                response = json.dumps({"assessment": "NEED_PLAN", "worked": [],
                                       "failed": [], "candidates": []})
                return iter([{"type": "result", "text": response,
                              "finish_reason": "stop", "usage": None}])

        adapter = Adapter()
        profile = StreamProfile(
            endpoint=adapter.client.api_base,
            model="intern-s2", temperature=0.2, max_tokens=256,
            thinking_mode=True,
            messages_schema=(("system", ("content", "role")),
                             ("user", ("content", "role"))),
            evidence_kind="controlled_test", status="controlled_test",
            schema_fingerprint=_schema_fingerprint("explore"),
        )
        port = InternModelPort(
            adapter, original_problem="public input", transport_policy="stream_first",
            stream_profiles=(profile,),
        )
        first = {"role": "explore", "problem": "public input", "run_id": "same-run",
                 "call_id": "first"}
        list(port.complete(first))

        with self.assertRaises(InternPortError) as raised:
            port.complete({**first, "call_id": "second", "provider_tools": [{"type": "function"}]})

        self.assertEqual(
            "provider_native_tools_unsupported_with_stream", raised.exception.category
        )
        self.assertEqual(1, adapter.stream_calls)
        self.assertEqual(0, adapter.nonstream_calls)

    def test_legacy_native_tools_remain_nonstream_and_keep_legacy_evidence(self):
        from showcase.solver_harness.intern_port import InternModelPort

        class Adapter:
            model_id = "intern-s2"

            def __init__(self):
                self.received_tools = None

            def complete(self, _messages, *, tools=(), metadata=None):
                self.received_tools = tools
                return SimpleNamespace(
                    model_id="intern-s2", returned_model="intern-s2", finish_reason="stop",
                    usage={}, request_attempts=(), text=json.dumps({
                        "assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                    }), error_category=None,
                )

        adapter = Adapter()
        decisions = []
        port = InternModelPort(adapter, transport_choice_observer=lambda decision, _request:
                               decisions.append(decision) or True)
        tools = [{"type": "function", "function": {"name": "legacy_tool"}}]

        result = port.complete({
            "role": "explore", "problem": "synthetic", "run_id": "legacy-run",
            "provider_tools": tools,
        })

        self.assertEqual("SOLVED", result["assessment"])
        self.assertEqual(tools, adapter.received_tools)
        self.assertEqual(1, len(decisions))
        self.assertEqual("legacy", decisions[0]["policy"])
        self.assertEqual("nonstream", port.invocations[-1]["transport"]["transport"])
        self.assertEqual(
            "provider_native_tools_unsupported_with_stream",
            port.invocations[-1]["transport"]["reason"],
        )

    def test_legacy_stream_activity_does_not_override_native_tools_fallback(self):
        from showcase.solver_harness.intern_port import InternModelPort

        class Adapter:
            model_id = "intern-s2"

            def __init__(self):
                self.received_tools = None
                self.stream_calls = 0

            def complete(self, _messages, *, tools=(), metadata=None):
                self.received_tools = tools
                return SimpleNamespace(
                    model_id="intern-s2", returned_model="intern-s2", finish_reason="stop",
                    usage={}, request_attempts=(), text=json.dumps({
                        "assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                    }), error_category=None,
                )

            def stream_complete(self, *_args, **_kwargs):
                self.stream_calls += 1
                return iter(())

        adapter = Adapter()
        decisions = []
        port = InternModelPort(
            adapter, streaming=True, transport_policy="legacy",
            transport_choice_observer=lambda decision, _request:
                decisions.append(decision) or True,
        )
        tools = [{"type": "function", "function": {"name": "legacy_tool"}}]

        result = port.complete({
            "role": "explore", "problem": "synthetic", "run_id": "legacy-stream-tools",
            "provider_tools": tools,
        })

        self.assertIsInstance(result, dict)
        self.assertEqual("SOLVED", result["assessment"])
        self.assertEqual(tools, adapter.received_tools)
        self.assertEqual(0, adapter.stream_calls)
        self.assertEqual(1, len(decisions))
        self.assertEqual("nonstream", decisions[0]["transport"])
        self.assertEqual("provider_native_tools_unsupported_with_stream", decisions[0]["reason"])
        self.assertEqual("nonstream", port.invocations[-1]["transport"]["transport"])

    def test_resumed_run_rejects_changed_schema_profile_without_dispatch(self):
        import json

        from showcase.solver_harness.intern_port import InternModelPort, InternPortError

        class Adapter:
            model_id = "intern-s2"
            temperature = 0.2
            max_tokens = 256
            thinking_mode = True

            def __init__(self):
                self.client = SimpleNamespace(
                    api_base="http://127.0.0.1:5000/api/v1/chat/completions",
                    model="intern-s2", thinking_mode=True, loopback_only=True,
                )
                self.nonstream_calls = 0
                self.stream_calls = 0

            def _get_client(self):
                return self.client

            def complete(self, *_args, **_kwargs):
                self.nonstream_calls += 1
                raise AssertionError("restored stream policy must reject fallback")

            def stream_complete(self, *_args, **_kwargs):
                self.stream_calls += 1
                response = json.dumps({"assessment": "NEED_PLAN", "worked": [],
                                       "failed": [], "candidates": []})
                return iter([{"type": "result", "text": response,
                              "finish_reason": "stop", "usage": None}])

        adapter = Adapter()
        profile = StreamProfile(
            endpoint=adapter.client.api_base,
            model="intern-s2", temperature=0.2, max_tokens=256,
            thinking_mode=True,
            messages_schema=(("system", ("content", "role")),
                             ("user", ("content", "role"))),
            evidence_kind="controlled_test", status="controlled_test",
            schema_fingerprint=_schema_fingerprint("explore"),
        )
        selected = []
        first = InternModelPort(
            adapter, original_problem="public input", transport_policy="stream_first",
            stream_profiles=(profile,),
            transport_choice_observer=lambda decision, _request: selected.append(decision) or True,
        )
        request = {"role": "explore", "problem": "public input", "run_id": "resumed-run",
                   "call_id": "before-restart"}
        list(first.complete(request))
        decision = selected[0]
        saved_choice = {
            "policy": "stream_first",
            "profile_set_fingerprint": decision["profile_set_fingerprint"],
        }

        resumed = InternModelPort(
            adapter, original_problem="public input", transport_policy="stream_first",
            stream_profiles=(),
        )
        resumed.restore_transport_policy("resumed-run", saved_choice)
        with self.assertRaises(InternPortError) as raised:
            resumed.complete({**request, "role": "explore_polish", "call_id": "after-restart"})

        self.assertEqual("transport_policy_run_mismatch", raised.exception.category)
        self.assertEqual(1, adapter.stream_calls)
        self.assertEqual(0, adapter.nonstream_calls)


if __name__ == "__main__":
    unittest.main()
