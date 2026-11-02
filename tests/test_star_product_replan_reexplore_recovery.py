"""Public Job recovery passes post-replan research to the replacement planner."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.star_product_support import StarJobFixture

WINDOW = "reexplore_after_replan_results"
RESEARCH_FINDING = "RECOVERED_RESEARCH_SENTINEL"


def _crash_worker(folder):
    import tests.star_recovery_worker as worker
    from showcase.workspace import WorkspaceStore

    folder = Path(folder)
    hard_exit = os._exit
    worker.REPLAN_GUIDANCE_WINDOW = WINDOW
    original_guidance = worker.guidance_reply

    def scripted_guidance(role, context, data_folder):
        if role == "meta" and context.get("action") == "delegate_research_task":
            return {"tasks": [{"prompt": "Find an alternate derivation",
                               "permitted_tools": [], "timeout_seconds": 2}]}
        if role == "researcher":
            return {"findings": [RESEARCH_FINDING]}
        return original_guidance(role, context, data_folder)

    worker.guidance_reply = scripted_guidance
    original_config = worker.config

    def config(data_folder, *, crash_tools=False):
        result = original_config(data_folder, crash_tools=crash_tools)
        result["SHOWCASE_STAR_FEATURES"] = {
            **result["SHOWCASE_STAR_FEATURES"],
            "meta_guidance": True,
            "reexplore_after_replan": True,
        }
        result["SHOWCASE_STAR_BUDGET"] = worker.RunBudgetLimits(
            max_model_calls=24, max_http_attempts=24
        )
        return result

    worker.config = config
    # The existing worker has an earlier crash hook at the Guidance commit;
    # suppress that hook here and stop only after research is durably committed.
    worker.os._exit = lambda _status: None
    original_append = WorkspaceStore.append_event

    def exit_after_research(store, job_id, event):
        original_append(store, job_id, event)
        if event.get("solver_event_type") == "reexploration_completed":
            while not (folder / "job_id").exists():
                time.sleep(0.01)
            hard_exit(71)

    WorkspaceStore.append_event = exit_after_research
    sys.argv = [sys.argv[0], str(folder), WINDOW]
    worker.main()


class StarReexplorationRecoveryTest(StarJobFixture, unittest.TestCase):
    def test_recovered_research_is_consumed_by_the_replacement_planner(self):
        folder_handle = tempfile.TemporaryDirectory()
        self.addCleanup(folder_handle.cleanup)
        folder = Path(folder_handle.name)
        process = subprocess.run(
            [sys.executable, "-m", f"tests.{Path(__file__).stem}", "--worker", str(folder)],
            capture_output=True,
            timeout=90,
        )
        self.assertEqual(71, process.returncode,
                         process.stderr.decode(errors="replace"))
        job_id = (folder / "job_id").read_text(encoding="utf-8")
        before = [json.loads(line) for line in
                  (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(1, sum(item.get("role") == "researcher" for item in before))

        import tests.star_recovery_worker as worker
        from showcase.flask_app import create_app

        self.enterContext(patch.object(worker, "REPLAN_GUIDANCE_WINDOW", WINDOW))
        config = worker.config(folder)
        config["SHOWCASE_STAR_FEATURES"] = {
            **config["SHOWCASE_STAR_FEATURES"],
            "meta_guidance": True,
            "reexplore_after_replan": True,
        }
        config["SHOWCASE_STAR_BUDGET"] = worker.RunBudgetLimits(
            max_model_calls=24, max_http_attempts=24
        )
        original_reply_value = worker.reply_value

        def recovered_reply(window, context, data_folder):
            if context.get("role") == "planner":
                return {**worker.PLAN, "version": context.get("plan_version", 1)}
            return original_reply_value(window, context, data_folder)

        self.enterContext(patch.object(worker, "reply_value", side_effect=recovered_reply))
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}))
        self.enterContext(patch(
            "llm_client.requests.post",
            side_effect=lambda *args, **kwargs: worker.provider(folder, kwargs),
        ))
        app = create_app(config)
        self.app = app
        for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            self.addCleanup(app.extensions[name].close)
        self.client = app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]

        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
        )
        self.assertEqual(202, response.status_code, response.get_json())
        deadline = time.monotonic() + 25
        job = self.job(job_id)
        while job["status"] not in {"succeeded", "failed", "canceled"}:
            if time.monotonic() >= deadline:
                self.fail("public Job did not reach a terminal state after recovery")
            time.sleep(0.05)
            job = self.job(job_id)
        self.assertEqual("succeeded", job["status"], job)

        after = [json.loads(line) for line in
                 (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(before, after[:len(before)])
        self.assertEqual(1, sum(item.get("role") == "researcher" for item in after))
        old_planners = [item for item in before if item.get("role") == "planner"]
        new_planners = [item for item in after[len(before):]
                        if item.get("role") == "planner"]
        self.assertEqual(1, len(old_planners), before)
        self.assertEqual(1, len(new_planners), after)
        self.assertNotEqual(old_planners[0].get("call_id"),
                            new_planners[0].get("call_id"))
        self.assertEqual(2, new_planners[0].get("plan_version"))
        self.assertEqual(["WORKER_DIRECTION"], new_planners[0].get("forbidden_directions"))
        self.assertNotIn("exploration_findings", new_planners[0])
        findings = new_planners[0].get("reexploration_findings")
        self.assertIsInstance(findings, list)
        self.assertEqual(1, len(findings))
        self.assertEqual("unverified_exploration", findings[0].get("provenance"))
        self.assertEqual(1, json.dumps(findings[0], ensure_ascii=False).count(RESEARCH_FINDING))
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        archived = [event for event in evidence["timeline"]
                    if event.get("solver_event_type") == "plan_archived"]
        replaced = [event for event in evidence["timeline"]
                    if event.get("solver_event_type") == "plan_replaced"]
        self.assertEqual(1, len(archived), archived)
        self.assertEqual(1, len(replaced), replaced)
        self.assertIsInstance(archived[0].get("decision_revision"), int)
        self.assertEqual(archived[0].get("decision_revision"),
                         replaced[0].get("decision_revision"))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        _crash_worker(sys.argv[2])
    else:
        unittest.main()
