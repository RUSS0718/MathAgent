"""Public Job acceptance for opt-in isolated Python and its artifact contract."""

import hashlib
import json
import os
import subprocess
import time
import unittest
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from showcase.flask_app import create_app
from showcase.python_executor import DockerPythonExecutor
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")
FEATURES = {"final_generation": True, "final_solution_review": True, "local_code_tool": True}
NEED_PLAN = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
PLAN = {"version": 1, "steps": [{"step_id": "factor", "title": "Factor", "objective": "Factor x^2-1"}]}
CODE = "import sympy as sp\nx=sp.symbols('x')\nprint(sp.factor(x**2-1))"
EXPECTED = "(x - 1)*(x + 1)\n"
STEP = {"argument": "Factor the difference of squares", "blocked": False, "claims": [{
    "statement": "x^2 - 1 = (x - 1)(x + 1)", "label": "easy-verify", "tool_request": {
        "tool": "python_math", "arguments": {"code": CODE},
        "scope": "finite_computation", "expected_output": EXPECTED}}]}
VERDICT = {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT", "objection": ""}
FINAL = {"final_response": "x^2 - 1 = (x - 1)(x + 1)."}
ACCEPT = {"verdict": "ACCEPT", "reason": "The factorization is correct."}


def docker_events(run_id):
    now = datetime.now(UTC)
    since = (now - timedelta(seconds=30)).isoformat().replace("+00:00", "Z")
    until = (now + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    result = subprocess.run([
        "docker", "events", "--since", since, "--until", until,
        "--filter", "type=container", "--filter", f"label=mathagent.run_id={run_id}",
        "--format", "{{json .}}",
    ], capture_output=True, text=True, timeout=5, check=False)
    if result.returncode:
        raise AssertionError(result.stderr)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


@unittest.skipUnless(IMAGE, "set MATHAGENT_TEST_PYTHON_IMAGE to a validated local exact image ID")
class StarProductPythonTest(StarJobFixture, unittest.TestCase):
    # Observe the 20s tool allowance plus Docker lifecycle and Job persistence;
    # this test-only window does not change any execution deadline.
    observation_timeout_seconds = 40

    def setUp(self):
        # open_star keeps its API-key patch until cleanup; its environment
        # snapshot includes the enclosing image patch. Restore the original
        # image last so that nested patch cleanup cannot enable tools later.
        original = os.environ.get("SHOWCASE_STAR_PYTHON_IMAGE_ID")
        self.addCleanup(lambda: os.environ.pop("SHOWCASE_STAR_PYTHON_IMAGE_ID", None)
                        if original is None else os.environ.__setitem__(
                            "SHOWCASE_STAR_PYTHON_IMAGE_ID", original))

    def test_public_job_runs_registered_python_once_and_keeps_verified_artifacts(self):
        self.assert_registered_python_job_and_artifacts()

    def test_slow_docker_metadata_keeps_public_job_and_artifact_contract(self):
        original_command = DockerPythonExecutor._command
        delayed = []

        def command(args):
            if args[:2] == ["image", "inspect"] and not delayed:
                delayed.append(True)
                # A metadata response within its 15s command allowance can
                # arrive after the ordinary scripted Job's 8s observation.
                time.sleep(8.25)
            return original_command(args)

        with patch.object(DockerPythonExecutor, "_command", staticmethod(command)):
            self.assert_registered_python_job_and_artifacts()
        self.assertEqual([True], delayed)

    def assert_registered_python_job_and_artifacts(self):
        with patch.dict(os.environ, {"SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE}):
            self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, FINAL, ACCEPT],
                SHOWCASE_STAR_EVIDENCE_KIND="scripted",
                SHOWCASE_STAR_FEATURES=FEATURES,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("scripted", job["result"]["evidence_kind"])
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual(1, report["budget"]["tool_calls"])
        self.assertEqual(1, len(job["result"]["tool_results"]))
        tool = job["result"]["tool_results"][0]
        receipt = tool["receipt"]
        self.assertEqual("success", tool["status"])
        self.assertEqual("docker_isolated", receipt["source"])
        self.assertEqual(0, receipt["exit_code"])
        self.assertTrue(receipt["executed"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertEqual(IMAGE, receipt["image"])
        self.assertEqual("docker-python-v1", receipt["sandbox_policy_version"])
        self.assertEqual({"image_id": IMAGE, "policy": "docker-python-v1",
            "base_sha256": "b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377",
            "python": "3.11.17",
            "libraries": {"sympy": "1.14.0", "numpy": "2.3.4", "mpmath": "1.3.0"}},
            receipt["environment"])
        refs = {key: receipt[key] for key in ("code_ref", "input_ref", "stdout_ref", "stderr_ref", "receipt_ref")}
        contents = {}
        for key, reference in refs.items():
            response = self.client.get(
                f"/api/agent/jobs/{job_id}/artifacts/{reference['sha256']}")
            self.assertEqual(200, response.status_code, response.get_json())
            contents[key] = response.data
            self.assertEqual(reference["sha256"], hashlib.sha256(response.data).hexdigest())
        unauthenticated = self.app.test_client().get(
            f"/api/agent/jobs/{job_id}/artifacts/{refs['code_ref']['sha256']}")
        self.assertEqual(401, unauthenticated.status_code)
        malformed = self.client.get(f"/api/agent/jobs/{job_id}/artifacts/not-a-sha256-digest")
        self.assertEqual(409, malformed.status_code)
        missing = self.client.get(f"/api/agent/jobs/{job_id}/artifacts/{'0' * 64}")
        self.assertEqual(404, missing.status_code)
        self.assertEqual(CODE.encode(), contents["code_ref"])
        self.assertEqual({"code": CODE}, json.loads(contents["input_ref"]))
        self.assertEqual(EXPECTED.encode(), contents["stdout_ref"])
        stored_receipt = json.loads(contents["receipt_ref"])
        self.assertEqual(IMAGE, stored_receipt["image"])
        self.assertEqual(receipt["input_ref"], stored_receipt["input_ref"])
        events = docker_events(job_id)
        self.assertEqual(1, sum(event.get("Action") == "create" for event in events))
        self.assertEqual(1, sum(event.get("Action") == "destroy" for event in events))
        for surface in (job, report, self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)):
            serialized = json.dumps(surface, ensure_ascii=False) if not isinstance(surface, str) else surface
            self.assertNotIn(CODE, serialized)
            self.assertNotIn(EXPECTED, serialized)

        cookie = self.client.get_cookie("auth_session")
        reopened = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": self.app.config["SHOWCASE_DATA_DIR"],
            "SHOWCASE_STAR_ENABLED": True, "SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE,
            "SHOWCASE_STAR_FEATURES": FEATURES, "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_WORKER_ENABLED": False})
        try:
            other = reopened.test_client()
            other.set_cookie("auth_session", cookie.value)
            persisted = other.get(f"/api/agent/jobs/{job_id}").get_json()
            self.assertEqual("succeeded", persisted["status"])
            reference = persisted["result"]["tool_results"][0]["receipt"]["stdout_ref"]
            downloaded = other.get(f"/api/agent/jobs/{job_id}/artifacts/{reference['sha256']}")
            self.assertEqual(200, downloaded.status_code)
            self.assertEqual(EXPECTED.encode(), downloaded.data)
        finally:
            for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                reopened.extensions[name].close()

    def test_public_job_policy_denial_never_dispatches_python(self):
        with patch.dict(os.environ, {"SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE}):
            self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, FINAL, ACCEPT],
                SHOWCASE_STAR_FEATURES={**FEATURES, "local_code_tool": False},
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual(1, len(job["result"]["tool_results"]))
        tool = job["result"]["tool_results"][0]
        self.assertEqual("python_math", tool["name"])
        self.assertEqual("not_executed", tool["status"])
        self.assertEqual("tool_not_allowed", tool["receipt"]["reason"])
        self.assertEqual(0, self.report(job_id)["budget"]["tool_calls"])
        self.assertEqual([], docker_events(job_id))

    def test_public_job_output_limit_keeps_finite_claim_unverified(self):
        output_step = deepcopy(STEP)
        output_step["claims"][0]["tool_request"]["arguments"]["code"] = (
            "import os; os.write(1, b'X' * 40000)")
        with patch.dict(os.environ, {"SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE}):
            self.open_star([NEED_PLAN, PLAN, output_step, VERDICT, FINAL, ACCEPT],
                SHOWCASE_STAR_EVIDENCE_KIND="fault_injection",
                SHOWCASE_STAR_FEATURES=FEATURES,
                SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])
        receipt = job["result"]["tool_results"][0]["receipt"]
        self.assertEqual("output_limit", receipt["status"])
        self.assertFalse(receipt["assertion_matched"])
        self.assertTrue(receipt["cleanup_verified"])
        self.assertLessEqual(receipt["retained_output_bytes"], 16000)
        self.assertGreater(receipt["observed_output_bytes"], 16000)
        events = docker_events(job_id)
        self.assertEqual(1, sum(event.get("Action") == "create" for event in events))
        self.assertEqual(1, sum(event.get("Action") == "destroy" for event in events))


if __name__ == "__main__":
    unittest.main()
