"""Offline acceptance for the fixed, bounded DeepSeek live pilot."""

import json
import os
import re
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ricl_runtime.live_pilot import _call_with_deadline, run_live_pilot
from ricl_runtime.providers.chat_completions import ChatCompletionReply, ProviderTimeoutError

ENVIRONMENT = {
    "API_KEY": "inert-fixture-key",
    "BASE_URL": "https://api.deepseek.com",
    "MODEL": "deepseek-v4-flash",
}


class LivePilotTests(unittest.TestCase):
    def test_shared_matrix_and_rollback_stay_within_the_approval(self):
        reply = ChatCompletionReply(
            "4",
            model="deepseek-flash",
            input_tokens=100,
            output_tokens=1,
            usage_source="fixture",
            request_id="fixture-request",
            finish_reason="stop",
        )

        def complete(prompt):
            if "Report one public Repair step line" not in prompt:
                return reply
            if "If you use an applicable verified result" in prompt:
                evidence_id = re.search(r"evidence_[0-9a-f]+", prompt).group()
                return replace(
                    reply,
                    text=f"Evidence used: {evidence_id}\n"
                    "Repair step: 2 + 2 = 1 + 1 + 2 = 4\nFinal answer: 4",
                )
            if "Intervention feedback:\nTry regrouping." in prompt:
                return replace(reply, text="Repair step: 2 + 2 = 1 + 1 + 2 = 4\nFinal answer: 4")
            return replace(reply, text="Repair step: 2 + 2 = 4\nFinal answer: 4")

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, ENVIRONMENT),
            patch("ricl_runtime.live_pilot._call_with_deadline", side_effect=complete) as call,
        ):
            root = Path(directory) / "pilot"
            manifest = run_live_pilot(root)
            self.assertEqual(manifest["counts"]["planned"], 9)
            self.assertEqual(manifest["counts"]["status"], {"completed": 9})
            self.assertEqual(manifest["rollback_pair"]["status"], "completed")
            self.assertEqual(manifest["counts"]["intervention_consumed"], 1)
            self.assertGreater(call.call_count, 11)
            self.assertLessEqual(call.call_count, 47)
            self.assertEqual(call.call_count, manifest["provider_attempts"])
            self.assertLessEqual(float(manifest["reserved_cost_usd"]), 0.10)
            repair_runs = {}
            for entry in manifest["runs"]:
                record = json.loads(Path(entry["run"]).read_text(encoding="utf-8"))
                self.assertLessEqual(record["budget"]["model_requests"]["used"], 5)
                self.assertEqual(record["budget"]["tools"]["used"], 0)
                self.assertEqual(record["model"]["actual"], "deepseek-flash")
                if entry["condition_id"] in ("random-repair", "diagnostic-repair"):
                    repair_runs[entry["condition_id"]] = record["intervention"]
                    self.assertEqual(record["branches"]["control"]["request_count"], 1)
                    self.assertEqual(record["branches"]["treatment"]["request_count"], 1)
            self.assertNotEqual(
                repair_runs["random-repair"]["selected_repair_id"],
                repair_runs["diagnostic-repair"]["selected_repair_id"],
            )
            self.assertNotIn(
                "inert-fixture-key", (root / "requests.jsonl").read_text(encoding="utf-8")
            )
            with self.assertRaises(FileExistsError):
                run_live_pilot(root)
            self.assertEqual(call.call_count, manifest["provider_attempts"])

    def test_provider_failure_stops_new_requests_and_retains_the_denominator(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, ENVIRONMENT),
            patch(
                "ricl_runtime.live_pilot._call_with_deadline", side_effect=ProviderTimeoutError()
            ) as call,
        ):
            manifest = run_live_pilot(Path(directory) / "pilot")
        call.assert_called_once()
        self.assertEqual(len(manifest["runs"]), 9)
        self.assertEqual(manifest["rollback_pair"]["status"], "incomplete")
        self.assertEqual(manifest["provider_stop_reason"], "timeout")

    def test_wall_clock_deadline_is_supervised(self):
        with patch(
            "ricl_runtime.live_pilot.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 30),
        ) as worker:
            with self.assertRaises(ProviderTimeoutError):
                _call_with_deadline("Compute 2 + 2.")
        self.assertEqual(worker.call_args.kwargs["timeout"], 30)


if __name__ == "__main__":
    unittest.main()
