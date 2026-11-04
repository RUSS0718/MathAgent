"""Provider-live stream profile registration at the public selector seam."""

import unittest
from types import SimpleNamespace

from showcase.stream_preference import VERIFIED_STREAM_PROFILES, select_transport

ENDPOINT = "https://chat.intern-ai.org.cn/api/v1/chat/completions"
MODEL = "intern-s2"
SCHEMAS = {
    "explore": "89fbfab654098a2025a0b69375f8dc8a7d8000391507639243712ca85a3a1473",
    "final_generator": "54ac692b082da9544bf9ee6ebc6c71cbf38396b8863aeb2e9d932de7f2cb6c10",
    "whole_solution_verifier": "edaea8b9ad088955e19001ef3b3bc6479028b604003ddf6dee7feeef56507aec",
}
LAYERED_SCHEMAS = {
    "planner": "47d696ba141a0df8916096620b35e322e402c59c41a80fca7b268a4c2ee2efee",
    "reasoner": "8836d710fac9532e05ef506e19a3da7fee87bb4a96b588396dd9842e83d986ef",
    "step_verifier": "f45df661a9c9ae45dee4ed363ed244c934a60b951d5cd4eeb2464b3fd2606eb7",
    "meta": "db00d390d3dd387091b0ead73c45125c45094bf98ea7f04df5dce1257dd238ee",
    "explore_polish": "818c4d7d0098f6117fa023907d53dc161f8d45bfbd847285ff07d0d890877b87",
    "researcher": "e5b9cd4d259add409204822298e4ed299c8eb2a02f27a359b688058b90721a4f",
}
COUNTEREXAMPLE_SCHEMA = "d34c4ad6068e396ff084b945939e6bb3839bc2af86603e7aa2784161ac59a097"
PARTIAL_EXPLORATION_SCHEMA = "0bee07618015f9cd6ecedf2f63e6785b9cad5b92e7e22aabc0feeca03dc86bf7"
COUNTEREXAMPLE_PROFILE = "85543b0bdce2793ca8a0a0b666fea45de190ba74e814b8bbdfa30bc7bb8cc17a"
MESSAGE = ("system", ("content", "role"))
USER = ("user", ("content", "role"))
SHAPE_2 = (MESSAGE, USER)
SHAPE_5 = (MESSAGE, MESSAGE, MESSAGE, MESSAGE, USER)


def adapter(*, endpoint=ENDPOINT, model=MODEL, temperature=0.2, thinking_mode=False,
            max_tokens=32768):
    """Build an inert adapter-shaped object for selection-only tests."""
    client = SimpleNamespace(api_base=endpoint, model=model, thinking_mode=thinking_mode)
    return SimpleNamespace(
        _get_client=lambda: client,
        model_id=MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking_mode=thinking_mode,
        stream_complete=lambda *_args, **_kwargs: iter(()),
    )


def messages_for(shape):
    """Create messages with the requested role/key shape, without prompt data."""
    return [{"role": role, "content": "synthetic"} for role, _keys in shape]


