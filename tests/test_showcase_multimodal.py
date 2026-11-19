from __future__ import annotations

import io
import json
import os
import struct
import tempfile
import time
import unittest
import uuid
import zlib
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.graph import ToolExecutionResult
from showcase.image_intake import classify_problem
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry
from tests.reviewer_support import reviewer_client
from tests.test_live_tool_workspace import ProviderResponse, _native_tool_response
from tests.test_live_workspace_pipeline import StubLivePipeline

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cf00000004000101e2dd0000000049454e44ae426082')


class ImageReply:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"finish_reason": "stop", "message": {"content": self.content}}]}


class Pipeline(StubLivePipeline):
    def __init__(self):
        self.model = InternModelAdapter(InternChatClient(retry=1))
        self.problems = []

    def run(self, run_id, problem, **kwargs):
        self.problems.append(problem)
        return super().run(run_id, problem, **kwargs)


class ShowcaseMultimodalTest(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "unused-test-key"}))
        self.reply = ImageReply()
        self.reply.content = json.dumps({"image_text": "求解 x+1=2。", "problem_type": "equation"})
        self.post = self.enterContext(patch("llm_client.requests.post", return_value=self.reply))
        self.pipeline = Pipeline()
        self.app = create_app({"TESTING": True, "SHOWCASE_MODE": "live", "SHOWCASE_VISION_ENABLED": True,
                               "SHOWCASE_DATA_DIR": root, "SHOWCASE_JOB_DELAY_SECONDS": 0,
                               "SHOWCASE_LIVE_PIPELINE": self.pipeline})
        for key in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[key].close)
        self.client = self.app.test_client()
        self.headers = {"X-CSRF-Token": self.client.get("/api/check_auth").json["csrf_token"],
                        "Idempotency-Key": str(uuid.uuid4())}
        self.session = self.client.post("/api/new_chat", headers=self.headers).json["new_session_id"]

    def submit(self, message, image=False, **options):
        payload = {"message": message, "session_id": self.session, **options}
        if image:
            upload = self.client.post("/api/upload_file", data={"file": (io.BytesIO(PNG), "question.png")},
                                      headers=self.headers)
            self.assertEqual(201, upload.status_code)
            payload["input_user_file_id"] = upload.json["file"]["file_id"]
        response = self.client.post("/api/agent/jobs", json=payload, headers=self.headers)
        self.assertEqual(202, response.status_code, response.json)
        path = f"/api/agent/jobs/{response.json['job_id']}"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = self.client.get(path).json
            if job["status"] in {"succeeded", "failed"}:
                return path, job, payload
            time.sleep(0.01)
        self.fail(f"Job did not finish: {job}")

    def test_image_only_uses_vision_then_saves_a_readable_snapshot_once(self):
        path, job, payload = self.submit("", image=True)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(["求解 x+1=2。"], self.pipeline.problems)
        self.assertEqual({"modality": "image", "status": "ready", "problem_type": "equation"}, job["result"]["input_intake"])
        content = json.loads(self.post.call_args.kwargs["data"])["messages"][-1]["content"]
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))
        removed = self.client.post("/api/delete_file", json={"file_id": payload["input_user_file_id"]},
                                   headers=self.headers)
        self.assertEqual(200, removed.status_code)
        duplicate = self.client.post("/api/agent/jobs", json=payload, headers=self.headers)
        self.assertEqual(200, duplicate.status_code)
        self.assertEqual(job["job_id"], duplicate.json["job_id"])
        conflict = self.client.post("/api/agent/jobs", json={**payload, "message": "Different question"},
                                    headers=self.headers)
        self.assertEqual(409, conflict.status_code)
        fresh_headers = {**self.headers, "Idempotency-Key": str(uuid.uuid4())}
        missing = self.client.post("/api/agent/jobs", json=payload, headers=fresh_headers)
        self.assertEqual(404, missing.status_code)
        self.assertEqual(job, self.client.get(path).json)
        self.assertEqual(1, self.post.call_count)
        reviewer, _ = reviewer_client(self.app)
        budget = reviewer.get(path).json["result"]["budget"]
        self.assertEqual(1, budget["logical_calls"])
        self.assertEqual(1, budget["http_attempts"])
        run = reviewer.get(f"/api/runs/{job['job_id']}").json
        self.assertEqual("implemented", run["vision_status"])
        self.assertEqual("implemented", reviewer.get(path + "/report").json["report"]["asset_refs"][0]["vision_status"])
        for url in (path, path + "/report", f"/api/runs/{job['job_id']}", f"/api/runs/{job['job_id']}/evidence"):
            raw = reviewer.get(url).get_data(as_text=True)
            self.assertNotIn("base64", raw)
            self.assertNotIn("image_text", raw)

    def test_text_and_image_both_reach_solver(self):
        _, job, _ = self.submit("请保留计算过程。", image=True)
        self.assertEqual("succeeded", job["status"], job)
        self.assertIn("请保留计算过程。", self.pipeline.problems[0])
        self.assertIn("求解 x+1=2。", self.pipeline.problems[0])
        self.assertEqual("text_image", job["result"]["input_intake"]["modality"])

    def test_image_only_can_finish_after_a_python_tool_timeout(self):
        registry = ToolRegistry()
        registry.register_python_math()
        self.app.extensions["showcase_workspace_service"].pipeline = LiveAgentPipeline(self.pipeline.model, registry)
        self.post.side_effect = [
            self.reply,
            ProviderResponse({"content": "Solve and check by substitution."}),
            _native_tool_response("timed-out", "python_math", {"code": "print(1)"}),
            ProviderResponse({"content": "Subtract 1 from both sides: x = 1."}),
            ProviderResponse({"content": "x = 1; no tool evidence."}),
        ]
        with patch.object(registry, "invoke", return_value=ToolExecutionResult(
            status="timeout", error_category="tool_timeout", tool_call_id="timed-out",
        )) as invoke:
            path, job, _ = self.submit("", image=True)
        self.assertEqual("succeeded", job["status"], job.get("error"))
        self.assertEqual("ready", job["result"]["input_intake"]["status"])
        invoke.assert_called_once()
        self.assertEqual(5, self.post.call_count)
        continuation = json.loads(self.post.call_args_list[3].kwargs["data"])
        self.assertNotIn("tools", continuation)
        receipt = continuation["messages"][-1]
        self.assertEqual("timed-out", receipt["tool_call_id"])
        self.assertEqual("timeout", json.loads(receipt["content"])["status"])
        reviewer, _ = reviewer_client(self.app)
        result = reviewer.get(path).json["result"]
        self.assertIn("x = 1", result["final_response"])
        self.assertEqual("tool_timeout", result["tool_results"][0]["error_category"])
        self.assertNotEqual("pass", result["verification"]["status"])

    def test_invalid_transcription_does_not_solve_only_the_caption(self):
        self.reply.content = '{"image_text": null, "problem_type": "unknown"}'
        _, job, _ = self.submit("请看图。", image=True)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("image_problem_unreadable", job["result"]["input_intake"]["error"])
        self.assertEqual([], self.pipeline.problems)

    def test_image_request_obeys_the_existing_job_budget(self):
        limits = {"max_model_calls": 6, "max_http_attempts": 6, "max_tool_calls": 0,
                  "max_tokens": 100, "max_runtime_seconds": 60}
        _, job, _ = self.submit("", image=True, budget_limits=limits, deadline_at=time.time()+45)
        self.assertEqual("failed", job["status"], job)
        self.assertEqual("run_budget_exhausted", job["result"]["input_intake"]["error"])
        self.assertEqual([], self.pipeline.problems)
        self.post.assert_not_called()

    def test_text_type_is_recognized_without_an_extra_model_request(self):
        _, job, _ = self.submit("求三角形 ABC 的面积")
        self.assertEqual("geometry", job["result"]["input_intake"]["problem_type"])
        self.assertEqual(["求三角形 ABC 的面积"], self.pipeline.problems)
        self.post.assert_not_called()

    def test_png_limit_reserves_room_for_the_default_budget(self):
        size = 128 * 1024
        self.assertEqual(size, self.client.get("/api/capabilities").json["files"]["upload"]["max_bytes"])
        for length in (size, size + 1):
            padding = b"tEXt" + b"Comment\0" + b" " * (length - len(PNG) - 20)
            image = PNG[:-12] + struct.pack(">I", len(padding) - 4) + padding + struct.pack(">I", zlib.crc32(padding)) + PNG[-12:]
            self.assertEqual(length, len(image))
            upload = self.client.post("/api/upload_file", data={"file": (io.BytesIO(image), "question.png")},
                                      headers=self.headers)
            if length == size:
                self.assertEqual(201, upload.status_code)
                _, job, _ = self.submit("", input_user_file_id=upload.json["file"]["file_id"])
                self.assertEqual("succeeded", job["status"], job)
                self.assertEqual(1, self.post.call_count)
            else:
                self.assertEqual(413, upload.status_code)
                self.assertEqual("image_too_large", upload.json["error"])

    def test_basic_type_hints_prefer_intent_over_symbols(self):
        for question, expected in (
            ("Calculate x+1 given x=2", "calculation"), ("求解 x²=4", "equation"),
            ("x ≤ 5", "inequality"), ("求三角形 ABC 的面积", "geometry"),
            ("求事件 A 的概率", "probability_statistics"), ("证明 x²≥0", "proof"),
            ("分析给定对象之间的关系。", "unknown"),
        ):
            with self.subTest(question=question):
                self.assertEqual(expected, classify_problem(question))

    def test_interrupted_image_intake_is_not_resent_on_resume(self):
        upload = self.client.post("/api/upload_file", data={"file": (io.BytesIO(PNG), "question.png")},
                                  headers=self.headers)
        service = self.app.extensions["showcase_workspace_service"]
        with patch.object(service, "_submit"):
            response = self.client.post("/api/agent/jobs", headers=self.headers, json={
                "session_id": self.session, "input_user_file_id": upload.json["file"]["file_id"],
            })
        self.assertEqual(202, response.status_code)
        job_id = response.json["job_id"]

        class WorkerStopped(BaseException):
            pass
        with patch.object(service.store, "set_image_intake", side_effect=WorkerStopped), self.assertRaises(WorkerStopped):
            service._execute(job_id)
        self.assertEqual(1, self.post.call_count)
        service.store.recover_incomplete_jobs()
        path = f"/api/agent/jobs/{job_id}"
        job = self.client.get(path).json
        self.assertEqual("failed", job["status"])
        self.assertEqual("image_intake_interrupted", job["result"]["input_intake"]["error"])
        resumed = self.client.post(path + "/resume", json={}, headers=self.headers)
        self.assertEqual(409, resumed.status_code)
        self.assertEqual(1, self.post.call_count)
        self.assertEqual([], self.pipeline.problems)
