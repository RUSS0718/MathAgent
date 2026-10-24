"""Create representative Runs with the pre-ALIGN build (ALIGN-AC-15 history).

Run with ``PYTHONPATH`` pointing at an extracted pre-ALIGN tree so ``showcase``
and ``llm_client`` resolve to the old build; the environment provides the rest.
The produced database keeps the historical schema increments absent: no
classified ledger entries, no protocol-failure call records and no reviewer or
exploration tool receipts. The new build must still read, review, export and
resume these Runs without fabricating evidence grades or repeating history.
"""

import json
import os
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import requests

SOLVED = {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
          "solution_candidate": "2"}
POLISH = {"solution_candidate": "1+1=2 as recorded by the old build"}
ACCEPT = {"verdict": "ACCEPT", "reason": "Addition"}


def main():
    folder, mode = Path(sys.argv[1]), sys.argv[2]
    replies = ([SOLVED, requests.Timeout("old polish outcome unknown"), POLISH, ACCEPT]
               if mode == "interrupted" else [SOLVED, POLISH, ACCEPT])

    def respond(*args, **kwargs):
        value = replies.pop(0)
        if isinstance(value, BaseException):
            raise value

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"finish_reason": "stop",
                                     "message": {"content": json.dumps(value)}}],
                        "model": "intern-s2",
                        "usage": {"prompt_tokens": 5, "completion_tokens": 5,
                                  "total_tokens": 10}}
        return Reply()

    os.environ["INTERN_API_KEY"] = "scripted-only"
    from llm_client import InternChatClient
    from showcase.adapters import InternModelAdapter
    from showcase.flask_app import create_app
    from showcase.run_budget import RunBudgetLimits

    with patch("llm_client.requests.post", side_effect=respond):
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(folder),
                          "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
                          "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                              InternChatClient(retry=1), max_tokens=256),
                          "SHOWCASE_STAR_EVIDENCE_KIND": "scripted",
                          "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
                              max_model_calls=8, max_http_attempts=8)})
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = str(uuid.uuid4())
        response = client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": session, "solver_mode": "star_limited"},
            headers=headers)
        job_id = response.get_json()["job_id"]
        for _ in range(2000):
            job = client.get(f"/api/agent/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(.01)
    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
        app.extensions[name].close()
    (folder / f"old_{mode}_id").write_text(job_id)
    print("old build", mode, job_id, job["status"])


if __name__ == "__main__":
    main()
