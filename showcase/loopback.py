"""Persistence for the local single-user Showcase identity boundary."""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class AuthSession:
    """The public identity data associated with one loopback Cookie."""

    session_id: str
    user_id: str
    username: str
    csrf_token: str
    permissions: tuple[str, ...]


class LoopbackStore:
    """Persist the one local user and its revocable authentication sessions."""

    user_id = "local-user"
    username = "local"
    permissions = ("dashboard.access",)

    def __init__(self, database_path: str | Path = ":memory:") -> None:
        self.database_path = str(database_path)
        self._lock = RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS loopback_users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                permissions_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                csrf_token TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY (user_id) REFERENCES loopback_users(user_id)
            );
            """
        )
        self._connection.execute(
            """
            INSERT INTO loopback_users(user_id, username, permissions_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (self.user_id, self.username, json.dumps(self.permissions), _utc_now()),
        )
        self._connection.commit()

    def get_or_create(self, session_id: str | None) -> tuple[AuthSession, bool]:
        """Return a valid session, creating one when the Cookie is absent or revoked."""

        with self._lock, self._connection:
            if session_id:
                session = self._get(session_id)
                if session is not None:
                    self._connection.execute(
                        "UPDATE auth_sessions SET last_seen_at = ? WHERE session_id = ?",
                        (_utc_now(), session.session_id),
                    )
                    return session, False

            now = _utc_now()
            new_session = AuthSession(
                session_id=secrets.token_urlsafe(32),
                user_id=self.user_id,
                username=self.username,
                csrf_token=secrets.token_urlsafe(32),
                permissions=self.permissions,
            )
            self._connection.execute(
                """
                INSERT INTO auth_sessions(
                    session_id, user_id, csrf_token, created_at, last_seen_at, revoked_at
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    new_session.session_id,
                    new_session.user_id,
                    new_session.csrf_token,
                    now,
                    now,
                ),
            )
            return new_session, True

    def get(self, session_id: str | None) -> AuthSession | None:
        """Return a non-revoked session without creating a new Cookie."""

        with self._lock:
            return self._get(session_id)

    def revoke(self, session_id: str) -> None:
        """Revoke one Cookie while retaining all user and Run history."""

        with self._lock, self._connection:
            self._connection.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE session_id = ?",
                (_utc_now(), session_id),
            )

    def close(self) -> None:
        """Close the SQLite connection used by the identity boundary."""

        with self._lock:
            self._connection.close()

    def _get(self, session_id: str | None) -> AuthSession | None:
        if not session_id:
            return None
        row = self._connection.execute(
            """
            SELECT s.session_id, s.user_id, u.username, s.csrf_token, u.permissions_json
            FROM auth_sessions AS s
            JOIN loopback_users AS u ON u.user_id = s.user_id
            WHERE s.session_id = ? AND s.revoked_at IS NULL
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            permissions = tuple(json.loads(row["permissions_json"]))
        except (TypeError, ValueError):
            permissions = ()
        return AuthSession(
            session_id=row["session_id"],
            user_id=row["user_id"],
            username=row["username"],
            csrf_token=row["csrf_token"],
            permissions=permissions,
        )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
