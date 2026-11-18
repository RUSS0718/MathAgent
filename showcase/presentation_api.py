"""Authenticated S06 output endpoints over the existing Job/report seam."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from flask import Blueprint, g, jsonify, request

from .presentation import (
    MODES,
    build_presentation,
    failed_presentation,
    presentation_snapshot,
    revalidate,
)
from .workspace import WorkspaceError


def register_presentation_api(app, *, workspace_service, job_loader: Callable, report_loader: Callable):
    """Register explicit output modes without creating a solver or budget path."""
    blueprint = Blueprint("s06_presentation", __name__)

    @blueprint.post("/api/agent/jobs/<job_id>/<mode>")
    def present_job(job_id: str, mode: str):
        if mode not in MODES:
            return _error("presentation_mode_invalid", 400)
        user_id = getattr(g.auth_session, "user_id", None)
        if not user_id:
            return _error("auth_required", 401)
        try:
            job = job_loader(job_id, user_id)
        except WorkspaceError as exc:
            return _error(exc.code, exc.status)
        if "presentation_mode" not in (job.get("result") or {}):
            return _error("presentation_run_not_frozen", 409)
        frozen = (job.get("result") or {}).get("presentation_mode")
        if frozen != mode:
            return _error("presentation_mode_mismatch", 409)
        try:
            public = report_loader(job_id, user_id)
        except WorkspaceError as exc:
            return _error(exc.code, exc.status)
        snapshot = presentation_snapshot(job, public)
        body = request.get_json(silent=True)
        if body is None:
            body = {}
        if not isinstance(body, Mapping):
            return _error("presentation_request_invalid", 400)
        if body.get("renderer") == "fail" and app.testing:
            artifact = failed_presentation(snapshot, mode, "presentation_renderer_failed")
        else:
            artifact = workspace_service.get_presentation(
                user_id=user_id, job_id=job_id, mode=mode,
                source_fingerprint=snapshot["fingerprint"],
            )
            if artifact is None:
                try:
                    artifact = build_presentation(snapshot, mode)
                except (TimeoutError, ConnectionError, ValueError):
                    artifact = failed_presentation(snapshot, mode, "presentation_renderer_failed")
                else:
                    artifact = workspace_service.save_presentation(
                        user_id=user_id, job_id=job_id, artifact=artifact,
                    )
        history = []
        for old in workspace_service.list_presentations(user_id=user_id, job_id=job_id, mode=mode):
            if old.get("source_fingerprint") != snapshot["fingerprint"]:
                history.append(revalidate(old, snapshot))
        return jsonify({
            "version": artifact["schema_version"], "evidence_id": job_id,
            "status": job.get("status"), "mode": mode,
            "answer": public["report"]["answer"], "presentation": artifact,
            "presentation_history": history, "report": public["report"],
        })

    app.register_blueprint(blueprint)


def _error(code: str, status: int):
    return jsonify({"code": code, "error": code, "success": False}), status
