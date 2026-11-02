"""Persistence contract tests for the public Solver Harness seam."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from showcase.solver_harness import (
    SolverHarness,
    SolverIdentityError,
    SolverRunNotFoundError,
    SolverValidationError,
)
from showcase.storage import SQLiteStore


class SolverHarnessPersistenceTest(unittest.TestCase):
    def test_run_state_events_and_revision_survive_harness_recreation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            config = {"profile": "showcase_mvp", "max_explore_rounds": 2}
            first = SolverHarness(database_path=database_path, config=config)
            metadata = {"run_id": "solver-recovery", "token": "SECRET_METADATA"}
            created = first.solve("计算 1 + 1", metadata)
            self.assertEqual(
                created,
                first.solve("计算 1 + 1", metadata),
            )
            self.assertNotIn("计算 1 + 1", repr(created))
            self.assertNotIn("SECRET_METADATA", repr(created))
            first.close()

            second = SolverHarness(database_path=database_path, config=config)
            self.assertEqual(
                created,
                second.get_run("solver-recovery", problem="计算 1 + 1"),
            )
            self.assertEqual(0, created["state"]["state_revision"])
            self.assertEqual("solver-recovery", created["state"]["run_id"])
            self.assertEqual(1, len(created["events"]))
            self.assertEqual(0, created["events"][0]["state_revision"])
            self.assertIsNone(created["state"]["candidate_registry"])
            self.assertIsNone(created["state"]["best_effort_decision"])
            self.assertIsNone(created["state"]["finalization_reason"])
            second.close()

    def test_run_identity_rejects_problem_and_config_mismatches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            first = SolverHarness(database_path=database_path, config={"mode": "offline"})
            first.solve("原始题目", {"run_id": "solver-identity"})
            first.close()

            same_config = SolverHarness(database_path=database_path, config={"mode": "offline"})
            with self.assertRaises(SolverIdentityError):
                same_config.solve("不同题目", {"run_id": "solver-identity"})
            with self.assertRaises(SolverIdentityError):
                same_config.get_run("solver-identity", problem="不同题目")
            with self.assertRaises(SolverRunNotFoundError):
                same_config.get_run("missing-run")
            same_config.close()

            different_config = SolverHarness(
                database_path=database_path,
                config={"mode": "different"},
            )
            with self.assertRaises(SolverIdentityError):
                different_config.get_run("solver-identity")
            different_config.close()

    def test_solver_state_does_not_change_product_run_snapshot_or_events(self) -> None:
        from showcase.run_service import RunService

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            product = RunService(database_path=database_path)
            product_run = product.create_run({"problem": "产品 Run"})
            product_before = product.get_run(product_run["run_id"])
            events_before = product.get_events(product_run["run_id"])

            solver = SolverHarness(database_path=database_path, config={"mode": "offline"})
            solver.solve("Solver Run", {"run_id": "solver-separate"})

            self.assertEqual(product_before, product.get_run(product_run["run_id"]))
            self.assertEqual(events_before, product.get_events(product_run["run_id"]))
            solver.close()
            product.close()

    def test_harness_can_use_the_existing_showcase_store_connection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "showcase.sqlite3"
            store = SQLiteStore(database_path)
            product_snapshot = {"run_id": "product-run", "status": "COMPLETED"}
            store.save_run(product_snapshot)

            harness = SolverHarness(store=store)
            solver_snapshot = harness.solve("Solver Run", {"run_id": "solver-shared"})

            self.assertEqual(product_snapshot, store.get_run("product-run"))
            self.assertEqual(solver_snapshot, harness.get_run("solver-shared"))
            harness.close()
            store.save_run({"run_id": "still-open", "status": "COMPLETED"})
            store.close()

    def test_run_id_is_validated_and_generated_at_the_api_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            harness = SolverHarness(database_path=Path(directory) / "showcase.sqlite3")
            for run_id in ("", "  ", 42):
                with self.assertRaises(SolverValidationError):
                    harness.solve("题目", {"run_id": run_id})
            with self.assertRaises(SolverValidationError):
                harness.get_run("  ")

            generated = harness.solve("题目")
            self.assertTrue(generated["run_id"].startswith("solver_"))
            self.assertEqual(generated["run_id"], generated["state"]["run_id"])
            harness.close()


if __name__ == "__main__":
    unittest.main()
