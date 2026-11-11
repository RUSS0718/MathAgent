"""Explicit imports retain and revalidate every source scope."""

import json
import sqlite3
import unittest
import uuid
from contextlib import closing

from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from showcase.solver_harness.faithful_memory_injection import load_population_memory
from tests.star_product_support import StarJobFixture


class MemoryImportChainTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE chat_sessions(session_id TEXT PRIMARY KEY, user_id TEXT);
            CREATE TABLE workspace_jobs(job_id TEXT PRIMARY KEY, session_id TEXT,
                                        user_id TEXT, status TEXT);
            INSERT INTO chat_sessions VALUES ('a','owner'),('b','owner'),('c','owner');
            INSERT INTO workspace_jobs VALUES ('run-a','a','owner','succeeded'),
                ('run-b','b','owner','failed'),('current','c','owner','running');
        """)
        self.store = FaithfulMemoryStore(self.db)
        self.origin = MemoryScope("run", "run-a", "owner", "a")
        self.middle = MemoryScope("run", "run-b", "owner", "b")
        self.target = MemoryScope("population", "c", "owner", "c")
        self.root_id = self.store.record_observation(self.origin, {
            "outcome": "failure", "applicability": {"domain": "algebra"},
            "versions": {}, "cost": {}, "content": {},
        }, provenance={"source_run_id": "run-a"})
        self.middle_id = self.store.import_observation(
            self.root_id, self.middle, actor_id="owner", allow_cross_workspace=True)
        self.final_id = self.store.import_observation(
            self.middle_id, self.target, actor_id="owner", allow_cross_workspace=True)
        self.store.set_injection_enabled(self.target, True, actor_id="owner")
        self.db.commit()

    def load(self):
        return load_population_memory(
            self.db, run_id="current", problem_spec={"domain": "algebra"})["observations"]

    def test_explicit_cross_session_chain_loads_without_upgrading_authority(self):
        loaded = self.load()
        self.assertEqual([self.final_id], [item["record_id"] for item in loaded])
        self.assertEqual("run-a", loaded[0]["provenance"]["source_run_id"])
        self.assertEqual("diagnostic_only", loaded[0]["use"])
        self.assertEqual("advisory_only", loaded[0]["authority"])

    def test_revoked_ancestor_or_scope_owner_prevents_injection(self):
        self.assertEqual(1, len(self.load()))
        for sql, args in (
            ("UPDATE faithful_memory_entries SET state='cleared' WHERE record_id=?", (self.root_id,)),
            ("UPDATE chat_sessions SET user_id='foreign' WHERE session_id='a'", ()),
            ("UPDATE workspace_jobs SET status='running' WHERE job_id='run-a'", ()),
            ("UPDATE workspace_jobs SET user_id='foreign' WHERE job_id='run-b'", ()),
            ("UPDATE faithful_memory_entries SET payload_json='{}' WHERE record_id=?", (self.root_id,)),
            ("UPDATE faithful_memory_entries SET state='cleared' WHERE record_id=?", (self.middle_id,)),
        ):
            with self.subTest(sql=sql):
                self.db.execute("SAVEPOINT mutation")
                self.db.execute(sql, args)
                self.assertEqual([], self.load())
                self.db.execute("ROLLBACK TO mutation")
                self.db.execute("RELEASE mutation")
        self.store.disable_scope(self.origin, actor_id="owner")
        self.assertEqual([], self.load())

    def test_forged_import_actor_or_source_scope_is_rejected(self):
        raw = self.db.execute("SELECT payload_json FROM faithful_memory_entries WHERE record_id=?",
                              (self.final_id,)).fetchone()[0]
        for field, value in (("imported_by", "foreign"), ("source_run_id", "run-b")):
            with self.subTest(field=field):
                payload = json.loads(raw)
                payload["provenance"][field] = value
                self.db.execute("UPDATE faithful_memory_entries SET payload_json=? WHERE record_id=?",
                                (json.dumps(payload), self.final_id))
                self.assertEqual([], self.load())

    def test_import_container_can_be_active_while_origin_must_be_terminal(self):
        self.db.execute("UPDATE workspace_jobs SET status='running' WHERE job_id='run-b'")
        self.assertEqual(1, len(self.load()))


class MemoryImportChainAPITest(StarJobFixture, unittest.TestCase):
    def test_cross_session_population_chain_remains_visible(self):
        self.open_star([], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        workspace = self.app.extensions["showcase_workspace_service"].store
        job, _ = workspace.create_job(
            user_id="local-user", session_id=self.session, problem="test",
            idempotency_key=uuid.uuid4().hex, request_digest=uuid.uuid4().hex)
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            record = FaithfulMemoryStore(db).record_observation(
                MemoryScope("run", job["job_id"], "local-user", self.session),
                {"outcome": "failure", "applicability": {"domain": "algebra"},
                 "versions": {}, "cost": {}, "content": {}},
                provenance={"source_run_id": job["job_id"]})
            db.commit()
        source_session, source_kind, source_scope = self.session, "run", job["job_id"]
        for _ in range(2):
            session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]
            url = f"/api/sessions/{session}/memory/population/{session}"
            response = self.client.post(url + "/imports", headers=self.headers(), json={
                "record_id": record, "source_kind": source_kind,
                "source_scope_id": source_scope, "source_session_id": source_session})
            self.assertEqual(201, response.status_code, response.get_json())
            record = response.get_json()["record_id"]
            self.assertEqual([record], [item["record_id"] for item in
                                      self.client.get(url).get_json()["observations"]])
            source_session, source_kind, source_scope = session, "population", session

    def test_public_import_chain_loads_and_ancestor_clear_revokes_it(self):
        self.open_star([], SHOWCASE_FAITHFUL_MEMORY_ENABLED=True)
        workspace = self.app.extensions["showcase_workspace_service"].store
        ids = []
        for _ in range(2):
            job, _ = workspace.create_job(
                user_id="local-user", session_id=self.session, problem="test",
                idempotency_key=uuid.uuid4().hex, request_digest=uuid.uuid4().hex)
            ids.append(job["job_id"])
            with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
                db.execute("UPDATE workspace_jobs SET status='succeeded' WHERE job_id=?", (ids[-1],))
                db.commit()
        base = f"/api/sessions/{self.session}/memory"
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            store = FaithfulMemoryStore(db)
            record = store.record_observation(
                MemoryScope("run", ids[0], "local-user", self.session),
                {"outcome": "failure", "applicability": {"domain": "algebra"},
                 "versions": {}, "cost": {}, "content": {}},
                provenance={"source_run_id": ids[0]})
            db.commit()
        for source, target in ((ids[0], f"run/{ids[1]}"),
                               (ids[1], f"population/{self.session}")):
            response = self.client.post(
                f"{base}/{target}/imports", headers=self.headers(),
                json={"record_id": record, "source_kind": "run", "source_scope_id": source})
            self.assertEqual(201, response.status_code, response.get_json())
            record = response.get_json()["record_id"]
        response = self.client.put(f"{base}/population/{self.session}/injection",
                                   headers=self.headers(), json={"enabled": True})
        self.assertEqual(200, response.status_code)
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            self.assertEqual([record], [item["record_id"] for item in load_population_memory(
                db, run_id=ids[1], problem_spec={"domain": "algebra"})["observations"]])
        response = self.client.delete(f"{base}/run/{ids[0]}", headers=self.headers())
        self.assertEqual(200, response.status_code)
        history = self.client.get(f"{base}/population/{self.session}").get_json()
        self.assertEqual("observations_only", history["authority"])
        self.assertEqual([record], [item["record_id"] for item in history["observations"]])
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            self.assertEqual([], load_population_memory(
                db, run_id=ids[1], problem_spec={"domain": "algebra"})["observations"])


if __name__ == "__main__":
    unittest.main()
