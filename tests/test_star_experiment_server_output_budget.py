"""Tests for the registered model output cap enforced by ExperimentServer."""

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_star_readiness_97 import _build_adapter
from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT
from showcase.run_budget import RunBudgetLedger, bind_budget
from showcase.star_experiment_policy import ExperimentRunPolicy
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_v7 import V7_MODEL, V7_ROUND_LIMITS, V7_RUN_LIMITS
from tests.star_experiment_support import LoopbackProvider


class ExperimentServerOutputBudgetTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.provider = LoopbackProvider()
        self.addCleanup(self.provider.close)
        self.policy = ExperimentRunPolicy(0)

    def make_server(self, *, adapter_name="nonstream", max_output_tokens=None):
        kwargs = {} if max_output_tokens is None else {
            "max_output_tokens": max_output_tokens,
        }
        return ExperimentServer(
            self.folder / adapter_name,
            adapter_name,
            self.provider.adapters()[adapter_name],
            self.policy,
            "scripted",
            **kwargs,
        )

    def test_legacy_default_accepts_historical_8192_adapter(self):
        server = self.make_server()
        self.addCleanup(server.close)
        self.assertEqual(8192, server.max_output_tokens)

    def test_explicit_16384_registration_accepts_matching_adapter(self):
        adapter = self.provider.adapters()["nonstream"]
        adapter.max_tokens = 16384
        server = ExperimentServer(
            self.folder / "registered-16384",
            "nonstream",
            adapter,
            self.policy,
            "scripted",
            max_output_tokens=16384,
        )
        self.addCleanup(server.close)
        self.assertEqual(16384, server.max_output_tokens)

    def test_v7_cli_adapter_sends_registered_cap_in_metered_payload(self):
        environment = {
            "INTERN_API_KEY": "test-only-not-a-real-key",
            "INTERN_API_BASE": INTERN_S2_LIVE_ENDPOINT,
            "INTERN_MODEL": "intern-s2",
        }
        body = json.dumps({
            "model": "intern-s2",
            "choices": [{"message": {"content": "fixture answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        }).encode("utf-8")
        run = V7_RUN_LIMITS[0]
        policy = ExperimentRunPolicy(time.time() + V7_ROUND_LIMITS["wall_seconds"])
        policy.prepare({
            "max_model_calls": run["logical_calls"],
            "max_http_attempts": run["http_attempts"],
            "max_tool_calls": run["problem_tool_calls"],
            "max_tokens": run["charged_tokens"],
            "max_runtime_seconds": run["wall_seconds"],
        })
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        budget = ledger.ensure("v7-payload", policy.budget(), deadline_at=policy.deadline_at)

        with patch.dict("os.environ", environment), patch("requests.Session") as session_factory, \
                patch("socket.socket.connect", side_effect=AssertionError("network forbidden")):
            session = session_factory.return_value.__enter__.return_value
            response = session.post.return_value
            response.status_code = 200
            response.iter_content.return_value = [body]
            adapter = _build_adapter({
                "model": dict(V7_MODEL),
                "provider_endpoint": INTERN_S2_LIVE_ENDPOINT,
            })
            server = ExperimentServer(
                self.folder / "v7-payload", "nonstream", adapter, policy, "live",
                request_timeout_seconds=900, max_output_tokens=16384,
            )
            self.addCleanup(server.close)
            with bind_budget(budget):
                result = adapter.complete(
                    [{"role": "user", "content": json.dumps({"role": "explore"})}],
                    metadata={"role": "explore"},
                )

        session.post.assert_called_once()
        self.assertEqual(INTERN_S2_LIVE_ENDPOINT, session.post.call_args.args[0])
        self.assertEqual(16384, json.loads(session.post.call_args.kwargs["data"])["max_tokens"])
        self.assertEqual("fixture answer", result.text)
        self.assertEqual(1, budget.snapshot()["http_attempts"])

    def test_registered_cap_rejects_mismatched_adapter(self):
        with self.assertRaisesRegex(ValueError, "experiment_conditions_mismatch"):
            self.make_server(max_output_tokens=16384)


if __name__ == "__main__":
    unittest.main()
