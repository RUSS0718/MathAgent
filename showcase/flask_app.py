"""Flask Showcase entry point for the v0.2 loopback workspace."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, request, send_from_directory, stream_with_context
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from .evidence import EvidencePackExporter, replay_evidence
from .loopback import AuthSession, LoopbackStore
from .profile import SHOWCASE_PROFILE, ensure_showcase_profile
from .run_service import (
    RunNotFoundError,
    RunResumeUnavailable,
    RunService,
    RunValidationError,
)
from .server import create_live_service
from .verification import LightweightVerificationHook
from .workspace import WorkspaceError, WorkspaceService

AUTH_COOKIE = "auth_session"
MAX_BODY_BYTES = 1_000_000
MAX_PNG_BYTES = 2 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
VERIFICATION_MODES = ["auto", "required", "off"]


def create_app(
    config: Mapping[str, Any] | None = None,
    *,
    database_path: str | Path | None = None,
    service: RunService | None = None,
    profile: str = SHOWCASE_PROFILE,
) -> Flask:
    """Build the product-side Flask application without starting a server."""

    ensure_showcase_profile(profile)
    app = Flask(__name__)
    app.config.from_mapping(
        TESTING=False,
        SHOWCASE_PROFILE=profile,
        SHOWCASE_MODE="fake",
        SHOWCASE_DATA_DIR=None,
        SHOWCASE_DATABASE_PATH=None,
        SHOWCASE_VISION_ENABLED=os.getenv("SHOWCASE_VISION_ENABLED", "").lower() in {"1", "true", "yes"},
    )
    if config:
        app.config.from_mapping(dict(config))

    storage_root, resolved_database = _storage_paths(app.config, database_path)
    storage_root.mkdir(parents=True, exist_ok=True)
    (storage_root / "attachments").mkdir(exist_ok=True)
    (storage_root / "events").mkdir(exist_ok=True)
    app.config["SHOWCASE_DATA_DIR"] = str(storage_root)
    app.config["SHOWCASE_DATABASE_PATH"] = str(resolved_database)

    loopback_store = LoopbackStore(resolved_database)
    if service is None:
        if app.config["SHOWCASE_MODE"] == "live":
            service = create_live_service(database_path=resolved_database)
        else:
            service = RunService(database_path=resolved_database)
    shared_connection = getattr(getattr(service, "_store", None), "_connection", None)
    workspace_service = WorkspaceService(resolved_database, connection=shared_connection)
    app.extensions["loopback_store"] = loopback_store
    app.extensions["showcase_run_service"] = service
    app.extensions["showcase_workspace_service"] = workspace_service
    app.extensions["showcase_verifier"] = LightweightVerificationHook()
    app.extensions["showcase_evidence_exporter"] = EvidencePackExporter()
    files_index = storage_root / "attachments" / "index.json"
    try:
        persisted_files = json.loads(files_index.read_text(encoding="utf-8")) if files_index.is_file() else {}
    except (OSError, ValueError):
        persisted_files = {}
    app.extensions["showcase_files"] = persisted_files if isinstance(persisted_files, dict) else {}
    app.extensions["showcase_files_index"] = files_index

    @app.before_request
    def attach_request_context() -> Response | None:
        g.request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
        g.auth_session = loopback_store.get(request.cookies.get(AUTH_COOKIE))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            body_limit = MAX_PNG_BYTES + 64 * 1024 if request.path == "/api/upload_file" else MAX_BODY_BYTES
            if request.content_length is not None and request.content_length > body_limit:
                return _json_error("invalid_body_size", 400)
            if g.auth_session is None:
                return _json_error("auth_required", 401)
            csrf_token = request.headers.get("X-CSRF-Token")
            if not csrf_token:
                return _json_error("csrf_required", 403)
            if csrf_token != g.auth_session.csrf_token:
                return _json_error("csrf_invalid", 403)
        return None

    @app.after_request
    def add_request_id(response: Response) -> Response:
        response.headers.setdefault("X-Request-ID", g.get("request_id", f"req_{uuid.uuid4().hex}"))
        return response

    @app.errorhandler(404)
    def not_found(_error: Any) -> tuple[Response, int]:
        return _json_error("not_found", 404)

    @app.errorhandler(WorkspaceError)
    def workspace_error(error: WorkspaceError) -> tuple[Response, int]:
        return _workspace_error(error)

    @app.get("/health")
    def health() -> Response:
        return jsonify(service.health())

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/dashboard/")
    @app.get("/dashboard/<path:subpath>")
    def dashboard(subpath: str = "") -> Response:
        del subpath
        frontend_index = Path(__file__).parent / "frontend" / "chat-frontend" / "dist" / "index.html"
        body = frontend_index.read_text(encoding="utf-8") if frontend_index.is_file() else _dashboard_page()
        response = Response(body, content_type="text/html; charset=utf-8")
        return _set_auth_cookie_if_new(response, loopback_store)

    @app.get("/dashboard-assets/<path:asset_path>")
    def dashboard_asset(asset_path: str) -> Response:
        asset_root = Path(__file__).parent / "frontend" / "chat-frontend" / "dist"
        if not (asset_root / asset_path).is_file():
            return _json_error("not_found", 404)[0], 404
        return send_from_directory(asset_root, asset_path)

    @app.get("/api/check_auth")
    def check_auth() -> Response:
        session, created = loopback_store.get_or_create(request.cookies.get(AUTH_COOKIE))
        g.auth_session = session
        payload = _auth_payload(session)
        response = jsonify(payload)
        if created:
            _set_auth_cookie(response, session)
        return response

    @app.post("/api/logout")
    def logout() -> Response:
        session: AuthSession = g.auth_session
        loopback_store.revoke(session.session_id)
        response = jsonify({"success": True})
        response.delete_cookie(AUTH_COOKIE, path="/", httponly=True, samesite="Lax")
        return response

    @app.get("/api/capabilities")
    def capabilities() -> Response:
        upload = {
            "enabled": bool(app.config.get("SHOWCASE_VISION_ENABLED")),
            "status": "available" if app.config.get("SHOWCASE_VISION_ENABLED") else "unavailable",
            "reason": None if app.config.get("SHOWCASE_VISION_ENABLED") else "capability_unavailable",
            "mime": "image/png",
            "max_bytes": MAX_PNG_BYTES,
        }
        return jsonify(
            {
                "profile": profile,
                "jobs": {"enabled": True, "status": "available"},
                "sse": {"enabled": True, "status": "available"},
                "verification_mode": VERIFICATION_MODES,
                "files": {"upload": upload},
                "capabilities": {
                    "jobs": True,
                    "sse": True,
                    "verification_mode": VERIFICATION_MODES,
                    "file_upload": upload,
                },
            }
        )

    @app.get("/api/files")
    def files() -> Response:
        return jsonify(list(app.extensions["showcase_files"].values()))

    @app.post("/api/upload_file")
    def upload_file() -> tuple[Response, int]:
        if not app.config.get("SHOWCASE_VISION_ENABLED"):
            return _json_error("capability_unavailable", 503)
        uploaded = request.files.get("file")
        if uploaded is None or not uploaded.filename:
            return _json_error("file_required", 400)
        content = uploaded.read(MAX_PNG_BYTES + 1)
        if len(content) > MAX_PNG_BYTES:
            return _json_error("image_too_large", 413)
        if not content.startswith(PNG_SIGNATURE):
            return _json_error("image_signature_invalid", 400)
        if len(content) < 33 or content[12:16] != b"IHDR" or int.from_bytes(content[16:20], "big") == 0 or int.from_bytes(content[20:24], "big") == 0 or not content.endswith(b"IEND\xaeB`\x82"):
            return _json_error("image_corrupt", 400)
        file_id = f"file_{uuid.uuid4().hex}"
        digest = hashlib.sha256(content).hexdigest()
        attachment = Path(app.config["SHOWCASE_DATA_DIR"]) / "attachments" / f"{file_id}.png"
        attachment.write_bytes(content)
        reference = {"file_id": file_id, "reference": file_id, "mime": "image/png", "size": len(content), "sha256": digest, "status": "ready"}
        app.extensions["showcase_files"][file_id] = reference
        files_index.write_text(json.dumps(app.extensions["showcase_files"], ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return jsonify({"file": reference}), 201

    @app.post("/api/delete_file")
    def delete_file() -> tuple[Response, int]:
        if not app.config.get("SHOWCASE_VISION_ENABLED"):
            return _json_error("capability_unavailable", 503)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        file_id = payload.get("file_id")
        files_by_id = app.extensions["showcase_files"]
        if files_by_id.pop(file_id, None) is None:
            return _json_error("file_not_found", 404)
        path = Path(app.config["SHOWCASE_DATA_DIR"]) / "attachments" / f"{file_id}.png"
        path.unlink(missing_ok=True)
        files_index.write_text(json.dumps(files_by_id, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return jsonify({"success": True, "file_id": file_id}), 200

    @app.get("/api/sessions")
    def list_sessions() -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            return jsonify(workspace_service.list_sessions(session.user_id))
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/new_chat")
    def new_chat() -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            session_id = workspace_service.create_session(session.user_id)
            return jsonify({"success": True, "new_session_id": session_id}), 200
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.get("/api/load_session")
    def load_session() -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        session_id = request.args.get("session", "")
        try:
            messages = workspace_service.load_session(session_id, session.user_id)
            return jsonify({"success": True, "messages": messages})
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/change_session")
    def change_session() -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        session_id = payload.get("session_id")
        title = payload.get("title")
        if not isinstance(session_id, str) or not isinstance(title, str) or not title.strip():
            return _json_error("invalid_session_title", 400)
        if len(title.strip()) > 200:
            return _json_error("session_title_too_large", 400)
        try:
            workspace_service.rename_session(session_id, session.user_id, title.strip())
            return jsonify({"success": True, "session_id": session_id, "title": title.strip()}), 200
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/delete_session")
    def delete_session() -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return _json_error("session_id_required", 400)
        try:
            workspace_service.delete_session(session_id, session.user_id)
            return jsonify({"success": True}), 200
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/agent/jobs")
    def create_job() -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        message = payload.get("message")
        session_id = payload.get("session_id")
        if not isinstance(message, str) or not message.strip():
            return _json_error("message_must_be_non_empty", 400)
        if not isinstance(session_id, str) or not session_id:
            return _json_error("session_id_required", 400)
        if len(message.strip()) > 100_000:
            return _json_error("message_too_large", 400)
        file_id = payload.get("input_user_file_id")
        if file_id is not None:
            if not app.config.get("SHOWCASE_VISION_ENABLED"):
                return _json_error("capability_unavailable", 503)
            if file_id not in app.extensions["showcase_files"]:
                return _json_error("file_not_found", 404)
        idempotency_key = request.headers.get("Idempotency-Key", "")
        try:
            job, existing = workspace_service.create_job(
                user_id=session.user_id,
                session_id=session_id,
                problem=message.strip(),
                idempotency_key=idempotency_key,
                web_search_enabled=payload.get("web_search_enabled", False) is True,
                input_user_file_id=file_id,
                verification_mode=payload.get("verification_mode", "auto"),
            )
        except WorkspaceError as exc:
            return _workspace_error(exc)
        status = 200 if existing else 202
        return jsonify({"success": True, "job_id": job["job_id"], "status": job["status"], "existing": existing}), status

    @app.get("/api/agent/jobs/active")
    def active_jobs() -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        session_id = request.args.get("session_id")
        try:
            return jsonify({"success": True, "jobs": workspace_service.active_jobs(session.user_id, session_id)})
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.get("/api/agent/jobs/<job_id>")
    def get_job(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            return jsonify({"success": True, **workspace_service.get_job(job_id, session.user_id)})
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.get("/api/agent/jobs/<job_id>/events")
    def get_job_events(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        raw_cursor = request.args.get("last_event_id")
        if raw_cursor is None:
            raw_cursor = request.headers.get("Last-Event-ID", "0")
        after_id = _parse_event_cursor(raw_cursor)
        if after_id is None:
            return _json_error("invalid_last_event_id", 400)
        try:
            # Validate ownership before returning a lazy streaming response.
            workspace_service.get_job(job_id, session.user_id)
            events = workspace_service.stream_events(job_id, session.user_id, after_id)
        except WorkspaceError as exc:
            return _workspace_error(exc)

        def generate():
            for event in events:
                data = json.dumps(event["data"], ensure_ascii=False, separators=(",", ":"))
                if event["id"] is None:
                    yield f"event: {event['event']}\ndata: {data}\n\n"
                else:
                    yield (
                        f"id: {int(event['id'])}\n"
                        f"event: {event['event']}\n"
                        f"data: {data}\n\n"
                    )

        return Response(
            stream_with_context(generate()),
            content_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/agent/jobs/<job_id>/resume")
    def resume_job(job_id: str) -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        try:
            result, existing = workspace_service.resume_job(
                user_id=session.user_id,
                job_id=job_id,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                answer=str(payload.get("answer", "")),
            )
            return jsonify({**result, "existing": existing}), 200 if existing else 202
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/agent/jobs/<job_id>/cancel")
    def cancel_job(job_id: str) -> tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        del payload
        try:
            result, existing = workspace_service.cancel_job(
                user_id=session.user_id,
                job_id=job_id,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
            )
            return jsonify({**result, "existing": existing}), 200
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/runs")
    def create_run() -> tuple[Response, int]:
        try:
            payload = request.get_json(silent=False)
        except (BadRequest, UnsupportedMediaType):
            return _json_error("invalid_json", 400)
        if not isinstance(payload, dict):
            return _json_error("body_must_be_object", 400)
        try:
            snapshot = service.create_run(payload)
        except RunValidationError as exc:
            return _json_error(exc.category, 400)
        return jsonify(snapshot), 201

    @app.get("/api/runs/<run_id>")
    def get_run(run_id: str) -> Response | tuple[Response, int]:
        try:
            return jsonify(service.get_run(run_id))
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)

    @app.get("/api/runs/<run_id>/events")
    def get_events(run_id: str) -> Response | tuple[Response, int]:
        try:
            return jsonify({"run_id": run_id, "events": service.get_events(run_id)})
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)

    @app.get("/api/runs/<run_id>/evidence")
    def get_evidence(run_id: str) -> Response | tuple[Response, int]:
        try:
            snapshot = service.get_run(run_id)
            events = service.get_events(run_id)
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)
        tool_results = [event for event in events if event.get("type") == "tool_completed"]
        verification = app.extensions["showcase_verifier"].verify(snapshot, tool_results)
        pack = app.extensions["showcase_evidence_exporter"].export(
            snapshot,
            events=events,
            tool_results=tool_results,
            verification=verification,
        )
        return jsonify(pack)

    @app.get("/api/runs/<run_id>/report")
    def get_run_report(run_id: str) -> Response | tuple[Response, int]:
        """Return the stable public report DTO for an existing Run."""

        try:
            snapshot = service.get_run(run_id)
            events = service.get_events(run_id)
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)
        tool_results = [event for event in events if event.get("type") == "tool_completed"]
        verification = app.extensions["showcase_verifier"].verify(snapshot, tool_results)
        return jsonify({
            "version": app.extensions["showcase_evidence_exporter"].report_version,
            "evidence_id": run_id,
            "status": snapshot.get("status"),
            "mode": snapshot.get("execution_mode", "unavailable"),
            "report": app.extensions["showcase_evidence_exporter"].report(
                snapshot, tool_results=tool_results, verification={
                    "status": verification.status,
                    "findings": list(verification.findings),
                    "checker": verification.checker,
                }
            ),
        })

    @app.post("/api/evidence/replay")
    def replay_saved_evidence() -> Response | tuple[Response, int]:
        """Replay a saved public pack; this route has no model/tool execution path."""

        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        try:
            return jsonify(replay_evidence(payload))
        except ValueError:
            return _json_error("replay_invalid", 400)

    @app.get("/api/runs/<run_id>/replay")
    def replay_run_evidence(run_id: str) -> Response | tuple[Response, int]:
        try:
            snapshot = service.get_run(run_id)
            events = service.get_events(run_id)
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)
        tool_results = [event for event in events if event.get("type") == "tool_completed"]
        pack = app.extensions["showcase_evidence_exporter"].export(snapshot, events=events, tool_results=tool_results)
        return jsonify(replay_evidence(pack))

    @app.get("/api/agent/jobs/<job_id>/report")
    def get_job_report(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            job = workspace_service.get_job(job_id, session.user_id)
            events = workspace_service.events(job_id, session.user_id)
        except WorkspaceError as exc:
            return _workspace_error(exc)
        result = job.get("result") if isinstance(job.get("result"), Mapping) else {}
        snapshot = {
            "run_id": job_id,
            "execution_mode": "live" if app.config.get("SHOWCASE_MODE") == "live" else "fake",
            "status": str(job.get("status", "unavailable")).upper(),
            "stage": _job_stage(events),
            "result": result,
            "final_response": result.get("final_response"),
            "error": job.get("error"),
            "asset_refs": ([{**app.extensions["showcase_files"].get(job.get("input_user_file_id"), {"file_id": job.get("input_user_file_id")}), "vision_status": "unavailable"}] if job.get("input_user_file_id") else []),
            "vision_status": "unavailable" if job.get("input_user_file_id") else None,
        }
        tool_results = [event["data"] for event in events if event.get("event") == "tool_completed"]
        verification = {"status": "unknown", "findings": ["verification_not_run"]}
        if job.get("verification_mode") == "required" and not tool_results:
            verification["findings"] = ["needs_review", "tool_evidence_missing"]
        report = app.extensions["showcase_evidence_exporter"].report(snapshot, tool_results=tool_results, verification=verification)
        return jsonify({"version": app.extensions["showcase_evidence_exporter"].report_version, "evidence_id": job_id, "status": job.get("status"), "mode": snapshot["execution_mode"], "report": report})

    @app.post("/api/runs/<run_id>/resume")
    def resume_run(run_id: str) -> tuple[Response, int]:
        try:
            snapshot = service.get_run(run_id)
            if snapshot["status"] not in {"FAILED", "NEEDS_REVIEW"}:
                return _json_error("run_not_reviewable", 409)
            resumed = service.resume_run(run_id)
            return jsonify(resumed), 200
        except RunNotFoundError as exc:
            return _json_error(exc.category, 404)
        except RunResumeUnavailable as exc:
            return _json_error(exc.category, 409)

    return app


def main() -> None:
    """Run the loopback Flask Showcase server."""

    parser = argparse.ArgumentParser(description="Local v0.2 Flask Showcase API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    config: dict[str, Any] = {"SHOWCASE_MODE": args.mode}
    if args.data_dir:
        config["SHOWCASE_DATA_DIR"] = args.data_dir
    app = create_app(config)
    app.run(host=args.host, port=args.port, debug=False)


def _storage_paths(config: Mapping[str, Any], database_path: str | Path | None) -> tuple[Path, Path]:
    configured_root = config.get("SHOWCASE_DATA_DIR") or os.getenv("SHOWCASE_DATA_DIR")
    configured_root = configured_root or os.getenv("SHOWCASE_STORAGE_DIR")
    configured_root = configured_root or os.getenv("SHOWCASE_ARTIFACTS_DIR")
    root = Path(configured_root or "artifacts/showcase-v0.2")
    configured_database = database_path or config.get("SHOWCASE_DATABASE_PATH")
    configured_database = configured_database or os.getenv("SHOWCASE_DATABASE_PATH")
    database = Path(configured_database) if configured_database else root / "showcase.sqlite3"
    if str(database) != ":memory:":
        database.parent.mkdir(parents=True, exist_ok=True)
    return root, database


def _auth_payload(session: AuthSession) -> dict[str, Any]:
    return {
        "isLoggedIn": True,
        "username": session.username,
        "role": "user",
        "permissions": list(session.permissions),
        "csrf_token": session.csrf_token,
        "dashboard": {"access": "dashboard.access" in session.permissions},
    }


def _set_auth_cookie_if_new(response: Response, store: LoopbackStore) -> Response:
    if getattr(g, "auth_session", None) is None:
        session, _created = store.get_or_create(request.cookies.get(AUTH_COOKIE))
        g.auth_session = session
        _set_auth_cookie(response, session)
    return response


def _set_auth_cookie(response: Response, session: AuthSession) -> None:
    response.set_cookie(AUTH_COOKIE, session.session_id, httponly=True, samesite="Lax", path="/")


def _parse_event_cursor(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    if value.startswith("+") or value.startswith("-"):
        return None
    try:
        cursor = int(value, 10)
    except ValueError:
        return None
    if cursor < 0 or cursor > 9_007_199_254_740_991:
        return None
    return cursor


def _json_error(error: str, status: int) -> tuple[Response, int]:
    messages = {
        "auth_required": "请先完成本地登录。",
        "csrf_required": "请求缺少安全令牌。",
        "csrf_invalid": "安全令牌无效。",
        "invalid_json": "请求体必须是有效 JSON。",
        "body_must_be_object": "请求体必须是对象。",
        "capability_unavailable": "当前环境未启用该能力。",
        "not_found": "请求的资源不存在。",
        "invalid_last_event_id": "事件游标无效。",
    }
    response = jsonify({
        "success": False,
        "error": error,
        "code": error,
        "message": messages.get(error, "请求无法完成，请检查输入后重试。"),
        "request_id": g.get("request_id"),
    })
    return response, status


def _workspace_error(error: WorkspaceError) -> tuple[Response, int]:
    return _json_error(error.code, error.status)


def _require_auth(session: AuthSession | None) -> AuthSession:
    if session is None:
        raise WorkspaceError("auth_required", status=401)
    return session


def _request_object() -> dict[str, Any] | tuple[Response, int]:
    try:
        payload = request.get_json(silent=False)
    except (BadRequest, UnsupportedMediaType):
        return _json_error("invalid_json", 400)
    if not isinstance(payload, dict):
        return _json_error("body_must_be_object", 400)
    return payload


def _job_stage(events: list[Mapping[str, Any]]) -> str:
    """Map the latest public Job event to a report stage."""

    if not events:
        return "unknown"
    latest = events[-1].get("data", {})
    return str(latest.get("stage") or latest.get("node_name") or latest.get("type") or "unknown")


def _dashboard_page() -> str:
    title = html.escape("MathAgent Showcase Workbench")
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{title}</title></head><body><main><h1>{title}</h1>"
        "<p>本机 loopback 工作区。</p></main></body></html>"
    )


if __name__ == "__main__":
    main()
