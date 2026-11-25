"""Offline contracts for the independent RiCL Runtime CLI."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from ricl_runtime import DeterministicModelPort, Runtime
from ricl_runtime.__main__ import main
from ricl_runtime.port import ModelPortFailure
from ricl_runtime.providers.deepseek import DeepSeekModelPort

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class RuntimeOfflineTests(unittest.TestCase):
    """Exercise the Runtime and command-line public boundaries without a Provider."""

    def test_population_cli_rejects_live_provider_before_configuration(self) -> None:
        stderr = StringIO()
        with (
            redirect_stderr(stderr),
            patch("ricl_runtime.__main__.DeepSeekModelPort.from_environment") as load_provider,
            self.assertRaises(SystemExit) as raised,
        ):
            main(["--provider", "deepseek", "--population", "--problem", "Compute 2 + 2."])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--population requires the offline provider", stderr.getvalue())
        load_provider.assert_not_called()

    def test_verification_leaves_ambiguous_answer_text_unknown(self) -> None:
        cases = {
            "The answer is not 4.": "unknown",
            "0.4": "unknown",
            "2 + 2 ≠ 4": "unknown",
            "7 + 1 = 4": "unknown",
            "2 + 2 = 4": "verified",
            "The answer is 5.": "failed",
        }
        with tempfile.TemporaryDirectory() as directory:
            for answer, expected in cases.items():
                with self.subTest(answer=answer):
                    run = Runtime(DeterministicModelPort(answer)).run(
                        "Compute 2 + 2.", output_root=Path(directory)
                    )
                    self.assertEqual(run["result"]["answer"], answer)
                    self.assertEqual(run["verification"]["status"], expected)

    def test_run_persists_answer_verification_budget_and_redacted_trace(self) -> None:
        answer = "Adding the two numbers gives 4."
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort(answer)).run(
                problem="Compute 2 + 2.",
                problem_id="addition-example",
                condition_id="offline-baseline",
                output_root=Path(directory),
            )

            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")
            events = [json.loads(line) for line in trace.splitlines()]

        self.assertEqual(saved, result)
        self.assertEqual(result["result"]["answer"], answer)
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertEqual(result["verification"]["scope"], "integer arithmetic reference check")
        self.assertEqual(result["problem"]["id"], "addition-example")
        self.assertEqual(result["condition_id"], "offline-baseline")
        self.assertEqual(result["run"]["status"], "completed")
        self.assertEqual(result["run"]["stop_reason"], "answer_generated")
        self.assertTrue(result["source"]["revision"])
        self.assertEqual(len(result["config_sha256"]), 64)
        self.assertEqual(result["model"]["requested"], "deterministic-offline")
        self.assertEqual(result["model"]["actual"], "deterministic-offline")
        self.assertEqual(result["budget"]["model_requests"], {"limit": 1, "used": 1})
        self.assertEqual(result["usage"]["tokens"], "unknown")
        self.assertEqual(result["cost"]["amount_usd"], "unknown")
        self.assertEqual(events[-1]["event"], "run_stopped")
        self.assertNotIn("Compute 2 + 2.", trace)
        self.assertNotIn(answer, trace)
        self.assertGreaterEqual(result["provider_requests"][0]["elapsed_ms"], 0)
        self.assertGreaterEqual(events[2]["elapsed_ms"], 0)
        self.assertEqual(
            events[1]["answer_sha256"], hashlib.sha256(answer.encode("utf-8")).hexdigest()
        )

    def test_runtime_normalizes_provider_specific_failure_status(self) -> None:
        class UnclassifiedFailurePort:
            name = "fixture-model"

            def complete(self, problem: str):
                del problem
                failure = ModelPortFailure()
                failure.failure_status = "provider_custom_failure"
                raise failure

        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(UnclassifiedFailurePort()).run(
                "fixture problem",
                output_root=Path(directory),
            )

        self.assertEqual(result["run"]["failure_status"], "unknown_outcome")
        self.assertEqual(
            result["provider_requests"][0]["failure_status"], "unknown_outcome"
        )
        self.assertEqual(result["provider_requests"][0]["status"], "unknown_outcome")

    def test_deepseek_cli_persists_a_redacted_timeout_failure(self) -> None:
        problem = "private fixture problem"
        credential = "inert-fixture-secret"
        base_url = "https://api.deepseek.com/v1"
        opener = Mock()
        opener.open.side_effect = TimeoutError(f"{problem} {credential} {base_url}")
        output = StringIO()

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {"API_KEY": credential, "BASE_URL": base_url, "MODEL": "deepseek-flash"},
            ),
            patch(
                "ricl_runtime.providers.deepseek.urllib.request.build_opener",
                return_value=opener,
            ),
            redirect_stdout(output),
        ):
            exit_code = main(
                [
                    "--provider",
                    "deepseek",
                    "--thinking",
                    "disabled",
                    "--problem",
                    problem,
                    "--output-root",
                    directory,
                ]
            )
            result = json.loads(output.getvalue())
            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertEqual(saved, result)
        self.assertEqual(result["run"]["status"], "failed")
        self.assertEqual(result["run"]["failure_status"], "timeout")
        self.assertEqual(result["run"]["stop_reason"], "timeout")
        self.assertEqual(result["model"]["requested"], "deepseek-flash")
        self.assertEqual(result["model"]["actual"], "unknown")
        self.assertEqual(result["model"]["provider_request_id"], "unknown")
        self.assertEqual(result["usage"]["tokens"], "unknown")
        self.assertEqual(result["usage"]["source"], "unknown")
        self.assertEqual(result["budget"]["model_requests"], {"limit": 1, "used": 1})
        self.assertEqual(result["provider_requests"][0]["status"], "timeout")
        self.assertEqual(result["provider_requests"][0]["failure_status"], "timeout")
        self.assertEqual(opener.open.call_count, 1)
        for secret in (problem, credential, base_url):
            self.assertNotIn(secret, output.getvalue() + json.dumps(saved) + trace)

    def test_completed_protocol_failure_retains_known_usage_and_model(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "id": "provider-protocol-fixture",
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {
                "content": None, "reasoning_content": "private reasoning sentinel",
            }}],
            "usage": {"prompt_tokens": 12, "completion_tokens": -3},
        }).encode()
        opener = Mock()
        opener.open.return_value = response
        port = DeepSeekModelPort("inert-fixture-key", "https://api.deepseek.com/v1", "deepseek-v4-flash")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("ricl_runtime.providers.deepseek.urllib.request.build_opener", return_value=opener),
        ):
            run = Runtime(port).run("Compute 2 + 2.", output_root=Path(directory))
            trace = Path(run["artifacts"]["trace"]).read_text(encoding="utf-8")

        self.assertEqual(run["run"]["stop_reason"], "protocol_failed")
        self.assertEqual(run["model"]["actual"], "deepseek-flash")
        self.assertEqual(run["model"]["provider_request_id"], "provider-protocol-fixture")
        self.assertEqual(run["usage"], {
            "input_tokens": 12, "output_tokens": "unknown", "tokens": "unknown", "source": "provider",
        })
        self.assertEqual(run["provider_requests"][0]["finish_reason"], "stop")
        self.assertIsNone(run["result"])
        self.assertNotIn("private reasoning sentinel", json.dumps(run) + trace)

    def test_deepseek_cli_persists_success_without_secret_configuration(self) -> None:
        credential = "inert-cli-secret"
        base_url = "https://api.deepseek.com/v1"
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "id": "provider-request-fixture",
                "model": "DeepSeek-V4.1-Flash-1017",
                "choices": [{"message": {"content": "4"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }
        ).encode()
        opener = Mock()
        opener.open.return_value = response
        output = StringIO()

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {"API_KEY": credential, "BASE_URL": base_url, "MODEL": "deepseek-v4-flash"},
            ),
            patch(
                "ricl_runtime.providers.deepseek.urllib.request.build_opener",
                return_value=opener,
            ),
            redirect_stdout(output),
        ):
            exit_code = main(
                [
                    "--provider",
                    "deepseek",
                    "--thinking",
                    "enabled",
                    "--problem",
                    "Compute 2 + 2.",
                    "--output-root",
                    directory,
                ]
            )
            result = json.loads(output.getvalue())
            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")

        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(exit_code, 0)
        self.assertEqual(saved, result)
        self.assertEqual(result["run"]["status"], "completed")
        self.assertEqual(result["model"]["requested"], "deepseek-v4-flash")
        self.assertEqual(result["model"]["actual"], "DeepSeek-V4.1-Flash-1017")
        self.assertEqual(result["model"]["provider_request_id"], "provider-request-fixture")
        self.assertIs(result["provider_requests"][0]["request_sent"], True)
        self.assertEqual(result["usage"]["tokens"], 15)
        self.assertEqual(result["usage"]["source"], "provider")
        self.assertEqual(result["config"]["reasoning_config"], {"type": "enabled"})
        self.assertEqual(payload["max_tokens"], 256)
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["model"], "deepseek-v4-flash")
        self.assertNotIn("tools", payload)
        self.assertEqual(opener.open.call_count, 1)
        self.assertNotIn(credential, output.getvalue() + json.dumps(saved) + trace)
        self.assertNotIn(base_url, output.getvalue() + json.dumps(saved) + trace)

    def test_deepseek_cli_rejects_oversized_prompt_before_request(self) -> None:
        credential = "inert-cli-secret"
        base_url = "https://api.deepseek.com/v1"
        problem = "x" * (16 * 1024 + 1)
        opener = Mock()
        output = StringIO()

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(
                os.environ,
                {"API_KEY": credential, "BASE_URL": base_url, "MODEL": "deepseek-flash"},
            ),
            patch(
                "ricl_runtime.providers.deepseek.urllib.request.build_opener",
                return_value=opener,
            ),
            redirect_stdout(output),
        ):
            exit_code = main(
                [
                    "--provider",
                    "deepseek",
                    "--thinking",
                    "enabled",
                    "--problem",
                    problem,
                    "--output-root",
                    directory,
                ]
            )
            result = json.loads(output.getvalue())
            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")

        self.assertEqual(exit_code, 1)
        self.assertEqual(saved, result)
        self.assertEqual(result["run"]["failure_status"], "preflight_rejected")
        self.assertEqual(result["provider_requests"][0]["status"], "preflight_rejected")
        self.assertEqual(
            result["provider_requests"][0]["failure_status"], "preflight_rejected"
        )
        self.assertIs(result["provider_requests"][0]["request_sent"], False)
        self.assertEqual(result["budget"]["cost_usd"]["limit"], 0.05)
        self.assertEqual(
            result["budget"]["cost_usd"]["preflight_upper_bound"], "0.0055296"
        )
        self.assertEqual(result["budget"]["cost_usd"]["used"], "unknown")
        self.assertEqual(result["config"]["provider_config"]["cost_limit_usd"], 0.05)
        self.assertEqual(
            result["config"]["provider_config"]["preflight_cost_upper_bound_usd"], "0.0055296"
        )
        opener.open.assert_not_called()
        for secret in (problem, credential, base_url):
            self.assertNotIn(secret, output.getvalue() + json.dumps(saved) + trace)

    def test_missing_independent_criterion_is_explicitly_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("Every prime is odd.")).run(
                problem="Prove every prime number is odd.",
                problem_id="unsupported-proof",
                condition_id="offline-baseline",
                output_root=Path(directory),
            )

        self.assertEqual(result["verification"]["status"], "unknown")
        self.assertEqual(result["verification"]["scope"], "none")
        self.assertEqual(result["verification"]["reason"], "no_applicable_criterion")
        self.assertEqual(result["result"]["answer"], "Every prime is odd.")

    def test_incorrect_integer_candidate_is_not_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = Runtime(DeterministicModelPort("The answer is 5.")).run(
                problem="Compute 2 + 2.",
                output_root=Path(directory),
            )

        self.assertEqual(result["verification"]["status"], "failed")
        self.assertEqual(result["verification"]["reason"], "answer_differs_from_reference")

    def test_cli_output_matches_saved_offline_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ricl_runtime",
                    "--problem",
                    "Compute 2 + 2.",
                    "--offline-answer",
                    "The sum is 4.",
                    "--problem-id",
                    "addition-example",
                    "--condition-id",
                    "offline-baseline",
                    "--output-root",
                    directory,
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            result = json.loads(completed.stdout)
            run_dir = Path(directory) / result["run_id"]
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")

        self.assertEqual(saved, result)
        self.assertEqual(result["result"]["answer"], "The sum is 4.")
        self.assertEqual(result["verification"]["status"], "verified")
        self.assertIs(result["provider_requests"][0]["request_sent"], False)
        self.assertTrue(trace)


if __name__ == "__main__":
    unittest.main()
