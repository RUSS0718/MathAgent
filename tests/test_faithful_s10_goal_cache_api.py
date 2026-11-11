"""Authenticated, session-scoped management contracts for Global Goal Cache."""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

from showcase.flask_app import create_app
from showcase.solver_harness.faithful_goal_cache import GlobalGoalCache


class GoalCacheManagementAPITest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = self._create_app(enabled=True)
        self.apps = [self.app]
        self.addCleanup(self._close_apps)
        self.client = self.app.test_client()
        auth = self.client.get("/api/check_auth").get_json()
        self.csrf = auth["csrf_token"]
        self.session_id = self.client.post(
            "/api/new_chat", headers=self._headers()
        ).get_json()["new_session_id"]

    def _create_app(self, *, enabled):
        return create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": self.folder.name,
            "SHOWCASE_WORKER_ENABLED": False,
            "SHOWCASE_FAITHFUL_MEMORY_ENABLED": enabled,
        })

    @staticmethod
    def _close_app(app):
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            resource = app.extensions.get(name)
            if resource is not None:
                try:
                    resource.close()
                except sqlite3.ProgrammingError:
                    pass

    def _close_apps(self):
        for app in self.apps:
            self._close_app(app)

    def _headers(self, token=None):
        return {"X-CSRF-Token": token or self.csrf}

    def _url(self, session_id=None):
        return f"/api/sessions/{session_id or self.session_id}/goal-cache"

    def _seed_entry(self, *, session_id=None, owner_id="local-user"):
        workspace_id = session_id or self.session_id
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            GlobalGoalCache(db, owner_id=owner_id, workspace_id=workspace_id)
            now = datetime.now(UTC).isoformat()
            cache_id = "cache-" + uuid4().hex
            identity = {
                "goal": {"target": "x=x"},
                "hypotheses": [],
                "proof_hash": "SENSITIVE_OLD_PROOF_PAYLOAD",
            }
            identity_key = "a" * 64
            lookup_key = "b" * 64
            db.execute(
                """INSERT INTO faithful_goal_cache_entries(
                       cache_id, owner_id, workspace_id, identity_key, lookup_key,
                       identity_json, state, state_reason, proof_source_hash, proof_hash,
                       target_hash, environment_hash, grade, source_run_id,
                       source_attempt_id, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, 'active', NULL, ?, ?, ?, ?, 'L2', ?, ?, ?, ?)""",
                (
                    cache_id, owner_id, workspace_id, identity_key, lookup_key,
                    json.dumps(identity), "source-hash", "SENSITIVE_OLD_PROOF_PAYLOAD",
                    "target-hash", "environment-hash", "run-123", "attempt-123", now, now,
                ),
            )
            db.commit()
        return cache_id

    def test_routes_are_absent_without_explicit_feature_flag(self):
        disabled = self._create_app(enabled=False)
        self.addCleanup(self._close_app, disabled)
        response = disabled.test_client().get(self._url())
        self.assertEqual(404, response.status_code)

    def test_get_requires_authenticated_session_and_mutations_require_csrf(self):
        url = self._url()
        anonymous = self.app.test_client()
        self.assertEqual(401, anonymous.get(url).status_code)
        self.assertEqual(403, self.client.put(url, json={"enabled": False}).status_code)
        self.assertEqual(403, self.client.delete(url, headers=self._headers("invalid")).status_code)

    def test_get_exposes_metadata_only_and_never_claims_cache_use(self):
        cache_id = self._seed_entry()
        response = self.client.get(self._url())
        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual("no-store", response.headers.get("Cache-Control"))
        default_body = response.get_json()
        self.assertFalse(default_body["enabled"])
        self.assertEqual([], default_body["entries"])
        self.assertNotIn("cache_enabled", [item["event"] for item in default_body["events"]])

        enabled = self.client.put(
            self._url(), json={"enabled": True}, headers=self._headers()
        )
        self.assertEqual(200, enabled.status_code, enabled.get_json())
        body = self.client.get(self._url()).get_json()
        self.assertTrue(body["enabled"])
        self.assertEqual([cache_id], [item["cache_id"] for item in body["entries"]])
        entry = body["entries"][0]
        self.assertEqual("run-123", entry["source_run_id"])
        self.assertEqual("attempt-123", entry["source_attempt_id"])
        self.assertEqual("L2", entry["source_grade"])
        self.assertEqual("L2", entry["grade_ceiling"])
        encoded = json.dumps(body)
        for forbidden in (
            "SENSITIVE_OLD_PROOF_PAYLOAD", "verified_gain", "proof_hash",
            "source_grade_used_as_proof", "hit", "reused",
        ):
            self.assertNotIn(forbidden, encoded)
        self.assertIn("events", body)

    def test_cross_session_and_cross_user_requests_do_not_reveal_metadata(self):
        other_session = self.client.post(
            "/api/new_chat", headers=self._headers()
        ).get_json()["new_session_id"]
        current_cache_id = self._seed_entry()
        other_cache_id = self._seed_entry(session_id=other_session)
        for session_id in (self.session_id, other_session):
            self.assertEqual(
                200,
                self.client.put(
                    self._url(session_id),
                    json={"enabled": True},
                    headers=self._headers(),
                ).status_code,
            )
        current_view = self.client.get(self._url()).get_json()
        other_view = self.client.get(self._url(other_session)).get_json()
        self.assertEqual([current_cache_id], [item["cache_id"] for item in current_view["entries"]])
        self.assertEqual([other_cache_id], [item["cache_id"] for item in other_view["entries"]])

        identity_store = self.app.extensions["loopback_store"]
        now = datetime.now(UTC).isoformat()
        with identity_store._connection:
            identity_store._connection.execute(
                "INSERT INTO loopback_users VALUES (?,?,?,?)",
                ("foreign-user", "foreign", "[]", now),
            )
            identity_store._connection.execute(
                "INSERT INTO auth_sessions VALUES (?,?,?,?,?,?)",
                ("foreign-auth", "foreign-user", "foreign-csrf", now, now, None),
            )
        foreign = self.app.test_client()
        foreign.set_cookie("auth_session", "foreign-auth")
        for method in ("get", "put", "delete"):
            response = getattr(foreign, method)(
                self._url(), json={"enabled": False} if method == "put" else None,
                headers={"X-CSRF-Token": "foreign-csrf"},
            )
            self.assertEqual(404, response.status_code, response.get_json())
            self.assertNotIn("entries", response.get_json())
            self.assertNotIn("events", response.get_json())

    def test_recheck_rejection_reason_is_visible_in_metadata_only_view(self):
        cache_id = self._seed_entry()
        url = self._url()
        self.client.put(url, json={"enabled": True}, headers=self._headers())
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            db.execute(
                "UPDATE faithful_goal_cache_entries SET state='stale', state_reason=? WHERE cache_id=?",
                ("lean_recheck_failed", cache_id),
            )
            db.execute(
                """INSERT INTO faithful_goal_cache_audit(
                       event_id, owner_id, workspace_id, cache_id, event, actor_id,
                       details_json, created_at
                   ) VALUES ('recheck-event', 'local-user', ?, ?, 'receipt_stale',
                             'local-user', ?, '2026-11-10T03:00:00Z')""",
                (self.session_id, cache_id, json.dumps({"reason": "lean_recheck_failed"})),
            )
            db.commit()
        response = self.client.get(url)
        self.assertEqual(200, response.status_code)
        body = response.get_json()
        self.assertEqual("lean_recheck_failed", body["entries"][0]["reason"])
        event = next(item for item in body["events"] if item["event"] == "receipt_stale")
        self.assertEqual("lean_recheck_failed", event["details"]["reason"])

    def test_disable_enable_clear_and_audit_survive_app_restart(self):
        cache_id = self._seed_entry()
        url = self._url()
        default_view = self.client.get(url).get_json()
        self.assertFalse(default_view["enabled"])
        self.assertEqual([], default_view["entries"])
        disabled = self.client.put(url, json={"enabled": False}, headers=self._headers())
        self.assertEqual(200, disabled.status_code, disabled.get_json())
        hidden = self.client.get(url).get_json()
        self.assertFalse(hidden["enabled"])
        self.assertEqual([], hidden["entries"])
        self.assertIn("cache_disabled", [item["event"] for item in hidden["events"]])

        enabled = self.client.put(url, json={"enabled": True}, headers=self._headers())
        self.assertEqual(200, enabled.status_code, enabled.get_json())
        self.assertEqual([cache_id], [item["cache_id"] for item in self.client.get(url).get_json()["entries"]])
        cleared = self.client.delete(url, headers=self._headers())
        self.assertEqual(200, cleared.status_code, cleared.get_json())
        cleared_view = self.client.get(url).get_json()
        self.assertEqual([cache_id], [item["cache_id"] for item in cleared_view["entries"]])
        self.assertEqual("invalidated", cleared_view["entries"][0]["state"])
        before = cleared_view
        self.assertIn("cache_cleared", [item["event"] for item in before["events"]])

        cookie = self.client.get_cookie("auth_session").value
        self.app = self._create_app(enabled=True)
        self.apps.append(self.app)
        self.client = self.app.test_client()
        self.client.set_cookie("auth_session", cookie)
        after = self.client.get(url)
        self.assertEqual(200, after.status_code, after.get_json())
        self.assertEqual("invalidated", after.get_json()["entries"][0]["state"])
        self.assertEqual(
            [event["event"] for event in before["events"]],
            [event["event"] for event in after.get_json()["events"]],
        )


if __name__ == "__main__":
    unittest.main()
