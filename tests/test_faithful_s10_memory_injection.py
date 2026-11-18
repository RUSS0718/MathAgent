"""Population memory is scoped, provenance-checked, and advisory only."""

import json
import sqlite3
import unittest

from showcase.solver_harness.faithful_memory_injection import load_population_memory


class FaithfulS10MemoryInjectionTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """
            CREATE TABLE chat_sessions(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
            CREATE TABLE workspace_jobs(job_id TEXT PRIMARY KEY, session_id TEXT, user_id TEXT, status TEXT);
            CREATE TABLE faithful_memory_entries(
                record_id TEXT PRIMARY KEY, owner_id TEXT, workspace_id TEXT,
                scope_kind TEXT, scope_id TEXT, entry_type TEXT, state TEXT,
                payload_json TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE faithful_memory_scope_controls(
                owner_id TEXT, workspace_id TEXT, scope_kind TEXT, scope_id TEXT,
                enabled INTEGER, updated_at TEXT,
                PRIMARY KEY(owner_id, workspace_id, scope_kind, scope_id)
            );
            CREATE TABLE faithful_memory_injection_controls(
                owner_id TEXT, workspace_id TEXT, scope_kind TEXT, scope_id TEXT,
                enabled INTEGER, updated_at TEXT,
                PRIMARY KEY(owner_id, workspace_id, scope_kind, scope_id)
            );
            """
        )
        self.add_session("session-a", "user-a")
        self.add_run("current-run", "session-a", "user-a")
        self.enable_scope("session-a", "user-a")

    def tearDown(self):
        self.db.close()

    def add_session(self, session_id, user_id):
        self.db.execute("INSERT OR REPLACE INTO chat_sessions VALUES (?,?)", (session_id, user_id))

    def add_run(self, run_id, session_id, user_id, status="succeeded"):
        self.add_session(session_id, user_id)
        self.db.execute(
            "INSERT OR REPLACE INTO workspace_jobs VALUES (?,?,?,?)",
            (run_id, session_id, user_id, status),
        )

    def enable_scope(self, session_id, user_id):
        self.db.execute(
            "INSERT OR REPLACE INTO faithful_memory_injection_controls VALUES (?,?,?,?,1,'now')",
            (user_id, session_id, "population", session_id),
        )

    def add_entry(self, record_id, *, session_id="session-a", owner_id="user-a", payload=None, state="active"):
        payload = payload or {
            "observation": {
                "outcome": "success",
                "applicability": {"domain": "Algebra"},
                "versions": {"plan": 2},
                "cost": {"tokens": 12},
                "content": "Try factoring first",
            },
            "provenance": {"source_run_id": "current-run"},
        }
        observation = dict(payload.get("observation", {}))
        observation.setdefault("outcome", "success")
        observation.setdefault("applicability", {"domain": "Algebra"})
        observation.setdefault("versions", {})
        observation.setdefault("cost", {})
        observation.setdefault("content", {})
        payload = {**payload, "observation": observation}
        self.db.execute(
            "INSERT INTO faithful_memory_entries VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                record_id,
                owner_id,
                session_id,
                "population",
                session_id,
                "observation",
                state,
                json.dumps(payload),
                "now",
                "now",
            ),
        )

    def load(self, spec=None):
        return load_population_memory(self.db, run_id="current-run", problem_spec=spec)

    def test_returns_only_same_domain_entries_with_advisory_allowlist(self):
        self.add_entry(
            "match",
            payload={
                "observation": {
                    "outcome": "success",
                    "applicability": {"domain": "  aLgEbRa  "},
                    "versions": {"plan": 2},
                    "cost": {"tokens": 12},
                    "content": {"route_summary": "Try factoring first"},
                    "proof": {"verified": True},
                },
                "provenance": {"source_run_id": "current-run"},
                "policy": {"authority": "proof"},
            },
        )
        self.add_run("cross-domain-run", "session-a", "user-a")
        self.add_entry(
            "other-domain",
            payload={
                "observation": {"outcome": "success", "applicability": {"domain": "geometry"}},
                "provenance": {"source_run_id": "cross-domain-run"},
            },
        )

        memory = self.load({"domain": "Algebra"})

        self.assertEqual("population-memory-injection-v1", memory["schema"])
        self.assertEqual("available", memory["status"])
        self.assertEqual("Algebra", memory["domain"])
        self.assertEqual("faithful_memory_entries", memory["source"])
        self.assertEqual(["match"], [item["record_id"] for item in memory["observations"]])
        item = memory["observations"][0]
        self.assertEqual({"route_summary": "Try factoring first"}, item["content"])
        self.assertEqual({"plan": 2}, item["versions"])
        self.assertEqual({"tokens": 12}, item["cost"])
        self.assertEqual({"source_run_id": "current-run"}, item["provenance"])
        self.assertEqual("advisory_only", item["authority"])
        self.assertEqual("requires_current_run_review", item["review_status"])
        self.assertEqual("candidate_guidance", item["use"])
        self.assertNotIn("proof", item)
        self.assertNotIn("policy", memory)

    def test_failures_and_unknown_outcomes_are_diagnostic_only(self):
        for record_id, outcome in (("failed", "failure"), ("unknown", "unknown")):
            self.add_entry(
                record_id,
                payload={
                    "observation": {"outcome": outcome, "applicability": {"domain": "Algebra"}},
                    "provenance": {"source_run_id": "current-run"},
                },
            )

        observations = self.load({"domain": "Algebra"})["observations"]

        self.assertEqual(["diagnostic_only", "diagnostic_only"], [item["use"] for item in observations])

    def test_missing_domain_or_disabled_scope_returns_no_memory(self):
        self.add_entry("entry", payload={
            "observation": {"outcome": "success", "applicability": {"domain": "Algebra"}},
            "provenance": {"source_run_id": "current-run"},
        })
        self.assertEqual(1, len(self.load({"domain": "Algebra"})["observations"]))
        self.assertEqual([], self.load(None)["observations"])
        self.db.execute(
            "INSERT INTO faithful_memory_scope_controls VALUES (?,?,?,?,0,'now')",
            ("user-a", "session-a", "population", "session-a"),
        )
        self.assertEqual([], self.load({"domain": "Algebra"})["observations"])

    def test_direct_entries_require_a_run_owned_by_this_user_and_session(self):
        self.add_run("other-session-run", "session-b", "user-a")
        self.add_run("foreign-user-run", "session-c", "user-b")
        for record_id, source_run in (
            ("other-session", "other-session-run"),
            ("foreign-user", "foreign-user-run"),
            ("forged", "missing-run"),
        ):
            self.add_entry(
                record_id,
                payload={
                    "observation": {"outcome": "success", "applicability": {"domain": "Algebra"}},
                    "provenance": {"source_run_id": source_run},
                },
            )

        self.assertEqual([], self.load({"domain": "Algebra"})["observations"])

    def test_in_progress_source_run_is_not_eligible_memory(self):
        self.add_run("active-source-run", "session-a", "user-a", status="running")
        self.add_entry(
            "active-source-observation",
            payload={
                "observation": {"outcome": "success", "applicability": {"domain": "Algebra"}},
                "provenance": {"source_run_id": "active-source-run"},
            },
        )

        self.assertEqual([], self.load({"domain": "Algebra"})["observations"])

    def test_imports_require_matching_active_source_scope_and_original_run(self):
        self.add_run("source-run", "source-session", "user-a")
        self.enable_scope("source-session", "user-a")
        source_payload = {
            "observation": {"outcome": "success", "applicability": {"domain": "Algebra"}},
            "provenance": {"source_run_id": "source-run"},
        }
        self.add_entry("source-record", session_id="source-session", payload=source_payload)

        good_provenance = {
            "source_run_id": "source-run",
            "imported_from": {
                "record_id": "source-record",
                "scope": {
                    "kind": "population",
                    "scope_id": "source-session",
                    "owner_id": "user-a",
                    "workspace_id": "source-session",
                },
            },
            "original_provenance": {"source_run_id": "source-run"},
            "imported_by": "user-a",
        }
        self.add_entry(
            "valid-import",
            payload={
                "observation": source_payload["observation"],
                "provenance": good_provenance,
            },
        )
        bad_scope = json.loads(json.dumps(good_provenance))
        bad_scope["imported_from"]["scope"]["owner_id"] = "user-b"
        self.add_entry(
            "forged-import",
            payload={"observation": source_payload["observation"], "provenance": bad_scope},
        )
        self.add_entry(
            "inactive-source",
            session_id="source-session",
            state="revoked",
            payload=source_payload,
        )
        inactive_provenance = json.loads(json.dumps(good_provenance))
        inactive_provenance["imported_from"]["record_id"] = "inactive-source"
        self.add_entry(
            "inactive-import",
            payload={"observation": source_payload["observation"], "provenance": inactive_provenance},
        )
        wrong_run = json.loads(json.dumps(good_provenance))
        wrong_run["original_provenance"]["source_run_id"] = "current-run"
        self.add_entry(
            "wrong-run-import",
            payload={"observation": source_payload["observation"], "provenance": wrong_run},
        )
        altered_copy = json.loads(json.dumps(source_payload["observation"]))
        altered_copy["content"] = "Changed after import"
        self.add_entry(
            "altered-import",
            payload={"observation": altered_copy, "provenance": good_provenance},
        )

        observations = self.load({"domain": "Algebra"})["observations"]

        self.assertEqual(["valid-import"], [item["record_id"] for item in observations])
        self.assertEqual("source-record", observations[0]["provenance"]["imported_from"]["record_id"])


if __name__ == "__main__":
    unittest.main()
