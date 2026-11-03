"""Public Job event streaming and safe snapshot routes."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from flask import Flask, Response, g, jsonify, request, stream_with_context

from .loopback import AuthSession
from .workspace import WorkspaceError, WorkspaceService

_PUBLIC_EVENT_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_PUBLIC_EVENT_SUMMARIES = {
    "queued": "Job queued",
    "running": "Job started",
    "final_result": "Final result recorded",
    "verification_completed": "Verification completed",
    "interrupt": "Job paused for input",
    "resumed": "Job resumed",
    "canceled": "Job canceled",
    "needs_review": "Job needs review",
    "timeout": "Job timed out",
    "error": "Job failed",
    "solver_progress": "Solver progress recorded",
    "tool_completed": "Tool execution completed",
    "tool_call_result": "Tool call result recorded",
}


def public_event_summary(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project one persisted event to a fixed, non-sensitive public summary."""

    code = event.get("event")
    if not isinstance(code, str) or _PUBLIC_EVENT_CODE.fullmatch(code) is None:
        return None
    summary = _PUBLIC_EVENT_SUMMARIES.get(code)
    if summary is None:
        return None
    result: dict[str, Any] = {"event": code, "summary": summary}
    data = event.get("data")
    activity = event.get("stream_activity")
    if activity is None and isinstance(data, Mapping):
        activity = data.get("stream_activity")
    safe_activity = _public_stream_activity(activity)
    if code == "solver_progress" and safe_activity:
        result["stream_activity"] = safe_activity
    return result


def _public_stream_activity(value: Any) -> dict[str, Any]:
    """Keep only typed timing counters and states from stream activity."""

    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    timestamps = (
        "dispatched_at", "response_headers_at", "first_event_at",
        "first_reasoning_at", "first_content_at", "last_content_at",
        "last_activity_at", "completion_at",
    )
    for key in timestamps:
        item = value.get(key)
        if isinstance(item, str) and _is_timestamp(item):
            result[key] = item
    for key in ("event_count", "reasoning_chars", "content_bytes"):
        item = value.get(key)
        if type(item) is int and item >= 0:
            result[key] = item
    if type(value.get("usage_known")) is bool:
        result["usage_known"] = value["usage_known"]
    if value.get("status") in {"dispatched", "streaming", "completed", "unknown"}:
        result["status"] = value["status"]
    return result


def _is_timestamp(value: str) -> bool:
    """Accept ISO timestamps only when their timezone is explicit."""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def register_job_event_route(
    app: Flask,
    workspace_service: WorkspaceService,
    *,
    require_auth: Callable[[AuthSession | None], AuthSession],
    json_error: Callable[[str, int], tuple[Response, int]],
    workspace_error: Callable[[WorkspaceError], tuple[Response, int]],
) -> None:
    """Register the public Job event stream."""

    @app.get("/api/agent/jobs/<job_id>/events")
    def get_job_events(job_id: str) -> Response | tuple[Response, int]:
        session = require_auth(g.auth_session)
        raw_cursor = request.args.get("last_event_id")
        if raw_cursor is None:
            raw_cursor = request.headers.get("Last-Event-ID", "0")
        after_id = _parse_event_cursor(raw_cursor)
        if after_id is None:
            return json_error("invalid_last_event_id", 400)

        snapshot = request.args.get("snapshot")
        if snapshot not in {None, "1"}:
            return json_error("invalid_event_snapshot", 400)
        limit = 50
        if snapshot == "1":
            try:
                limit = int(request.args.get("limit", "50"))
            except (TypeError, ValueError):
                return json_error("invalid_event_limit", 400)
            if not 1 <= limit <= 100:
                return json_error("invalid_event_limit", 400)

        try:
            # Validate ownership before returning a lazy streaming response.
            workspace_service.get_job(job_id, session.user_id)
            if snapshot == "1":
                raw_events = workspace_service.events(job_id, session.user_id, after_id)
                raw_page = raw_events[:limit]
                events = [
                    {"id": event["id"], **summary}
                    for event in raw_page
                    if (summary := public_event_summary(event)) is not None
                ]
                next_cursor = raw_page[-1]["id"] if raw_page else after_id
                has_more = len(raw_events) > limit
            else:
                events = workspace_service.stream_events(job_id, session.user_id, after_id)
        except WorkspaceError as exc:
            return workspace_error(exc)

        if snapshot == "1":
            response = jsonify(
                {
                    "job_id": job_id,
                    "events": events,
                    "next_cursor": next_cursor,
                    "has_more": has_more,
                }
            )
            response.headers["Cache-Control"] = "no-store"
            return response

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
