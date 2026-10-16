"""Flask Showcase entry point for the v0.2 loopback workspace."""

from __future__ import annotations

import argparse
import html
import os
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from .evidence import EvidencePackExporter
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

AUTH_COOKIE = "auth_session"
MAX_BODY_BYTES = 1_000_000
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
    app.extensions["loopback_store"] = loopback_store
    app.extensions["showcase_run_service"] = service
    app.extensions["showcase_verifier"] = LightweightVerificationHook()
    app.extensions["showcase_evidence_exporter"] = EvidencePackExporter()

    @app.before_request
    def attach_request_context() -> Response | None:
        g.request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex}"
        g.auth_session = loopback_store.get(request.cookies.get(AUTH_COOKIE))
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.content_length is not None and request.content_length > MAX_BODY_BYTES:
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

    @app.get("/health")
    def health() -> Response:
        return jsonify(service.health())

    @app.get("/")
    @app.get("/dashboard")
    @app.get("/dashboard/")
    @app.get("/dashboard/<path:subpath>")
    def dashboard(subpath: str = "") -> Response:
        del subpath
        response = Response(_dashboard_page(), content_type="text/html; charset=utf-8")
        return _set_auth_cookie_if_new(response, loopback_store)

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
            "enabled": False,
            "status": "unavailable",
            "reason": "capability_unavailable",
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
        return jsonify([])

    @app.post("/api/upload_file")
    @app.post("/api/delete_file")
    def unavailable_file_operation() -> tuple[Response, int]:
        return _json_error("capability_unavailable", 503)

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


def _json_error(error: str, status: int) -> tuple[Response, int]:
    return jsonify({"success": False, "error": error, "code": error}), status


def _dashboard_page() -> str:
    title = html.escape("MathAgent Showcase Workbench")
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        f"<title>{title}</title></head><body><main><h1>{title}</h1>"
        "<p>本机 loopback 工作区。</p></main></body></html>"
    )


if __name__ == "__main__":
    main()
