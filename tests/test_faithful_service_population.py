"""Ordinary submission selects actual routes under the original Job budget."""

import threading
import unittest
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.star_product_config import CORE_FEATURES
from tests.star_product_support import StarJobFixture
from tests.test_star_population_runtime import CAPACITY, PROBLEM, ROOT_ID, SPEC


class FaithfulPopulationJobTest(StarJobFixture, unittest.TestCase):
    def run_plain_submission(self, *, runtime=7200, timeout=15, capacity=CAPACITY,
                             selection_mode="population", multi_step=False, fault=None, modes=None, step_count=3, job_timeout=20):
        entered = threading.Barrier(2)
        concurrent = []
        failed_once = set()

        decisions = iter(modes or ["population", "serial"] if selection_mode == "serial" else modes or ["serial"])

        def provider(request):
            role = request["role"]
            if role == "problem_intake":
                spec = deepcopy(SPEC)
                if multi_step:
                    spec["root_obligations"] = [{**spec["root_obligations"][0],
                        "obligation_id": f"root:result-{i}"} for i in range(step_count)]
                return spec
            if role == "planner":
                plan = {"version": 1, "steps": [{
                    "step_id": "direct", "title": "Direct", "objective": PROBLEM,
                    "method_id": "direct", "obligation_ids": [ROOT_ID],
                    "auxiliary_goal_ids": [],
                }]}
                if multi_step:
                    plan["steps"] = [{**plan["steps"][0], "step_id": f"direct-{i}",
                                      "depends_on": [f"direct-{i-1}"] if i else [],
                                      "obligation_ids": [f"root:result-{i}"]}
                                     for i in range(step_count)]
                alternative = deepcopy(plan)
                if multi_step:
                    alternative["steps"] = [{**step, "step_id": f"construction-{i}",
                        "method_id": "construction", "depends_on": [f"construction-{i-1}"] if i else []}
                        for i, step in enumerate(alternative["steps"])]
                else:
                    alternative["steps"][0].update(step_id="construction", method_id="construction")
                return {**plan, "alternative_plans": [alternative],
                        "execution_selection": {"mode": selection_mode,
                                                "reason": "Two independent methods cover the goal."}}
            if request.get("execution_mode_decision"):
                if fault == "mode_unknown" and not failed_once:
                    from requests.exceptions import ConnectionError
                    failed_once.add("mode_unknown")
                    raise ConnectionError("unknown mode response")
                return {"mode": next(decisions, "keep"), "reason": "Current fronts and progress justify this mode."}
            if role == "reasoner":
                try:
                    entered.wait(timeout=2)
                    concurrent.append(request)
                except threading.BrokenBarrierError:
                    pass
                if fault in {"cancel", "unknown"} and request["step"]["step_id"].endswith("construction-0") and not failed_once:
                    import time

                    from requests.exceptions import ConnectionError

                    for _ in range(100):
                        observed = self.job(request["run_id"]).get("result", {}).get("solver", {}).get("execution_switch", {})
                        if observed.get("status") == "converging":
                            break
                        time.sleep(0.02)
                    self.assertEqual("converging", observed.get("status"))
                    if fault == "cancel":
                        canceled = self.client.post(f"/api/agent/jobs/{request['run_id']}/cancel",
                                                    json={}, headers=self.headers())
                        self.assertEqual(200, canceled.status_code)
                    else:
                        failed_once.add("unknown")
                        raise ConnectionError("unknown response")
                return {"argument": "1+1=2", "claims": [
                    {"statement": "1+1=2", "label": "verified"}], "blocked": False}
            if role == "step_verifier":
                if fault == "stagnation" and not failed_once:
                    failed_once.add("blocked")
                    return {"goal_gate": "NO", "logic_gate": "FAIL", "verdict": "REJECT",
                            "objection": "This method did not establish the goal."}
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "obligation_evidence": [{
                            "obligation_id": request["step"]["obligation_ids"][0], "evidence_category": "format_check",
                            "claim_indexes": [0]}]}
            if role == "final_generator":
                return {"final_response": "1+1=2"}
            if role == "whole_solution_verifier":
                return {"verdict": "ACCEPT", "reason": "Complete answer."}
            return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}

        limits = RunBudgetLimits(max_model_calls=40, max_http_attempts=40,
                                 max_tokens=2_000_000, max_runtime_seconds=runtime)
        self.open_star([provider] * 40, SHOWCASE_FAITHFUL_AUTONOMOUS=True,
            SHOWCASE_STAR_FULL_ENABLED=True,
            SHOWCASE_STAR_FULL_FEATURES=dict.fromkeys(CORE_FEATURES | {
                "auto_problem_spec", "problem_spec", "proof_graph",
                "progress_scheduling", "serial_routes"}, True),
            SHOWCASE_STAR_FULL_BUDGET=limits,
            SHOWCASE_STAR_POPULATION_ENABLED=True,
            SHOWCASE_STAR_POPULATION_CAPACITY=capacity,
            SHOWCASE_STAR_POPULATION_REQUEST_TIMEOUT_SECONDS=timeout,
            # This separate advanced-preset budget must never replace the root.
            SHOWCASE_STAR_POPULATION_BUDGET=RunBudgetLimits(max_model_calls=99))
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        with patch.object(pipeline, "full_gaps", return_value=[]):
            response = self.client.post("/api/agent/jobs", headers=self.headers(),
                json={"message": PROBLEM, "session_id": self.session})
            self.assertEqual(202, response.status_code, response.get_json())
            job_id = response.get_json()["job_id"]
            final = self.terminal(job_id, timeout=job_timeout)
        self.assertEqual("canceled" if fault == "cancel" else "failed" if fault in {"unknown", "mode_unknown", "mode_crash"} else "succeeded",
                         final["status"], final)
        return job_id, final, concurrent

    def test_plain_submission_selects_parallel_routes_and_reloads_bound_delivery(self):
        job_id, final, concurrent = self.run_plain_submission()
        planner = next(item for item in self.outbound if item["role"] == "planner")
        self.assertIn("execution_selection only on the primary top-level plan", planner["instruction"])
        self.assertIn("alongside checkpoint in checkpoint replies", planner["instruction"])
        self.assertIn("NEVER include execution_selection in alternative_plans", planner["instruction"])
        self.assertIn("normal complete plans without execution_selection", planner["instruction"])
        self.assertIn("the primary plan must itself be one complete whole-problem route",
                      planner["instruction"])
        self.assertIn("not a union or coordinator of methods", planner["instruction"])
        self.assertIn("Put other complete independent routes only in alternative_plans, "
                      "not in the primary steps", planner["instruction"])
        self.assertIn("Do not schedule cross-route reconciliation or waiting as primary work",
                      planner["instruction"])
        self.assertIn("the executor manages the route race and first qualified delivery",
                      planner["instruction"])
        self.assertIn("optional whole-proof directions as alternative complete plans", planner["instruction"])
        self.assertIn("not mandatory proof steps after a shared answer", planner["instruction"])
        self.assertIn("Each route must establish its own conclusions, equality conditions and completeness",
                      planner["instruction"])
        self.assertIn("Explore candidates are unverified", planner["instruction"])
        self.assertIn("never freeze their maximum or equality claims as established", planner["instruction"])
        self.assertIn("Choose one complete serial method when independent exploration adds no value",
                      planner["instruction"])
        self.assertIn("or its budget cost is not justified", planner["instruction"])
        solver = final["result"]["solver"]
        self.assertEqual("population", solver.get("execution_selection", {}).get("selected"))
        self.assertEqual(2, len(concurrent))
        self.assertEqual(2, len({item["call_id"] for item in concurrent}))
        self.assertEqual({job_id}, {item["run_id"] for item in self.outbound})
        self.assertEqual(40, final["result"]["budget"]["limits"]["max_model_calls"])
        self.assertEqual(final["result"]["budget"]["deadline_at"],
                         solver["execution_selection"]["budget"]["deadline_at"])
        route_attempts = [item for item in final["result"]["request_attempts"]
                          if item["role"] in {"reasoner", "step_verifier"}]
        self.assertTrue(route_attempts)
        self.assertTrue(all(0 < item["effective_timeout_seconds"] <= 15 for item in route_attempts))
        final_attempts = [item for item in final["result"]["request_attempts"]
                          if item["role"] in {"final_generator", "whole_solution_verifier"}]
        self.assertEqual(2, len(final_attempts))
        self.assertTrue(all(15 < item["effective_timeout_seconds"] <= 30 for item in final_attempts))
        self.assertEqual(len(self.outbound), final["result"]["budget"]["logical_calls"])
        self.assertEqual(2, len(solver["population"]["routes"]))
        before = len(self.outbound)
        report = self.report(job_id)
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual("delivered", report["solver"]["solver"]["population"]["delivery"]["status"])
        self.assertEqual(final["result"]["final_response"], self.job(job_id)["result"]["final_response"])
        self.assertEqual(before, len(self.outbound))

    def test_population_proposal_with_insufficient_root_time_uses_serial_without_reset(self):
        job_id, final, concurrent = self.run_plain_submission(runtime=180, timeout=30)
        selection = final["result"]["solver"]["execution_selection"]
        self.assertEqual("population", selection["requested"])
        self.assertEqual("serial", selection["selected"])
        self.assertEqual("root_budget_insufficient", selection["reason"])
        self.assertEqual([], concurrent)
        self.assertNotIn("population", final["result"]["solver"])
        self.assertEqual(180, final["result"]["budget"]["limits"]["max_runtime_seconds"])
        self.assertEqual(selection, self.job(job_id)["result"]["solver"]["execution_selection"])

    def test_unavailable_population_preserves_admission_reason_for_either_model_choice(self):
        for capacity, timeout, mode, reason in (
            ({**CAPACITY, "status": "unverified"}, 15, "population", "population_capacity_unverified"),
            (CAPACITY, 31, "population", "population_request_timeout_invalid"),
            ({**CAPACITY, "worker_slots": 0}, 15, "serial", "population_capacity_invalid"),
        ):
            with self.subTest(reason=reason, mode=mode):
                job_id, final, concurrent = self.run_plain_submission(
                    capacity=capacity, timeout=timeout, selection_mode=mode)
                selection = final["result"]["solver"]["execution_selection"]
                self.assertEqual(reason, selection["reason"])
                self.assertEqual("serial", selection["selected"])
                self.assertEqual([], concurrent)
                planner = next(item for item in self.outbound if item["role"] == "planner")
                self.assertEqual(reason, planner["autonomous_routes"]["unavailable_reason"])
                before = len(self.outbound)
                self.assertEqual(selection, self.job(job_id)["result"]["solver"]["execution_selection"])
                self.assertEqual(before, len(self.outbound))

    def test_midrun_switch_preserves_initial_selection_and_readonly_projection(self):
        job_id, final, _ = self.run_plain_submission(selection_mode="serial", multi_step=True)
        solver = final["result"]["solver"]
        self.assertEqual("serial", solver["execution_selection"]["selected"])
        switch = solver.get("execution_switch", {})
        self.assertEqual("switched", switch.get("status"))
        self.assertEqual("population", switch["source"])
        self.assertEqual("serial", switch["target"])
        self.assertIsInstance(switch["checkpoint_revision"], int)
        history = solver["execution_switch_history"]
        self.assertEqual([("serial", "population"), ("population", "serial")],
                         [(item["source"], item["target"]) for item in history])
        self.assertLess(history[0]["checkpoint_revision"], history[1]["checkpoint_revision"])
        self.assertEqual(40, final["result"]["budget"]["limits"]["max_model_calls"])
        self.assertEqual(solver["execution_selection"]["budget"]["deadline_at"],
                         final["result"]["budget"]["deadline_at"])
        self.assertEqual(len(self.outbound), final["result"]["budget"]["logical_calls"])
        initial_work = [item for item in self.outbound if item["role"] == "reasoner"
                        and item.get("step", {}).get("step_id") == "direct-0"]
        self.assertEqual(1, len(initial_work))
        self.assertEqual("serial", switch["current_mode"])
        self.assertEqual(switch, solver["progress"]["execution_switch"])
        before = len(self.outbound)
        self.assertEqual(switch, self.job(job_id)["result"]["solver"]["execution_switch"])
        self.assertEqual(before, len(self.outbound))

    def test_initial_population_converges_to_actual_serial_continuation(self):
        job_id, final, _ = self.run_plain_submission(multi_step=True)
        solver = final["result"]["solver"]
        self.assertEqual("population", solver["execution_selection"]["selected"])
        self.assertEqual("serial", solver["execution_switch"]["current_mode"])
        self.assertEqual(1, len(solver["execution_switch_history"]))
        checkpoint = solver["serial_checkpoint"]
        self.assertLessEqual(solver["execution_switch"]["checkpoint_revision"], checkpoint["revision"])
        self.assertIsInstance(checkpoint["route_revision"], int)
        before = len(self.outbound)
        report = self.report(job_id)
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        self.assertEqual(checkpoint, report["solver"]["solver"]["serial_checkpoint"])
        self.assertEqual(before, len(self.outbound))

    def test_unknown_blocks_switch_and_readonly_recovery_does_not_redispatch(self):
        job_id, final, _ = self.run_plain_submission(multi_step=True, fault="unknown")
        switch = final["result"]["solver"]["execution_switch"]
        self.assertEqual("needs_review", switch["status"])
        self.assertIsNone(switch["checkpoint_revision"])
        self.assertEqual("population", switch["current_mode"])
        self.assertGreater(final["result"]["budget"]["reserved_tokens"], 0)
        before = len(self.outbound)
        self.assertEqual(switch, self.job(job_id)["result"]["solver"]["execution_switch"])
        self.report(job_id)
        self.assertEqual(before, len(self.outbound))

    def test_cancel_during_convergence_wins_over_checkpoint(self):
        from showcase.solver_harness.population_runtime import _work

        settled = []
        def work(*args, **kwargs):
            done = threading.Event()
            settled.append(done)
            try:
                return _work(*args, **kwargs)
            finally:
                done.set()

        with patch("showcase.solver_harness.population_runtime._work", work):
            try:
                job_id, _, _ = self.run_plain_submission(multi_step=True, fault="cancel")
                final = self.job(job_id)
                switch = final["result"]["solver"]["execution_switch"]
                self.assertEqual("canceled", switch["status"])
                self.assertIsNone(switch["checkpoint_revision"])
                self.assertEqual("population", switch["current_mode"])
            finally:
                # Cancellation is observable before physical workers close SQLite.
                for done in settled:
                    self.assertTrue(done.wait(10), "canceled route worker did not settle")

    def test_runtime_model_can_keep_population_after_progress(self):
        _, final, _ = self.run_plain_submission(multi_step=True, modes=["keep"])
        decisions = [r for r in self.outbound if r.get("execution_mode_decision")]
        self.assertTrue(decisions)
        self.assertNotIn("execution_switch_history", final["result"]["solver"])

    def test_explicit_unknown_retry_dispatches_new_identity_during_switch(self):
        import uuid

        job_id, failed, _ = self.run_plain_submission(multi_step=True, fault="unknown")
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
        old = failed["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        before = len(self.outbound)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(202, response.status_code)
        self.terminal(job_id)
        self.assertEqual(before, len(self.outbound))
        replacement = str(uuid.uuid4())
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": old, "new_call_id": replacement}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id, timeout=20)
        self.assertEqual(1, sum(r.get("call_id") == replacement for r in self.outbound), final.get("error"))
        self.assertGreater(final["result"]["budget"]["reserved_tokens"], 0)
        self.assertEqual("switched", final["result"]["solver"]["execution_switch"]["status"])

    def test_population_can_contract_expand_and_contract_on_new_receipts(self):
        _, final, _ = self.run_plain_submission(multi_step=True, step_count=6,
                                               modes=["serial", "population", "serial"])
        history = final["result"]["solver"]["execution_switch_history"]
        self.assertEqual(["serial", "population", "serial"], [s["target"] for s in history])

    def test_checkpoint_export_is_legal_for_native_serial_validator(self):
        from types import SimpleNamespace

        from showcase.solver_harness.autonomous_routes import serial_checkpoint_view
        from showcase.solver_harness.faithful_intervention_native import NativeCheckpointExecutor

        observed = []
        original = NativeCheckpointExecutor.validate_checkpoint
        from showcase.solver_harness.population_store import command
        def capture(*args, **kwargs):
            parent = command(*args, **kwargs)
            if args[2] != "execution_checkpoint" or not parent["state"].get("serial_checkpoint"):
                return parent
            state = serial_checkpoint_view(parent["state"], expected_revision=parent["state_revision"])
            step = next(s for s in state["plan"]["steps"] if s["step_id"] == state["current_step"])
            action = SimpleNamespace(target=step["step_id"], action_type="reasoning_method",
                                     parameters={"method_id": step["method_id"]})
            original(SimpleNamespace(config={"features": {"stream_recovery": True}}), state, action)
            observed.append(state)
            return parent
        with patch("showcase.solver_harness.population_store.command", capture):
            self.run_plain_submission(multi_step=True)
        self.assertTrue(observed)

    def test_serial_can_expand_before_first_accepted_step(self):
        _, final, _ = self.run_plain_submission(selection_mode="serial", multi_step=True,
                                               fault="stagnation")
        requests = [r for r in self.outbound if r.get("execution_mode_decision")]
        self.assertTrue(requests)
        self.assertEqual("serial", requests[0]["current_mode"])
        history = final["result"]["solver"]["execution_switch_history"]
        self.assertEqual("population", history[0]["target"])

    def test_parent_mode_unknown_requires_explicit_retry_and_retains_hold(self):
        import uuid
        from concurrent.futures import wait

        from showcase.solver_harness.harness import SolverHarness
        from showcase.solver_harness.population_runtime import _collect

        original_dispatch = SolverHarness.dispatch
        def dispatch(harness, run, operation, request):
            if request.get("execution_mode_decision"):
                wait(list(harness._population_futures.values()))
                run = _collect(harness, harness.get_run(run["run_id"]))
            return original_dispatch(harness, run, operation, request)
        with patch.object(SolverHarness, "dispatch", dispatch):
            job_id, failed, _ = self.run_plain_submission(multi_step=True, fault="mode_unknown")
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        self.enterContext(patch.object(pipeline, "full_gaps", return_value=[]))
        old = failed["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        before = len(self.outbound)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(202, response.status_code)
        resumed = self.terminal(job_id, timeout=20)
        self.assertEqual(before, len(self.outbound))
        self.assertEqual("failed", resumed["status"])
        replacement = str(uuid.uuid4())
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": old, "new_call_id": replacement}}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(1, sum(r.get("call_id") == replacement for r in self.outbound))
        self.assertEqual(3, sum(bool(r.get("execution_mode_decision")) for r in self.outbound))
        self.assertGreater(final["result"]["budget"]["reserved_tokens"], 0)
        self.assertEqual(failed["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])

    def test_serial_checkpoint_refreshes_after_selected_route_settles(self):
        from showcase.solver_harness.autonomous_routes import serial_checkpoint_view
        from showcase.solver_harness.population_store import command

        observed = []
        def capture(*args, **kwargs):
            run = command(*args, **kwargs)
            state = run["state"]
            checkpoint = state.get("serial_checkpoint")
            if args[2] == "accept" and checkpoint:
                route = state["population"]["routes"][checkpoint["route_id"]]
                if (not route.get("inflight_action_id") and route["snapshot"].get("phase") == "STEP_EXECUTE"
                        and route["revision"] > checkpoint["route_revision"]):
                    serial_checkpoint_view(state, expected_revision=run["state_revision"])
                if (route["snapshot"].get("phase") == "STEP_EXECUTE"
                        and checkpoint["revision"] > state["execution_switch"]["checkpoint_revision"]):
                    observed.append(serial_checkpoint_view(state, expected_revision=run["state_revision"]))
                    stale = deepcopy(state)
                    stale["serial_checkpoint"]["snapshot_hash"] = "stale"
                    from showcase.solver_harness.faithful_intervention_records import (
                        FaithfulInterventionError,
                    )
                    with self.assertRaisesRegex(FaithfulInterventionError, "serial_checkpoint_source_changed"):
                        serial_checkpoint_view(stale, expected_revision=run["state_revision"])
                    if len(observed) == 1:
                        from showcase.solver_harness.faithful_intervention import (
                            FaithfulInterventionEngine,
                        )
                        from tests.test_faithful_s10_intervention_execution import _PausedParentGate

                        harness = args[0]
                        engine = FaithfulInterventionEngine(harness._state_store._connection,
                                                           connection_lock=threading.RLock())
                        engine.register_hypothesis({
                            "hypothesis_id": "refresh-hyp", "failure_category": "invalid_inference",
                            "evidence": {"event_id": "checkpoint"},
                            "candidate_action_ids": ("refresh-control", "refresh-treatment"),
                            "falsification_criteria": {"condition": "same result after review"}})
                        for name, mode in (("refresh-control", "direct"), ("refresh-treatment", "decompose")):
                            engine.register_action({"action_id": name, "action_type": "review_strategy",
                                "target": observed[-1]["current_step"], "parameters": {"mode": mode}})
                        pair = engine.reserve_pair(job_id=run["run_id"], job_gate=_PausedParentGate(),
                            run_id=run["run_id"], expected_revision=run["state_revision"],
                            hypothesis_id="refresh-hyp", control_action_id="refresh-control",
                            intervention_action_id="refresh-treatment", pair_id="refresh-pair", seed=17,
                            reservation={"input_estimate": 10, "output_cap": 20})
                        self.assertEqual("reserved", pair["status"])
                        self.assertEqual(state, harness.get_run(run["run_id"])["state"])
            return run
        with patch("showcase.solver_harness.population_runtime.command", capture):
            self.run_plain_submission(multi_step=True, step_count=8, job_timeout=40)
        self.assertTrue(observed)

    def test_completed_mode_receipt_replays_before_marker_and_intent(self):
        from showcase.solver_harness.harness import SolverHarness
        from showcase.solver_harness.population_store import command

        for boundary in ("execution_mode_decided", "execution_intent"):
            with self.subTest(boundary=boundary):
                stopped = []
                original = SolverHarness.commit_event
                def commit(harness, *args, **kwargs):
                    if boundary == "execution_mode_decided" and kwargs.get("event", {}).get("type") == boundary and not stopped:
                        stopped.append(True)
                        from concurrent.futures import wait

                        from showcase.solver_harness.population_runtime import _collect
                        wait(list(harness._population_futures.values()))
                        _collect(harness, harness.get_run(args[0]))
                        raise RuntimeError("mode completion consumption interrupted")
                    return original(harness, *args, **kwargs)
                def transition(*args, **kwargs):
                    if boundary == "execution_intent" and args[2] == boundary and not stopped:
                        stopped.append(True)
                        from concurrent.futures import wait

                        from showcase.solver_harness.population_runtime import _collect
                        wait(list(args[0]._population_futures.values()))
                        _collect(args[0], args[0].get_run(args[1]))
                        raise RuntimeError("mode intent interrupted")
                    return command(*args, **kwargs)
                with patch.object(SolverHarness, "commit_event", commit), patch(
                        "showcase.solver_harness.population_store.command", transition):
                    job_id, failed, _ = self.run_plain_submission(multi_step=True, fault="mode_crash")
                self.assertTrue(stopped)
                prior = [r for r in self.outbound if r.get("execution_mode_decision")]
                self.assertEqual(1, len(prior))
                pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
                with patch.object(pipeline, "full_gaps", return_value=[]):
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    final = self.terminal(job_id, timeout=20)
                self.assertEqual("succeeded", final["status"], final.get("error"))
                self.assertEqual(len(self.outbound), final["result"]["budget"]["logical_calls"])
                self.assertEqual("serial", final["result"]["solver"]["execution_switch"]["current_mode"])
                self.assertEqual(1, sum(r.get("call_id") == prior[0]["call_id"] for r in self.outbound))
                self.assertEqual(2, sum(bool(r.get("execution_mode_decision")) for r in self.outbound))
                self.assertEqual(failed["result"]["budget"]["deadline_at"], final["result"]["budget"]["deadline_at"])
