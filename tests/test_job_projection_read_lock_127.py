"""Public Job projections must not keep SQLite readers blocking progress commits."""

import threading
import unittest
from unittest.mock import patch

from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class JobProjectionReadLockTest(StarJobFixture, unittest.TestCase):
    def test_projecting_a_snapshot_does_not_block_another_job_progress(self):
        self.open_star([SOLVED, POLISH, ACCEPT])
        observed_job = self.create_job()
        self.assertEqual("succeeded", self.terminal(observed_job)["status"])
        service = self.app.extensions["showcase_workspace_service"]
        owner = service.store._connection.execute(
            "SELECT user_id FROM workspace_jobs WHERE job_id=?", (observed_job,)
        ).fetchone()[0]
        pending, _ = service.store.create_job(
            user_id=owner, session_id=self.session, problem="2+2",
            idempotency_key="projection-contention", request_digest="digest",
            execution_mode="star_limited", solver_identity={"solver_mode": "star_limited"},
        )
        service.store.start_job(pending["job_id"], execution_mode="star_limited")
        entered, release = threading.Event(), threading.Event()
        results, errors = [], []
        from showcase.star_product_pipeline import projection

        def slow_projection(*args, **kwargs):
            entered.set()
            if not release.wait(3):
                raise AssertionError("projection was not released")
            return projection(*args, **kwargs)

        def read():
            try:
                results.append(service.get_job(observed_job, owner))
            except BaseException as exc:
                errors.append(exc)

        with patch("showcase.star_product_pipeline.projection", side_effect=slow_projection):
            reader = threading.Thread(target=read)
            reader.start()
            try:
                self.assertTrue(entered.wait(2))
                service.store._connection.execute("PRAGMA busy_timeout=10")
                service.store.append_event(pending["job_id"], {
                    "type": "solver_progress", "solver_event_id": "parallel-progress",
                    "solver": {"state_revision": 1},
                })
            finally:
                release.set()
                reader.join(4)
        self.assertEqual([], errors)
        self.assertEqual("succeeded", results[0]["status"])
        self.assertEqual(1, service.store.get_job(pending["job_id"], owner)["result"]["solver"]["state_revision"])


if __name__ == "__main__":
    unittest.main()
