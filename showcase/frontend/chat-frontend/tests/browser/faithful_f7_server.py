"""Loopback-only browser fixture with real SQLite Job and persisted F6 output."""

from __future__ import annotations

import json
import os
import signal
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

from faithful_f7_formal import formal_fixture
from flask import jsonify, request
from product_server import (
    S03_PROBLEM,
    InternChatClient,
    InternModelAdapter,
    Provider,
    RunBudgetLimits,
    counts,
)
from werkzeug.serving import make_server

from showcase.flask_app import create_app

run_id_by_user: dict[tuple[str, bool], dict[str, object]] = {}
fixture_lock = threading.Lock()
evidence_dir = Path(__file__).resolve().parents[5] / "artifacts" / (
    "faithful-f7-public-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
)
evidence_dir.mkdir(parents=True)
formal = formal_fixture()
provider = ThreadingHTTPServer(("127.0.0.1", 8196), formal["provider"] if formal else Provider)
threading.Thread(target=provider.serve_forever, daemon=True).start()
os.environ["INTERN_API_KEY"] = "local-f7-fixture"
os.environ["INTERN_API_BASE"] = "http://127.0.0.1:8196/v1/chat/completions"
app = create_app({
    "TESTING": True,
    "SHOWCASE_MODE": "fake",
    "SHOWCASE_DATA_DIR": str(evidence_dir / "data"),
    "SHOWCASE_JOB_DELAY_SECONDS": 0.01,
    "SHOWCASE_PRESENTATION_ENABLED": True,
    "SHOWCASE_F7_SYSTEM_VIEW_ENABLED": True,
    "SHOWCASE_STAR_ENABLED": True,
    "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
    "SHOWCASE_STAR_FEATURES": {
        "problem_spec": True, "proof_graph": True,
        "final_generation": True, "final_solution_review": True, "local_code_tool": formal is not None,
    },
    "SHOWCASE_STAR_BUDGET": RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=3),
    "SHOWCASE_STAR_ADAPTER": InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
    **(formal["config"] if formal else {}),
})


@app.get("/__test__/f7/health")
def fixture_health():
    return jsonify({"status": "ok"})


@app.post("/__test__/f7/fixture")
def create_f7_fixture():
    user_id = getattr(g_auth(), "user_id", None)
    session_id = request.cookies.get("auth_session")
    if not user_id or not session_id:
        return jsonify({"error": "auth_required"}), 401
    with fixture_lock:
        synthetic = request.args.get("synthetic") == "true"
        existing = run_id_by_user.get((user_id, synthetic))
        if existing:
            return jsonify(existing)

        client = app.test_client()
        client.set_cookie("auth_session", session_id)
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid.uuid4())}
        session = client.post("/api/new_chat", headers=headers).get_json()
        created = client.post("/api/agent/jobs", json={
            "message": S03_PROBLEM,
            "session_id": session["new_session_id"],
            "presentation_mode": "teach",
            "solver_mode": "star_limited",
            "problem_spec": {
                "specification_version": 1, "original_problem": S03_PROBLEM,
                "domain": "integers", "quantifiers": [], "assumptions": [],
                "directions": ["evaluate"], "output_requirements": [],
                "root_obligations": [{"obligation_id": "root:s03",
                    "obligation_type": "universal", "statement": "1+1=2"}],
                "auxiliary_goals": [],
            },
            **(formal["payload"] if formal else {}),
        }, headers=headers)
        if created.status_code != 202:
            return jsonify({"error": "fixture_job_create_failed", "status": created.status_code}), 500
        run_id = created.get_json()["job_id"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            job = client.get(f"/api/agent/jobs/{run_id}").get_json()
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(0.01)
        if job["status"] != "succeeded":
            return jsonify({"error": "fixture_job_not_succeeded", "status": job["status"]}), 500

        output = client.post(f"/api/agent/jobs/{run_id}/teach", json={}, headers=headers)
        if output.status_code != 200:
            return jsonify({"error": "fixture_output_failed", "status": output.status_code,
                            "detail": output.get_json()}), 500
        artifact = output.get_json()["presentation"]
        report = client.get(f"/api/agent/jobs/{run_id}/report").get_json()
        if synthetic:
            _persist_synthetic_graph(run_id)
        detail = client.get(f"/api/faithful/runs/{run_id}", query_string={
            "scheme": "f7-deeplink-v1", "mode": "teach",
            "output": artifact["output_request"]["id"], "artifact": artifact["artifact"]["id"],
        }).get_json()
        graph = detail["graph"]
        paragraph = next(item for item in artifact["paragraphs"] if item["kind"] == "mathematical")
        value = {
            "run_id": run_id,
            "output_id": artifact["output_request"]["id"],
            "artifact_id": artifact["artifact"]["id"],
            "paragraph_id": paragraph["id"],
            "paragraph_ids": [item["id"] for item in artifact["paragraphs"]],
            "graph_version": graph["graph_version"],
            "node_id": graph["propositions"][-1]["id"],
            "node_count": len(graph["propositions"]),
            "execution_mode": detail["run"]["execution_mode"],
            "graph_origin": "synthetic_f7_performance" if synthetic else "real_harness",
            "provider_kind": "scripted_loopback_http",
            "provider_calls": sum(counts.values()),
            "public_detail": detail,
        }
        (evidence_dir / f"{run_id}.json").write_text(json.dumps({
            "fixture": value, "presentation": artifact,
            "report": report,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        run_id_by_user[user_id, synthetic] = value
        return jsonify(value)


def g_auth():
    """Return the authenticated local session attached by Flask's request hook."""
    from flask import g

    return getattr(g, "auth_session", None)


def _persist_synthetic_graph(run_id: str) -> None:
    service = app.extensions["showcase_workspace_service"]
    with service.store._lock:
        row = service.store._connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id=?", (run_id,),
        ).fetchone()
        state = json.loads(row["state_json"])
        nodes = {}
        derivations = {}
        for index in range(1, 501):
            node_id = f"synthetic-{index:04}"
            nodes[node_id] = {
                "status": "supported", "conflict": False,
                "sources": [],
            }
            if index > 1:
                derivations[f"edge-{index}"] = {
                    "conclusion": node_id, "premises": [f"synthetic-{index - 1:04}"],
                    "status": "accepted", "grade": "llm_reviewed", "source_refs": [],
                }
        graph = state["proof_graph"]
        graph["current_version"] = 7
        graph["data_origin"] = "synthetic_f7_performance"
        graph["snapshots"].append({
            "graph_version": 7, "propositions": nodes, "derivations": derivations,
            "sources": {}, "attempts": {},
        })
        state["state_revision"] += 1
        service.store._connection.execute(
            "UPDATE solver_states SET state_json=?,state_revision=? WHERE run_id=?",
            (json.dumps(state, ensure_ascii=False), state["state_revision"], run_id),
        )
        service.store._connection.commit()


server = make_server("127.0.0.1", 8096, app, threaded=True)
stop_requested = threading.Event()


def _request_stop(_signal, _frame):
    stop_requested.set()


def _shutdown_when_requested():
    stop_requested.wait()
    server.shutdown()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    shutdown_thread = threading.Thread(target=_shutdown_when_requested, daemon=True)
    shutdown_thread.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.extensions["showcase_workspace_service"].close()
        app.extensions["showcase_run_service"].close()
        app.extensions["loopback_store"].close()
        provider.shutdown()
        provider.server_close()
