"""Offline subprocess window: exit with a dispatched serialization repair."""

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import SOLVED


def config(folder):
    return {"TESTING": True, "SHOWCASE_DATA_DIR": str(folder), "SHOWCASE_STAR_ENABLED": True,
            "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
            "SHOWCASE_STAR_FEATURES": {"serialization_repair": True},
            "SHOWCASE_STAR_ADAPTER": InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
            "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=8, max_http_attempts=8)}


def main():
    folder = Path(sys.argv[1])
    ready = threading.Event()

    def provider(*args, **kwargs):
        ready.wait(5)
        context = json.loads(json.loads(kwargs["data"])["messages"][-1]["content"])
        with (folder / "requests.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"call_id": context["call_id"], "role": context["role"]}) + "\n")
            log.flush()
        if "visible_reply" in context:
            os._exit(71)

        class Reply:
            status_code = 200

            def raise_for_status(self):
                pass

            def close(self):
                pass

            def iter_content(self, **_kwargs):
                yield json.dumps(self.json()).encode()

            def json(self):
                return {"model": "intern-s2", "choices": [{"finish_reason": "stop", "message": {
                    "content": "```json\n" + json.dumps(SOLVED) + "\n```"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

        return Reply()

    with patch.dict(os.environ, {"INTERN_API_KEY": "offline-only"}), patch(
            "llm_client.requests.post", side_effect=provider):
        app = create_app(config(folder))
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = str(uuid.uuid4())
        reply = client.post("/api/agent/jobs", json={"message": "1+1", "session_id": session,
                            "solver_mode": "star_limited"}, headers=headers)
        (folder / "job_id").write_text(reply.get_json()["job_id"])
        ready.set()
        threading.Event().wait(15)
        raise SystemExit("worker did not reach repair exit window")


if __name__ == "__main__":
    main()
