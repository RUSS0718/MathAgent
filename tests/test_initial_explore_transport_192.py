"""Request capacity at the public provider/ledger seam, without live requests."""

import hashlib
import json
import unittest
from dataclasses import replace

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.run_budget import RunBudget, RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from tests.controlled_stream_profiles import configure_controlled_streaming
from tests.star_product_support import SOLVED, StarJobFixture


class InitialExploreTransportTest(StarJobFixture, unittest.TestCase):
    def exercise(self, *, streaming):
        adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=8192)
        profiles = configure_controlled_streaming(adapter)
        self.open_star([SOLVED], SHOWCASE_STAR_ADAPTER=adapter)
        port = InternModelPort(adapter, streaming=True, transport_policy="stream_first",
            stream_profiles=tuple(replace(p, max_tokens=2048) for p in profiles))
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        # A small root budget accepts the real 2048 reservation, but cannot accept8192.
        ledger.ensure("capacity", RunBudgetLimits(max_tokens=7000))
        snapshots = []
        original = self.post.side_effect

        def observe(*args, **kwargs):
            snapshots.append(ledger.snapshot("capacity"))
            return original(*args, **kwargs)

        self.post.side_effect = observe
        bodies = []
        request = {"run_id": "capacity", "call_id": "capacity:explore:1", "role": "explore",
                   "round": 1, "problem": "1+1", "max_output_tokens": 2048,
                   "_context_admission": lambda body, *_args: bodies.append(json.loads(body))}
        if not streaming:
            request["transport_override"] = "nonstream"
        estimated = port.serialized_payload_size(request)
        with bind_budget(RunBudget(ledger, "capacity")):
            reply = port.complete(request)
            if streaming:
                reply = list(reply)[-1]["result"]
        self.assertEqual("SOLVED", reply["assessment"])
        self.assertEqual(2048, bodies[0]["max_tokens"])
        self.assertEqual(streaming, bodies[0].get("stream", False))
        nonstream_body = dict(bodies[0])
        nonstream_body.pop("stream", None)
        self.assertEqual(len(json.dumps(nonstream_body, ensure_ascii=False).encode()), estimated)
        self.assertEqual(2048, snapshots[0]["reserved_tokens"] - snapshots[0]["local_input_estimate"])
        self.assertEqual(2048, ledger.attempts("capacity")[0]["max_tokens"])
        self.assertEqual(8192, adapter.max_tokens)
        decision = port.invocations[0]["transport"]
        if not streaming:
            self.assertEqual("documented", decision["evidence_kind"])
            expected = hashlib.sha256(json.dumps(bodies[0], sort_keys=True, ensure_ascii=False,
                                                 separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(expected, decision["payload_fingerprint"])
            self.assertNotIn("profile_fingerprint", decision)

    def test_nonstream_effective_cap_matches_serialization_reservation_attempt_and_fingerprint(self):
        self.exercise(streaming=False)

    def test_stream_effective_cap_uses_independent_controlled_profile_and_reservation(self):
        self.exercise(streaming=True)

    def test_old_stream_profile_does_not_authorize_new_cap(self):
        adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=8192)
        profiles = configure_controlled_streaming(adapter)
        self.open_star([], SHOWCASE_STAR_ADAPTER=adapter)
        port = InternModelPort(adapter, streaming=True, transport_policy="stream_first",
                               stream_profiles=profiles)
        with self.assertRaises(InternPortError) as error:
            port.complete({"role": "explore", "run_id": "new-cap", "round": 1,
                           "problem": "1+1", "max_output_tokens": 2048})
        self.assertTrue(error.exception.no_dispatch)
        self.assertEqual(0, self.post.call_count)

    def test_invalid_request_override_rejects_before_http(self):
        adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=8192)
        self.open_star([SOLVED], SHOWCASE_STAR_ADAPTER=adapter)
        port = InternModelPort(adapter)
        with self.assertRaises(InternPortError) as error:
            port.complete({"role": "explore", "problem": "1+1", "max_output_tokens": 0,
                           "transport_override": "nonstream"})
        self.assertTrue(error.exception.no_dispatch)
        self.assertEqual(0, self.post.call_count)
