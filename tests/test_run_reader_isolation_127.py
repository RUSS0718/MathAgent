"""Run reads must not share a workspace writer's uncommitted connection."""

import json
import unittest
from concurrent.futures import ThreadPoolExecutor

from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class RunReaderIsolationTest(StarJobFixture, unittest.TestCase):
    def test_public_run_reader_sees_only_committed_workspace_state(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        run_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(run_id)["status"])
        runs = self.app.extensions["showcase_run_service"]
        workspace = self.app.extensions["showcase_workspace_service"]
        before = runs.get_run(run_id)
        connection = workspace.store._connection
        with workspace.store._lock:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT snapshot_json FROM runs WHERE run_id=?", (run_id,)).fetchone()
                pending = json.loads(row[0])
                pending["final_response"] = "uncommitted-answer"
                connection.execute("UPDATE runs SET snapshot_json=? WHERE run_id=?", (json.dumps(pending), run_id))
                with ThreadPoolExecutor(max_workers=1) as reader:
                    observed = reader.submit(runs.get_run, run_id).result(timeout=2)
                self.assertEqual(before["final_response"], observed["final_response"])
            finally:
                connection.rollback()
        self.assertEqual(before["final_response"], runs.get_run(run_id)["final_response"])
        self.assertIs(workspace.budget_ledger.connection, workspace.store._connection)
        self.assertIs(workspace.budget_ledger.connection_lock, workspace.store._lock)


if __name__ == "__main__":
    unittest.main()
