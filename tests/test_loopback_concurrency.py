"""Concurrent authentication contracts through the public Flask routes."""

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Lock, get_ident
from time import sleep
from unittest.mock import patch

from showcase.flask_app import AUTH_COOKIE, create_app


class GuardedConnection(sqlite3.Connection):
    """Expose cross-thread transaction sharing instead of relying on SQLite timing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = None
        self.guard = Lock()

    def execute(self, sql, parameters=()):
        with self.guard:
            if self.owner is not None and self.owner != get_ident():
                raise sqlite3.InterfaceError("authentication transaction shared across threads")
            if sql.lstrip().startswith(("INSERT INTO auth_sessions", "UPDATE auth_sessions")):
                self.owner = get_ident()
        if self.owner is not None:
            sleep(0.02)
        return super().execute(sql, parameters)

    def commit(self):
        result = super().commit()
        with self.guard:
            self.owner = None
        return result

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            with self.guard:
                self.owner = None


class LoopbackConcurrencyTest(unittest.TestCase):
    def test_concurrent_auth_creation_read_and_revocation_keep_cookies_independent(self):
        connect = sqlite3.connect

        def auth_connect(*args, **kwargs):
            return connect(*args, **kwargs, factory=GuardedConnection)

        with tempfile.TemporaryDirectory() as directory:
            with patch("showcase.loopback.sqlite3.connect", side_effect=auth_connect):
                app = create_app(
                    {
                        "TESTING": True,
                        "SHOWCASE_DATA_DIR": str(Path(directory)),
                        "SHOWCASE_WORKER_ENABLED": False,
                    }
                )
            try:
                clients = [app.test_client() for _ in range(12)]
                existing = [
                    client.get("/api/check_auth").get_json()["csrf_token"] for client in clients[:8]
                ]
                cookies = [client.get_cookie(AUTH_COOKIE).value for client in clients[:8]]
                barrier = Barrier(12)

                def request(index):
                    client = clients[index]
                    barrier.wait(timeout=5)
                    if index < 4:
                        return client.post("/api/logout", headers={"X-CSRF-Token": existing[index]})
                    return client.get("/api/check_auth")

                with ThreadPoolExecutor(max_workers=12) as executor:
                    responses = list(executor.map(request, range(12)))
                self.assertEqual([200] * 12, [response.status_code for response in responses])
                for index in range(4, 8):
                    self.assertEqual(existing[index], responses[index].get_json()["csrf_token"])
                    self.assertNotIn("Set-Cookie", responses[index].headers)
                for cookie in cookies[:4]:
                    revoked = app.test_client()
                    revoked.set_cookie(AUTH_COOKIE, cookie)
                    self.assertEqual(
                        401,
                        revoked.post("/api/logout", headers={"X-CSRF-Token": "old"}).status_code,
                    )
                    self.assertEqual(200, revoked.get("/api/check_auth").status_code)
                    self.assertNotEqual(cookie, revoked.get_cookie(AUTH_COOKIE).value)
                active = clients[4:]
                self.assertEqual(
                    8, len({client.get_cookie(AUTH_COOKIE).value for client in active})
                )
                self.assertEqual(
                    8,
                    len(
                        {
                            client.get("/api/check_auth").get_json()["csrf_token"]
                            for client in active
                        }
                    ),
                )
            finally:
                for key in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                    app.extensions[key].close()
