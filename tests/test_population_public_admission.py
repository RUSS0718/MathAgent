"""Public Job admission rejection for duplicate routes and actions."""

import copy
import traceback
import unittest
import uuid
from unittest.mock import patch

from showcase.run_budget import RunBudgetLedger
from showcase.solver_harness import population_runtime
from showcase.solver_harness.population_store import PopulationConflict
from showcase.solver_harness.storage import SolverStateStore
from tests import test_star_population_runtime as runtime_fixture


class PopulationPublicAdmissionTests(runtime_fixture.PopulationLoopbackJobTest):
    """Observe rejection at scheduler write boundaries without another API."""

    def setUp(self):
        super().setUp()
        self.callback_errors = []

    def record_callback_errors(self, callback):
        def wrapped(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except PopulationConflict:
                raise
            except Exception as exc:
                self.callback_errors.append((exc, traceback.format_exc()))
                raise

        return wrapped

    @staticmethod
    def stable_budget(snapshot):
        return {key: value for key, value in snapshot.items() if key != "wall_time_seconds"}

    def public_events(self, job_id):
        response = self.client.get(
            f"/api/agent/jobs/{job_id}/events?snapshot=1&last_event_id=0&limit=100"
        )
        self.assertEqual(200, response.status_code, response.get_json())
        events = response.get_json()["events"]
        self.assertGreater(len(events), 0)
        return events

    def public_report(self, job_id):
        response = self.client.get(f"/api/agent/jobs/{job_id}/report")
        self.assertEqual(200, response.status_code, response.get_json())
        return response.get_json()

    def assert_terminal_projection(self, job_id, final):
        self.assertEqual("succeeded", final["status"], final)
        population = self.public_report(job_id)["solver"]["solver"]["population"]
        self.assertEqual(2, sum(population["scheduler"]["route_counts"].values()), population)
        self.assertGreater(len(self.public_events(job_id)), 0)

    def test_public_job_rejects_equivalent_frontier_without_new_budget_event_revision_or_http(self):
        original_command = population_runtime.command
        checks = []

        def reject_equivalent_frontier(harness, run_id, operation, **args):
            run = original_command(harness, run_id, operation, **args)
            if operation != "register_route" or checks:
                return run
            before = copy.deepcopy(run["state"]["population"])
            revision = run["state_revision"]
            events = list(run["events"])
            budget = self.stable_budget(
                RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
            )
            outbound = len(self.requests)
            with self.assertRaisesRegex(PopulationConflict, "duplicate_route_frontier"):
                original_command(
                    harness,
                    run_id,
                    "register_route",
                    route_id="route-equivalent-frontier",
                    frontier_digest=before["routes"][args["route_id"]]["frontier_digest"],
                    snapshot=before["routes"][args["route_id"]]["snapshot"],
                )
            persisted = harness._state_store.get_run(run_id)
            self.assertEqual(revision, persisted["state_revision"])
            self.assertEqual(events, persisted["events"])
            self.assertEqual(before, persisted["state"]["population"])
            self.assertEqual(
                budget,
                self.stable_budget(
                    RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
                ),
            )
            self.assertEqual(outbound, len(self.requests))
            checks.append("duplicate_route_frontier")
            return run

        with patch.object(
            population_runtime,
            "command",
            side_effect=self.record_callback_errors(reject_equivalent_frontier),
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=20)
        self.assertEqual([], self.callback_errors, self.callback_errors)
        self.assertEqual(["duplicate_route_frontier"], checks)
        self.assert_terminal_projection(job_id, final)

    def test_public_job_replays_admitted_action_without_new_budget_event_revision_or_http(self):
        original_command = population_runtime.command
        checks = []

        def replay_admitted_action(harness, run_id, operation, **args):
            run = original_command(harness, run_id, operation, **args)
            if operation != "admit" or checks:
                return run
            before = copy.deepcopy(run["state"]["population"])
            revision = run["state_revision"]
            events = list(run["events"])
            budget = self.stable_budget(
                RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
            )
            outbound = len(self.requests)
            action = before["actions"][args["action_id"]]
            replayed = original_command(
                harness,
                run_id,
                "admit",
                route_id=action["route_id"],
                action_id=action["action_id"],
                reservation=action["reservation"],
                closing_reserve=action["closing_reserve"],
                dependencies=action["dependencies"],
                adopt_evidence=args["adopt_evidence"],
            )
            persisted = harness._state_store.get_run(run_id)
            self.assertEqual(revision, replayed["state_revision"])
            self.assertEqual(revision, persisted["state_revision"])
            self.assertEqual(events, replayed["events"])
            self.assertEqual(events, persisted["events"])
            self.assertEqual(before, replayed["state"]["population"])
            self.assertEqual(before, persisted["state"]["population"])
            self.assertEqual(
                budget,
                self.stable_budget(
                    RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
                ),
            )
            self.assertEqual(outbound, len(self.requests))
            checks.append("replayed_admitted_action")
            return run

        with patch.object(
            population_runtime,
            "command",
            side_effect=self.record_callback_errors(replay_admitted_action),
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=20)
        self.assertEqual([], self.callback_errors, self.callback_errors)
        self.assertEqual(["replayed_admitted_action"], checks)
        self.assert_terminal_projection(job_id, final)

    def test_public_job_cross_process_capacity_race_keeps_one_admission_and_finishes(self):
        import json
        import os
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        from showcase.solver_harness.population_evidence import prepare_adoption

        original_command = population_runtime.command
        race = []
        child = r"""
import json, os, sys, time
from types import SimpleNamespace
from showcase.solver_harness.population_store import PopulationConflict, command
from showcase.solver_harness.storage import SolverStateStore
from showcase.storage import SQLiteStore
database, run_id, owner_json, args_json, ready, barrier, output = sys.argv[1:]
open(ready, "w", encoding="utf-8").close()
while not os.path.exists(barrier):
    time.sleep(0.002)
with SQLiteStore(database) as store:
    harness = SimpleNamespace(
        _state_store=SolverStateStore(store._connection),
        _showcase_store=store,
        _population_owner=json.loads(owner_json),
        _event_observer=None,
    )
    try:
        run = command(harness, run_id, "admit", **json.loads(args_json))
        result = {
            "status": "admitted",
            "revision": run["state_revision"],
            "actions": sorted(run["state"]["population"]["actions"]),
        }
    except PopulationConflict as exc:
        result = {"status": "conflict", "reason": str(exc)}
    with open(output, "w", encoding="utf-8") as stream:
        json.dump(result, stream)
"""

        def race_capacity_one(harness, run_id, operation, **args):
            if operation != "admit" or race:
                return original_command(harness, run_id, operation, **args)
            persisted = harness._state_store.get_run(run_id)
            capacity = persisted["state"]["population_policy"]["capacity"]
            self.assertEqual(1, capacity["max_inflight"])
            self.assertEqual(1, capacity["worker_slots"])
            self.assertEqual("fixture:capacity-one", capacity["evidence_ref"])
            population = persisted["state"]["population"]
            routes = list(population["routes"].values())
            if len(routes) != 2 or population["actions"]:
                return original_command(harness, run_id, operation, **args)
            budget_before = RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
            competitors = []
            for route in routes:
                adoption, dependencies = prepare_adoption(persisted["state"], route["snapshot"])
                candidate = {**route, "snapshot": {**route["snapshot"], **adoption}}
                reservation, closing = population_runtime._estimates(
                    harness, persisted, candidate, runtime_fixture.PROBLEM
                )
                retry = candidate["snapshot"].get("authorized_retry")
                action_id = (
                    f"{route['route_id']}:retry:{retry['new_call_id']}"
                    if isinstance(retry, dict)
                    else f"{route['route_id']}:work:{route.get('revision', 0)}"
                )
                competitors.append(
                    {
                        "route_id": route["route_id"],
                        "action_id": action_id,
                        "reservation": reservation,
                        "closing_reserve": closing,
                        "dependencies": dependencies,
                        "adopt_evidence": True,
                    }
                )
            self.assertEqual(2, len({item["action_id"] for item in competitors}))
            database = harness._state_store._connection.execute("PRAGMA database_list").fetchone()[
                2
            ]
            owner = population["owner"]
            with tempfile.TemporaryDirectory() as directory:
                ready_paths = [str(Path(directory) / f"ready-{i}") for i in range(2)]
                outputs = [str(Path(directory) / f"result-{i}.json") for i in range(2)]
                barrier = str(Path(directory) / "barrier")
                base = [sys.executable, "-c", child, database, run_id, json.dumps(owner)]
                environment = {
                    **os.environ,
                    "PYTHONPATH": os.pathsep.join(
                        [str(Path.cwd()), os.environ.get("PYTHONPATH", "")]
                    ),
                }
                processes = [
                    subprocess.Popen(
                        [*base, json.dumps(item), ready, barrier, output],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env=environment,
                    )
                    for item, ready, output in zip(competitors, ready_paths, outputs)
                ]
                try:
                    deadline = time.monotonic() + 10
                    while not all(Path(path).exists() for path in ready_paths):
                        if time.monotonic() >= deadline:
                            self.fail("admission competitors did not become ready")
                        time.sleep(0.005)
                    Path(barrier).write_text("go", encoding="utf-8")
                    completed = [process.communicate(timeout=15) for process in processes]
                    self.assertTrue(
                        all(process.returncode == 0 for process in processes), completed
                    )
                    results = [
                        json.loads(Path(output).read_text(encoding="utf-8")) for output in outputs
                    ]
                finally:
                    for process in processes:
                        if process.poll() is None:
                            process.kill()
                        process.communicate(timeout=5)
            self.assertEqual(
                ["admitted", "conflict"],
                sorted(item["status"] for item in results),
                results,
            )
            winner = next(item for item in results if item["status"] == "admitted")
            loser = next(item for item in results if item["status"] == "conflict")
            self.assertEqual("population_capacity_exhausted", loser["reason"], loser)
            persisted_after = harness._state_store.get_run(run_id)
            self.assertEqual(1, len(persisted_after["state"]["population"]["actions"]))
            self.assertEqual(
                1,
                sum(
                    event.get("type") == "population_action_admitted"
                    for event in persisted_after["events"]
                ),
            )
            winner_identity = next(
                item for item in competitors if item["action_id"] in winner["actions"]
            )
            budget = self.stable_budget(
                RunBudgetLedger(harness._state_store._connection).snapshot(run_id)
            )
            for field, reserved in (
                ("logical_calls", "model_calls"),
                ("http_attempts", "http_attempts"),
                ("charged_tokens", "tokens"),
            ):
                self.assertEqual(
                    winner_identity["reservation"][reserved],
                    budget[field] - budget_before[field],
                    field,
                )
            loser_identity = next(
                item for item in competitors if item["action_id"] != winner_identity["action_id"]
            )
            ledger = json.loads(
                harness._state_store._connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
                ).fetchone()[0]
            )
            self.assertFalse(
                any(
                    item.get("population_action_id") == loser_identity["action_id"]
                    for item in ledger["actions"]
                )
            )
            race.append(
                {
                    "winner": winner_identity,
                    "loser": next(
                        item
                        for item in competitors
                        if item["action_id"] != winner_identity["action_id"]
                    ),
                    "budget": budget,
                    "persisted": persisted_after,
                }
            )
            return original_command(harness, run_id, operation, **args)

        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        capacity = pipeline.population_config["population_policy"]["capacity"]
        capacity.update(
            max_inflight=1,
            worker_slots=1,
            evidence_ref="fixture:capacity-one",
        )
        with patch.object(
            population_runtime,
            "command",
            side_effect=self.record_callback_errors(race_capacity_one),
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=30)
        self.assertEqual([], self.callback_errors, self.callback_errors)
        self.assertEqual(1, len(race), race)
        self.assert_terminal_projection(job_id, final)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(200, evidence.status_code, evidence.get_json())
        self.assertEqual(
            "delivered",
            evidence.get_json()["solver"]["solver"]["population"]["delivery"]["status"],
        )
        competed = race[0]
        store = self.app.extensions["loopback_store"]
        with store._lock:
            persisted = SolverStateStore(store._connection).get_run(job_id)
        winner_id = competed["winner"]["action_id"]
        loser_id = competed["loser"]["action_id"]
        self.assertIn(winner_id, persisted["state"]["population"]["actions"])
        self.assertNotIn(loser_id, persisted["state"]["population"]["actions"])
        sent_action_ids = {
            call.get("action_id")
            for call in persisted["state"].get("calls", {}).values()
            if call.get("action_id")
            and call.get("status") in {"dispatched", "streaming", "completed", "unknown_outcome"}
        }
        self.assertTrue(sent_action_ids)
        self.assertEqual({winner_id}, sent_action_ids)
        self.assertEqual(1, self.reasoners)
        self.assertEqual(1, self.verifiers)


def load_tests(loader, tests, pattern):
    """Load only tests defined here; inherited runtime cases remain in their module."""
    suite = loader.suiteClass()
    for name, value in PopulationPublicAdmissionTests.__dict__.items():
        if name.startswith("test_") and callable(value):
            suite.addTest(PopulationPublicAdmissionTests(name))
    return suite


if __name__ == "__main__":
    unittest.main()
