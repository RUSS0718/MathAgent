"""Contracts for scoped, advisory Solver Harness memory persistence."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope


def _scope(kind="run", scope_id="run-1", owner_id="user-1", workspace_id="workspace-1"):
    return MemoryScope(
        kind=kind,
        scope_id=scope_id,
        owner_id=owner_id,
        workspace_id=workspace_id,
    )


def _observation(outcome="success"):
    return {
        "outcome": outcome,
        "applicability": {"domain": "rationals", "target_kind": "polynomial_identity"},
        "versions": {"graph": 4, "plan": 2},
        "cost": {"elapsed_seconds": 0.7, "provider_calls": 0},
        "content": {"route_summary": "normalize both sides before expansion"},
    }


class FaithfulMemoryCoreTest(unittest.TestCase):
    def test_initialization_does_not_commit_caller_transaction(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE caller_state (value TEXT)")
        connection.execute("INSERT INTO caller_state VALUES ('pending')")
        FaithfulMemoryStore(connection)
        connection.rollback()
        self.assertEqual([], connection.execute("SELECT value FROM caller_state").fetchall())
        connection.close()

    def test_run_and_population_observations_are_scoped_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            first_connection = sqlite3.connect(path)
            first = FaithfulMemoryStore(first_connection)
            record_id = first.record_observation(
                _scope(),
                _observation(),
                provenance={"source_run_id": "run-1", "source_state_revision": 4},
            )
            first_connection.close()

            second_connection = sqlite3.connect(path)
            second = FaithfulMemoryStore(second_connection)
            records = second.list_observations(_scope())
            self.assertEqual([record_id], [item["record_id"] for item in records])
            self.assertEqual("success", records[0]["observation"]["outcome"])
            self.assertEqual("historical_observation", records[0]["authority"])
            self.assertEqual("advisory", records[0]["trust"])
            for key in ("proof", "grade", "verified_gain", "policy_change"):
                self.assertNotIn(key, records[0])
            self.assertEqual([], second.list_observations(_scope(scope_id="another-run")))
            self.assertEqual(
                [], second.list_observations(_scope(owner_id="other-user"))
            )
            second_connection.close()

    def test_policy_version_is_recorded_as_source_metadata(self):
        connection = sqlite3.connect(":memory:")
        store = FaithfulMemoryStore(connection)
        observation = _observation()
        observation["versions"]["policy_version"] = "policy-v1"
        store.record_observation(
            _scope(), observation, provenance={"source_run_id": "run-1"}
        )
        self.assertEqual(
            "policy-v1",
            store.list_observations(_scope())[0]["observation"]["versions"]["policy_version"],
        )
        connection.close()

    def test_observation_cannot_smuggle_proof_or_policy_authority(self):
        connection = sqlite3.connect(":memory:")
        store = FaithfulMemoryStore(connection)
        for field, value in (("verified_gain", 1), ("proof", {"grade": "L2"}),
                             ("policy_change", {"policy_version": 2})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                store.record_observation(
                    _scope(),
                    {**_observation(), field: value},
                    provenance={"source_run_id": "run-1"},
                )
        connection.close()

    def test_cross_scope_import_is_explicit_and_records_origin(self):
        connection = sqlite3.connect(":memory:")
        store = FaithfulMemoryStore(connection)
        source_scope = _scope()
        population_scope = _scope(kind="population", scope_id="session-1")
        record_id = store.record_observation(
            source_scope,
            _observation("unknown"),
            provenance={"source_run_id": "run-1", "source_state_revision": 4},
        )

        imported_id = store.import_observation(
            record_id, population_scope, actor_id="user-1"
        )
        imported = store.list_observations(population_scope)[0]
        self.assertEqual(imported_id, imported["record_id"])
        self.assertEqual("unknown", imported["observation"]["outcome"])
        self.assertEqual(record_id, imported["provenance"]["imported_from"]["record_id"])
        self.assertEqual("user-1", imported["provenance"]["imported_by"])
        with self.assertRaises(ValueError):
            store.import_observation(
                record_id,
                _scope(kind="population", scope_id="foreign", workspace_id="other-workspace"),
                actor_id="user-1",
            )
        connection.close()

    def test_disable_and_clear_hide_records_but_keep_audit_tombstones(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "memory.sqlite3"
            connection = sqlite3.connect(path)
            store = FaithfulMemoryStore(connection)
            scope = _scope(kind="population", scope_id="session-1")
            first_id = store.record_observation(
                scope, _observation(), provenance={"source_run_id": "run-1"}
            )
            store.disable_scope(scope, actor_id="user-1")
            self.assertEqual([], store.list_observations(scope))
            store.enable_scope(scope, actor_id="user-1")
            store.record_observation(
                scope, _observation("failure"), provenance={"source_run_id": "run-2"}
            )
            store.clear_scope(scope, actor_id="user-1")
            self.assertEqual([], store.list_observations(scope))
            events = store.list_audit_events(scope)
            self.assertIn("scope_disabled", [item["event"] for item in events])
            self.assertIn("scope_cleared", [item["event"] for item in events])
            self.assertIn(first_id, [item.get("record_id") for item in events])
            connection.close()

            reopened = sqlite3.connect(path)
            recovered = FaithfulMemoryStore(reopened)
            events = recovered.list_audit_events(scope)
            self.assertIn("scope_disabled", [item["event"] for item in events])
            self.assertIn("scope_cleared", [item["event"] for item in events])
            self.assertEqual([], recovered.list_observations(scope))
            reopened.close()


if __name__ == "__main__":
    unittest.main()
