"""F07/F08 child: loopback protocol repair, isolated receipt, then real exit."""

import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

from showcase.flask_app import create_app
from showcase.workspace import WorkspaceStore
from tests.rb06_recovery_worker import config


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
        app = create_app(config(folder, endpoint, "star_reference"))
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        response = client.post("/api/agent/jobs", headers=headers, json={
            "message": "Compute 17*23 and briefly explain.", "session_id": session,
            "solver_mode": "star_reference"})
        if response.status_code != 202:
            raise AssertionError(response.get_json())
        time.sleep(40)
    raise AssertionError("repair receipt crash boundary not reached")


if __name__ == "__main__":
    main()
