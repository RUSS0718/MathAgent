"""Mixed escapes at real Adapter and authenticated Job boundaries (offline HTTP)."""
import json
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from tests.star_product_support import StarJobFixture
from tests.test_solver_harness_intern import FakeClient
from showcase.adapters import InternModelAdapter
from tests import test_star_product_protocol_failure as protocol_tests


class MixedEscapeAdapterTest(unittest.TestCase):
    def test_escape_values_and_strict_rejection(self):
        cases = [
            (r'"regex \\d+ path C:\Users"', r'regex \d+ path C:\Users'),
            (r'"path C:\Users regex \\d+"', r'path C:\Users regex \d+'),
            (r'"\\\d"', '\\\\d'),
            (r'"\\\\d \q"', '\\\\d \\q'),
            (r'"\u03b1 \q"', 'α \\q'),
            (r'"quote \" slash \\ newline \n \q"', 'quote " slash \\ newline \n \\q'),
            (r'"\u12xz \q"', None),
            (r'"\q",', None),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                raw = ('{"assessment":"NEED_PLAN","worked":[],"failed":[],'
                       '"candidates":[' + value + ']}')
                port = InternModelPort(InternModelAdapter(FakeClient([
                    {"content": raw, "finish_reason": "stop", "usage": {"total_tokens": 10}}
                ])))
                request = {"role": "explore", "problem": "1+1"}
                if expected is None:
                    with self.assertRaises(InternPortError) as caught:
                        port.complete(request)
                    self.assertEqual("invalid_json", caught.exception.category)
                    self.assertEqual(10, caught.exception.usage["total_tokens"])
                else:
                    self.assertEqual([expected], port.complete(request)["candidates"])
                    self.assertEqual(raw, port.invocations[0]["response"])


class MixedEscapeStreamingJobTest(StarJobFixture, unittest.TestCase):
    def open_plan(self, replies):
        import os
        with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}):
            adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=256)
        from tests.test_star_product_planning import FEATURES
        from showcase.run_budget import RunBudgetLimits
        self.open_star(replies, SHOWCASE_STAR_FEATURES=FEATURES, SHOWCASE_STAR_ADAPTER=adapter,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16))
        return self.create_job()

    test_mixed_escapes_preserve_text_without_format_reask = (
        protocol_tests.StarProtocolFailureTest.test_mixed_escapes_preserve_text_without_format_reask)
