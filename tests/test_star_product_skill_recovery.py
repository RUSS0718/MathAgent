"""Role Skills are restored through the public Job boundary without Run leakage."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app
from tests import star_recovery_worker
from tests.star_product_support import StarJobFixture


def _worker_script():
    return r"""
import json
import sys
from pathlib import Path
import tests.star_recovery_worker as worker

base_config = worker.config
base_provider = worker.provider

def config(folder, *, crash_tools=False):
    result = base_config(folder, crash_tools=crash_tools)
    result["SHOWCASE_STAR_FEATURES"] = {
        **result["SHOWCASE_STAR_FEATURES"], "skills": True, "meta_guidance": True,
    }
    return result

def provider(folder, request):
    wire = json.loads(request["data"])
    context = json.loads(wire["messages"][-1]["content"])
    with (Path(folder) / "wire_requests.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps({"context": context, "messages": wire["messages"]}) + "\n")
    return base_provider(folder, request)

worker.config = config
worker.provider = provider
worker.main()
"""


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _protocols(messages):
    for message in messages:
        if message.get("role") != "system":
            continue
        try:
            layer = json.loads(message["content"])
        except (KeyError, TypeError, ValueError):
            continue
        if layer.get("kind") == "protocols":
            return layer["protocols"]
    return []


class StarSkillRecoveryTest(StarJobFixture, unittest.TestCase):
    def test_public_job_resume_reloads_role_skills_and_isolates_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            child = subprocess.run(
                [sys.executable, "-c", _worker_script(), directory, "guidance_decided"],
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(71, child.returncode, child.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text(encoding="utf-8")
            before = _read_jsonl(folder / "wire_requests.jsonl")
            self.assertTrue(before)
            self.assertTrue(any(
                row["context"].get("role") == "meta"
                and "meta-intervention-protocol" in row["context"].get("active_skill_ids", [])
                for row in before
            ))

            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                "llm_client.requests.post",
                side_effect=lambda *args, **kwargs: self._audit_provider(folder, kwargs),
            ):
                app_config = star_recovery_worker.config(folder)
                app_config["SHOWCASE_STAR_FEATURES"] = {
                    **app_config["SHOWCASE_STAR_FEATURES"],
                    "skills": True,
                    "meta_guidance": True,
                }
                app = create_app(app_config)
                try:
                    self.app = app
                    self.client = app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    failed = self.job(job_id)
                    self.assertEqual("failed", failed["status"], failed)
                    session_id = failed["session_id"]

                    resumed = self.client.post(
                        f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
                    )
                    self.assertEqual(202, resumed.status_code, resumed.get_json())
                    self.assertEqual("succeeded", self.terminal(job_id)["status"])

                    rows = _read_jsonl(folder / "wire_requests.jsonl")
                    first_run_rows = [row for row in rows if row["context"].get("run_id") == job_id]
                    resumed_meta = [row for row in first_run_rows if row["context"].get("role") == "meta"]
                    self.assertGreaterEqual(len(resumed_meta), 2)
                    for protocol_id in ("meta-intervention-protocol", "math-solving-strategies"):
                        self.assertIn(protocol_id, resumed_meta[-1]["context"]["active_skill_ids"])
                    versions = {item["id"]: item["version"] for item in _protocols(resumed_meta[-1]["messages"])}
                    self.assertEqual("1", versions["meta-intervention-protocol"])
                    self.assertEqual("1", versions["math-solving-strategies"])

                    def second_reply(_window, context, _folder):
                        if context["role"] == "explore":
                            return {"assessment": "SOLVED", "worked": [], "failed": [],
                                    "candidates": [], "solution_candidate": "2"}
                        if context["role"] == "explore_polish":
                            return {"solution_candidate": "1+1=2 SECOND-RUN"}
                        if context["role"] == "final_generator":
                            return {"final_response": "1+1=2 SECOND-RUN"}
                        if context["role"] == "whole_solution_verifier":
                            return {"verdict": "ACCEPT", "reason": "Addition"}
                        return {}
                    with patch.object(star_recovery_worker, "reply_value", side_effect=second_reply):
                        created = self.client.post(
                            "/api/agent/jobs",
                            json={"message": "1+1", "session_id": session_id,
                                  "solver_mode": "star_limited"},
                            headers=self.headers(),
                        )
                        self.assertEqual(202, created.status_code, created.get_json())
                        second_job_id = created.get_json()["job_id"]
                        second = self.terminal(second_job_id)
                    self.assertEqual("succeeded", second["status"], second)

                    rows = _read_jsonl(folder / "wire_requests.jsonl")
                    second_run_rows = [row for row in rows
                                       if row["context"].get("run_id") == second_job_id]
                    self.assertTrue(second_run_rows)
                    self.assertTrue(all(
                        "REDO_FROM_SENTINEL" not in json.dumps(row, ensure_ascii=False)
                        for row in second_run_rows
                    ))
                    explore = next(row for row in second_run_rows
                                   if row["context"].get("role") == "explore")
                    self.assertEqual(["exploration-protocol"], explore["context"]["active_skill_ids"])
                    self.assertEqual("1", _protocols(explore["messages"])[0]["version"])
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        app.extensions[name].close()

    @staticmethod
    def _audit_provider(folder, request):
        wire = json.loads(request["data"])
        context = json.loads(wire["messages"][-1]["content"])
        with (folder / "wire_requests.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps({"context": context, "messages": wire["messages"]}) + "\n")
        return star_recovery_worker.provider(folder, request)


if __name__ == "__main__":
    unittest.main()
