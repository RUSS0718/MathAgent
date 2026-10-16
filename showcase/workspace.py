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
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
                    "INSERT INTO workspace_jobs(job_id,session_id,user_id,problem,status,result_json,error_code,idempotency_key,request_digest,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (job_id, session_id, user_id, problem, "queued", None, None, idempotency_key, request_digest, now, now),
                )
                self._connection.execute(
                    "INSERT INTO chat_messages(session_id,sender,text,analysis_job_id,created_at) VALUES(?,?,?,?,?)",
                    (session_id, "user", problem, job_id, now),
                )
                self._insert_event(job_id, "job_queued", {"type": "job_queued", "job_id": job_id, "status": "queued"})
                self._insert_run(job_id, problem, now)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        assert row is not None
        return self._job_payload(row), False

    def start_job(self, job_id: str) -> bool:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
                if row is None or row["status"] != "queued":
                    self._connection.rollback()
                    return False
                now = _utc_now()
                self._connection.execute("UPDATE workspace_jobs SET status='running',updated_at=? WHERE job_id=?", (now, job_id))
                self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "RUNNING", now)), now, job_id))
                self._insert_event(job_id, "job_started", {"type": "job_started", "job_id": job_id, "status": "running"})
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
                    (_json(_run_snapshot(job_id, "COMPLETED", now, result)), now, job_id),
                )
                self._insert_event(job_id, "final_result", {"type": "final_result", "job_id": job_id, "status": "succeeded", "data": {"type": "text", "summary": final_response}})
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

    def fail_job(self, job_id: str, code: str) -> None:
        with self._lock:
            now = _utc_now()
            self._connection.execute("UPDATE workspace_jobs SET status='failed',error_code=?,updated_at=? WHERE job_id=? AND status IN ('queued','running')", (code, now, job_id))
            self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "FAILED", now, error={"category": code})), now, job_id))
            self._insert_event(job_id, "error", {"type": "error", "job_id": job_id, "message": code})
            self._connection.commit()

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
        return self._job_payload(row, include_result=True)

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
            {"id": int(event["event_id"]), "event": event["event_type"], "data": _loads(event["payload_json"]), "created_at": event["created_at"]}
            for event in events
        ]

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
            (job_id, _json(_run_snapshot(job_id, "QUEUED", now, input_text=problem)), now, now),
        )

    @staticmethod
    def _job_payload(row: sqlite3.Row, *, include_result: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": row["job_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "last_event_id": None,
        }
        if include_result and row["result_json"]:
            payload["result"] = _loads(row["result_json"])
        if row["error_code"]:
            payload["error"] = row["error_code"]
        return payload


class WorkspaceService:
    """Application service that queues deterministic fake Jobs exactly once."""

    def __init__(self, database_path: str | Path = ":memory:", connection: sqlite3.Connection | None = None) -> None:
        self.store = WorkspaceStore(database_path, connection=connection)
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
        if input_user_file_id is not None:
            raise WorkspaceError("capability_unavailable", status=503)
        if verification_mode not in {"auto", "required", "off"}:
            raise WorkspaceError("verification_mode_invalid", status=400)
        if not idempotency_key.strip():
            raise WorkspaceError("idempotency_key_required", status=400)
        digest = _request_digest(session_id, problem, web_search_enabled, input_user_file_id, verification_mode)
        payload, existing = self.store.create_job(
            user_id=user_id,
            session_id=session_id,
            problem=problem,
            idempotency_key=idempotency_key,
            request_digest=digest,
        )
        if not existing:
            self._submit(payload["job_id"])
        return payload, existing

    def _submit(self, job_id: str) -> None:
        with self._submit_lock:
            if job_id in self._submitted:
                return
            self._submitted.add(job_id)
        self._executor.submit(self._execute, job_id)

    def _execute(self, job_id: str) -> None:
        try:
            if not self.store.start_job(job_id):
                return
            # Keep the worker asynchronous even for the deterministic adapter so
            # the HTTP contract never waits for execution.
            time.sleep(0.005)
            self.store.complete_job(
                job_id,
                "Fake Agent completed a deterministic showcase run.",
                "fake adapter",
            )
        except Exception:
            self.store.fail_job(job_id, "job_execution_failed")

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        return self.store.get_job(job_id, user_id)

    def active_jobs(self, user_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        return self.store.active_jobs(user_id, session_id)

    def events(self, job_id: str, user_id: str, after_id: int = 0) -> list[dict[str, Any]]:
        return self.store.events(job_id, user_id, after_id)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
        self.store.close()


def _request_digest(session_id: str, problem: str, web_search_enabled: bool, file_id: Any, verification_mode: str) -> str:
    payload = {"session_id": session_id, "message": problem, "web_search_enabled": web_search_enabled, "input_user_file_id": file_id, "verification_mode": verification_mode}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _run_snapshot(
    job_id: str,
    status: str,
    now: str,
    result: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    input_text: str = "",
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "run_id": job_id,
        "profile": "showcase_mvp",
        "execution_mode": "fake",
        "status": status,
        "stage": "queued" if status == "QUEUED" else ("synthesis" if status == "COMPLETED" else "solving"),
        "input_ref": {"kind": "text", "length": len(input_text)} if input_text else {"kind": "text"},
        "asset_refs": [],
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
