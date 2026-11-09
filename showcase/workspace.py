"""Persistent ChatSession and asynchronous Job service for the v0.2 workspace.

The workspace service deliberately sits beside :class:`RunService`.  The old
``/api/runs`` contract remains synchronous; this module owns the product chat
contract and queues one deterministic adapter call after durable acceptance.
"""

from __future__ import annotations

import hashlib
import json
import math
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

from .evidence_store import append_check
from .final_evidence import bind_verification
from .presentation import MODES, POLICY_VERSION, SCHEMA_VERSION, normalize_mode
from .redaction import redact
from .run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget, freeze_budget
from .run_checkpoints import RunCheckpointSaver
from .run_control import RunControl, RunStopped, bind_control
from .star_product_hints import migrate_hints, validate_hint
from .star_product_modes import STAR_MODES

ACTIVE_JOB_STATUSES = ("queued", "running", "waiting_input")
TERMINAL_JOB_STATUSES = ("succeeded", "failed", "canceled")


def _apply_formal_requirement(result: dict[str, Any]) -> None:
    policy = result.get("formal_policy")
    solver = result.get("solver")
    if not isinstance(policy, Mapping) or not isinstance(solver, Mapping):
        return
    semantics = solver.get("semantics")
    if not isinstance(semantics, Mapping):
        return
    formal = result.get("formal_verification")
    if not isinstance(formal, Mapping):
        formal = solver.get("formal_verification")
    met = (isinstance(formal, Mapping) and formal.get("status") == "solved"
           and formal.get("grade") in {"L2", "L3"})
    updated_solver = dict(solver)
    updated_solver["semantics"] = {
        **dict(semantics),
        "formal_requirement": ("met" if met else "unmet")
        if policy.get("require_formal") is True else "default",
    }
    result["solver"] = updated_solver


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
                problem_spec_json TEXT,
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
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                event_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (run_id, sequence),
                FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
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
            CREATE TABLE IF NOT EXISTS presentation_artifacts (
                job_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                mode TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                artifact_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(job_id, mode, source_fingerprint),
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
        if "problem_spec_json" not in columns:
            self._connection.execute("ALTER TABLE workspace_jobs ADD COLUMN problem_spec_json TEXT")
        migrate_hints(self._connection, columns)
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
        execution_mode: str = "fake",
        verification_mode: str = "auto",
        input_user_file_id: str | None = None,
        solver_identity: Mapping[str, Any] | None = None,
        experiment_binding: Mapping[str, Any] | None = None,
        solver_hint: str | None = None,
        problem_spec: Mapping[str, Any] | None = None,
        presentation_config: Mapping[str, Any] | None = None,
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
                    "INSERT INTO workspace_jobs(job_id,session_id,user_id,problem,status,result_json,error_code,input_user_file_id,verification_mode,problem_spec_json,idempotency_key,request_digest,created_at,updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (job_id, session_id, user_id, problem, "queued", _json({"execution_mode": execution_mode, **(solver_identity or {}), **(dict(presentation_config or {})), **({"experiment_pair": dict(experiment_binding)} if experiment_binding else {})}), None, input_user_file_id, verification_mode, _json(problem_spec) if problem_spec is not None else None, idempotency_key, request_digest, now, now),
                )
                self._connection.execute(
                    "INSERT INTO chat_messages(session_id,sender,text,analysis_job_id,created_at) VALUES(?,?,?,?,?)",
                    (session_id, "user", problem, job_id, now),
                )
                if solver_hint is not None:
                    self._connection.execute("UPDATE workspace_jobs SET solver_hint=? WHERE job_id=?", (solver_hint, job_id))
                self._insert_run(job_id, problem, now, execution_mode)
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
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        assert row is not None
        return self._job_payload(row), False

    def job_identity(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        return _loads(row[0]) if row else {}

    def record_pair_applied_config(
        self, job_id: str, expected_binding: Mapping[str, Any], config: Mapping[str, Any]
    ) -> None:
        """Persist the resolved arm flags before the pipeline can call a provider."""
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT status,result_json FROM workspace_jobs WHERE job_id=?", (job_id,)
                ).fetchone()
                if row is None or row["status"] != "running":
                    raise WorkspaceError("experiment_pair_job_not_running", status=409)
                result = _loads(row["result_json"]) if row["result_json"] else {}
                binding = result.get("experiment_pair")
                if (
                    not isinstance(binding, dict)
                    or binding != dict(expected_binding)
                    or dict(config) != binding.get("features")
                ):
                    raise WorkspaceError("experiment_pair_applied_config_mismatch", status=409)
                binding = {
                    **binding,
                    "applied_config_status": "applied",
                    "applied_component_config": dict(config),
                }
                result["experiment_pair"] = binding
                self._connection.execute(
                    "UPDATE workspace_jobs SET result_json=?,updated_at=? WHERE job_id=?",
                    (_json(result), _utc_now(), job_id),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise

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
                self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "RUNNING", now, execution_mode=execution_mode, result=self.job_identity(job_id), asset_refs=self._asset_refs(job_id))), now, job_id))
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
                prior = _loads(row["result_json"]) if row["result_json"] else {}
                result = {"final_response": final_response, "summary": summary, "verification": bind_verification(final_response), "execution_mode": prior.get("execution_mode", "unavailable"), **_presentation_identity(prior)}
                if isinstance(prior.get("experiment_pair"), dict):
                    result["experiment_pair"] = prior["experiment_pair"]
                    _mark_pair_config_not_applied(result)
                result["budget"] = freeze_budget(self._connection, job_id)
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
                    (_json(_run_snapshot(job_id, "COMPLETED", now, result, execution_mode=result["execution_mode"], asset_refs=self._asset_refs(job_id))), now, job_id),
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

    def control_status(self, job_id: str):
        with self._lock:
            row = self._connection.execute("SELECT status,error_code FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        return dict(row) if row else None

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
            snapshot_row = self._connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (job_id,)).fetchone()
            snapshot = _loads(snapshot_row["snapshot_json"])
            snapshot.update(status="WAITING_INPUT", stage="planned", updated_at=now)
            self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(snapshot), now, job_id))
            self._insert_event(job_id, "interrupt", {"type": "interrupt", "job_id": job_id, "status": "waiting_input"})
            self._connection.commit()

    def control_job(self, *, user_id: str, job_id: str, operation: str, idempotency_key: str, request_digest: str, retry_call=None) -> tuple[dict[str, Any], bool]:
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
                        freeze_budget(self._connection, job_id)
                        result_json = _loads(row["result_json"]) if row["result_json"] else {}
                        _mark_pair_config_not_applied(result_json)
                        self._connection.execute("UPDATE workspace_jobs SET status='canceled',result_json=?,updated_at=? WHERE job_id=?", (_json(result_json), now, job_id))
                        self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "CANCELED", now, execution_mode=(_loads(row["result_json"]) if row["result_json"] else {}).get("execution_mode", "unavailable"), result=self.job_identity(job_id), asset_refs=self._asset_refs(job_id))), now, job_id))
                        self._insert_event(job_id, "canceled", {"type": "canceled", "job_id": job_id, "status": "canceled", "scope": "future_dispatch", "remote_request": "cannot_revoke"})
                    result = {"success": True, "job_id": job_id, "status": "canceled"}
                else:
                    from .star_product_recovery import authorize_resume

                    star_resume = authorize_resume(self._connection, row, retry_call)
                    if status != "waiting_input" and not star_resume:
                        raise WorkspaceError("job_not_resumable", status=409)
                    now = _utc_now()
                    if star_resume:
                        self._connection.execute(
                            "UPDATE run_budgets SET ledger_json=json_remove(ledger_json,'$.ended_at') WHERE run_id=?",
                            (job_id,),
                        )
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

    def recover_incomplete_jobs(self, checkpointer=None) -> int:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            rows = self._connection.execute("SELECT job_id,status,result_json FROM workspace_jobs WHERE status IN ('queued','running','waiting_input')").fetchall()
            for row in rows:
                job_id = row["job_id"]
                if row["status"] == "waiting_input" and checkpointer is not None and checkpointer.is_interrupted(job_id):
                    continue
                now = _utc_now()
                result = _loads(row["result_json"]) if row["result_json"] else {}
                _mark_pair_config_not_applied(result)
                self._connection.execute("UPDATE workspace_jobs SET status='failed',error_code='needs_review',result_json=?,updated_at=? WHERE job_id=?", (_json(result), now, job_id))
                self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "NEEDS_REVIEW", now, execution_mode=(_loads(row["result_json"]) if row["result_json"] else {}).get("execution_mode", "unavailable"), result=self.job_identity(job_id), error={"category": "needs_review"}, asset_refs=self._asset_refs(job_id))), now, job_id))
                self._insert_event(job_id, "needs_review", {"type": "needs_review", "job_id": job_id, "status": "failed", "reason": "process_restart"})
            self._connection.commit()
            if checkpointer is not None:
                for row in rows:
                    state = self.control_status(row["job_id"])
                    if state["status"] == "failed":
                        checkpointer.stop(row["job_id"], "NEEDS_REVIEW", "needs_review")
            return len(rows)

    def fail_job(self, job_id: str, code: str, *, execution_mode: str = "fake") -> None:
        with self._lock:
            now = _utc_now()
            stored = self._connection.execute("SELECT result_json FROM workspace_jobs WHERE job_id=? AND status IN ('queued','running')", (job_id,)).fetchone()
            if stored is None:
                self._connection.commit()
                return
            result = _loads(stored["result_json"]) if stored["result_json"] else {}
            _mark_pair_config_not_applied(result)
            updated = self._connection.execute("UPDATE workspace_jobs SET status='failed',error_code=?,result_json=?,updated_at=? WHERE job_id=? AND status IN ('queued','running')", (code, _json(result), now, job_id))
            if updated.rowcount == 0:
                self._connection.commit()
                return
            execution_mode = result.get('execution_mode', 'unavailable')
            freeze_budget(self._connection, job_id)
            self._connection.execute("UPDATE runs SET snapshot_json=?,updated_at=? WHERE run_id=?", (_json(_run_snapshot(job_id, "FAILED", now, execution_mode=execution_mode, result=self.job_identity(job_id), error={"category": code}, asset_refs=self._asset_refs(job_id))), now, job_id))
            self._insert_event(
                job_id,
                "timeout" if code == "run_deadline_exhausted" else "error",
                {
                    "type": "timeout" if code == "run_deadline_exhausted" else "error",
                    "job_id": job_id,
                    "status": "failed",
                    "message": code,
                },
            )
            self._connection.commit()

    def append_event(self, job_id: str, event: Mapping[str, Any]) -> None:
        """Append one already-redacted public pipeline event."""

        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            if row["status"] in TERMINAL_JOB_STATUSES and event.get("type") not in {"request_attempt", "tool_call_result"}:
                return
            from .star_product_projection import project_solver_event

            if not project_solver_event(self._connection, job_id, event):
                return
            payload = redact(dict(event))
            payload.setdefault("job_id", job_id)
            self._insert_event(job_id, str(payload.get("type", "progress")), payload)
            self._connection.commit()

    def finish_live_job(self, job_id: str, state: Mapping[str, Any]) -> None:
        """Persist a live pipeline result without exposing private model values."""

        if state.get("status") == "WAITING_INPUT":
            self.mark_waiting_input(job_id)
            return
        status = str(state.get("status", "FAILED"))
        terminal_status = "succeeded" if status == "COMPLETED" else "failed"
        final_response = state.get("final_response")
        result = {
            "execution_mode": str(state.get("execution_mode", "live")),
            "final_response": final_response if isinstance(final_response, str) else "",
            "summary": str(state.get("summary", "live pipeline")),
            "request_attempts": list(state.get("request_attempts", [])),
            "budget": state.get("budget"),
            "tool_results": [
                {key: value for key, value in item.items() if key != "_value"}
                for item in state.get("tool_results", [])
                if isinstance(item, Mapping)
            ],
            "verification": dict(state.get("verification", {}))
            if isinstance(state.get("verification"), Mapping)
            else {"status": "unknown"},
        }
        result.update({key: state[key] for key in ("solver_mode", "preset_version", "population_policy_hash", "missing_capabilities", "evidence_kind", "solver", "acceptance_mode", "engineering_delivery", "presentation_mode", "presentation_schema_version", "presentation_policy_version", "formal_policy", "formal_policy_hash", "formal_verification") if key in state})
        result["verification"] = bind_verification(result["final_response"], result["verification"])
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
                prior = _loads(row["result_json"]) if row["result_json"] else {}
                result.update(_presentation_identity(prior))
                for frozen_key in ("formal_policy", "formal_policy_hash"):
                    if frozen_key in prior:
                        result[frozen_key] = prior[frozen_key]
                _apply_formal_requirement(result)
                if isinstance(prior.get("experiment_pair"), dict):
                    result["experiment_pair"] = prior["experiment_pair"]
                    _mark_pair_config_not_applied(result)
                now = _utc_now()
                result["budget"] = freeze_budget(self._connection, job_id) or result.get("budget")
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
                                status if status in {"COMPLETED", "NEEDS_REVIEW"} else "FAILED",
                                now,
                                execution_mode=str(state.get("execution_mode", "live")),
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
            payload = {"checker": "polynomial_check", "result": dict(result)}
            append_check(
                self._connection, job_id, result, _utc_now(), WorkspaceError,
                lambda: self._insert_event(job_id, "verification_completed", {"type": "verification_completed", "job_id": job_id, "status": result.get("candidate_status", "unknown"), "data": payload}),
            )

    def save_presentation(self, job_id: str, user_id: str, artifact: Mapping[str, Any]) -> dict[str, Any]:
        source = artifact.get("source_fingerprint")
        mode = artifact.get("mode")
        if not isinstance(source, str) or mode not in MODES:
            raise WorkspaceError("presentation_artifact_invalid", status=400)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT status,updated_at,result_json FROM workspace_jobs WHERE job_id=? AND user_id=?",
                    (job_id, user_id),
                ).fetchone()
                if row is None:
                    raise WorkspaceError("job_not_found", status=404)
                expected = artifact.get("source_versions") or {}
                event = self._connection.execute(
                    "SELECT COALESCE(MAX(event_id),0) FROM workspace_events "
                    "WHERE job_id=? AND event_type!='presentation_artifact_saved'", (job_id,),
                ).fetchone()
                solver_row = self._connection.execute(
                    "SELECT state_revision,state_json FROM solver_states WHERE run_id=?", (job_id,)
                ).fetchone()
                state = _loads(solver_row["state_json"]) if solver_row is not None else {}
                actual = {
                    "job_status": row["status"], "job_updated_at": row["updated_at"],
                    "source_event_id": int(event[0]),
                    "state_revision": int(solver_row["state_revision"]) if solver_row is not None else None,
                    "specification_version": state.get("specification_version"),
                    "graph_version": (state.get("proof_graph") or {}).get("graph_version"),
                }
                if any(expected.get(key) != value for key, value in actual.items()):
                    raise WorkspaceError("presentation_source_changed", status=409)
                current_result = _loads(row["result_json"]) if row["result_json"] else {}
                if (current_result.get("final_response") or "") != (artifact.get("answer") or ""):
                    raise WorkspaceError("presentation_source_changed", status=409)
                now = _utc_now()
                inserted = self._connection.execute(
                    "INSERT OR IGNORE INTO presentation_artifacts(job_id,user_id,mode,source_fingerprint,artifact_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (job_id, user_id, mode, source, _json(dict(artifact)), now, now),
                ).rowcount
                if inserted:
                    self._insert_event(job_id, "presentation_artifact_saved", {
                        "type": "presentation_artifact_saved", "job_id": job_id,
                        "mode": mode, "status": artifact.get("status"),
                        "schema_version": artifact.get("schema_version"),
                        "artifact_sha256": (artifact.get("artifact") or {}).get("sha256"),
                    })
                stored = self._connection.execute(
                    "SELECT artifact_json FROM presentation_artifacts WHERE job_id=? AND user_id=? AND mode=? AND source_fingerprint=?",
                    (job_id, user_id, mode, source),
                ).fetchone()
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return _loads(stored["artifact_json"])

    def get_presentation(self, job_id: str, user_id: str, mode: str, source_fingerprint: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT artifact_json FROM presentation_artifacts WHERE job_id=? AND user_id=? AND mode=? AND source_fingerprint=?",
                (job_id, user_id, mode, source_fingerprint),
            ).fetchone()
        return _loads(row["artifact_json"]) if row is not None else None

    def list_presentations(self, job_id: str, user_id: str, mode: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT artifact_json FROM presentation_artifacts WHERE job_id=? AND user_id=? AND mode=? ORDER BY created_at",
                (job_id, user_id, mode),
            ).fetchall()
        return [_loads(row["artifact_json"]) for row in rows]

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._connection.execute("SELECT * FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
        payload = self._job_payload(row, include_result=True)
        payload["last_event_id"] = self.last_event_id(job_id, user_id)
        payload["source_event_id"] = self.source_event_id(job_id, user_id)
        return payload

    def get_job_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str, request_digest: str
    ) -> dict[str, Any]:
        from .experiment_transport_projection import project_transport_identity

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM workspace_jobs WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchall()
        if not rows:
            raise WorkspaceError("job_not_found", status=404)
        if len(rows) != 1:
            raise WorkspaceError("idempotency_lookup_ambiguous", status=409)
        row = rows[0]
        if row["request_digest"] != request_digest:
            raise WorkspaceError("idempotency_conflict", status=409)
        with self._lock:
            state_row = self._connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (row["job_id"],)
            ).fetchone()
            try:
                state = json.loads(state_row["state_json"]) if state_row is not None else None
            except (TypeError, ValueError):
                state = None
            transport_identity = project_transport_identity(state, row["job_id"])
        payload = self._job_payload(row)
        payload["request_digest"] = row["request_digest"]
        payload["transport_identity"] = transport_identity
        return payload

    def verification_mode(self, job_id: str) -> str:
        with self._lock:
            row = self._connection.execute("SELECT verification_mode FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        return str(row["verification_mode"]) if row is not None else "auto"

    def solver_hint(self, job_id: str) -> str | None:
        """Read the private execution hint without adding it to the Job DTO."""
        with self._lock:
            row = self._connection.execute("SELECT solver_hint FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        return str(row["solver_hint"]) if row is not None and row["solver_hint"] is not None else None

    def problem_spec(self, job_id: str) -> dict[str, Any] | None:
        """Read the private frozen ProblemSpec supplied at Job creation."""
        with self._lock:
            row = self._connection.execute(
                "SELECT problem_spec_json FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
        return _loads(row["problem_spec_json"]) if row is not None and row["problem_spec_json"] else None

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

    def events(
        self, job_id: str, user_id: str, after_id: int = 0, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        with self._lock:
            row = self._connection.execute("SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            query = (
                "SELECT event_id,event_type,payload_json,created_at FROM workspace_events "
                "WHERE job_id=? AND event_id>? ORDER BY event_id"
            )
            params: tuple[Any, ...] = (job_id, after_id)
            if limit is not None:
                query += " LIMIT ?"
                params += (limit,)
            events = self._connection.execute(query, params).fetchall()
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

    def source_event_id(self, job_id: str, user_id: str) -> int:
        with self._lock:
            owned = self._connection.execute(
                "SELECT 1 FROM workspace_jobs WHERE job_id=? AND user_id=?", (job_id, user_id)
            ).fetchone()
            if owned is None:
                raise WorkspaceError("job_not_found", status=404)
            event = self._connection.execute(
                "SELECT COALESCE(MAX(event_id),0) FROM workspace_events "
                "WHERE job_id=? AND event_type!='presentation_artifact_saved'", (job_id,),
            ).fetchone()
        return int(event[0])

    def close(self) -> None:
        with self._lock:
            if self._owns_connection:
                self._connection.close()

    def _assert_session(self, session_id: str, user_id: str) -> None:
        row = self._connection.execute("SELECT 1 FROM chat_sessions WHERE session_id=? AND user_id=?", (session_id, user_id)).fetchone()
        if row is None:
            raise WorkspaceError("session_not_found", status=404)

    def _insert_event(self, job_id: str, event_type: str, payload: Mapping[str, Any]) -> None:
        created_at = _utc_now()
        status = self._connection.execute("SELECT status FROM workspace_jobs WHERE job_id=?", (job_id,)).fetchone()
        if status is not None and status[0] in TERMINAL_JOB_STATUSES:
            freeze_budget(self._connection, job_id)
        event_payload = redact(dict(payload))
        event_payload.setdefault("job_id", job_id)
        event_payload.setdefault("created_at", created_at)
        self._connection.execute(
            "INSERT INTO workspace_events(job_id,event_type,payload_json,created_at) VALUES(?,?,?,?)",
            (job_id, event_type, _json(event_payload), created_at),
        )
        row = self._connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) AS last_sequence FROM events WHERE run_id=?",
            (job_id,),
        ).fetchone()
        event_payload["run_id"] = job_id
        event_payload["sequence"] = int(row["last_sequence"]) + 1
        self._connection.execute(
            "INSERT INTO events(run_id,sequence,event_json,created_at) VALUES(?,?,?,?)",
            (job_id, event_payload["sequence"], _json(event_payload), created_at),
        )

    def _insert_run(self, job_id: str, problem: str, now: str, execution_mode: str) -> None:
        self._connection.execute(
            "INSERT OR IGNORE INTO runs(run_id,snapshot_json,created_at,updated_at) VALUES(?,?,?,?)",
            (job_id, _json(_run_snapshot(job_id, "QUEUED", now, execution_mode=execution_mode, result=self.job_identity(job_id), input_text=problem, asset_refs=self._asset_refs(job_id))), now, now),
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
            "updated_at": row["updated_at"],
            "verification_mode": row["verification_mode"],
            "input_user_file_id": row["input_user_file_id"],
            "last_event_id": None,
        }
        if include_result and row["result_json"]:
            payload["result"] = _loads(row["result_json"])
            payload["result"].pop("retry_call", None)
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
        star_pipeline: Any | None = None,
        stream_timeout_policy_version: str | None = None,
    ) -> None:
        from .stream_timeout_policy import policy_for_version

        self.store = WorkspaceStore(database_path, connection=connection)
        self.execution_mode = execution_mode
        self.execution_delay = max(0.0, float(execution_delay))
        self.worker_enabled = worker_enabled
        self.waiting_input_marker = waiting_input_marker
        self.pipeline = pipeline
        self.star_pipeline = star_pipeline
        self.stream_timeout_policy = policy_for_version(stream_timeout_policy_version)
        self.budget_ledger = RunBudgetLedger(
            self.store._connection, connection_lock=self.store._lock
        )
        self.checkpointer = None
        if (pipeline is not None and hasattr(pipeline, "checkpointer")) or star_pipeline is not None:
            self.checkpointer = RunCheckpointSaver(database_path)
            if pipeline is not None:
                pipeline.checkpointer = self.checkpointer
            if star_pipeline is not None:
                star_pipeline.checkpointer = self.checkpointer
        self._waiting_input_jobs: set[str] = set()
        self.store.recover_incomplete_jobs(self.checkpointer)
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
        budget_limits: RunBudgetLimits | None = None,
        deadline_at: float | None = None,
        solver_mode: str = "legacy",
        solver_options: Any = None,
        solver_hint: Any = None,
        experiment_binding: Mapping[str, Any] | None = None,
        problem_spec: Mapping[str, Any] | None = None,
        presentation_mode: str | None = None,
        formal_policy: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        from .star_product_modes import validate_mode
        requested_presentation_mode = normalize_mode(presentation_mode)

        identity = validate_mode(solver_mode, enabled=self.star_pipeline is not None, verification_mode=verification_mode, options=solver_options, pipeline=self.star_pipeline)
        validate_hint(solver_hint, solver_mode)
        presentation_identity = ({
            "presentation_mode": requested_presentation_mode,
            "presentation_schema_version": SCHEMA_VERSION,
            "presentation_policy_version": POLICY_VERSION,
        } if presentation_mode is not None else {})
        selected = self.star_pipeline if solver_mode in STAR_MODES else self.pipeline
        from .solver_harness.formal_policy import FormalPolicyError, normalize_formal_policy

        formal_identity = {}
        if formal_policy is not None:
            if solver_mode not in STAR_MODES:
                raise WorkspaceError("formal_policy_requires_star_mode", status=400)
            try:
                if not isinstance(formal_policy, Mapping):
                    raise FormalPolicyError("formal_policy_invalid")
                if "timeout_seconds" in formal_policy:
                    timeout = formal_policy["timeout_seconds"]
                    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                            or not math.isfinite(timeout) or timeout <= 0):
                        raise FormalPolicyError("formal_timeout_invalid")
                formal_policy = normalize_formal_policy(
                    formal_policy,
                    configured=(getattr(selected, "formal_backend", None) is not None),
                    server_template=getattr(selected, "formal_server_policy", None),
                )
            except FormalPolicyError as exc:
                raise WorkspaceError(exc.category, status=400) from exc
            formal_identity = {
                "formal_policy": formal_policy,
                "formal_policy_hash": _request_digest(formal_policy),
            }
        if problem_spec is not None:
            if solver_mode not in STAR_MODES:
                raise WorkspaceError("problem_spec_requires_star_mode", status=400)
            preset = selected.preset_config(solver_mode)
            if preset.get("features", {}).get("problem_spec") is not True:
                raise WorkspaceError("problem_spec_feature_disabled", status=400)
            from .solver_harness.specification import normalize_problem_spec

            try:
                problem_spec = normalize_problem_spec(problem_spec)
            except (TypeError, ValueError) as exc:
                raise WorkspaceError("problem_spec_invalid", status=400) from exc
            if problem_spec["original_problem"] != problem:
                raise WorkspaceError("problem_spec_original_problem_mismatch", status=400)
        elif (solver_mode in STAR_MODES
              and selected.preset_config(solver_mode).get("features", {}).get("problem_spec") is True):
            raise WorkspaceError("problem_spec_required", status=400)
        if web_search_enabled:
            raise WorkspaceError("capability_unavailable", status=503)
        if input_user_file_id is not None and (not isinstance(input_user_file_id, str) or not input_user_file_id):
            raise WorkspaceError("file_id_invalid", status=400)
        if not isinstance(verification_mode, str) or verification_mode not in {"auto", "required", "off"}:
            raise WorkspaceError("verification_mode_invalid", status=400)
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        if budget_limits is not None and deadline_at is not None and deadline_at > time.time() + budget_limits.max_runtime_seconds:
            raise WorkspaceError("run_budget_deadline_invalid", status=400)
        digest = workspace_job_request_digest(
            session_id=session_id,
            message=problem,
            web_search_enabled=web_search_enabled,
            input_user_file_id=input_user_file_id,
            verification_mode=verification_mode,
            solver_mode=solver_mode,
            solver_hint=solver_hint,
            budget_limits=budget_limits,
            deadline_at=deadline_at,
            experiment_binding=experiment_binding,
            problem_spec=problem_spec,
            presentation_mode=presentation_mode,
            population_policy_hash=identity.get("population_policy_hash"),
            formal_policy=formal_policy,
        )
        payload, existing = self.store.create_job(
            user_id=user_id,
            session_id=session_id,
            problem=problem,
            idempotency_key=idempotency_key,
            request_digest=digest,
            execution_mode=solver_mode if solver_mode in STAR_MODES else getattr(selected, "execution_mode", self.execution_mode),
            solver_identity={
                **identity,
                "evidence_kind": getattr(selected, "evidence_kind", self.execution_mode),
                **({"stream_timeout_policy": self.stream_timeout_policy}
                   if self.stream_timeout_policy is not None else {}),
                **presentation_identity,
                **formal_identity,
            },
            experiment_binding=experiment_binding,
            problem_spec=problem_spec,
            solver_hint=solver_hint,
            verification_mode=verification_mode,
            input_user_file_id=input_user_file_id,
        )
        if budget_limits is not None:
            frozen_identity = self.store.job_identity(payload["job_id"])
            self.budget_ledger.ensure(
                payload["job_id"],
                budget_limits,
                deadline_at=deadline_at,
                stream_timeout_policy=frozen_identity.get("stream_timeout_policy"),
            )
            snapshot = self.budget_ledger.snapshot(payload["job_id"])
            expected_limits = {
                "max_model_calls": budget_limits.max_model_calls,
                "max_http_attempts": budget_limits.max_http_attempts,
                "max_tool_calls": budget_limits.max_tool_calls,
                "max_tokens": budget_limits.max_tokens,
                "max_runtime_seconds": budget_limits.max_runtime_seconds,
            }
            if (
                snapshot is None
                or snapshot["limits"] != expected_limits
                or (deadline_at is not None and snapshot["deadline_at"] != deadline_at)
            ):
                raise WorkspaceError("run_budget_binding_mismatch", status=409)
        if not existing:
            self._submit(payload["job_id"])
        return payload, existing

    def resume_job(self, *, user_id: str, job_id: str, idempotency_key: str, answer: str = "", retry_call=None) -> tuple[dict[str, Any], bool]:
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        digest = _request_digest("resume", job_id, answer, retry_call)
        result, existing = self.store.control_job(
            user_id=user_id, job_id=job_id, operation="resume", idempotency_key=idempotency_key, request_digest=digest, retry_call=retry_call
        )
        if not existing:
            with self._submit_lock:
                self._submitted.discard(job_id)
            self._submit(job_id)
        return result, existing

    def formal_attempt(
        self, *, user_id: str, job_id: str, idempotency_key: str,
        expected_attempt_id: str, operation: str,
        requested_backend: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Append one explicit formal child attempt without re-solving the Run."""
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        payload = {"expected_attempt_id": expected_attempt_id, "operation": operation}
        if requested_backend is not None:
            payload["requested_backend"] = requested_backend
        digest = _request_digest("formal_attempt", job_id, payload)
        from .solver_harness.formal_integration import (
            FormalIntegrationError,
            FormalIntegrationState,
            commit_formal_retry_reservation,
        )
        from .solver_harness.storage import (
            SolverEventConflictError,
            SolverPersistenceError,
            SolverStateStore,
        )

        state_store = SolverStateStore(self.store._connection)
        with self.store._lock:
            existing = self.store._connection.execute(
                "SELECT operation,job_id,request_digest,response_json FROM workspace_actions "
                "WHERE user_id=? AND idempotency_key=?",
                (user_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if (existing["operation"] != "formal_attempt"
                        or existing["job_id"] != job_id
                        or existing["request_digest"] != digest):
                    raise WorkspaceError("idempotency_conflict", status=409)
                return _loads(existing["response_json"]), True
            row = self.store._connection.execute(
                "SELECT status,result_json FROM workspace_jobs WHERE job_id=? AND user_id=?",
                (job_id, user_id),
            ).fetchone()
            if row is None:
                raise WorkspaceError("job_not_found", status=404)
            if row["status"] != "succeeded":
                raise WorkspaceError("formal_retry_job_not_terminal", status=409)
            identity = _loads(row["result_json"]) if row["result_json"] else {}
            policy = identity.get("formal_policy")
            if identity.get("solver_mode") not in STAR_MODES or not isinstance(policy, dict):
                raise WorkspaceError("formal_retry_unavailable", status=409)
            registry = getattr(self.star_pipeline, "formal_registry", None)
            if registry is None:
                raise WorkspaceError("formal_retry_unavailable", status=409)
            if operation == "switch":
                if not isinstance(requested_backend, str) or not requested_backend.strip():
                    raise WorkspaceError("formal_backend_required", status=400)
                selected_policy = {
                    **policy, "backend": requested_backend.strip(),
                    "requested_backend": requested_backend.strip(),
                }
            else:
                if requested_backend is not None:
                    raise WorkspaceError("formal_retry_request_invalid", status=400)
                selected_policy = policy
            try:
                backend = registry.select(policy["target"], selected_policy)
            except ValueError as exc:
                raise WorkspaceError("formal_backend_unsupported", status=409) from exc
            current = state_store.get_run(job_id)
            if current is None:
                raise WorkspaceError("formal_retry_unavailable", status=409)
            formal = current["state"].get("formal_verification")
            if not isinstance(formal, Mapping):
                raise WorkspaceError("formal_retry_unavailable", status=409)
            formal_state = FormalIntegrationState(
                job_id=job_id, run_id=job_id, problem=self.store.problem(job_id),
                problem_spec=current["state"].get("problem_spec", {}),
                policy=policy, target=policy["target"],
            )
            event = {
                "event_id": f"formal-retry-{uuid.uuid4().hex}",
                "type": "formal_verification_dispatched", "status": "dispatched",
                "grade": None,
            }

            def transaction_hook_factory(record):
                result = {"success": True, "job_id": job_id, "status": "queued",
                          "attempt_id": record["current_attempt_id"]}

                def persist(connection):
                    prior = connection.execute(
                        "SELECT operation,job_id,request_digest FROM workspace_actions "
                        "WHERE user_id=? AND idempotency_key=?",
                        (user_id, idempotency_key),
                    ).fetchone()
                    if prior is not None:
                        raise SolverEventConflictError(job_id, event["event_id"])
                    connection.execute(
                        "INSERT INTO workspace_actions(user_id,idempotency_key,operation,job_id,request_digest,response_json,created_at) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (user_id, idempotency_key, "formal_attempt", job_id, digest,
                         _json(result), _utc_now()),
                    )
                    updated = connection.execute(
                        "UPDATE workspace_jobs SET status='running',updated_at=? "
                        "WHERE job_id=? AND user_id=? AND status='succeeded'",
                        (_utc_now(), job_id, user_id),
                    )
                    if updated.rowcount != 1:
                        raise SolverPersistenceError("formal_retry_job_not_terminal")

                return persist

            try:
                preview = commit_formal_retry_reservation(
                    self.store, job_id, snapshot=current, state=formal_state,
                    existing=formal, expected_attempt_id=expected_attempt_id,
                    operation=operation,
                    backend=backend, requested_backend=requested_backend,
                    event=event,
                    transaction_hook_factory=transaction_hook_factory,
                )
            except FormalIntegrationError as exc:
                raise WorkspaceError(exc.category, status=409) from exc
            except SolverEventConflictError as exc:
                with self.store._lock:
                    prior = self.store._connection.execute(
                        "SELECT operation,job_id,request_digest,response_json FROM workspace_actions "
                        "WHERE user_id=? AND idempotency_key=?",
                        (user_id, idempotency_key),
                    ).fetchone()
                if (prior is not None and prior["operation"] == "formal_attempt"
                        and prior["job_id"] == job_id and prior["request_digest"] == digest):
                    return _loads(prior["response_json"]), True
                raise WorkspaceError("idempotency_conflict", status=409) from exc
            except SolverPersistenceError as exc:
                raise WorkspaceError("formal_retry_persistence_failed", status=409) from exc
            result = {"success": True, "job_id": job_id, "status": "queued",
                      "attempt_id": preview["current_attempt_id"]}
            with self._submit_lock:
                self._submitted.add(job_id)
            self._executor.submit(self._execute_formal_attempt, job_id)
            return result, False

    def _execute_formal_attempt(self, job_id: str) -> None:
        """Run one child formal attempt through the bounded formal helper."""
        from .solver_harness.formal_integration import run_explicit_formal_retry
        from .solver_harness.storage import SolverStateStore

        identity = self.store.job_identity(job_id)
        state_store = SolverStateStore(self.store._connection)
        with self.store._lock:
            current = state_store.get_run(job_id)
        if current is None:
            return
        record = current["state"].get("formal_verification")
        if not isinstance(record, Mapping):
            return
        try:
            result = run_explicit_formal_retry(
                self, job_id, run_id=job_id,
                problem=self.store.problem(job_id), policy=identity["formal_policy"],
                expected_attempt_id=record["current"].get("parent_attempt_id"),
                operation=record["current"].get("requested_operation", "retry"),
                reserved_attempt_id=record["current_attempt_id"],
            )
            formal = result["record"]
            budget = result["budget"]
        except Exception:  # noqa: BLE001 - do not leave an accepted retry inflight
            from .solver_harness.formal_integration import mark_inflight_unknown

            with self.store._lock:
                current = state_store.get_run(job_id)
            saved = current["state"].get("formal_verification") if current else None
            if (isinstance(saved, Mapping) and saved.get("current_attempt_id") == record["current_attempt_id"]
                    and saved.get("status") == "dispatched"):
                formal = mark_inflight_unknown(saved)
                from .solver_harness.formal_integration import commit_formal_state_with_one_retry

                commit_formal_state_with_one_retry(
                    self.store, job_id, expected_revision=current["state_revision"],
                    formal_verification=formal,
                    event={"event_id": f"formal-{record['current_attempt_id']}-recovered-unknown",
                           "type": "formal_verification_recovered_unknown",
                           "status": "unknown", "grade": None},
                    expected_attempt_id=record["current_attempt_id"],
                    expected_status="dispatched",
                )
            else:
                formal = saved if isinstance(saved, Mapping) else record
            budget = self.budget_ledger.snapshot(job_id)
        persisted = self.store.job_identity(job_id)
        persisted["formal_verification"] = formal
        if budget is not None:
            persisted["budget"] = budget
        _apply_formal_requirement(persisted)
        with self.store._lock:
            self.store._connection.execute(
                "UPDATE workspace_jobs SET status='succeeded',error_code=NULL,result_json=?,updated_at=? WHERE job_id=?",
                (_json(persisted), _utc_now(), job_id),
            )
            self.store._connection.commit()

    def cancel_job(self, *, user_id: str, job_id: str, idempotency_key: str) -> tuple[dict[str, Any], bool]:
        if not _is_uuid_v4(idempotency_key):
            raise WorkspaceError("idempotency_key_invalid", status=400)
        result, existing = self.store.control_job(
            user_id=user_id, job_id=job_id, operation="cancel", idempotency_key=idempotency_key, request_digest=_request_digest("cancel", job_id, "")
        )
        if self.checkpointer is not None:
            self.checkpointer.stop(job_id, "CANCELED", "run_canceled")
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
            identity = self.store.job_identity(job_id)
            pair_binding = identity.get("experiment_pair")
            if pair_binding is not None:
                from .star_product_modes import BEST_EFFORT_MODES

                if (
                    not isinstance(pair_binding, dict)
                    or identity.get("solver_mode") not in STAR_MODES - BEST_EFFORT_MODES
                    or identity.get("execution_mode") != identity.get("solver_mode")
                ):
                    self.store.fail_job(job_id, "experiment_pair_execution_mode_invalid")
                    return
            pipeline = self.star_pipeline if identity.get("solver_mode") in STAR_MODES else self.pipeline
            execution_mode = identity.get("execution_mode", self.execution_mode)
            if not self.store.start_job(job_id, execution_mode=execution_mode):
                return
            # Keep the worker asynchronous even for the deterministic adapter so
            # the HTTP contract never waits for execution.
            time.sleep(self.execution_delay)
            if self.execution_mode == "fake" and self.budget_ledger.snapshot(job_id) is not None:
                budget = self.budget_ledger.ensure(
                    job_id,
                    RunBudgetLimits(),
                    stream_timeout_policy=identity.get("stream_timeout_policy"),
                )
                RunControl(self.store, job_id, budget).check()
            if self.execution_mode == "live" or execution_mode in STAR_MODES:
                if pipeline is None:
                    self.store.fail_job(job_id, "unavailable", execution_mode="live")
                    return
                component_features = None
                if isinstance(pair_binding, dict):
                    from .solver_harness.paired_conditions import STRATEGIES
                    from .star_product_modes import BEST_EFFORT_MODES

                    component_features = pair_binding.get("features")
                    applied_status = pair_binding.get("applied_config_status")
                    applied_config = pair_binding.get("applied_component_config")
                    if (
                        identity.get("solver_mode") in BEST_EFFORT_MODES
                        or not isinstance(component_features, dict)
                        or set(component_features) != STRATEGIES
                        or any(type(enabled) is not bool for enabled in component_features.values())
                        or component_features.get("best_effort") is not False
                        or not (
                            (applied_status == "pre_execution" and applied_config is None)
                            or (applied_status == "applied" and applied_config == component_features)
                        )
                    ):
                        raise WorkspaceError("experiment_pair_features_invalid")
                limits = (pipeline.budget_for_mode(identity.get("solver_mode"))
                          if execution_mode in STAR_MODES else getattr(pipeline, "budget", RunBudgetLimits()))
                deadline = getattr(getattr(pipeline, "experiment_policy", None), "deadline_at", None)
                with bind_budget(self.budget_ledger.ensure(
                    job_id,
                    limits,
                    deadline_at=deadline,
                    stream_timeout_policy=identity.get("stream_timeout_policy"),
                )) as budget, bind_control(RunControl(self.store, job_id, budget, self.checkpointer)) as control:
                    control.check()
                    state = pipeline.run(
                        job_id,
                        self._problem(job_id),
                        verification_mode=self.store.verification_mode(job_id),
                        emit=lambda event: self.store.append_event(job_id, event),
                        **({"solver_hint": self.store.solver_hint(job_id),
                            "retry_call": identity.get("retry_call"),
                            "solver_mode": identity.get("solver_mode"),
                            "problem_spec": self.store.problem_spec(job_id)}
                           if execution_mode in STAR_MODES else {}),
                        **({"component_features": component_features,
                            "on_component_config_applied": lambda config: self.store.record_pair_applied_config(
                                job_id, pair_binding, config
                            )} if component_features is not None else {}),
                    )
                self.store.finish_live_job(job_id, state)
                if self.checkpointer is not None and state.get("status") != "WAITING_INPUT":
                    job = self.store.control_status(job_id)
                    status = "CANCELED" if job["status"] == "canceled" else ("COMPLETED" if job["status"] == "succeeded" else str(state.get("status", "FAILED")))
                    self.checkpointer.stop(job_id, status, job["error_code"])
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
        except RunStopped as exc:
            if exc.category == "run_deadline_exhausted":
                self.store.fail_job(job_id, exc.category)
                if self.checkpointer is not None:
                    self.checkpointer.stop(job_id, "FAILED", exc.category)
            return
        except Exception as exc:
            from .job_failure import record_job_failure

            record_job_failure(job_id, exc)
            self.store.fail_job(job_id, "job_execution_failed", execution_mode=self.execution_mode)
            if self.checkpointer is not None:
                self.checkpointer.stop(job_id, "FAILED", "job_execution_failed")

    def get_job(self, job_id: str, user_id: str) -> dict[str, Any]:
        # File-backed STAR reads deliberately leave the writer connection and
        # in-process lock to job_read_snapshot; that independent read-only
        # connection is required by the non-blocking public snapshot contract.
        from .job_read_snapshot import read_job

        return read_job(self, job_id, user_id)

    def _problem(self, job_id: str) -> str:
        return self.store.problem(job_id)

    def get_job_by_idempotency_key(
        self, *, user_id: str, idempotency_key: str, request_digest: str
    ) -> dict[str, Any]:
        job = self.store.get_job_by_idempotency_key(
            user_id=user_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
        )
        job["budget"] = self.budget_ledger.snapshot(job["job_id"])
        return job

    def active_jobs(self, user_id: str, session_id: str | None = None) -> list[dict[str, Any]]:
        payloads = self.store.active_jobs(user_id, session_id)
        for payload in payloads:
            payload["last_event_id"] = self.store.last_event_id(payload["job_id"], user_id)
        return payloads

    def events(
        self, job_id: str, user_id: str, after_id: int = 0, *, limit: int | None = None
    ) -> list[dict[str, Any]]:
        return self.store.events(job_id, user_id, after_id, limit=limit)

    def status(self, job_id: str, user_id: str) -> str:
        return self.store.status(job_id, user_id)

    def record_verification(self, *, user_id: str, job_id: str, result: Mapping[str, Any]) -> None:
        self.store.get_job(job_id, user_id)
        self.store.record_verification(job_id, result)

    def get_presentation(self, *, user_id: str, job_id: str, mode: str, source_fingerprint: str) -> dict[str, Any] | None:
        self.store.get_job(job_id, user_id)
        return self.store.get_presentation(job_id, user_id, mode, source_fingerprint)

    def save_presentation(self, *, user_id: str, job_id: str, artifact: Mapping[str, Any]) -> dict[str, Any]:
        return self.store.save_presentation(job_id, user_id, artifact)

    def list_presentations(self, *, user_id: str, job_id: str, mode: str) -> list[dict[str, Any]]:
        self.store.get_job(job_id, user_id)
        return self.store.list_presentations(job_id, user_id, mode)

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
        if self.budget_ledger is not None:
            self.budget_ledger.close()
        if self.checkpointer is not None:
            self.checkpointer.close()
        self.store.close()


def _request_digest(*args: Any) -> str:
    if len(args) == 5:
        session_id, problem, web_search_enabled, file_id, verification_mode = args
        payload = {"session_id": session_id, "message": problem, "web_search_enabled": web_search_enabled, "input_user_file_id": file_id, "verification_mode": verification_mode}
    else:
        payload = {"operation": list(args)}
    return hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()


def _presentation_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("presentation_mode", "presentation_schema_version", "presentation_policy_version")
        if key in value
    }


def workspace_job_request_digest(
    *,
    session_id: str,
    message: str,
    web_search_enabled: bool = False,
    input_user_file_id: Any = None,
    verification_mode: str = "auto",
    solver_mode: str = "legacy",
    solver_hint: str | None = None,
    budget_limits: RunBudgetLimits | None = None,
    deadline_at: float | None = None,
    experiment_binding: Mapping[str, Any] | None = None,
    problem_spec: Mapping[str, Any] | None = None,
    presentation_mode: str | None = None,
    population_policy_hash: str | None = None,
    formal_policy: Mapping[str, Any] | None = None,
) -> str:
    """Fingerprint the exact public Job request, including any frozen budget."""
    request_parts = (session_id, message, web_search_enabled, input_user_file_id, verification_mode)
    digest = (
        _request_digest(*request_parts)
        if solver_mode == "legacy"
        else _request_digest(*request_parts, solver_mode)
    )
    if solver_hint is not None:
        digest = _request_digest(digest, solver_hint)
    if budget_limits is not None or deadline_at is not None:
        digest = _request_digest(
            digest,
            {
                "budget_limits": None if budget_limits is None else {
                    "max_model_calls": budget_limits.max_model_calls,
                    "max_http_attempts": budget_limits.max_http_attempts,
                    "max_tool_calls": budget_limits.max_tool_calls,
                    "max_tokens": budget_limits.max_tokens,
                    "max_runtime_seconds": budget_limits.max_runtime_seconds,
                },
                "deadline_at": deadline_at,
            },
        )
    if experiment_binding is not None:
        digest = _request_digest(digest, {"experiment_pair": dict(experiment_binding)})
    if problem_spec is not None:
        digest = _request_digest(digest, {"problem_spec": dict(problem_spec)})
    if presentation_mode is not None:
        digest = _request_digest(digest, {"presentation_mode": presentation_mode})
    if population_policy_hash is not None:
        digest = _request_digest(digest, {"population_policy_hash": population_policy_hash})
    if formal_policy is not None:
        digest = _request_digest(digest, {"formal_policy": dict(formal_policy)})
    return digest


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


def _mark_pair_config_not_applied(result: dict[str, Any]) -> None:
    """Replace a stale pre-execution marker on a terminal pair Job."""
    binding = result.get("experiment_pair")
    if isinstance(binding, dict) and binding.get("applied_config_status") == "pre_execution":
        result["experiment_pair"] = {
            **binding,
            "applied_config_status": "not_applied",
            "applied_component_config": None,
        }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["WorkspaceError", "WorkspaceService"]
