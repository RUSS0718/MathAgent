"""Controlled public Job worker for a completed #175 mode-reply crash."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from showcase.solver_harness.storage import SolverStateStore
from tests.test_faithful_service_population import FaithfulPopulationJobTest


def main():
    folder = Path(sys.argv[1])
    resume = len(sys.argv) > 2 and sys.argv[2] == "resume"
    case = FaithfulPopulationJobTest()
    case.setUp()
    original_open = case.open_star
    original_commit = SolverStateStore.commit_event

    class ResumeObserved(Exception):
        pass

    def open_star(replies, **config):
        def logged(context):
            with (folder / "requests.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps(context) + "\n")
            return replies[0](context)
        original_open([logged] * len(replies), SHOWCASE_DATA_DIR=str(folder), **config)
        if resume:
            saved = json.loads((folder / "crash.json").read_text(encoding="utf-8"))
            pipeline = case.app.extensions["showcase_workspace_service"].star_pipeline
            case.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
            response = case.client.post(
                f'/api/agent/jobs/{saved["job_id"]}/resume', json={}, headers=case.headers())
            case.assertEqual(202, response.status_code, response.get_json())
            final = case.terminal(saved["job_id"], timeout=20)
            (folder / "resumed.json").write_text(json.dumps(final), encoding="utf-8")
            raise ResumeObserved()

    def committed(store, run_id, **kwargs):
        run = original_commit(store, run_id, **kwargs)
        completed_modes = [call for call in run["state"].get("calls", {}).values()
                           if call["call_id"].startswith("execution-mode:")
                           and call["status"] == "completed"
                           and call.get("request", {}).get("current_mode") == "serial"]
        if not resume and completed_modes and kwargs["event"].get("type") == "call_audit":
            snapshot = {"job_id": run_id, "state": run["state"], "job": case.job(run_id),
                        "events": run["events"]}
            (folder / "crash.json").write_text(json.dumps(snapshot), encoding="utf-8")
            os._exit(75)
        return run

    case.open_star = open_star
    try:
        with patch.object(SolverStateStore, "commit_event", committed):
            case.run_plain_submission(multi_step=True)
    except ResumeObserved:
        pass
    finally:
        case.doCleanups()


if __name__ == "__main__":
    main()

