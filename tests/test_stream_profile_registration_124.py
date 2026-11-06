"""Provider transport admission is independent of business reply schemas."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from showcase.stream_preference import (
    VERIFIED_STREAM_PROFILES,
    _profile_identity,
    select_transport,
)

ENDPOINT = "https://chat.intern-ai.org.cn/api/v1/chat/completions"


def adapter(**overrides):
    values = dict(endpoint=ENDPOINT, model="intern-s2", temperature=0.2,
                  thinking_mode=False, max_tokens=32768)
    values.update(overrides)
    client = SimpleNamespace(api_base=values["endpoint"], model=values["model"],
                             thinking_mode=values["thinking_mode"])
    return SimpleNamespace(_get_client=lambda: client, model_id=values["model"],
                           temperature=values["temperature"], max_tokens=values["max_tokens"],
                           thinking_mode=values["thinking_mode"], stream_complete=lambda: iter(()))


def messages(count):
    return [{"role": "system", "content": "role-specific instructions"}] * (count - 1) + [
        {"role": "user", "content": "business request"},
    ]


class VerifiedStreamProfileRegistrationTest(unittest.TestCase):
    def test_one_production_profile_does_not_bind_business_schema(self):
        self.assertEqual(1, len(VERIFIED_STREAM_PROFILES))
        profile = VERIFIED_STREAM_PROFILES[0]
        self.assertEqual(ENDPOINT, profile.endpoint)
        self.assertEqual("intern-s2", profile.model)
        identity = _profile_identity(profile)
        self.assertNotIn("messages_schema", identity)
        self.assertNotIn("schema_fingerprint", identity)
        self.assertEqual(identity, _profile_identity(replace(
            profile, schema_fingerprint="new-action", messages_schema=(("user", ("content", "role")),),
        )))

    def test_roles_actions_and_message_counts_use_the_same_transport_identity(self):
        decisions = [select_transport(adapter(), messages(count), policy="stream_first",
                                      schema_fingerprint=f"business-schema-{count}")
                     for count in (1, 2, 3, 5, 7)]
        self.assertEqual(["stream"] * 5, [d["transport"] for d in decisions])
        self.assertEqual(1, len({d["profile_fingerprint"] for d in decisions}))
        self.assertEqual(1, len({d["profile_set_fingerprint"] for d in decisions}))

    def test_actual_transport_configuration_changes_still_require_verification(self):
        for overrides in (
            {"endpoint": "https://example.invalid/chat"}, {"model": "intern-s1"},
            {"thinking_mode": True}, {"temperature": 0.3}, {"max_tokens": 16384},
        ):
            with self.subTest(overrides=overrides):
                decision = select_transport(adapter(**overrides), messages(2), policy="stream_first")
                self.assertEqual("reject", decision["transport"])
                self.assertTrue(decision["new_run_required"])
        self.assertEqual("reject", select_transport(
            adapter(), messages(2), policy="stream_first", native_tools=True,
        )["transport"])

    def test_invalid_wire_messages_are_rejected(self):
        for invalid in ([], [{"role": "unknown", "content": "text"}],
                        [{"role": "tool", "content": "text"}],
                        [{"role": "user", "content": {"text": "multimodal"}}],
                        [{"role": "assistant", "content": "text", "tool_calls": []}]):
            with self.subTest(messages=invalid):
                self.assertEqual("reject", select_transport(
                    adapter(), invalid, policy="stream_first",
                )["transport"])


if __name__ == "__main__":
    unittest.main()
