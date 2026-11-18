"""Authenticated, session-bound controls for advisory Faithful Memory."""

import sqlite3
import unittest
import uuid
from contextlib import closing
from datetime import UTC, datetime

from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from tests.star_product_support import StarJobFixture


def _observation():
    return {
        "outcome": "failure",
        "applicability": {"domain": "polynomials"},
        "versions": {"graph": 2},
        "cost": {"provider_calls": 1},
        "content": {"route_summary": "check the sign before expanding"},
    }


class FaithfulMemoryControlAPITest(StarJobFixture, unittest.TestCase):
    def open_app(self, enabled=True):
        self.open_star([], SHOWCASE_FAITHFUL_MEMORY_ENABLED=enabled)

    def owned_job(self, session_id=None):
        workspace = self.app.extensions["showcase_workspace_service"].store
        job, _ = workspace.create_job(
            user_id="local-user",
            session_id=session_id or self.session,
            problem="test problem",
            idempotency_key=uuid.uuid4().hex,
            request_digest=uuid.uuid4().hex,
        )
        return job["job_id"]

    def seed_observation(self, scope, source_run_id):
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as connection:
            store = FaithfulMemoryStore(connection)
            return store.record_observation(
                scope,
                _observation(),
                provenance={"source_run_id": source_run_id},
            )

    def path(self, session_id, kind, scope_id, suffix=""):
        return f"/api/sessions/{session_id}/memory/{kind}/{scope_id}{suffix}"

    def test_routes_require_explicit_flag_authentication_and_csrf(self):
        self.open_app(enabled=False)
        url = self.path(self.session, "population", self.session)
        self.assertEqual(404, self.client.get(url).status_code)

        self.open_app(enabled=True)
        anonymous = self.app.test_client()
        self.assertEqual(401, anonymous.get(url).status_code)
        self.assertEqual(
            405,
            self.client.post(
                url,
                json=_observation(),
                headers=self.headers(),
            ).status_code,
        )
        no_csrf = self.client.put(url, json={"enabled": False})
        self.assertEqual(403, no_csrf.status_code)
        self.assertEqual("csrf_required", no_csrf.get_json()["code"])

    def test_memory_observation_and_audit_reads_are_not_cached(self):
        self.open_app()
        run_id = self.owned_job()
        self.seed_observation(
            MemoryScope("run", run_id, "local-user", self.session), run_id
        )
        memory_url = self.path(self.session, "run", run_id)
        audit_url = memory_url + "/audit"

        memory = self.client.get(memory_url)
        audit = self.client.get(audit_url)

        self.assertEqual(200, memory.status_code, memory.get_json())
        self.assertEqual(200, audit.status_code, audit.get_json())
        self.assertEqual("no-store", memory.headers.get("Cache-Control"))
        self.assertEqual("no-store", audit.headers.get("Cache-Control"))

    def test_population_and_run_scope_are_bound_to_authenticated_session(self):
        self.open_app()
        other_session = self.client.post("/api/new_chat", headers=self.headers()).get_json()[
            "new_session_id"
        ]
        other_job = self.owned_job(other_session)
        record_id = self.seed_observation(
            MemoryScope("run", other_job, "local-user", other_session), other_job
        )

        cross_session = self.client.get(self.path(self.session, "population", other_session))
        self.assertEqual(404, cross_session.status_code)
        cross_run = self.client.get(self.path(self.session, "run", other_job))
        self.assertEqual(404, cross_run.status_code)

        destination = self.path(self.session, "population", self.session, "/imports")
        response = self.client.post(
            destination,
            json={"record_id": record_id, "source_kind": "run", "source_scope_id": other_job},
            headers=self.headers(),
        )
        self.assertEqual(404, response.status_code, response.get_json())

        identity = self.app.extensions["loopback_store"]
        now = datetime.now(UTC).isoformat()
        with identity._connection:
            identity._connection.execute(
                "INSERT INTO loopback_users VALUES (?,?,?,?)",
                ("other-user", "other", "[]", now),
            )
            identity._connection.execute(
                "INSERT INTO auth_sessions VALUES (?,?,?,?,?,?)",
                ("other-auth", "other-user", "csrf", now, now, None),
            )
        foreign = self.app.test_client()
        foreign.set_cookie("auth_session", "other-auth")
        self.assertEqual(
            404,
            foreign.get(self.path(self.session, "population", self.session)).status_code,
        )
        for suffix in ("/audit", ""):
            denied = foreign.get(self.path(self.session, "run", other_job, suffix))
            self.assertEqual(404, denied.status_code, denied.get_json())
            self.assertNotIn("events", denied.get_json())
        denied_clear = foreign.delete(
            self.path(self.session, "population", self.session),
            headers={"X-CSRF-Token": "csrf"},
        )
        self.assertEqual(404, denied_clear.status_code, denied_clear.get_json())

    def test_import_control_clear_and_audit_tombstone_survive_restart(self):
        self.open_app()
        run_id = self.owned_job()
        run = MemoryScope("run", run_id, "local-user", self.session)
        source_id = self.seed_observation(run, run_id)

        response = self.client.get(self.path(self.session, "run", run_id))
        self.assertEqual(200, response.status_code, response.get_json())
        self.assertEqual(
            [source_id], [item["record_id"] for item in response.get_json()["observations"]]
        )
        self.assertEqual("advisory", response.get_json()["observations"][0]["trust"])
        self.assertNotIn("verified_gain", str(response.get_json()))

        imported = self.client.post(
            self.path(self.session, "population", self.session, "/imports"),
            json={"record_id": source_id, "source_kind": "run", "source_scope_id": run_id},
            headers=self.headers(),
        )
        self.assertEqual(201, imported.status_code, imported.get_json())
        imported_id = imported.get_json()["record_id"]
        self.assertEqual(
            [imported_id],
            [
                item["record_id"]
                for item in self.client.get(
                    self.path(self.session, "population", self.session)
                ).get_json()["observations"]
            ],
        )

        population_url = self.path(self.session, "population", self.session)
        disabled = self.client.put(population_url, json={"enabled": False}, headers=self.headers())
        self.assertEqual(200, disabled.status_code, disabled.get_json())
        self.assertEqual([], self.client.get(population_url).get_json()["observations"])
        disabled_import = self.client.post(
            population_url + "/imports",
            json={"record_id": source_id, "source_kind": "run", "source_scope_id": run_id},
            headers=self.headers(),
        )
        self.assertEqual(409, disabled_import.status_code, disabled_import.get_json())
        self.assertEqual("memory_scope_disabled", disabled_import.get_json()["code"])
        enabled = self.client.put(population_url, json={"enabled": True}, headers=self.headers())
        self.assertEqual(200, enabled.status_code, enabled.get_json())
        self.assertEqual(1, len(self.client.get(population_url).get_json()["observations"]))

        cleared = self.client.delete(population_url, headers=self.headers())
        self.assertEqual(200, cleared.status_code, cleared.get_json())
        self.assertEqual([], self.client.get(population_url).get_json()["observations"])
        audit_url = self.path(self.session, "population", self.session, "/audit")
        before = self.client.get(audit_url).get_json()["events"]
        self.assertIn("scope_cleared", [event["event"] for event in before])
        self.assertIn(imported_id, [event.get("record_id") for event in before])
        tombstones = [event for event in before if event["event"] == "entry_cleared"]
        self.assertEqual([imported_id], [event["record_id"] for event in tombstones])
        self.assertTrue(tombstones[0]["details"]["tombstone"])
        run_url = self.path(self.session, "run", run_id)
        self.assertEqual(
            200,
            self.client.put(run_url, json={"enabled": False}, headers=self.headers()).status_code,
        )

        from showcase.flask_app import create_app

        restarted = create_app(
            {
                "TESTING": True,
                "SHOWCASE_DATA_DIR": self.data_dir,
                "SHOWCASE_FAITHFUL_MEMORY_ENABLED": True,
                "SHOWCASE_WORKER_ENABLED": False,
            }
        )
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(restarted.extensions[name].close)
        client = restarted.test_client()
        client.set_cookie("auth_session", self.client.get_cookie("auth_session").value)
        after_response = client.get(audit_url)
        self.assertEqual(200, after_response.status_code, after_response.get_json())
        after = after_response.get_json()["events"]
        self.assertEqual([event["event"] for event in before], [event["event"] for event in after])
        self.assertIn("scope_cleared", [event["event"] for event in after])
        self.assertEqual([], client.get(population_url).get_json()["observations"])
        self.assertEqual([], client.get(run_url).get_json()["observations"])
        self.assertEqual(
            200,
            client.put(
                run_url, json={"enabled": True}, headers={"X-CSRF-Token": self.csrf}
            ).status_code,
        )
        self.assertEqual(
            [source_id],
            [item["record_id"] for item in client.get(run_url).get_json()["observations"]],
        )

    def test_provenance_must_match_run_scope_and_current_session(self):
        self.open_app()
        run_id = self.owned_job()
        other_session = self.client.post("/api/new_chat", headers=self.headers()).get_json()[
            "new_session_id"
        ]
        foreign_run = self.owned_job(other_session)
        workspace = self.app.extensions["showcase_workspace_service"].store
        # A second persisted Job in the same session, without starting a worker.
        with workspace._connection:
            workspace._connection.execute(
                "UPDATE workspace_jobs SET status='succeeded' WHERE job_id=?", (run_id,)
            )
        second_run = self.owned_job()
        run_scope = MemoryScope("run", run_id, "local-user", self.session)
        population = MemoryScope("population", self.session, "local-user", self.session)
        valid_id = self.seed_observation(run_scope, run_id)
        invalid_ids = [
            self.seed_observation(run_scope, source)
            for source in (second_run, foreign_run, "missing-run")
        ]
        run_url = self.path(self.session, "run", run_id)
        listed = self.client.get(run_url)
        self.assertEqual(200, listed.status_code, listed.get_json())
        self.assertEqual(
            [valid_id], [item["record_id"] for item in listed.get_json()["observations"]]
        )
        for record_id in invalid_ids:
            denied = self.client.post(
                self.path(self.session, "population", self.session, "/imports"),
                json={"record_id": record_id, "source_kind": "run", "source_scope_id": run_id},
                headers=self.headers(),
            )
            self.assertEqual(404, denied.status_code, denied.get_json())

        historical_import = self.client.post(
            self.path(self.session, "run", second_run, "/imports"),
            json={
                "record_id": valid_id,
                "source_kind": "run",
                "source_scope_id": run_id,
            },
            headers=self.headers(),
        )
        self.assertEqual(201, historical_import.status_code, historical_import.get_json())
        imported_id = historical_import.get_json()["record_id"]
        imported_run = self.client.get(self.path(self.session, "run", second_run))
        self.assertEqual(200, imported_run.status_code, imported_run.get_json())
        imported_item = next(
            item
            for item in imported_run.get_json()["observations"]
            if item["record_id"] == imported_id
        )
        self.assertEqual(run_id, imported_item["provenance"]["source_run_id"])
        self.assertEqual(
            run_id, imported_item["provenance"]["original_provenance"]["source_run_id"]
        )
        self.assertEqual("advisory", imported_item["trust"])
        population_id = self.seed_observation(population, run_id)
        foreign_id = self.seed_observation(population, foreign_run)
        listed = self.client.get(self.path(self.session, "population", self.session)).get_json()
        self.assertEqual([population_id], [item["record_id"] for item in listed["observations"]])
        foreign_import = self.client.post(
            run_url + "/imports",
            json={
                "record_id": foreign_id,
                "source_kind": "population",
                "source_scope_id": self.session,
            },
            headers=self.headers(),
        )
        self.assertEqual(404, foreign_import.status_code)

        for kind, scope_id in (("run", foreign_run), ("population", other_session)):
            audit = self.client.get(self.path(self.session, kind, scope_id, "/audit"))
            self.assertEqual(404, audit.status_code, audit.get_json())
            self.assertNotIn("events", audit.get_json())

    def test_cross_session_import_requires_explicit_source_and_preserves_origin(self):
        self.open_app()
        source_session = self.client.post(
            "/api/new_chat", headers=self.headers()
        ).get_json()["new_session_id"]
        source_run = self.owned_job(source_session)
        destination_run = self.owned_job(self.session)
        source_scope = MemoryScope("run", source_run, "local-user", source_session)
        source_id = self.seed_observation(source_scope, source_run)

        destination_url = self.path(self.session, "run", destination_run, "/imports")
        denied = self.client.post(
            destination_url,
            json={"record_id": source_id, "source_kind": "run", "source_scope_id": source_run},
            headers=self.headers(),
        )
        self.assertEqual(404, denied.status_code, denied.get_json())

        imported = self.client.post(
            destination_url,
            json={
                "record_id": source_id,
                "source_kind": "run",
                "source_scope_id": source_run,
                "source_session_id": source_session,
            },
            headers=self.headers(),
        )
        self.assertEqual(201, imported.status_code, imported.get_json())
        self.assertEqual(source_session, imported.get_json()["source_session_id"])
        self.assertEqual(self.session, imported.get_json()["destination_session_id"])
        visible = self.client.get(self.path(self.session, "run", destination_run))
        self.assertEqual(200, visible.status_code, visible.get_json())
        observation = visible.get_json()["observations"][0]
        self.assertEqual(source_run, observation["provenance"]["source_run_id"])
        self.assertEqual("advisory", observation["trust"])
        self.assertEqual(
            source_session,
            observation["provenance"]["imported_from"]["scope"]["workspace_id"],
        )

    def test_invalid_requests_and_store_errors_return_stable_4xx(self):
        self.open_app()
        url = self.path(self.session, "population", self.session)
        for payload in ([], {}, {"enabled": 1}, {"enabled": "false"}):
            response = self.client.put(url, json=payload, headers=self.headers())
            self.assertEqual(400, response.status_code, response.get_json())
            self.assertEqual("memory_request_invalid", response.get_json()["code"])
        run_id = self.owned_job()
        record_id = self.seed_observation(
            MemoryScope("population", self.session, "local-user", self.session), run_id
        )
        same_scope = self.client.post(
            url + "/imports",
            json={
                "record_id": record_id,
                "source_kind": "population",
                "source_scope_id": self.session,
            },
            headers=self.headers(),
        )
        self.assertEqual(404, same_scope.status_code, same_scope.get_json())
        self.assertEqual("memory_scope_not_found", same_scope.get_json()["code"])


if __name__ == "__main__":
    unittest.main()
