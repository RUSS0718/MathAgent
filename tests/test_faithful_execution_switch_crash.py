"""Public Job recovery must consume the durable mode reply without reissuing it."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app


class ExecutionSwitchCrashTest(unittest.TestCase):
    def test_completed_mode_reply_before_marker_is_not_resent_on_public_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)

            def worker(*args):
                return subprocess.run(
                    [sys.executable, "-m", "tests.faithful_execution_switch_crash_worker", directory, *args],
                    capture_output=True, timeout=30, env={**os.environ, "PYTHONUTF8": "1"})

            crashed = worker()
            self.assertEqual(75, crashed.returncode, crashed.stderr.decode(errors="replace"))
            saved = json.loads((folder / "crash.json").read_text(encoding="utf-8"))
            state = saved["state"]

            completed = [call for call in state["calls"].values()
                         if call["call_id"].startswith("execution-mode:") and call["status"] == "completed"
                         and call.get("request", {}).get("current_mode") == "serial"]
            self.assertEqual(1, len(completed))
            revision = completed[0]["call_id"].split(":")[-1]
            self.assertNotIn(f"execution-mode-decided-{revision}",
                             {event["event_id"] for event in saved["events"]})

            before = [json.loads(line) for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            with patch("llm_client.requests.post") as provider, patch(
                "showcase.request_transport.strict_loopback_post", new=provider
            ):
                app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": directory})
                try:
                    client = app.test_client()
                    client.get("/api/check_auth")
                    for _ in range(2):
                        response = client.get(f'/api/agent/jobs/{saved["job_id"]}')
                        self.assertEqual(200, response.status_code)
                        recovered = response.get_json()
                        for field in ("started_at", "deadline_at", "limits", "logical_calls", "reserved_tokens"):
                            self.assertEqual(saved["job"]["result"]["budget"][field],
                                             recovered["result"]["budget"][field], field)
                        self.assertEqual(state["config_hash"], recovered["result"]["solver"]["config_hash"])
                    provider.assert_not_called()
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        app.extensions[name].close()
            resumed = worker("resume")
            self.assertEqual(0, resumed.returncode, resumed.stderr.decode(errors="replace"))
            final = json.loads((folder / "resumed.json").read_text(encoding="utf-8"))
            self.assertEqual("succeeded", final["status"], final.get("error"))
            for field in ("started_at", "deadline_at", "limits", "reserved_tokens"):
                self.assertEqual(saved["job"]["result"]["budget"][field], final["result"]["budget"][field], field)
            after = [json.loads(line) for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
            original = next(item for item in reversed(before) if item.get("execution_mode_decision"))
            same_decision = [item for item in after if item.get("execution_mode_decision")
                             and item["current_mode"] == original["current_mode"]
                             and item["progress"] == original["progress"]
                             and item["frontiers"] == original["frontiers"]]
            self.assertEqual(1, len(same_decision),
                             f'completed mode reply resent: {[item["call_id"] for item in same_decision]}')

