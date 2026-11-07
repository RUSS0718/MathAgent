"""Dedicated frozen-policy subprocess windows for S01 recovery acceptance."""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.flask_app import create_app
from showcase.workspace import WorkspaceStore
from tests.controlled_stream_profiles import configure_controlled_streaming
from tests.star_recovery_worker import config as base_config
from tests.star_recovery_worker import stream_transport

POLICY_VERSION = "faithful-stream-v1"


def app_config(folder: Path, *, freeze_policy: bool):
    """Use the existing scripted STAR scenario with a controlled stream adapter."""
    configuration = base_config(folder)
    adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=256)
    configuration.update(
        SHOWCASE_STAR_ADAPTER=adapter,
        SHOWCASE_STAR_TRANSPORT_POLICY="stream_first",
        SHOWCASE_STAR_TRANSPORT_PROFILES=configure_controlled_streaming(adapter),
        SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION=POLICY_VERSION if freeze_policy else None,
    )
    return configuration


def main() -> None:
    """Create one durable Job and exit at a selected stream recovery boundary."""
    folder = Path(sys.argv[1])
    window = sys.argv[2]
    shared_window = "stream_exit" if window == "stream_exit" else "response"
    (folder / "window").write_text(shared_window, encoding="utf-8")
    transport = stream_transport(folder, "stream_exit" if window == "stream_exit" else "after")

    if window == "receipt_exit":
        original_append = WorkspaceStore.append_event

        def append_then_exit(store, job_id, event):
            original_append(store, job_id, event)
            if event.get("solver_event_type") != "call_audit":
                return
            request_log = folder / "requests.jsonl"
            if not request_log.exists():
                return
            requests = [json.loads(line) for line in request_log.read_text(
                encoding="utf-8").splitlines()]
            latest = requests[-1] if requests else {}
            if (event.get("solver_event_type") == "call_audit"
                    and event.get("call_status") == "completed"
                    and latest.get("role") == "step_verifier"
                    and latest.get("step", {}).get("step_id") == "s2"):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                os._exit(71)

        patcher = patch.object(WorkspaceStore, "append_event", append_then_exit)
    else:
        patcher = nullcontext()

    with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
        "showcase.adapters.requests.post", side_effect=transport
    ), patch("showcase.request_transport.strict_loopback_post", side_effect=transport), patcher:
        app = create_app(app_config(folder, freeze_policy=True))
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "4b0e8a66-77b9-45aa-8f08-26eb51a24b80"}
        session_id = client.post("/api/new_chat", headers=headers).get_json()["new_session_id"]
        headers["Idempotency-Key"] = "a91cbbee-8d7e-4e17-8fd7-6102a7bc6f20"
        response = client.post(
            "/api/agent/jobs",
            json={"message": "1+1", "session_id": session_id, "solver_mode": "star_limited"},
            headers=headers,
        )
        if response.status_code != 202:
            raise RuntimeError(f"job_create_failed:{response.status_code}")
        (folder / "job_id").write_text(response.get_json()["job_id"], encoding="utf-8")
        time.sleep(20)
    raise RuntimeError("recovery_exit_window_not_reached")


if __name__ == "__main__":
    main()
