"""Disposable RB06 process: real HTTP, managed Docker, exit after receipt commit."""

import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.workspace import WorkspaceStore


def config(folder, endpoint):
    """Use only the explicit loopback provider; no provider credentials are loaded."""
    with patch.dict(os.environ, {"INTERN_API_KEY": "loopback-only"}):
        client = InternChatClient(retry=1, timeout=3)
    client.api_base = endpoint
    return {"TESTING": True, "SHOWCASE_DATA_DIR": str(folder),
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(client, max_tokens=256),
            "SHOWCASE_STAR_PYTHON_IMAGE_ID": os.environ["MATHAGENT_TEST_PYTHON_IMAGE"],
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_FEATURES": {"skills": True, "local_code_tool": True,
                                       "final_generation": True, "final_solution_review": True},
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=8, max_http_attempts=8)}


def main():
    folder, endpoint = Path(sys.argv[1]), sys.argv[2]
    original = WorkspaceStore.append_event

    def crash(store, job_id, event):
        result = original(store, job_id, event)
        if event.get("solver_event_type") == "tool_receipt":
            (folder / "job_id").write_text(job_id)
            os._exit(71)
        return result

    with patch.object(WorkspaceStore, "append_event", crash):
        app = create_app(config(folder, endpoint))
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        response = client.post("/api/agent/jobs", headers=headers, json={
            "message": "Compute 17*23 and briefly explain.", "session_id": session,
            "solver_mode": "star_limited"})
        if response.status_code != 202:
            raise AssertionError(response.get_json())
        time.sleep(40)
    raise AssertionError("receipt crash boundary not reached")


if __name__ == "__main__":
    main()