def schema_fingerprint_for(request):
    """Fingerprint a local protocol variant to assert it stays unregistered."""
    import hashlib
    import json

    from showcase.solver_harness.intern_schemas import response_schema

    schema = response_schema(request)
    encoded = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class VerifiedStreamProfileRegistrationTest(unittest.TestCase):
    def test_partial_exploration_meta_uses_only_its_probe_verified_shape(self):
        actual = schema_fingerprint_for({"role": "meta", "action": "partial_exploration"})
        self.assertEqual(PARTIAL_EXPLORATION_SCHEMA, actual)
        decision = select_transport(adapter(), messages_for(SHAPE_5), policy="stream_first",
                                    schema_fingerprint=actual)
        self.assertEqual("stream", decision["transport"])
        self.assertEqual("reject", select_transport(
            adapter(), messages_for(SHAPE_2), policy="stream_first",
            schema_fingerprint=actual,
        )["transport"])

    def test_counterexample_schema_fingerprint_matches_registered_live_profile(self):
        """Keep the counterexample response schema and live profile in sync."""
        actual = schema_fingerprint_for({"role": "researcher", "action": "counterexample_check"})
        self.assertEqual(COUNTEREXAMPLE_SCHEMA, actual)
        self.assertIn(
            (actual, SHAPE_5),
            {(profile.schema_fingerprint, profile.messages_schema)
             for profile in VERIFIED_STREAM_PROFILES},
        )

    def test_only_fourteen_probe_verified_schema_and_message_shape_pairs_are_registered(self):
        expected = ({(fingerprint, shape) for fingerprint in SCHEMAS.values()
                     for shape in (SHAPE_2, SHAPE_5)}
                    | {(fingerprint, SHAPE_5) for fingerprint in LAYERED_SCHEMAS.values()}
                    | {(COUNTEREXAMPLE_SCHEMA, SHAPE_5), (PARTIAL_EXPLORATION_SCHEMA, SHAPE_5)})
        self.assertEqual(14, len(VERIFIED_STREAM_PROFILES))
        self.assertEqual(
            expected,
            {(profile.schema_fingerprint, profile.messages_schema)
             for profile in VERIFIED_STREAM_PROFILES},
        )
        counterexample = next(
            profile for profile in VERIFIED_STREAM_PROFILES
            if profile.schema_fingerprint == COUNTEREXAMPLE_SCHEMA
        )
        from showcase.experiment_transport import profile_fingerprint

        self.assertEqual(COUNTEREXAMPLE_PROFILE, profile_fingerprint(counterexample))
        for profile in VERIFIED_STREAM_PROFILES:
            self.assertEqual(ENDPOINT, profile.endpoint)
            self.assertEqual(MODEL, profile.model)
            self.assertEqual(0.2, profile.temperature)
            self.assertEqual(32768, profile.max_tokens)
            self.assertIs(profile.thinking_mode, False)
            self.assertEqual("provider_live", profile.evidence_kind)
            self.assertEqual("provider_live_verified", profile.status)

    def test_each_registered_pair_selects_stream_at_the_public_boundary(self):
        expected_pairs = [*((fingerprint, shape) for fingerprint in SCHEMAS.values()
                            for shape in (SHAPE_2, SHAPE_5)),
                          *((fingerprint, SHAPE_5)
                            for fingerprint in LAYERED_SCHEMAS.values()),
                          (COUNTEREXAMPLE_SCHEMA, SHAPE_5), (PARTIAL_EXPLORATION_SCHEMA, SHAPE_5)]
        for schema_fingerprint, shape in expected_pairs:
            with self.subTest(schema=schema_fingerprint, shape=len(shape)):
                decision = select_transport(
                    adapter(), messages_for(shape), policy="stream_first",
                    schema_fingerprint=schema_fingerprint,
                )
                self.assertEqual("stream", decision["transport"])
                self.assertEqual("provider_live", decision["evidence_kind"])

    def test_changed_schema_or_request_configuration_rejects_before_dispatch(self):
        cases = (
            (adapter(), SHAPE_2, "changed-schema", False),
            (adapter(thinking_mode=True), SHAPE_2, SCHEMAS["explore"], False),
            (adapter(max_tokens=16384), SHAPE_2, SCHEMAS["explore"], False),
            (adapter(temperature=0.3), SHAPE_2, SCHEMAS["explore"], False),
            (adapter(model="intern-s1"), SHAPE_2, SCHEMAS["explore"], False),
            (adapter(endpoint="https://example.invalid/chat"), SHAPE_2,
             SCHEMAS["explore"], False),
            (adapter(), SHAPE_2 + (MESSAGE,), SCHEMAS["explore"], False),
            (adapter(), SHAPE_2, SCHEMAS["explore"], True),
            (adapter(), SHAPE_2, LAYERED_SCHEMAS["planner"], False),
            (adapter(), SHAPE_5,
             schema_fingerprint_for({"role": "meta", "action": "delegate_research_task"}),
             False),
            (adapter(), SHAPE_5,
             schema_fingerprint_for({"role": "reasoner", "checkpoint_protocol": True}),
             False),
        )
        for selected_adapter, shape, schema_fingerprint, native_tools in cases:
            with self.subTest(shape=len(shape), schema=schema_fingerprint,
                              native_tools=native_tools):
                decision = select_transport(
                    selected_adapter, messages_for(shape), policy="stream_first",
                    schema_fingerprint=schema_fingerprint, native_tools=native_tools,
                )
                self.assertEqual("reject", decision["transport"])
                self.assertTrue(decision["new_run_required"])


if __name__ == "__main__":
    unittest.main()
