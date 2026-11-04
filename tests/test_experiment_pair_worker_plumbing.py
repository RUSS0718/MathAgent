"""Pair component settings cross the public Job worker and read-only verifier."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.experiment_pair import pair_manifest_digest, validate_pair_manifest
from showcase.experiment_pair_verification import verify_pair_arm_component_config
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.test_showcase_experiment_pair_cli import _pair


class _Response:
    status_code = 200

    def __init__(self, reply: dict):
        self.reply = reply

    def raise_for_status(self):
        pass

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(self.reply)}}],
            "model": "intern-s2",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class _PublicJobReader:
    def __init__(self, client):
        self.client = client

    def request(self, method, path):
        if method != "GET":
            raise AssertionError("pair verification must be read-only")
        response = self.client.get(path)
        if response.status_code != 200:
            raise RuntimeError("job evidence unavailable")
        return response.get_json()


class ExperimentPairWorkerPlumbingTest(unittest.TestCase):
    def test_pair_manifest_rejects_best_effort_arms(self):
        cases = []
        enabled_feature = _pair("pair-best-effort-feature")
        enabled_feature["baseline"]["features"]["best_effort"] = True
        enabled_feature["variant"]["features"]["best_effort"] = True
        cases.append(enabled_feature)
        enabled_mode = _pair("pair-best-effort-mode")
        enabled_mode["baseline"]["manifest"]["model"]["solver_mode"] = "star_limited_best_effort"
        enabled_mode["variant"]["manifest"]["model"]["solver_mode"] = "star_limited_best_effort"
        cases.append(enabled_mode)
        for pair in cases:
            with self.subTest(pair=pair["pair_id"]):
                with self.assertRaisesRegex(ValueError, "experiment_pair_manifest_invalid"):
                    validate_pair_manifest(pair)

    def test_pair_features_are_applied_persisted_and_independently_read_back(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        report = {"schema_version": 1, "issue_number": 127, "status": "PASS"}
        pair = _pair("pair-worker", report)
        limits = {
            "max_model_calls": 3,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 20000,
            "max_runtime_seconds": 120,
        }
        for arm in ("baseline", "variant"):
            pair[arm]["manifest"]["model"]["solver_mode"] = "star_limited"
            pair[arm]["manifest"]["model"]["verification_mode"] = "auto"
            pair[arm]["manifest"]["run_limits"] = dict(limits)

        replies = {
            "explore": {"assessment": "SOLVED", "worked": ["addition"], "failed": [],
                        "candidates": [], "solution_candidate": "draft: 2"},
            "explore_polish": {"solution_candidate": "1 + 1 = 2."},
            "whole_solution_verifier": {"verdict": "ACCEPT", "reason": "Direct addition."},
        }

        def scripted_response(_url, *, data, **_kwargs):
            request = json.loads(data)
            role = json.loads(request["messages"][-1]["content"])["role"]
            return _Response(replies[role])

        with patch.dict(os.environ, {"INTERN_API_KEY": "test-key"}):
            with patch("llm_client.requests.post", side_effect=scripted_response) as provider:
                app = create_app({
                    "TESTING": True,
                    "SHOWCASE_DATA_DIR": str(Path(temporary.name) / "showcase"),
                    "SHOWCASE_JOB_DELAY_SECONDS": 0,
                    "SHOWCASE_EXPERIMENT_PAIR_ENABLED": True,
                    "SHOWCASE_EXPERIMENT_READINESS_VERIFIER": lambda _report: {"status": "PASS"},
                    "SHOWCASE_STAR_ENABLED": True,
                    "SHOWCASE_STAR_BUDGET": RunBudgetLimits(**limits),
                    "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                        InternChatClient(retry=1), max_tokens=256
                    ),
                    "SHOWCASE_STAR_EVIDENCE_KIND": "scripted",
                })
                self.addCleanup(app.extensions["showcase_workspace_service"].close)
                self.addCleanup(app.extensions["showcase_run_service"].close)
                self.addCleanup(app.extensions["loopback_store"].close)
                client = app.test_client()
                csrf = client.get("/api/check_auth").get_json()["csrf_token"]
                jobs = {}
                for arm in ("baseline", "variant"):
                    session = client.post(
                        "/api/new_chat", headers={"X-CSRF-Token": csrf}
                    ).get_json()["new_session_id"]
                    response = client.post(
                        f"/api/experiments/pairs/{pair['pair_id']}/arms/{arm}/jobs",
                        json={
                            "pair_manifest": pair,
                            "pair_sha256": pair_manifest_digest(pair),
                            "readiness_report": report,
                            "sample_id": "sample-01",
                            "message": "x+1=2\n",
                            "budget_limits": dict(limits),
                            "deadline_at": time.time() + 60,
                            "session_id": session,
                        },
                        headers={
                            "X-CSRF-Token": csrf,
                            "Idempotency-Key": str(uuid.uuid4()),
                        },
                    )
                    self.assertEqual(202, response.status_code, response.get_json())
                    jobs[arm] = response.get_json()["job_id"]

                deadline = time.monotonic() + 8
                observed = {}
                while time.monotonic() < deadline:
                    observed = {
                        arm: client.get(f"/api/agent/jobs/{job_id}").get_json()
                        for arm, job_id in jobs.items()
                    }
                    if all(item["status"] in {"succeeded", "failed", "canceled"}
                           for item in observed.values()):
                        break

                self.assertEqual({"succeeded"}, {item["status"] for item in observed.values()}, observed)
                self.assertEqual(6, provider.call_count)
                for arm in ("baseline", "variant"):
                    binding = observed[arm]["result"]["experiment_pair"]
                    self.assertEqual("applied", binding["applied_config_status"])
                    self.assertEqual(pair[arm]["features"], binding["applied_component_config"])
                    self.assertEqual(pair[arm]["run_id"], binding["arm_run_id"])
                self.assertNotEqual(jobs["baseline"], jobs["variant"])

                reader = _PublicJobReader(client)
                for arm in ("baseline", "variant"):
                    verification = verify_pair_arm_component_config(
                        reader, jobs[arm], pair, arm
                    )
                    self.assertEqual("PASS", verification["status"], verification)
                    self.assertEqual(pair[arm]["features"],
                                     verification["applied_component_config"])

                altered = dict(observed["variant"])
                altered["result"] = dict(altered["result"])
                altered_binding = dict(altered["result"]["experiment_pair"])
                altered_binding["applied_component_config"] = pair["baseline"]["features"]
                altered["result"]["experiment_pair"] = altered_binding
                mismatch = verify_pair_arm_component_config(
                    type("Reader", (), {"request": lambda _self, *_args: altered})(),
                    jobs["variant"], pair, "variant",
                )
                self.assertEqual("FAIL", mismatch["status"])


if __name__ == "__main__":
    unittest.main()
