"""Public Job acceptance for Population delivery through unknown dependencies."""

from __future__ import annotations

import json
import threading
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from showcase.solver_harness import finalize, population_runtime
from tests.test_star_population_runtime import PopulationLoopbackJobTest


class PopulationPublicUnknownTest(PopulationLoopbackJobTest):
    @contextmanager
    def _wait_for_real_workers(self):
        """Keep the patch through assertions, then wait for all started workers."""
        started, completed = set(), set()
        finished = threading.Condition()
        original = population_runtime._work

        def tracked(*args, **kwargs):
            action_id = args[4]
            with finished:
                started.add(action_id)
            try:
                return original(*args, **kwargs)
            finally:
                with finished:
                    completed.add(action_id)
                    finished.notify_all()

        with patch.object(population_runtime, "_work", side_effect=tracked):
            try:
                yield started, completed
            finally:
                with finished:
                    self.assertTrue(
                        finished.wait_for(lambda: completed == started, timeout=15),
                        {"started": sorted(started), "completed": sorted(completed)},
                    )

    @contextmanager
    def _pause_before_finalization(self):
        """Pause the worker, then reload durable state before finalization."""
        reached, release = threading.Event(), threading.Event()
        original = finalize.run_finalization

        def gated(harness, run, **kwargs):
            if run["state"]["phase"] == "FINAL_GENERATE" and not reached.is_set():
                reached.set()
                if not release.wait(10):
                    raise RuntimeError("finalization barrier timed out")
                run = harness.get_run(run["run_id"])
            return original(harness, run, **kwargs)

        with patch.object(finalize, "run_finalization", side_effect=gated):
            try:
                yield reached, release
            finally:
                release.set()

    def _promote_obligation_review_to_unknown(self, job_id):
        """Counterfactual fault injection using an existing review and its real holds."""
        store = self.app.extensions["loopback_store"]
        with store._lock:
            row = store._connection.execute(
                "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
            ).fetchone()
            state = json.loads(row[0])
            self.assertEqual("FINAL_GENERATE", state["phase"])
            evidence = next(
                item
                for item in state.get("obligation_evidence_ledger", [])
                if item.get("review_call_id")
                and item.get("valid") is not False
                and item.get("invalidated") is not True
            )
            review_id = evidence["review_call_id"]
            call = state["calls"][review_id]
            action = state["population"]["actions"][call["action_id"]]
            self.assertEqual("completed", call["status"])
            self.assertEqual("completed", action["status"])
            ledger = json.loads(
                store._connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)
                ).fetchone()[0]
            )
            logical = [
                item
                for item in ledger["actions"]
                if item.get("kind") == "logical" and item.get("solver_call_id") == review_id
            ]
            physical = [
                item
                for item in ledger["actions"]
                if item.get("kind") == "http"
                and item.get("population_action_id") == action["action_id"]
                and item.get("status") != "pre_reserved"
            ]
            self.assertTrue(logical, self._diagnostic(state, job_id))
            self.assertTrue(physical, self._diagnostic(state, job_id))
            call["status"] = "unknown_outcome"
            action["status"] = "unknown"
            action["settlement_status"] = "pending"
            state["population"]["routes"][action["route_id"]]["status"] = "unknown"
            store._connection.execute(
                "UPDATE solver_states SET state_json=? WHERE run_id=?",
                (json.dumps(state, ensure_ascii=False), job_id),
            )
            store._connection.commit()
            return action["action_id"], review_id, action["reservation"]

    def _diagnostic(self, state=None, job_id=None):
        summary = {"job_id": job_id}
        if state is not None:
            summary.update(
                {
                    "phase": state.get("phase"),
                    "reason": state.get("result_reason"),
                    "actions": [
                        (item.get("action_id"), item.get("status"), item.get("settlement_status"))
                        for item in state.get("population", {}).get("actions", {}).values()
                    ],
                    "evidence": [
                        (item.get("review_call_id"), item.get("valid"), item.get("invalidated"))
                        for item in state.get("obligation_evidence_ledger", [])
                    ],
                }
            )
        if job_id is not None:
            job = self.job(job_id)
            summary.update(
                {
                    "job_status": job.get("status"),
                    "error": job.get("error"),
                    "delivery": ((job.get("result") or {}).get("solver") or {})
                    .get("population", {})
                    .get("delivery"),
                    "reserved_tokens": ((job.get("result") or {}).get("budget") or {}).get(
                        "reserved_tokens"
                    ),
                }
            )
        return summary

    def _views(self, job_id):
        report = self.report(job_id)
        evidence = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        return report, evidence

    def _assert_terminal_resume_rejected(self, job_id, requests_before):
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers()
        )
        self.assertEqual(409, response.status_code, response.get_json())
        payload = response.get_json()
        self.assertFalse(payload["success"], payload)
        self.assertIn(payload["code"], {"job_not_resumable", "star_recovery_terminal"}, payload)
        self.assertEqual(requests_before, len(self.requests))
        return payload

    def _population_call_ids(self, job_id):
        state = self.state(job_id)
        return {
            call_id
            for call_id, call in state.get("calls", {}).items()
            if call.get("action_id") in state.get("population", {}).get("actions", {})
        }

    def test_unknown_dependency_rejects_delivery_through_public_job(self):
        self.provider.timeout = 12
        self.server_delay = 5
        self.verifier_gate.set()
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.population_config["population_policy"]["request_timeout_seconds"] = 12
        with self._wait_for_real_workers():
            with self._pause_before_finalization() as (reached, release):
                job_id = self.create_population_job()
                self.assertTrue(reached.wait(20), self._diagnostic(job_id=job_id))
                action_id, review_id, reservation = self._promote_obligation_review_to_unknown(
                    job_id
                )
                calls_before = self._population_call_ids(job_id)
                release.set()
                final = self.terminal(job_id, timeout=25)

            self.assertEqual(
                "failed", final["status"], self._diagnostic(self.state(job_id), job_id)
            )
            self.assertTrue(calls_before.issubset(self._population_call_ids(job_id)))
            report, evidence = self._views(job_id)
            population = report["solver"]["solver"]["population"]
            self.assertEqual("not_delivered", population["delivery"]["status"])
            self.assertEqual(
                "population_unknown_proof_dependency", population["delivery"]["reason"]
            )
            self.assertEqual(
                "not_delivered", evidence["solver"]["solver"]["population"]["delivery"]["status"]
            )
            state = self.state(job_id)
            self.assertEqual(reservation, state["population"]["actions"][action_id]["reservation"])
            self.assertIn(
                review_id,
                [item.get("review_call_id") for item in state["obligation_evidence_ledger"]],
            )
            requests_before = len(self.requests)
            self._assert_terminal_resume_rejected(job_id, requests_before)
            after, evidence_after = self._views(job_id)
            self.assertEqual(
                reservation, self.state(job_id)["population"]["actions"][action_id]["reservation"]
            )
            self.assertEqual(
                report["budget"]["reserved_tokens"], after["budget"]["reserved_tokens"]
            )
            self.assertEqual(
                after["solver"]["solver"]["population"],
                evidence_after["solver"]["solver"]["population"],
            )

    def test_independent_route_delivers_before_late_unknown_without_auto_retry(self):
        self.provider.timeout = 2
        self.server_delay = 5
        self.verifier_gate.set()
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.population_config["population_policy"]["request_timeout_seconds"] = 2
        with self._wait_for_real_workers():
            job_id = self.create_population_job()
            final = self.terminal(job_id, timeout=25)
            self.assertEqual(
                "succeeded", final["status"], self._diagnostic(self.state(job_id), job_id)
            )
            self.assertEqual("1+1=2 by addition.", final["result"]["final_response"])
            report, evidence = self._views(job_id)
            self.assertEqual(
                "delivered", report["solver"]["solver"]["population"]["delivery"]["status"]
            )
            self.assertEqual(
                "delivered", evidence["solver"]["solver"]["population"]["delivery"]["status"]
            )
            self.wait_for(
                lambda: any(
                    item.get("status") == "unknown"
                    for item in self.state(job_id)["population"]["actions"].values()
                ),
                timeout=15,
            )

            state = self.state(job_id)
            unknown = next(
                item
                for item in state["population"]["actions"].values()
                if item.get("status") == "unknown"
            )
            reservation = unknown["reservation"]
            calls_before = self._population_call_ids(job_id)
            self.assertGreater(report["budget"]["reserved_tokens"], 0)
            ledger = json.loads(
                self.app.extensions["loopback_store"]
                ._connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)
                )
                .fetchone()[0]
            )
            self.assertTrue(
                any(
                    item.get("population_action_id") == unknown["action_id"]
                    and item.get("status") in {"reserved", "unknown", "error"}
                    for item in ledger["actions"]
                    if item.get("kind") == "http"
                )
            )
            requests_before = len(self.requests)
            self._assert_terminal_resume_rejected(job_id, requests_before)
            self.assertTrue(calls_before.issubset(self._population_call_ids(job_id)))
            self.assertEqual(
                reservation,
                self.state(job_id)["population"]["actions"][unknown["action_id"]]["reservation"],
            )
            after, evidence_after = self._views(job_id)
            self.assertEqual(
                "delivered", after["solver"]["solver"]["population"]["delivery"]["status"]
            )
            self.assertEqual(
                after["solver"]["solver"]["population"],
                evidence_after["solver"]["solver"]["population"],
            )

    def state(self, job_id):
        row = (
            self.app.extensions["loopback_store"]
            ._connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,))
            .fetchone()
        )
        self.assertIsNotNone(row)
        return json.loads(row[0])


def load_tests(loader, standard_tests, pattern):
    """Load only tests declared here, never the inherited loopback fixture suite."""
    suite = unittest.TestSuite()
    for name in sorted(PopulationPublicUnknownTest.__dict__):
        if name.startswith("test_"):
            suite.addTest(PopulationPublicUnknownTest(name))
    return suite


if __name__ == "__main__":
    unittest.main()
