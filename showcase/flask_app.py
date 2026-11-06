"""Flask Showcase entry point for the v0.2 loopback workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from flask import Flask, Response, g, jsonify, request, send_from_directory
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

from presentation_pages import render_presentation_page

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - showcase dependency installs python-dotenv
    load_dotenv = None
else:
    load_dotenv()

from .campaign_api import register_campaigns
from .evidence import EvidencePackExporter, replay_evidence
from .final_evidence import checked_verification
from .job_events import register_job_event_route
from .loopback import AuthSession, LoopbackStore
from .polynomial import PolynomialChecker
from .profile import SHOWCASE_PROFILE, ensure_showcase_profile
from .run_budget import RunBudgetLimits
from .run_service import (
    RunNotFoundError,
    RunResumeUnavailable,
    RunService,
    RunValidationError,
)
from .server import create_live_pipeline, create_live_service
from .star_product_modes import STAR_MODES
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
        SHOWCASE_JOB_DELAY_SECONDS=0.05,
        SHOWCASE_WORKER_ENABLED=True,
        SHOWCASE_WAITING_INPUT_MARKER="",
        SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED=False,
        SHOWCASE_EXPERIMENT_PAIR_ENABLED=False,
    )
    if config:
        app.config.from_mapping(dict(config))

    storage_root, resolved_database = _storage_paths(app.config, database_path)
    service_database = getattr(getattr(service, '_store', None), 'database_path', ':memory:')
    if service is not None and ((service_database == ':memory:' and (app.config.get('SHOWCASE_LIVE_PIPELINE') is not None or app.config.get('SHOWCASE_STAR_ENABLED') is True)) or (service_database != ':memory:' and Path(service_database).resolve() != resolved_database.resolve())):
        raise ValueError('service_database_mismatch')
    storage_root.mkdir(parents=True, exist_ok=True)
    (storage_root / "attachments").mkdir(exist_ok=True)
    (storage_root / "events").mkdir(exist_ok=True)
    app.config["SHOWCASE_DATA_DIR"] = str(storage_root)
    app.config["SHOWCASE_DATABASE_PATH"] = str(resolved_database)

    if app.config["SHOWCASE_MODE"] not in {"fake", "live"}:
        raise ValueError("showcase_mode_invalid")
    from .star_product_modes import capabilities as star_capabilities
    from .star_product_runtime import create_star_product_pipeline

    star_pipeline = create_star_product_pipeline(
        resolved_database, storage_root=storage_root, config=app.config)
    loopback_store = LoopbackStore(resolved_database)
    live_pipeline = app.config.get("SHOWCASE_LIVE_PIPELINE")
    if service is None:
        if app.config["SHOWCASE_MODE"] == "live":
            service = create_live_service(database_path=resolved_database)
            if live_pipeline is None:
                live_pipeline = create_live_pipeline()
        else:
            service = RunService(database_path=resolved_database)
    shared_connection = getattr(getattr(service, "_store", None), "_connection", None)
    # File-backed Run readers must not step the Job writer's connection from
    # another thread. Job and budget writes still share Workspace's connection.
    if getattr(getattr(service, "_store", None), "database_path", ":memory:") != ":memory:":
        shared_connection = None
    workspace_service = WorkspaceService(
        resolved_database,
        connection=shared_connection,
        execution_mode=str(app.config.get("SHOWCASE_MODE", "fake")),
        execution_delay=float(app.config.get("SHOWCASE_JOB_DELAY_SECONDS", 0.05)),
        worker_enabled=bool(app.config.get("SHOWCASE_WORKER_ENABLED", True)),
        waiting_input_marker=str(app.config.get("SHOWCASE_WAITING_INPUT_MARKER", "")),
        pipeline=live_pipeline,
        star_pipeline=star_pipeline,
    )
    app.extensions["loopback_store"] = loopback_store
    app.extensions["showcase_run_service"] = service
    app.extensions["showcase_workspace_service"] = workspace_service
    app.extensions["showcase_live_pipeline"] = live_pipeline
    app.extensions["showcase_verifier"] = LightweightVerificationHook()
    app.extensions["showcase_evidence_exporter"] = EvidencePackExporter()
    files_index = storage_root / "attachments" / "index.json"
    try:
        persisted_files = json.loads(files_index.read_text(encoding="utf-8")) if files_index.is_file() else {}
    except (OSError, ValueError):
        persisted_files = {}
    app.extensions["showcase_files"] = persisted_files if isinstance(persisted_files, dict) else {}
    app.extensions["showcase_files_index"] = files_index
    register_campaigns(app, workspace_service, service, resolved_database, storage_root)

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
        solver_modes = star_capabilities(star_pipeline is not None, star_pipeline)
        response = jsonify(
            {
                "profile": profile,
                "jobs": {"enabled": True, "status": "available"},
                "sse": {"enabled": True, "status": "available"},
                "solver_modes": solver_modes,
                "verification_mode": VERIFICATION_MODES,
                "files": {"upload": upload},
                "execution": {
                    "mode": getattr(live_pipeline, "execution_mode", str(app.config.get("SHOWCASE_MODE", "fake"))),
                    "provider": "fake" if getattr(live_pipeline, "execution_mode", app.config.get("SHOWCASE_MODE")) == "fake" else "intern",
                    "status": "configured" if os.getenv("INTERN_API_KEY") else "missing_credentials",
                },
                "applied_model_config": _applied_model_config(star_pipeline, solver_modes),
                "capabilities": {
                    "jobs": True,
                    "sse": True,
                    "verification_mode": VERIFICATION_MODES,
                    "file_upload": upload,
                },
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

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
        budget_limits = None
        deadline_at = payload.get("deadline_at")
        raw_limits = payload.get("budget_limits")
        if raw_limits is not None:
            expected_limit_keys = {
                "max_model_calls", "max_http_attempts", "max_tool_calls",
                "max_tokens", "max_runtime_seconds",
            }
            if not isinstance(raw_limits, dict) or set(raw_limits) != expected_limit_keys:
                return _json_error("run_budget_invalid", 400)
            try:
                budget_limits = RunBudgetLimits(**raw_limits)
            except (TypeError, ValueError):
                return _json_error("run_budget_invalid", 400)
            if (
                type(deadline_at) not in {int, float}
                or not math.isfinite(deadline_at)
                or deadline_at <= 0
            ):
                return _json_error("run_budget_deadline_invalid", 400)
        elif deadline_at is not None:
            return _json_error("run_budget_invalid", 400)
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
                budget_limits=budget_limits,
                deadline_at=deadline_at,
                solver_mode=payload.get("solver_mode", "legacy"),
                solver_options=payload.get("solver_options"),
                solver_hint=payload.get("solver_hint"),
            )
        except WorkspaceError as exc:
            return _workspace_error(exc)
        status = 200 if existing else 202
        return jsonify({"success": True, "job_id": job["job_id"], "status": job["status"], "existing": existing}), status

    if app.config.get("SHOWCASE_EXPERIMENT_PAIR_ENABLED") is True:
        @app.post("/api/experiments/pairs/<pair_id>/readiness")
        def verify_experiment_pair_readiness(pair_id: str) -> tuple[Response, int]:
            _require_auth(g.auth_session)
            payload = _request_object()
            if isinstance(payload, tuple):
                return payload
            try:
                from .experiment_manifest import canonical_json
                from .experiment_pair import pair_manifest_digest, validate_pair_manifest

                pair = validate_pair_manifest(payload.get("pair_manifest"))
                report = payload.get("readiness_report")
                if (
                    pair["pair_id"] != pair_id
                    or payload.get("pair_sha256") != pair_manifest_digest(pair)
                    or not isinstance(report, dict)
                    or hashlib.sha256(canonical_json(report)).hexdigest()
                    != pair["readiness_report_sha256"]
                    or type(report.get("issue_number")) is not int
                    or report["issue_number"] != 127
                    or report.get("status") != "PASS"
                ):
                    raise ValueError("experiment_readiness_mismatch")
                verifier = app.config.get("SHOWCASE_EXPERIMENT_READINESS_VERIFIER")
                if not callable(verifier):
                    raise ValueError("experiment_readiness_not_verified")
                verified = verifier(report)
                if not isinstance(verified, dict) or verified.get("status") != "PASS":
                    raise ValueError("experiment_readiness_not_verified")
                return jsonify({"status": "PASS"}), 200
            except Exception:
                return _json_error("experiment_readiness_not_verified", 400)

        @app.post("/api/experiments/pairs/<pair_id>/arms/<arm>/jobs")
        def create_experiment_pair_job(pair_id: str, arm: str) -> tuple[Response, int]:
            session = _require_auth(g.auth_session)
            payload = _request_object()
            if isinstance(payload, tuple):
                return payload
            try:
                from .experiment_manifest import canonical_json
                from .experiment_pair import pair_manifest_digest, validate_pair_manifest

                pair = validate_pair_manifest(payload.get("pair_manifest"))
                if pair["pair_id"] != pair_id:
                    raise ValueError("experiment_pair_id_mismatch")
                pair_sha256 = payload.get("pair_sha256")
                if pair_manifest_digest(pair) != pair_sha256:
                    raise ValueError("experiment_pair_manifest_hash_mismatch")
                if arm not in {"baseline", "variant"}:
                    raise ValueError("experiment_pair_arm_invalid")
                report = payload.get("readiness_report")
                report_hash = hashlib.sha256(canonical_json(report)).hexdigest()
                if (
                    not isinstance(report, dict)
                    or type(report.get("issue_number")) is not int
                    or report["issue_number"] != 127
                    or report_hash != pair["readiness_report_sha256"]
                    or report.get("status") != "PASS"
                ):
                    raise ValueError("experiment_readiness_not_passed")
                readiness_verifier = app.config.get("SHOWCASE_EXPERIMENT_READINESS_VERIFIER")
                if not callable(readiness_verifier) or readiness_verifier(report).get("status") != "PASS":
                    raise ValueError("experiment_readiness_not_verified")

                arm_registration = pair[arm]
                manifest = arm_registration["manifest"]
                sample_id = payload.get("sample_id")
                samples = [sample for sample in manifest["samples"] if sample["id"] == sample_id]
                if len(samples) != 1:
                    raise ValueError("experiment_sample_invalid")
                message = payload.get("message")
                if not isinstance(message, str) or not message.strip():
                    raise ValueError("message_must_be_non_empty")
                if hashlib.sha256(message.encode("utf-8")).hexdigest() != samples[0]["text_sha256"]:
                    raise ValueError("experiment_sample_hash_mismatch")

                raw_limits = payload.get("budget_limits")
                if raw_limits != manifest["run_limits"]:
                    raise ValueError("run_budget_invalid")
                budget_limits = RunBudgetLimits(**raw_limits)
                deadline_at = payload.get("deadline_at")
                if (
                    type(deadline_at) not in {int, float}
                    or not math.isfinite(deadline_at)
                    or deadline_at <= 0
                    or deadline_at > time.time() + budget_limits.max_runtime_seconds
                ):
                    raise ValueError("run_budget_deadline_invalid")

                binding = {
                    "pair_id": pair["pair_id"],
                    "pair_sha256": pair_sha256,
                    "arm": arm,
                    "arm_run_id": arm_registration["run_id"],
                    "factor": pair["factor"],
                    "features": dict(arm_registration["features"]),
                    "applied_config_status": "pre_execution",
                    "applied_component_config": None,
                }
                job, existing = workspace_service.create_job(
                    user_id=session.user_id,
                    session_id=payload.get("session_id"),
                    problem=message.strip(),
                    idempotency_key=request.headers.get("Idempotency-Key", ""),
                    verification_mode=manifest["model"]["verification_mode"],
                    budget_limits=budget_limits,
                    deadline_at=deadline_at,
                    solver_mode=manifest["model"]["solver_mode"],
                    experiment_binding=binding,
                )
            except WorkspaceError as exc:
                return _workspace_error(exc)
            except Exception:
                return _json_error("experiment_pair_request_invalid", 400)
            status = 200 if existing else 202
            return jsonify({"success": True, "job_id": job["job_id"], "status": job["status"], "existing": existing}), status

    if app.config.get("SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED") is True:
        @app.get("/api/agent/jobs/by-idempotency")
        def get_job_by_idempotency_key() -> tuple[Response, int] | Response:
            session = _require_auth(g.auth_session)
            idempotency_key = request.headers.get("Idempotency-Key", "")
            request_digest = request.headers.get("X-Request-Digest", "")
            try:
                if uuid.UUID(idempotency_key).version != 4:
                    raise ValueError
            except (AttributeError, TypeError, ValueError):
                return _json_error("idempotency_key_invalid", 400)
            if (
                len(request_digest) != 64
                or any(character not in "0123456789abcdef" for character in request_digest)
            ):
                return _json_error("request_digest_invalid", 400)
            try:
                result = workspace_service.get_job_by_idempotency_key(
                    user_id=session.user_id,
                    idempotency_key=idempotency_key,
                    request_digest=request_digest,
                )
            except WorkspaceError as exc:
                return _workspace_error(exc)
            return jsonify(result)

    @app.get("/api/agent/jobs/<job_id>/artifacts/<digest>")
    def tool_artifact(job_id, digest):
        from .tool_artifacts import ToolArtifactError

        session = _require_auth(g.auth_session)
        try:
            workspace_service.get_job(job_id, session.user_id)
        except WorkspaceError as exc:
            return _workspace_error(exc)
        executor = getattr(getattr(star_pipeline, "registry", None), "container_python_executor", None)
        if executor is None:
            return _json_error("artifact_unavailable", 404)
        try:
            content = executor.artifacts.read(job_id, digest)
        except ToolArtifactError as exc:
            return _json_error(str(exc), 404 if str(exc) == "artifact_not_found" else 409)
        return Response(content, content_type="application/octet-stream", headers={
            "Content-Disposition": "attachment; filename=" + digest,
            "X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"})

    @app.get("/api/agent/jobs/active")
    def active_jobs() -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        session_id = request.args.get("session_id")
        try:
            return jsonify({"success": True, "jobs": workspace_service.active_jobs(session.user_id, session_id)})
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.post("/api/agent/jobs/<job_id>/polynomial-check")
    def verify_job_polynomial(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        payload = _request_object()
        if isinstance(payload, tuple):
            return payload
        try:
            result = PolynomialChecker().check(payload)
            workspace_service.record_verification(user_id=session.user_id, job_id=job_id, result=result)
            return jsonify({"success": True, "job_id": job_id, "result": result}), 200
        except WorkspaceError as exc:
            return _workspace_error(exc)

    @app.get("/api/agent/jobs/<job_id>")
    def get_job(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            return jsonify({"success": True, **workspace_service.get_job(job_id, session.user_id)})
        except WorkspaceError as exc:
            return _workspace_error(exc)

    register_job_event_route(
        app,
        workspace_service,
        require_auth=_require_auth,
        json_error=_json_error,
        workspace_error=_workspace_error,
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
                retry_call=payload.get("retry_call"),
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
        tool_results = _stored_tool_results(snapshot, events)
        verification = _stored_verification(
            snapshot, tool_results, app.extensions["showcase_verifier"]
        )
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
        tool_results = _stored_tool_results(snapshot, events)
        verification = _stored_verification(
            snapshot, tool_results, app.extensions["showcase_verifier"]
        )
        return jsonify({
            "version": app.extensions["showcase_evidence_exporter"].report_version,
            "evidence_id": run_id,
            "status": snapshot.get("status"),
            "mode": snapshot.get("execution_mode", "unavailable"),
            "report": app.extensions["showcase_evidence_exporter"].report(
                snapshot, tool_results=tool_results, verification=verification
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

    @app.get("/api/agent/jobs/<job_id>/candidate-replay")
    def replay_job_candidates(job_id: str) -> Response | tuple[Response, int]:
        session = _require_auth(g.auth_session)
        try:
            job = workspace_service.get_job(job_id, session.user_id)
        except WorkspaceError as exc:
            return _workspace_error(exc)
        if (job.get("result") or {}).get("solver_mode") not in STAR_MODES:
            return _json_error("star_replay_unavailable", 409)
        from .star_product_candidates import replay_candidates
        from .star_product_projection import persisted_solver

        with workspace_service.store._lock:
            persisted = persisted_solver(workspace_service.store._connection, job_id)
        if persisted is None:
            return _json_error("star_replay_unavailable", 409)
        run, _ = persisted
        return jsonify(replay_candidates(run))

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
            "execution_mode": result.get(
                "execution_mode",
                "unavailable",
            ),
            "status": str(job.get("status", "unavailable")).upper(),
            "stage": _job_stage(events),
            "result": result,
            "final_response": result.get("final_response"),
            "error": job.get("error"),
            "asset_refs": ([{**app.extensions["showcase_files"].get(job.get("input_user_file_id"), {"file_id": job.get("input_user_file_id")}), "vision_status": "unavailable"}] if job.get("input_user_file_id") else []),
            "vision_status": "unavailable" if job.get("input_user_file_id") else None,
        }
        stored_tools = result.get("tool_results") if isinstance(result.get("tool_results"), list) else []
        tool_results = [item for item in stored_tools if isinstance(item, Mapping)]
        if not tool_results:
            tool_results = [
                {
                    "name": event["data"].get("name", event["data"].get("tool_name")),
                    "status": event["data"].get("status"),
                    "summary": event["data"].get("summary", ""),
                    "result_summary": event["data"].get("summary", ""),
                }
                for event in events
                if event.get("event") in {"tool_completed", "tool_call_result"}
                and isinstance(event.get("data"), Mapping)
            ]
        verification = _stored_verification(
            snapshot, tool_results, app.extensions["showcase_verifier"]
        )
        if job.get("verification_mode") == "required" and not tool_results:
            verification["findings"] = ["needs_review", "tool_evidence_missing"]
        report = app.extensions["showcase_evidence_exporter"].report(snapshot, tool_results=tool_results, verification=verification)
        return jsonify({"version": app.extensions["showcase_evidence_exporter"].report_version, "evidence_id": job_id, "status": job.get("status"), "mode": snapshot["execution_mode"], "solver": {key: (job.get("result") or {}).get(key) for key in ("solver_mode", "missing_capabilities", "evidence_kind", "solver")}, "report": report})

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


def _applied_model_config(star_pipeline: Any, solver_modes: list[dict[str, Any]]) -> dict[str, Any]:
    """Project only the active STAR adapter settings needed by frozen experiment preflight."""
    from .stream_preference import profile_set_fingerprint

    adapter = getattr(star_pipeline, "adapter", None)
    read_applied_config = getattr(adapter, "applied_config", None)
    try:
        model = read_applied_config() if callable(read_applied_config) else None
    except Exception:
        model = None
    modes = sorted(
        record["solver_mode"]
        for record in solver_modes
        if record.get("solver_mode", "").startswith("star_") and record.get("enabled") is True
    )
    transport = None
    if star_pipeline is not None:
        transport = {
            "policy": star_pipeline.transport_policy,
            "profile_set_fingerprint": profile_set_fingerprint(
                star_pipeline.stream_profiles
            ),
        }
    available = (
        star_pipeline is not None
        and isinstance(model, dict)
        and set(model) == {
            "name",
            "thinking_mode",
            "temperature",
            "max_output_tokens",
            "request_timeout_seconds",
            "retry",
        }
        and isinstance(model["name"], str)
        and bool(model["name"].strip())
        and isinstance(model["thinking_mode"], bool)
        and type(model["temperature"]) in {int, float}
        and math.isfinite(model["temperature"])
        and model["temperature"] >= 0
        and type(model["max_output_tokens"]) is int
        and model["max_output_tokens"] > 0
        and type(model["request_timeout_seconds"]) is int
        and model["request_timeout_seconds"] > 0
        and type(model["retry"]) is int
        and model["retry"] >= 0
        and transport is not None
    )
    projection = {
        "schema_version": 1,
        "status": "available" if available else "unavailable",
        "model": model if available else None,
        "solver_modes": modes if available else [],
        "verification_modes": VERIFICATION_MODES if available else [],
        "transport": transport if available else None,
    }
    canonical = json.dumps(
        projection, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    projection["config_sha256"] = hashlib.sha256(canonical).hexdigest()
    return projection


def main() -> None:
    """Run the loopback Flask Showcase server."""

    parser = argparse.ArgumentParser(description="Local v0.2 Flask Showcase API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--mode", choices=("fake", "live"), default="fake")
    parser.add_argument("--data-dir", default=None)
    parser.add_argument("--star-limited", action="store_true", help="Enable explicit limited STAR selection")
    parser.add_argument("--star-full", action="store_true", help="Enable full STAR presets after isolated runtime preflight; requires exact image configuration")
    parser.add_argument(
        "--experiment-idempotency-lookup",
        action="store_true",
        help="Enable the experiment CLI's idempotency lookup Job route",
    )
    args = parser.parse_args()
    config: dict[str, Any] = {"SHOWCASE_MODE": args.mode, "SHOWCASE_STAR_ENABLED": args.star_limited,
                              "SHOWCASE_STAR_FULL_ENABLED": args.star_full,
                              "SHOWCASE_EXPERIMENT_IDEMPOTENCY_LOOKUP_ENABLED": args.experiment_idempotency_lookup}
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
    messages = {
        "auth_required": "请先完成本地登录。",
        "csrf_required": "请求缺少安全令牌。",
        "csrf_invalid": "安全令牌无效。",
        "invalid_json": "请求体必须是有效 JSON。",
        "body_must_be_object": "请求体必须是对象。",
        "capability_unavailable": "当前环境未启用该能力。",
        "not_found": "请求的资源不存在。",
        "star_prerequisites_unverified": "完整 STAR 前置能力尚未通过验收，请选择明确受限模式。",
        "star_not_enabled": "服务尚未启用 STAR 受限模式。",
        "star_review_required": "STAR 必须执行整题审查，不能关闭验证。",
        "solver_mode_invalid": "求解模式无效或尚未实现。",
        "solver_options_unsupported": "当前 STAR 使用固定受限预设，不接受自定义开关。",
        "solver_hint_invalid": "STAR 提示须为 1 至 2000 字的非空文本。",
        "invalid_last_event_id": "事件游标无效。",
        "invalid_event_snapshot": "事件快照模式无效。",
        "invalid_event_limit": "事件快照数量无效。",
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


def _stored_tool_results(
    snapshot: Mapping[str, Any], events: list[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    result = snapshot.get("result")
    stored = result.get("tool_results") if isinstance(result, Mapping) else None
    if isinstance(stored, list):
        return [dict(item) for item in stored if isinstance(item, Mapping)]
    return [
        dict(event)
        for event in events
        if event.get("type") in {"tool_completed", "tool_call_result"}
    ]


def _stored_verification(
    snapshot: Mapping[str, Any],
    tool_results: list[dict[str, Any]],
    verifier: Any,
) -> dict[str, Any]:
    result = snapshot.get("result")
    stored = result.get("verification") if isinstance(result, Mapping) else None
    if isinstance(stored, Mapping):
        return dict(stored)
    checked = verifier.verify(dict(snapshot), tool_results)
    return checked_verification(str(snapshot.get("final_response") or ""), checked, tool_results)


def _dashboard_page() -> str:
    """Return the shared local presentation surface."""
    return render_presentation_page("unbuilt")


if __name__ == "__main__":
    main()
