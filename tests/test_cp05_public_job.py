"""Public Job acceptance contracts for CP-05 checkpoint integration."""

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
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits


PLAN = {
    "version": 1,
    "steps": [{"step_id": "s1", "title": "proof", "objective": "derive the result"}],
}


def planner_checkpoint(status="YIELD", marker="planner-draft", *, gaps=None):
    return {
        "protocol_version": 1,
        "checkpoint_id": marker,
        "status": status,
        "objective": "derive the result",
        "dependencies": ["known fact"],
        "evidence": [marker],
        "gaps": ["close the implication"] if gaps is None else gaps,
        "next_action": "close the implication",
    }


def reasoner_checkpoint(status="YIELD", marker="reasoner-draft", *, blocked=False):
    return {
        "checkpoint": {
            "protocol_version": 1,
            "checkpoint_id": marker,
            "status": status,
            "objective": "derive the result",
            "argument": marker,
            "claims": [{"statement": marker, "label": "hard-verify"}],
            "blocked": blocked,
            "dependencies": [],
            "evidence": [marker],
            "gaps": ["close the implication"] if status == "YIELD" else [],
            "next_action": "close the implication",
        }
    }


class _JsonResponse:
    status_code = 200

    def __init__(self, value):
        self.value = value

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(self.value)}}],
            "model": "intern-s2",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
        }


class CP05PublicJobTest(unittest.TestCase):
    def open_app(self, replies):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.requests = []
        remaining = list(replies)

        def post(*_args, **kwargs):
            payload = json.loads(kwargs["data"])
            context = json.loads(payload["messages"][-1]["content"])
            self.requests.append(context)
            return _JsonResponse(remaining.pop(0))

        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        self.enterContext(patch("llm_client.requests.post", side_effect=post))
        app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": str(Path(directory.name) / "showcase"),
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_FEATURES": {
                "final_generation": True,
                "final_solution_review": True,
                "meta_guidance": True,
                "planner_checkpoints": True,
                "reasoner_checkpoints": True,
            },
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
                max_model_calls=12, max_http_attempts=12, max_tool_calls=0
            ),
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                InternChatClient(retry=1), max_tokens=256
            ),
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(app.extensions[name].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        return client, headers, session

    def wait_for_terminal(self, client, job_id):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(0.01)
        self.fail("CP-05 public Job did not reach a terminal state")

    def test_non_stream_checkpoint_job_covers_handoff_meta_and_final_review(self):
        replies = [
            {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []},
            {"checkpoint": planner_checkpoint()},
            {"checkpoint": planner_checkpoint("FINAL", "planner-final", gaps=[]), "plan": PLAN},
            reasoner_checkpoint(blocked=True),
            {
                "action_type": "retry_different_method",
                "specific_task": "close the implication symbolically",
                "use_pure_reasoning": True,
                "trace_back_to": None,
                "rationale": "the first route is blocked",
            },
            reasoner_checkpoint("FINAL", "reasoner-final"),
            {
                "goal_gate": "YES",
                "logic_gate": "PASS",
                "verdict": "ACCEPT",
                "objection": "",
            },
            {"final_response": "The result follows from the accepted proof."},
            {"verdict": "ACCEPT", "reason": "The complete candidate is consistent."},
        ]
        client, headers, session = self.open_app(replies)
        created = client.post(
            "/api/agent/jobs",
            json={"message": "prove the result", "session_id": session, "solver_mode": "star_limited"},
            headers=headers,
        )
        self.assertEqual(202, created.status_code, created.get_json())
        job_id = created.get_json()["job_id"]
        job = self.wait_for_terminal(client, job_id)

        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(
            [
                "explore",
                "planner",
                "planner",
                "reasoner",
                "meta",
                "reasoner",
                "step_verifier",
                "final_generator",
                "whole_solution_verifier",
            ],
            [request["role"] for request in self.requests],
        )
        self.assertTrue(job["result"]["solver"]["progress"]["steps"][0]["reported"])
        self.assertEqual("completed", job["result"]["solver"]["semantics"]["execution"])
        self.assertEqual("accepted", job["result"]["solver"]["semantics"]["whole_review"])
        self.assertEqual("The result follows from the accepted proof.", job["result"]["final_response"])

        stream = client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("checkpoint_status", stream)
        self.assertIn("meta_guidance_decided", stream)
        self.assertNotIn("prove the result", stream)
        self.assertNotIn("close the implication symbolically", stream)

    def test_checkpoint_feature_switch_is_rejected_only_when_unknown_and_disabled_path_stays_legacy(self):
        from showcase.run_budget import RunBudgetLimits
        from showcase.star_product_config import limited_config

        disabled = limited_config(RunBudgetLimits(3, 3, 0))
        self.assertNotIn("planner_checkpoints", disabled["features"])
        self.assertNotIn("reasoner_checkpoints", disabled["features"])
        enabled = limited_config(
            RunBudgetLimits(3, 3, 0),
            {"planner_checkpoints": True, "reasoner_checkpoints": True},
        )
        self.assertTrue(enabled["features"]["planner_checkpoints"])
        self.assertTrue(enabled["features"]["reasoner_checkpoints"])
        with self.assertRaisesRegex(ValueError, "star_features_invalid"):
            limited_config(RunBudgetLimits(3, 3, 0), {"unknown_checkpoint": True})


class CP05DocumentationContractTest(unittest.TestCase):
    def test_handoff_document_records_scope_and_evidence_boundary(self):
        document = Path("docs/evals/showcase-cp05-checkpoint-handoff.md").read_text(
            encoding="utf-8"
        )
        for marker in (
            "CP-01..CP-04",
            "#112",
            "loopback",
            "replay",
            "provider-live",
            "unknown",
            "not_run",
            "deadline",
            "脱敏",
            "静默",
            "无正文",
            "缺 usage",
            "断流",
            "取消",
            "迟到",
        ):
            self.assertIn(marker, document)
        self.assertNotIn("INTERN_API_KEY", document)
        self.assertNotIn("Obey this exact response schema", document)


if __name__ == "__main__":
    unittest.main()
