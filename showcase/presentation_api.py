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
    @blueprint.get("/api/agent/jobs/<job_id>/outputs/<mode>")
    def present_job(job_id: str, mode: str):
        """Generate only on explicit POST; GET restores an existing current output."""
        if mode not in MODES:
            return _error("presentation_mode_invalid", 400)
        user_id = getattr(g.auth_session, "user_id", None)
        if not user_id:
            return _error("auth_required", 401)
        try:
            job = job_loader(job_id, user_id)
        except WorkspaceError as exc:
            return _error(exc.code, exc.status)
        result = job.get("result") or {}
        ordinary = (result.get("faithful") or {}).get("version") == "faithful-task-v1"
        if "presentation_mode" not in result and not ordinary:
            return _error("presentation_run_not_frozen", 409)
        frozen = (job.get("result") or {}).get("presentation_mode")
        if frozen is not None and frozen != mode:
            return _error("presentation_mode_mismatch", 409)
        if job.get("status") not in {"succeeded", "failed", "canceled"}:
            return _error("presentation_job_not_terminal", 409)
        try:
            public = report_loader(job_id, user_id)
        except WorkspaceError as exc:
            return _error(exc.code, exc.status)
        if request.method == "POST":
            body = request.get_json(silent=True)
            if body is not None and not isinstance(body, Mapping):
                return _error("presentation_request_invalid", 400)
        if result.get("presentation_rule"):
            from .output_generation import source_job
            snapshot = presentation_snapshot(source_job(workspace_service, user_id, job_id))
            artifact = workspace_service.get_presentation(
                user_id=user_id, job_id=job_id, mode=mode,
                source_fingerprint=snapshot["fingerprint"])
            if artifact is None:
                return _error("presentation_pending_or_stale", 409)
            response = jsonify({"version": artifact["schema_version"], "evidence_id": job_id,
                "status": job["status"], "mode": mode, "answer": snapshot["answer"],
                "presentation": artifact, "presentation_history": [], "report": public["report"]})
            response.headers["Cache-Control"] = "no-store"
            return response
        snapshot = presentation_snapshot(job, public)
        body = request.get_json(silent=True) if request.method == "POST" else {}
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
                if request.method == "GET":
                    return _error("presentation_unavailable", 404)
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
        response = jsonify({
            "version": artifact["schema_version"], "evidence_id": job_id,
            "status": job.get("status"), "mode": mode,
            "answer": public["report"]["answer"], "presentation": artifact,
            "presentation_history": history, "report": public["report"],
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    app.register_blueprint(blueprint)


def _error(code: str, status: int):
    return jsonify({"code": code, "error": code, "success": False}), status


def get_final_answer(workspace_service, user_id, job_id, public_report=None):
    """Read one saved final answer; never reconcile, generate, or resume work."""
    from .output_generation import generation_state, source_job

    job = source_job(workspace_service, user_id, job_id)
    result = job.get('result') or {}
    snapshot = presentation_snapshot(job)
    mode = result.get('presentation_mode', 'solve')
    answer = snapshot['answer']
    # export_result's nonempty transport fallback is not a delivered answer.
    if job['status'] in {'succeeded', 'failed', 'canceled'} and answer.strip() in {
            '', 'No complete answer is available for this run.'}:
        return {'job_id': job_id, 'status': job['status'], 'mode': mode, 'answer': '',
                'presentation_status': 'unavailable',
                'notice': '本次任务没有可用解答，请查看任务状态与求解进展。'}
    artifact = None
    status, notice = 'legacy', '历史答复，保留原有格式。'
    if result.get('presentation_rule'):
        state = generation_state(workspace_service, job_id)
        status, notice = 'pending', '正在整理答复。'
        answer = ''
        if state:
            if state['source'] != snapshot['fingerprint'] or state['status'] == 'stale':
                status, notice = 'stale', '答复来源已变化，显示当前原答案。'
            elif state['status'] in {'failed', 'unknown'}:
                status, notice = 'failed', '所选格式生成失败或结果待核对，显示原答案。'
            elif state['status'] == 'ready':
                artifact = workspace_service.get_presentation(user_id=user_id, job_id=job_id,
                    mode=mode, source_fingerprint=snapshot['fingerprint'])
                if artifact and artifact['status'] == 'ready':
                    answer = '\n\n'.join(p['text'] for p in artifact['paragraphs'])
                    status, notice = 'ready', '答复表达不代表新增数学验证。'
                else:
                    artifact = None
                    status, notice = 'unavailable', '答复暂不可用，显示原答案。'
            if status not in {'ready', 'pending'}:
                answer = snapshot['answer']
    if status != 'pending' and not answer:
        status, notice = 'unavailable', '当前没有可用答复，请核对任务状态。'
    if answer:
        scope = snapshot['scope']
        completion = artifact.get('completion') if artifact else (snapshot.get('selection') or {}).get('completeness')
        selection = snapshot.get('selection')
        reviewed = (job['status'] == 'succeeded' and answer == snapshot['answer']
            and snapshot['whole_review'] == 'accepted' and snapshot['answer_binding'] == 'same_artifact'
            and any(source.get('scope') == 'whole_solution_llm_review'
                    and source.get('artifact') == snapshot['answer_artifact']
                    and source.get('status') == 'current' for source in snapshot['sources'])
            and (not selection or (selection.get('eligible')
                 and selection.get('completeness') == 'complete'
                 and selection.get('selected_answer_artifact') == snapshot['answer_artifact'])))
        if reviewed:
            notice += ' 当前原答案已完成并经整题模型审查；不代表步骤级或形式化证明。'
        elif completion in {'partial', 'incomplete'} or scope['unresolved'] or scope['covered'] < scope['total']:
            notice += f" 当前仅为部分结果，仍有未完成目标；已覆盖 {scope['covered']}/{scope['total']} 项目标。"
        if not reviewed:
            notice += ' 当前答复未验证，不代表整题证明。'
    return {'job_id': job_id, 'status': job['status'], 'mode': mode, 'answer': answer,
            'presentation_status': status, 'notice': notice}
