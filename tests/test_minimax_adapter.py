"""Offline acceptance of the MiniMax gateway through the shared Runtime CLI."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from ricl_runtime.__main__ import main
from ricl_runtime.providers.chat_completions import ProviderPreflightError
from ricl_runtime.providers.minimax import GATEWAY_ROOT, MODEL_ID, MiniMaxModelPort


def price_table():
    return {
        "success": True,
        "data": [
            {
                "model_name": MODEL_ID,
                "quota_type": 0,
                "model_ratio": 0.5,
                "completion_ratio": 4,
                "enable_groups": ["a", "b"],
                "supported_endpoint_types": ["openai"],
            }
        ],
        "group_ratio": {"a": 0.04, "b": 0.075},
    }


class MiniMaxAdapterTests(unittest.TestCase):
    def test_cli_uses_the_selected_model_and_persists_only_the_final_answer(self):
        problem = "Compute 2 + 2."
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "id": "minimax-fixture-request",
                "model": "MiniMax-M3.1-Flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": "<think>inline secret reasoning</think>2 + 2 = 4",
                            "reasoning_content": "separate secret reasoning",
                        },
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 44},
            }
        ).encode()
        opener = MagicMock()
        opener.open.return_value = response
        output = StringIO()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {
                    "API_KEY": "fake-key",
                    "BASE_URL": GATEWAY_ROOT,
                    "MODEL": "unrelated",
                    "MINIMAX_MODEL": MODEL_ID,
                },
            ),
            patch(
                "ricl_runtime.providers.minimax.read_json",
                side_effect=[
                    price_table(),
                    {"success": True, "data": {"quota_per_unit": 500_000}},
                ],
            ) as rates,
            patch(
                "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
                return_value=opener,
            ),
            redirect_stdout(output),
        ):
            status = main(
                [
                    "--provider",
                    "minimax",
                    "--thinking",
                    "enabled",
                    "--problem",
                    problem,
                    "--output-root",
                    directory,
                ]
            )
            run = json.loads(output.getvalue())
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")
        self.assertEqual(status, 0)
        self.assertEqual(run["verification"]["status"], "verified")
        self.assertEqual(run["result"]["answer"], "2 + 2 = 4")
        self.assertEqual(run["model"]["requested"], MODEL_ID)
        self.assertEqual(run["model"]["actual"], "MiniMax-M3.1-Flash")
        self.assertEqual(run["model"]["reasoning_config"], {"type": "enabled", "effort": "low"})
        self.assertEqual(run["usage"]["output_tokens"], 44)
        self.assertEqual(
            Decimal(run["budget"]["cost_usd"]["preflight_upper_bound"]), Decimal("0.00015465")
        )
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, GATEWAY_ROOT + "/v1/chat/completions")
        self.assertEqual(
            json.loads(request.data),
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": problem}],
                "reasoning_effort": "low",
                "max_tokens": 256,
            },
        )
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        for call in rates.call_args_list:
            self.assertEqual(call.args[0].header_items(), [])
        for private in (
            "fake-key",
            "inline secret reasoning",
            "separate secret reasoning",
            problem,
        ):
            self.assertNotIn(private, output.getvalue() + trace)

    def test_unknown_or_excessive_pricing_blocks_the_model_post(self):
        excessive = price_table()
        excessive["group_ratio"]["b"] = 100
        for pricing in ({"success": False}, excessive):
            with (
                self.subTest(pricing=pricing),
                patch(
                    "ricl_runtime.providers.minimax.read_json",
                    side_effect=[
                        pricing,
                        {"success": True, "data": {"quota_per_unit": 500_000}},
                    ],
                ),
                patch("ricl_runtime.providers.minimax.post_chat_completion") as post,
            ):
                with self.assertRaises(ProviderPreflightError):
                    MiniMaxModelPort("fake-key", GATEWAY_ROOT, MODEL_ID).complete("Compute 2 + 2.")
                post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
