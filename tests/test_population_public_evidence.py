"""Public Job evidence acceptance for Population dependency and deduplication."""

import json
import traceback
import unittest
import uuid
from unittest.mock import patch

from showcase.solver_harness import population_runtime
from tests import test_star_population_runtime as runtime_fixture


class PopulationPublicEvidenceTests(runtime_fixture.PopulationLoopbackJobTest):
    """Group 3 observations over the existing real-loopback Population Job fixture."""

    def setUp(self):
        super().setUp()
        self.callback_errors = []

    def record_callback_errors(self, callback):
        def wrapped(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except Exception as exc:
                self.callback_errors.append((exc, traceback.format_exc()))
                raise

        return wrapped

    def assert_no_callback_errors(self):
        self.assertEqual([], self.callback_errors, self.callback_errors)

    def persisted_state(self, job_id):
        store = self.app.extensions["loopback_store"]
        with store._lock:
            row = store._connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
            ).fetchone()
        self.assertIsNotNone(row)
        return json.loads(row[0])

    def persisted_solver_events(self, job_id):
        store = self.app.extensions["loopback_store"]
        with store._lock:
            rows = store._connection.execute(
                "SELECT event_json FROM solver_events WHERE run_id=? ORDER BY sequence", (job_id,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def public_evidence(self, job_id):
        response = self.client.get(f"/api/runs/{job_id}/evidence")
        self.assertEqual(200, response.status_code, response.get_json())
        return response.get_json()

    def replace_persisted_state(self, job_id, transform):
        store = self.app.extensions["loopback_store"]
        with store._lock:
            row = store._connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
            ).fetchone()
            self.assertIsNotNone(row)
            state = json.loads(row[0])
            transform(state)
            store._connection.execute(
                "UPDATE solver_states SET state_json=? WHERE run_id=?",
                (json.dumps(state), job_id),
            )
            store._connection.commit()
            return json.loads(
                store._connection.execute(
                    "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
                ).fetchone()[0]
            )

    @staticmethod
    def math_ledgers(state):
        return {
            key: state.get(key, [])
            for key in (
                "verified_results_ledger",
                "accepted_results",
                "obligation_evidence_ledger",
                "obligation_ledger",
            )
        }

    def wait_and_refresh(self, harness, job_id):
        for future in list(harness._population_futures.values()):
            future.result(timeout=10)
        return harness._state_store.get_run(job_id)

    @staticmethod
    def pending_capture(latest):
        return [
            action
            for action in latest["state"]["population"]["actions"].values()
            if action.get("status") == "completed"
            and action.get("accepted") is False
            and action.get("dependencies")
        ]

    def run_after_both_futures(self, job_id):
        """Let all in-flight route futures persist before the normal collect/accept path."""
        original = population_runtime._collect
        waited = False

        def collect_after_both(harness, run):
            nonlocal waited
            if not waited and len(harness._population_futures) >= 2:
                run = self.wait_and_refresh(harness, job_id)
                waited = True
            return original(harness, run)

        with patch.object(
            population_runtime,
            "_collect",
            side_effect=self.record_callback_errors(collect_after_both),
        ):
            self.terminal(job_id, timeout=30)

    def rejection_events(self, job_id):
        return [
            event
            for event in self.persisted_solver_events(job_id)
            if event.get("type") == "population_action_rejected"
        ]

    def test_duplicate_root_gain_keeps_sources_and_costs_but_counts_once(self):
        job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
        self.run_after_both_futures(job_id)
        self.assert_no_callback_errors()
        final = self.job(job_id)
        self.assertEqual("succeeded", final["status"], final)
        roles = [
            context.get("role")
            for _role, context in self.requests
            if context.get("role") in {"reasoner", "step_verifier"}
        ]
        self.assertEqual(2, roles.count("reasoner"), roles)
        self.assertEqual(2, roles.count("step_verifier"), roles)

        state = self.persisted_state(job_id)
        routes = state["population"]["routes"]
        actions = state["population"]["actions"]
        self.assertEqual(2, len(routes), routes)
        self.assertEqual(2, len(actions), actions)
        evidence = state["obligation_evidence_ledger"]
        self.assertEqual(2, len(evidence), evidence)
        self.assertEqual(2, len({item["evidence_id"] for item in evidence}), evidence)
        self.assertEqual(1, len({item["obligation_id"] for item in evidence}), evidence)
        sources = {item["source"] for item in evidence}
        self.assertEqual(2, len(sources), evidence)
        self.assertEqual(set(routes), {source.rsplit(":", 1)[0] for source in sources})
        for action in actions.values():
            self.assertEqual("completed", action["status"], action)
            self.assertEqual(2, action["resource_use"]["http_attempts"], action)
            self.assertEqual(60, action["resource_use"]["tokens"], action)
            self.assertTrue(action["resource_use"]["cost_known"], action)

        report = self.report(job_id)
        solver = report["solver"]["solver"]
        obligations = solver["progress"]["root_obligations"]
        self.assertEqual(1, obligations["covered"], obligations)
        self.assertEqual(len(state["obligation_ledger"]), obligations["total"], obligations)
        self.assertEqual(1, solver["population"]["scheduler"]["verified_gain_count"])
        pack = self.public_evidence(job_id)
        self.assertEqual(solver, pack["solver"]["solver"])
        self.assertEqual(solver, final["result"]["solver"])

    def test_captured_revocation_records_rejection_without_ledger_growth(self):
        self.multi_step_construction = True
        self.both_two_step_routes = True
        self.server_delay = 0
        self.verifier_gate.set()
        population = population_runtime
        original = population._collect
        injected = False
        before_ledgers = {}

        def collect_after_capture(harness, run):
            nonlocal injected
            latest = self.wait_and_refresh(harness, job_id)
            pending = self.pending_capture(latest)
            refreshed = latest
            if pending and not injected:
                injected = True
                action = pending[0]
                dependency = action["dependencies"][0]

                def apply_precondition(state):
                    current = state["population"]["actions"][action["action_id"]]
                    self.assertFalse(current["accepted"])
                    self.assertEqual(action["dependencies"], current["dependencies"])
                    for item in state["verified_results_ledger"]:
                        if item["result_id"] == dependency["result_id"]:
                            item["invalidated"] = True
                            item["valid"] = False

                self.replace_persisted_state(job_id, apply_precondition)
                refreshed = harness._state_store.get_run(job_id)
                before_ledgers.update(self.math_ledgers(refreshed["state"]))
            return original(harness, refreshed)

        with patch.object(
            population, "_collect", side_effect=self.record_callback_errors(collect_after_capture)
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=30)
        self.assert_no_callback_errors()
        rejected = self.rejection_events(job_id)
        self.assertTrue(injected)
        self.assertTrue(rejected)
        self.assertEqual({"adopted_evidence_changed"}, {item.get("reason") for item in rejected})
        self.assertEqual(before_ledgers, self.math_ledgers(self.persisted_state(job_id)))
        pack = self.public_evidence(job_id)
        self.assertTrue(
            any(
                item.get("solver_event_type") == "population_action_rejected"
                for item in pack["timeline"]
            ),
            pack["timeline"],
        )
        self.assertEqual(
            0, self.report(job_id)["solver"]["solver"]["progress"]["root_obligations"]["covered"]
        )
        self.assertEqual(final["status"], self.job(job_id)["status"])

    def test_captured_conflict_records_rejection_without_ledger_growth(self):
        self.multi_step_construction = True
        self.both_two_step_routes = True
        self.server_delay = 0
        self.verifier_gate.set()
        population = population_runtime
        original = population._collect
        injected = False
        before_ledgers = {}

        def collect_after_capture(harness, run):
            nonlocal injected
            latest = self.wait_and_refresh(harness, job_id)
            pending = self.pending_capture(latest)
            refreshed = latest
            if pending and not injected:
                injected = True
                action = pending[0]
                dependency = action["dependencies"][0]

                def apply_precondition(state):
                    current = state["population"]["actions"][action["action_id"]]
                    self.assertFalse(current["accepted"])
                    self.assertEqual(action["dependencies"], current["dependencies"])
                    graph = state["proof_graph"]["snapshots"][-1]
                    graph["propositions"][dependency["proposition_id"]]["conflict"] = True

                self.replace_persisted_state(job_id, apply_precondition)
                refreshed = harness._state_store.get_run(job_id)
                before_ledgers.update(self.math_ledgers(refreshed["state"]))
            return original(harness, refreshed)

        with patch.object(
            population, "_collect", side_effect=self.record_callback_errors(collect_after_capture)
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=30)
        self.assert_no_callback_errors()
        rejected = self.rejection_events(job_id)
        self.assertTrue(injected)
        self.assertTrue(rejected)
        self.assertEqual({"adopted_evidence_changed"}, {item.get("reason") for item in rejected})
        self.assertEqual(before_ledgers, self.math_ledgers(self.persisted_state(job_id)))
        pack = self.public_evidence(job_id)
        self.assertTrue(
            any(
                item.get("solver_event_type") == "population_action_rejected"
                for item in pack["timeline"]
            ),
            pack["timeline"],
        )
        self.assertEqual(
            0, self.report(job_id)["solver"]["solver"]["progress"]["root_obligations"]["covered"]
        )
        self.assertEqual(final["status"], self.job(job_id)["status"])

    def test_unrelated_graph_version_change_allows_real_acceptance(self):
        self.multi_step_construction = True
        self.both_two_step_routes = True
        self.server_delay = 0
        self.verifier_gate.set()
        population = population_runtime
        original = population._collect
        injected = False
        captured = {}

        def collect_after_capture(harness, run):
            nonlocal injected
            latest = self.wait_and_refresh(harness, job_id)
            pending = self.pending_capture(latest)
            refreshed = latest
            if pending and not injected:
                injected = True
                action = pending[0]
                dependency = action["dependencies"][0]
                captured.update(
                    {
                        "action_id": action["action_id"],
                        "dependencies": action["dependencies"],
                    }
                )

                def apply_unrelated_version(state):
                    graph = state["proof_graph"]
                    previous = graph["snapshots"][-1]
                    next_snapshot = json.loads(json.dumps(previous))
                    next_snapshot["graph_version"] = graph["current_version"] + 1
                    next_snapshot["propositions"]["unrelated-public-proof"] = {
                        "id": "unrelated-public-proof",
                        "statement": "unrelated branch",
                        "scope": "problem",
                        "problem_version": state["specification_version"],
                        "status": "supported",
                        "conflict": False,
                        "sources": [],
                    }
                    graph["current_version"] = next_snapshot["graph_version"]
                    graph["snapshots"].append(next_snapshot)
                    self.assertEqual(
                        "supported",
                        next_snapshot["propositions"][dependency["proposition_id"]]["status"],
                    )

                self.replace_persisted_state(job_id, apply_unrelated_version)
                refreshed = harness._state_store.get_run(job_id)
            return original(harness, refreshed)

        with patch.object(
            population, "_collect", side_effect=self.record_callback_errors(collect_after_capture)
        ):
            job_id = self.create_population_job(idempotency_key=str(uuid.uuid4()))
            final = self.terminal(job_id, timeout=30)
        self.assert_no_callback_errors()
        self.assertTrue(injected)
        self.assertTrue(captured)
        state = self.persisted_state(job_id)
        action = state["population"]["actions"][captured["action_id"]]
        self.assertTrue(action["accepted"])
        self.assertEqual(captured["dependencies"], action["dependencies"])
        self.assertEqual([], self.rejection_events(job_id))
        progress = self.report(job_id)["solver"]["solver"]["progress"]
        self.assertEqual(1, progress["root_obligations"]["covered"])
        self.assertEqual(1, progress["population"]["scheduler"]["verified_gain_count"])
        pack = self.public_evidence(job_id)
        self.assertEqual(progress, pack["solver"]["solver"]["progress"])
        self.assertEqual(final["status"], self.job(job_id)["status"])


def load_tests(loader, tests, pattern):
    """Discover only tests defined by the new class, not inherited fixture methods."""
    suite = loader.suiteClass()
    for name, value in PopulationPublicEvidenceTests.__dict__.items():
        if name.startswith("test_") and callable(value):
            suite.addTest(PopulationPublicEvidenceTests(name))
    return suite


if __name__ == "__main__":
    unittest.main()
