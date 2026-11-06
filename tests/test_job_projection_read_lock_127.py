"""Public Job projections must not keep SQLite readers blocking progress commits."""

import json
import threading
import unittest
from unittest.mock import patch

from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture


class JobProjectionReadLockTest(StarJobFixture, unittest.TestCase):
    def test_job_projection_keeps_tool_recovery_events_without_loading_activity_history(self):
        """Public recovery keeps orphan tool dispatches and omits activity history."""
        self.open_star([SOLVED, POLISH, ACCEPT])
        job_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        service = self.app.extensions["showcase_workspace_service"]
        connection = service.store._connection
        latest = connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) FROM solver_events WHERE run_id=?", (job_id,)
        ).fetchone()[0]
        connection.executemany(
            "INSERT INTO solver_events(run_id,sequence,event_id,state_revision,event_json,created_at) "
            "VALUES(?,?,?,?,?,?)",
            [
                (
                    job_id,
                    latest + index,
                    f"activity-{index}",
                    index,
                    json.dumps({"run_id": job_id, "event_id": f"activity-{index}",
                                "state_revision": index, "type": "call_activity"}),
                    "2026-11-05T00:00:00+00:00",
                )
                for index in range(1, 101)
            ] + [
                (
                    job_id,
                    latest + 101,
                    "tool-probe:dispatch",
                    101,
                    json.dumps({"run_id": job_id, "event_id": "tool-probe:dispatch",
                                "state_revision": 101, "type": "tool_dispatched"}),
                    "2026-11-05T00:00:00+00:00",
                )
            ] + [
                (
                    job_id,
                    latest + 102,
                    "tool-complete:dispatch",
                    102,
                    json.dumps({"run_id": job_id, "event_id": "tool-complete:dispatch",
                                "state_revision": 102, "type": "tool_dispatched"}),
                    "2026-11-05T00:00:00+00:00",
                ),
                (
                    job_id,
                    latest + 103,
                    "tool-complete",
                    103,
                    json.dumps({"run_id": job_id, "event_id": "tool-complete",
                                "state_revision": 103, "type": "tool_receipt"}),
                    "2026-11-05T00:00:00+00:00",
                ),
            ],
        )
        connection.commit()
        from showcase.star_product_pipeline import projection

        observed = []

        def capture(run, **kwargs):
            observed.append(run)
            return projection(run, **kwargs)

        owner = connection.execute(
            "SELECT user_id FROM workspace_jobs WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        with patch("showcase.star_product_pipeline.projection", side_effect=capture):
            result = service.get_job(job_id, owner)

        self.assertEqual(
            [{"call_id": "tool-probe", "status": "unknown_outcome"}],
            result["result"]["solver"]["recovery"]["unknown_tools"],
        )
        self.assertEqual(
            ["tool_dispatched", "tool_dispatched", "tool_receipt"],
            [item["type"] for item in observed[0]["events"]],
        )
        from showcase.star_product_projection import persisted_solver

        full, _ = persisted_solver(connection, job_id)
        self.assertEqual(100, sum(item["type"] == "call_activity" for item in full["events"]))

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
