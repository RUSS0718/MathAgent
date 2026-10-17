"""Persistent ChatSession and asynchronous Job service for the v0.2 workspace.

The workspace service deliberately sits beside :class:`RunService`.  The old
``/api/runs`` contract remains synchronous; this module owns the product chat
contract and queues one deterministic adapter call after durable acceptance.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .redaction import redact

ACTIVE_JOB_STATUSES = ("queued", "running", "waiting_input")
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "canceled")


class WorkspaceError(RuntimeError):
    """Stable error exposed by the workspace HTTP contract."""

    def __init__(self, code: str, *, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class WorkspaceStore:
    """SQLite repository for sessions, messages, jobs, and public event seam."""

    def __init__(self, database_path: str | Path = ":memory:", connection: sqlite3.Connection | None = None) -> None:
        self.database_path = str(database_path)
        self._lock = threading.RLock()
        self._owns_connection = connection is None
        self._connection = connection or sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                text TEXT NOT NULL,
                analysis_job_id TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(session_id, analysis_job_id, sender),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS workspace_jobs (
                job_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                problem TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error_code TEXT,
                input_user_file_id TEXT,
                verification_mode TEXT NOT NULL DEFAULT 'auto',
                idempotency_key TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, idempotency_key),
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS workspace_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES workspace_jobs(job_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS workspace_actions (
                user_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                operation TEXT NOT NULL,
                job_id TEXT NOT NULL,
                request_digest TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, idempotency_key),
                FOREIGN KEY (job_id) REFERENCES workspace_jobs(job_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_updated
                ON chat_sessions(user_id, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_chat_messages_session_order
                ON chat_messages(session_id, message_id);
            CREATE INDEX IF NOT EXISTS idx_workspace_jobs_session_status
                ON workspace_jobs(session_id, status);
            CREATE INDEX IF NOT EXISTS idx_workspace_events_job_id
                ON workspace_events(job_id, event_id);
            """
        )
        columns = {row["name"] for row in self._connection.execute("PRAGMA table_info(workspace_jobs)")}
        if "verification_mode" not in columns:
            self._connection.execute("ALTER TABLE workspace_jobs ADD COLUMN verification_mode TEXT NOT NULL DEFAULT 'auto'")
        if "input_user_file_id" not in columns:
            self._connection.execute("ALTER TABLE workspace_jobs ADD COLUMN input_user_file_id TEXT")
        self._connection.commit()

    def create_session(self, user_id: str, title: str = "新对话") -> str:
        session_id = f"session_{secrets.token_hex(16)}"
        now = _utc_now()
        with self._lock:
            self._connection.execute(
                "INSERT INTO chat_sessions(session_id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (session_id, user_id, title, now, now),
            )
            self._connection.commit()
        return session_id

    def list_sessions(self, user_id: str) -> list[list[Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT session_id,title,updated_at FROM chat_sessions WHERE user_id=? "
                "ORDER BY updated_at DESC, session_id DESC",
                (user_id,),
            ).fetchall()
        return [
            [row["session_id"], {"preview": row["title"], "last_time": row["updated_at"]}]
            for row in rows
        ]

    def session_exists(self, session_id: str, user_id: str) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?",
                (session_id, user_id),
            ).fetchone()
        return row is not None

    def rename_session(self, session_id: str, user_id: str, title: str) -> None:
        with self._lock:
            cursor = self._connection.execute(
                "UPDATE chat_sessions SET title=?,updated_at=? WHERE session_id=? AND user_id=?",
                (title, _utc_now(), session_id, user_id),
            )
            self._connection.commit()
        if cursor.rowcount == 0:
            raise WorkspaceError("session_not_found", status=404)

    def delete_session(self, session_id: str, user_id: str) -> None:
        with self._lock:
            self._assert_session(session_id, user_id)
            row = self._connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE session_id=? AND status IN ('queued','running','waiting_input') LIMIT 1",
                (session_id,),
            ).fetchone()
            if row is not None:
                raise WorkspaceError("active_job_conflict", status=409)
            self._connection.execute("DELETE FROM chat_sessions WHERE session_id=?", (session_id,))
            self._connection.commit()

    def load_messages(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        with self._lock:
            self._assert_session(session_id, user_id)
            rows = self._connection.execute(
                "SELECT sender,text,analysis_job_id,created_at FROM chat_messages WHERE session_id=? ORDER BY message_id",
                (session_id,),
            ).fetchall()
        return [
            {
                "sender": row["sender"],
                "text": row["text"],
                "analysis_job_id": row["analysis_job_id"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def create_job(
        self,
        *,
        user_id: str,
        session_id: str,
        problem: str,
        idempotency_key: str,
        request_digest: str,
        verification_mode: str = "auto",
        input_user_file_id: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Durably accept one Job and its user message before returning."""

        with self._lock:
            self._assert_session(session_id, user_id)
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT * FROM workspace_jobs WHERE user_id=? AND idempotency_key=?",
                    (user_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["request_digest"] != request_digest:
                        raise WorkspaceError("idempotency_conflict", status=409)
                    self._connection.commit()
                    return self._job_payload(existing), True

                active = self._connection.execute(
                    "SELECT 1 FROM workspace_jobs WHERE session_id=? AND status IN ('queued','running','waiting_input') LIMIT 1",
                    (session_id,),
                ).fetchone()
                if active is not None:
                    raise WorkspaceError("active_job_conflict", status=409)

                job_id = f"run_{secrets.token_hex(16)}"
                now = _utc_now()
                self._connection.execute(
                    "INSERT INTO workspace_jobs(job_id,session_id,user_id,problem,status,result_json,error_code,input_user_file_id,verification_mode,idempotency_key,request_digest,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (job_id, session_id, user_id, problem, "queued", None, None, input_user_file_id, verification_mode, idempotency_key, request_digest, now, now),
                )
                self._connection.execute(
                    "INSERT INTO chat_messages(session_id,sender,text,analysis_job_id,created_at) VALUES(?,?,?,?,?)",
                    (session_id, "user", problem, job_id, now),
                )
                self._insert_event(
                    job_id,
                    "queued",
                    {
                        "type": "queued",
                        "job_id": job_id,
                        "status": "queued",
                        "step_id": "queue",
                        "node_name": "queue",
                        "title": "任务已排队",
                        "summary": "任务已持久化并等待执行",
                        "asset_ref": ({"file_id": input_user_file_id, "vision_status": "unavailable"} if input_user_file_id else None),
                    },
                )
                self._insert_run(job_id, problem, now)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        assert row is not None
        return self._job_payload(row), False

    def start_job(self, job_id: str, *, execution_mode: str = "fake") -> bool:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None or row["status"] != "queued":
                    self._connection.rollback()
                    return False
                now = _utc_now()
                self._connection.execute("UPDATE workspace_jobs SET status='running',updated_at=? WHERE job_id=?", (now, job_id))
                self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "RUNNING", now, execution_mode=execution_mode, asset_refs=self._asset_refs(job_id))), now, job_id))
                self._insert_event(
                    job_id,
                    "running",
                    {
                        "type": "running",
                        "job_id": job_id,
                        "status": "running",
                        "step_id": "solve",
                        "node_name": "solve",
                        "title": "正在求解",
                        "summary": "确定性适配器正在处理题目",
                    },
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return True

    def complete_job(self, job_id: str, final_response: str, summary: str) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None or row["status"] in TERMINAL_JOB_STATUSES:
                    self._connection.rollback()
                    return
                now = _utc_now()
                result = {"final_response": final_response, "summary": summary}
                self._connection.execute(
                    "UPDATE workspace_jobs SET status='succeeded',result_json=?,updated_at=? WHERE job_id=?",
                    (_json(result), now, job_id),
                )
                self._connection.execute(
                    "INSERT OR IGNORE INTO chat_messages(session_id,sender,text,analysis_job_id,created_at) VALUES(?,?,?,?,?)",
                    (row["session_id"], "ai", final_response, job_id, now),
                )
                self._connection.execute(
                    "UPDATE chat_sessions SET updated_at=? WHERE session_id=?", (now, row["session_id"])
                )
                self._connection.execute(
                    "UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?",
                    (_json(_run_snapshot(job_id, "COMPLETED", now, result, asset_refs=self._asset_refs(job_id))), now, job_id),
                )
                self._insert_event(
                    job_id,
                    "final_result",
                    {
                        "type": "final_result",
                        "job_id": job_id,
                        "status": "succeeded",
                        "data": {"type": "text", "summary": final_response},
                    },
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def mark_waiting_input(self, job_id: str) -> None:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                self._connection.rollback()
                raise WorkspaceError("job_not_found", status=404)
            if row["status"] not in ACTIVE_JOB_STATUSES:
                self._connection.rollback()
                raise WorkspaceError("job_not_waiting_input", status=409)
            now = _utc_now()
            self._connection.execute("UPDATE workspace_jobs SET status='waiting_input',updated_at=? WHERE job_id=?", (now, job_id))
            self._insert_event(job_id, "interrupt", {"type": "interrupt", "job_id": job_id, "status": "waiting_input"})
            self._connection.commit()

    def control_job(self, *, user_id: str, job_id: str, operation: str, idempotency_key: str, request_digest: str) -> tuple[dict[str, Any], bool]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT operation,job_id,request_digest,response_json FROM workspace_actions WHERE user_id=? AND idempotency_key=?",
                    (user_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing["operation"] != operation or existing["job_id"] != job_id or existing["request_digest"] != request_digest:
                        raise WorkspaceError("idempotency_conflict", status=409)
                    result = _loads(existing["response_json"])
                    self._connection.commit()
                    return result, True
                row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
                if row is None:
                    raise WorkspaceError("job_not_found", status=404)
                status = row["status"]
                if operation == "cancel":
                    if status in TERMINAL_JOB_STATUSES and status != "canceled":
                        raise WorkspaceError("job_not_cancelable", status=409)
                    if status != "canceled":
                        now = _utc_now()
                        self._connection.execute("UPDATE workspace_jobs SET status='canceled',updated_at=? WHERE job_id=?", (now, job_id))
                        self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "CANCELED", now, asset_refs=self._asset_refs(job_id))), now, job_id))
                        self._insert_event(job_id, "canceled", {"type": "canceled", "job_id": job_id, "status": "canceled"})
                    result = {"success": True, "job_id": job_id, "status": "canceled"}
                else:
                    if status != "waiting_input":
                        raise WorkspaceError("job_not_resumable", status=409)
                    now = _utc_now()
                    self._connection.execute("UPDATE workspace_jobs SET status='queued',updated_at=? WHERE job_id=?", (now, job_id))
                    self._insert_event(job_id, "resumed", {"type": "resumed", "job_id": job_id, "status": "queued"})
                    result = {"success": True, "job_id": job_id, "status": "queued"}
                self._connection.execute(
                    "INSERT INTO workspace_actions(user_id,idempotency_key,operation,job_id,request_digest,response_json,created_at) VALUES(?,?,?,?,?,?,?)",
                    (user_id, idempotency_key, operation, job_id, request_digest, _json(result), _utc_now()),
                )
                self._connection.commit()
                return result, False
            except Exception:
                self._connection.rollback()
                raise

    def recover_incomplete_jobs(self) -> int:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            rows = self._connection.execute("SELECT job_id FROM workspace_jobs WHERE status IN ('queued','running','waiting_input')").fetchall()
            for row in rows:
                job_id = row["job_id"]
                now = _utc_now()
                self._connection.execute("UPDATE workspace_jobs SET status='failed',error_code='needs_review',updated_at=? WHERE job_id=?", (now, job_id))
                self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "NEEDS_REVIEW", now, error={"category": "needs_review"}, asset_refs=self._asset_refs(job_id))), now, job_id))
                self._insert_event(job_id, "needs_review", {"type": "needs_review", "job_id": job_id, "status": "failed", "reason": "process_restart"})
            self._connection.commit()
            return len(rows)

    def fail_job(self, job_id: str, code: str, *, execution_mode: str = "fake") -> None:
        with self._lock:
            now = _utc_now()
            updated = self._connection.execute("UPDATE workspace_jobs SET status='failed',error_code=?,updated_at=? WHERE job_id=? AND status IN ('queued','running')", (code, now, job_id))
            if updated.rowcount == 0:
                self._connection.commit()
                return
            self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "FAILED", now, execution_mode=execution_mode, error={"category": code}, asset_refs=self._asset_refs(job_id))), now, job_id))
            self._insert_event(
                job_id,
                "error",
                {
                    "type": "error",
                    "job_id": job_id,
                    "status": "failed",
                    "message": code,
                },
            )
            self._connection.commit()

    def append_event(self, job_id: str, event: Mapping[str, Any]) -> None:
        """Append one already-redacted public pipeline event."""

        with self._lock:
            row = self._connection.execute(
                "SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            if row["status"] in TERMINAL_JOB_STATUSES:
                return
            payload = redact(dict(event))
            payload.setdefault("job_id", job_id)
            self._insert_event(job_id, str(payload.get("type", "progress")), payload)
            self._connection.commit()

    def finish_live_job(self, job_id: str, state: Mapping[str, Any]) -> None:
        """Persist a live pipeline result without exposing private model values."""

        status = str(state.get("status", "FAILED"))
        terminal_status = "succeeded" if status == "COMPLETED" else "failed"
        final_response = state.get("final_response")
        result = {
            "final_response": final_response if isinstance(final_response, str) else "",
            "summary": str(state.get("summary", "live pipeline")),
            "tool_results": [
                {key: value for key, value in item.items() if key != "_value"}
                for item in state.get("tool_results", [])
                if isinstance(item, Mapping)
            ],
            "verification": dict(state.get("verification", {}))
            if isinstance(state.get("verification"), Mapping)
            else {"status": "unknown"},
        }
        error = state.get("error") if isinstance(state.get("error"), Mapping) else None
        error_code = str(error.get("category")) if error else None
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                if row is None or row["status"] in TERMINAL_JOB_STATUSES:
                    self._connection.rollback()
                    return
                now = _utc_now()
                self._connection.execute(
                    "UPDATE workspace_jobs SET status=?,result_json=?,error_code=?,updated_at=? WHERE job_id=?",
                    (terminal_status, _json(result), error_code, now, job_id),
                )
                if terminal_status == "succeeded":
                    self._connection.execute(
                        "INSERT OR IGNORE INTO chat_messages(session_id,sender,text,analysis_job_id,created_at) VALUES(?,?,?,?,?)",
                        (row["session_id"], "ai", result["final_response"], job_id, now),
                    )
                    self._connection.execute(
                        "UPDATE chat_sessions SET updated_at=? WHERE session_id=?",
                        (now, row["session_id"]),
                    )
                self._connection.execute(
                    "UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?",
                    (
                        _json(
                            _run_snapshot(
                                job_id,
                                "COMPLETED" if terminal_status == "succeeded" else "FAILED",
                                now,
                                execution_mode="live",
                                result=result,
                                error=error,
                                input_text=str(row["problem"]),
                                stage=str(state.get("stage", "failed")),
                                asset_refs=self._asset_refs(job_id),
                            )
                        ),
                        now,
                        job_id,
                    ),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def record_verification(self, job_id: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            row = self._connection.execute("SELECT 1 FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            now = _utc_now()
            payload = {"checker": "polynomial_check", "result": dict(result)}
            self._connection.execute("UPDATE workspace_jobs SET result_json=?,updated_at=? WHERE job_id=?", (_json(payload), now, job_id))
            self._insert_event(job_id, "verification_completed", {"type": "verification_completed", "job_id": job_id, "status": result.get("candidate_status", "unknown"), "data": payload})
            self._connection.commit()

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
        payload = self._job_payload(row, include_result=True)
        payload["last_event_id"] = self.last_event_id(job_id, user_id)
        return payload

    def verification_mode(self, job_id: str) -> str:
        with self._lock:
            row = self._connection.execute("SELECT verification_mode FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        return str(row["verification_mode"]) if row is not None else "auto"

    def active_jobs(self, user_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            query = "SELECT * FROM workspace_jobs WHERE user_id=? AND status IN ('queued','running','waiting_input')"
            params: list[Any] = [user_id]
            if session_id:
                query += " AND session_id=?"
                params.append(session_id)
            query += " ORDER BY created_at"
            rows = self._connection.execute(query, params).fetchall()
        return [self._job_payload(row) for row in rows]

    def events(self, job_id: str, user_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            row = self._connection.execute("SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            events = self._connection.execute(
                "SELECT event_id,event_type,payload_json,created_at FROM workspace_events WHERE job_id=? AND event_id>? ORDER BY event_id",
                (job_id, after_id),
            ).fetchall()
        return [
            {
                "id": int(event["event_id"]),
                "event": event["event_type"],
                "data": _loads(event["payload_json"]),
                "created_at": event["created_at"],
            }
            for event in events
        ]

    def status(self, job_id: str, user_id: str) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT status FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (job_id, user_id),
            ).fetchone()
        if row is None:
            raise WorkspaceError("job_not_found", status=404)
        return str(row["status"])

    def problem(self, job_id: str) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT problem FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return "" if row is None else str(row["problem"])

    def last_event_id(self, job_id: str, user_id: str) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (job_id, user_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            event = self._connection.execute(
                "SELECT COALESCE(MAX(event_id), 0) AS last_event_id "
                "FROM workspace_events WHERE job_id=?",
                (job_id,),
            ).fetchone()
        return int(event["last_event_id"])

    def close(self) -> None:
        with self._lock:
            if self._owns_connection:
                self._connection.close()

    def _assert_session(self, session_id: str, user_id: str) -> None:
        row = self._connection.execute("SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?", (session_id, user_id)).fetchone()
        if row is None:
            raise WorkspaceError("session_not_found", status=404)

    def _insert_event(self, job_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        self._connection.execute(
            "INSERT INTO workspace_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (job_id, event_type, _json(payload), _utc_now()),
        )

    def _insert_run(self, job_id: str, problem: str, now: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO runs(run_id,snapshot_json,created_at,updated_at) VALUES(?,?,?,?)",
            (job_id, _json(_run_snapshot(job_id, "QUEUED", now, input_text=problem, asset_refs=self._asset_refs(job_id))), now, now),
        )

    def _asset_refs(self, job_id: str) -> list[dict[str, Any]]:
        row = self._connection.execute("SELECT input_user_file_id FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        value = row["input_user_file_id"] if row is not None else None
        return [{"file_id": value, "status": "unavailable"}] if value else []

    @staticmethod
    def _job_payload(row: sqlite3.Row, *, include_result: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": row["job_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "verification_mode": row["verification_mode"],
            "input_user_file_id": row["input_user_file_id"],
            "last_event_id": None,
        }
        if include_result and row["result_json"]:
            payload["result"] = _loads(row["result_json"])
        if row["error_code"]:
            payload["error"] = row["error_code"]
        return payload


class WorkspaceService:
    """Application service that queues one workspace Job exactly once."""

    def __init__(
        self,
        database_path: str | Path = ":memory:",
        connection: sqlite3.Connection | None = None,
        *,
        execution_mode: str = "fake",
        execution_delay: float = 0.05,
        worker_enabled: bool = True,
        waiting_input_marker: str = "",
        pipeline: Any | None = None,
    ) -> None:
        self.store = WorkspaceStore(database_path, connection=connection)
        self.execution_mode = execution_mode
        self.execution_delay = max(0.0, float(execution_delay))
        self.worker_enabled = worker_enabled
        self.waiting_input_marker = waiting_input_marker
        self.pipeline = pipeline
        self._waiting_input_jobs: set[str] = set()
        self.store.recover_incomplete_jobs()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="showcase-job")
        self._submitted: set[str] = set()
        self._submit_lock = threading.Lock()

    def create_session(self, user_id: str) -> str:
        return self.store.create_session(user_id)

    def list_sessions(self, user_id: str) -> list[list[Any]]:
        return self.store.list_sessions(user_id)

    def load_session(self, session_id: str, user_id: str) -> list[dict[str, Any]]:
        return self.store.load_messages(session_id, user_id)

    def rename_session(self, session_id: str, user_id: str, title: str) -> None:
        self.store.rename_session(session_id, user_id, title)

    def delete_session(self, session_id: str, user_id: str) -> None:
        self.store.delete_session(session_id, user_id)

    def create_job(
        self,
        *,
        user_id: str,
        session_id: str,
        problem: str,
        idempotency_key: str,
        web_search_enabled: bool = False,
        input_user_file_id: Any = None,
        verification_mode: str = "auto",
    ) -> tuple[dict[str, Any], bool]:
        if web_search_enabled:
            raise WorkspaceError("capability_unavailable", status=503)
        if input_user_file_id is not None and (not isinstance(input_user_file_id, str) or not input_user_file_id):
            raise WorkspaceError("file_id_invalid", status=400)
        if not isinstance(verification_mode, str) or verification_mode not in {"auto", "required", "off"}:
            raise WorkspaceError("verification_mode_invalid", status=400)
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        digest = _request_digest(session_id, problem, web_search_enabled, input_user_file_id, verification_mode)
        payload, existing = self.store.create_job(
            user_id=user_id,
            session_id=session_id,
            problem=problem,
            idempotency_key=idempotency_key,
            request_digest=digest,
            verification_mode=verification_mode,
            input_user_file_id=input_user_file_id,
        )
        if not existing:
            self._submit(payload["job_id"])
        return payload, existing

    def resume_job(self, *, user_id: str, job_id: str, idempotency_key: str, answer: str = "") -> tuple[dict[str, Any], bool]:
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        digest = _request_digest("resume", job_id, answer)
        result, existing = self.store.control_job(
            user_id=user_id, job_id=job_id, operation="resume", idempotency_key=idempotency_key, request_digest=digest
        )
        if not existing:
            with self._submit_lock:
                self._submitted.discard(job_id)
            self._submit(job_id)
        return result, existing

    def cancel_job(self, *, user_id: str, job_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        result, existing = self.store.control_job(
            user_id=user_id, job_id=job_id, operation="cancel", idempotency_key=idempotency_key, request_digest=_request_digest("cancel", job_id, "")
        )
        return result, existing

    def _submit(self, job_id: str) -> None:
        with self._submit_lock:
            if job_id in self._submitted:
                return
            self._submitted.add(job_id)
        if self.worker_enabled:
            self._executor.submit(self._execute, job_id)

    def _execute(self, job_id: str) -> None:
        try:
            if not self.store.start_job(job_id, execution_mode=self.execution_mode):
                return
            # Keep the worker asynchronous even for the deterministic adapter so
            # the HTTP contract never waits for execution.
            time.sleep(self.execution_delay)
            if self.execution_mode == "live":
                if self.pipeline is None:
                    self.store.fail_job(job_id, "unavailable", execution_mode="live")
                    return
                state = self.pipeline.run(
                    job_id,
                    self._problem(job_id),
                    verification_mode=self.store.verification_mode(job_id),
                    emit=lambda event: self.store.append_event(job_id, event),
                )
                self.store.finish_live_job(job_id, state)
                return
            if (
                self.waiting_input_marker
                and job_id not in self._waiting_input_jobs
                and self._problem(job_id).startswith(self.waiting_input_marker)
            ):
                self._waiting_input_jobs.add(job_id)
                self.store.mark_waiting_input(job_id)
                return
            if self.store.verification_mode(job_id) == "required":
                self.store.fail_job(job_id, "needs_review")
            else:
                self.store.complete_job(job_id, "Fake Agent completed a deterministic showcase run.", "fake adapter")
        except Exception:
            self.store.fail_job(job_id, "job_execution_failed", execution_mode=self.execution_mode)

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        return self.store.get_job(job_id, user_id)

    def _problem(self, job_id: str) -> str:
        return self.store.problem(job_id)

    def active_jobs(self, user_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        payloads = self.store.active_jobs(user_id, session_id)
        for payload in payloads:
            payload["last_event_id"] = self.store.last_event_id(payload["job_id"], user_id)
        return payloads

    def events(self, job_id: str, user_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        return self.store.events(job_id, user_id, after_id)

    def status(self, job_id: str, user_id: str) -> str:
        return self.store.status(job_id, user_id)

    def record_verification(self, *, user_id: str, job_id: str, result: Mapping[str, Any]) -> None:
        self.store.get_job(job_id, user_id)
        self.store.record_verification(job_id, result)

    def last_event_id(self, job_id: str, user_id: str) -> int:
        return self.store.last_event_id(job_id, user_id)

    def stream_events(
        self,
        job_id: str,
        user_id: str,
        after_id: int = 0,
        *,
        heartbeat_interval: float = 0.05,
        poll_interval: float = 0.01,
    ):
        """Yield committed public events until the Job reaches a terminal state.

        The stream never executes a Job. It polls the same SQLite source used
        by history and result queries, yielding a heartbeat when no committed
        event is available yet.
        """
        cursor = after_id
        heartbeat_at = time.monotonic()
        while True:
            pending = self.events(job_id, user_id, cursor)
            if pending:
                for event in pending:
                    cursor = max(cursor, int(event["id"]))
                    yield event
                heartbeat_at = time.monotonic()
                # A worker may commit the terminal status in the same
                # transaction as the last event. Loop once more so that a
                # terminal status observed after a pending batch cannot hide
                # events committed just after the query above.
                continue
            if self.status(job_id, user_id) in TERMINAL_JOB_STATUSES:
                return
            now = time.monotonic()
            if now - heartbeat_at >= heartbeat_interval:
                yield {
                    "id": None,
                    "event": "heartbeat",
                    "data": {"type": "heartbeat", "job_id": job_id},
                }
                heartbeat_at = now
            time.sleep(poll_interval)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self.store.close()


def _request_digest(*args: Any) -> str:
    if len(args) == 5:
        session_id, problem, web_search_enabled, file_id, verification_mode = args
        payload = {"session_id": session_id, "message": problem, "web_search_enabled": web_search_enabled, "input_user_file_id": file_id, "verification_mode": verification_mode}
    else:
        payload = {"operation": list(args)}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _is_uuid_v4(value: str) -> bool:
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return parsed.version == 4 and str(parsed) == value.lower()


def _run_snapshot(
    job_id: str,
    status: str,
    now: str,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    input_text: str = "",
    asset_refs: list[dict[str, Any]] | None = None,
    execution_mode: str = "fake",
    stage: str | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "run_id": job_id,
        "profile": "showcase_mvp",
        "execution_mode": execution_mode,
        "status": status,
        "stage": stage or ("queued" if status == "QUEUED" else ("synthesis" if status == "COMPLETED" else "solving")),
        "input_ref": {"kind": "text", "length": len(input_text)} if input_text else {"kind": "text"},
        "asset_refs": list(asset_refs or []),
        "vision_status": "unavailable" if asset_refs else None,
        "result": dict(result) if result else None,
        "final_response": result.get("final_response") if result else None,
        "error": dict(error) if error else None,
        "created_at": now,
        "updated_at": now,
    }
    return snapshot


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(value: str) -> Any:
    return json.loads(value)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["WorkspaceError", "WorkspaceService"]
