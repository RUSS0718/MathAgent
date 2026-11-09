"""Real-loopback Job coverage for concurrent Population/APRS."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture

CAPACITY = {
    "service_id": "loopback-capacity-fixture", "max_inflight": 2,
    "worker_slots": 2, "evidence_ref": "fixture:two-worker-provider-v1",
    "status": "controlled",
}
ROOT_ID = "root:result-format"
PROBLEM = "Compute 1+1 and return the result."
SPEC = {
    "specification_version": 1, "original_problem": PROBLEM,
    "domain": "natural numbers", "quantifiers": [], "assumptions": [],
    "directions": ["forward"], "output_requirements": ["result"],
    "root_obligations": [{"obligation_id": ROOT_ID, "obligation_type": "format",
                          "statement": "Return the required result format."}],
    "auxiliary_goals": [],
}


class PopulationLoopbackJobTest(StarJobFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(patch.dict(os.environ, {"INTERN_API_KEY": "loopback-only"}))
        self.reasoners = 0
        self.active_reasoners = 0
        self.max_active_reasoners = 0
        self.verifiers = 0
        self.reasoner_gate = threading.Event()
        self.verifier_gate = threading.Event()
        self.lock = threading.Lock()
        self.requests = []
        self.server_delay = 0
        self.reasoner_barrier_timeout = 2
        self.reject_construction = False
        self.rate_limit_construction = False
        self.multi_step_construction = False
        self.both_two_step_routes = False
        self.second_reasoner_gate = threading.Event()
        self.second_reasoners = 0
        self.reject_first_final = False
        self.whole_reviews = 0
        case = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                context = json.loads(payload["messages"][-1]["content"])
                role = context["role"]
                with case.lock:
                    case.requests.append((role, context))
                    if role == "reasoner":
                        case.reasoners += 1
                        case.active_reasoners += 1
                        case.max_active_reasoners = max(case.max_active_reasoners,
                                                        case.active_reasoners)
                        if case.both_two_step_routes and context.get("step", {}).get("step_id", "").endswith((":direct", ":construction")):
                            case.second_reasoners += 1
                            if case.second_reasoners >= 2:
                                case.second_reasoner_gate.set()
                        if case.reasoners >= 2:
                            case.reasoner_gate.set()
                    elif role == "step_verifier":
                        case.verifiers += 1
                        if case.verifiers >= 2:
                            case.verifier_gate.set()
                if (role == "reasoner" and case.rate_limit_construction
                        and context.get("step", {}).get("step_id", "").endswith(":construction-setup")):
                    case.reasoner_gate.wait(case.reasoner_barrier_timeout)
                    with case.lock:
                        case.active_reasoners -= 1
                    body = b'{"error":"controlled_rate_limit"}'
                    self.send_response(429)
                    self.send_header("Retry-After", "0")
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if role == "reasoner":
                    case.reasoner_gate.wait(case.reasoner_barrier_timeout)
                    response = {
                        "argument": "1+1=2 by addition.",
                        "claims": [{"statement": "1+1=2 by addition.", "label": "verified"}],
                        "blocked": False,
                    }
                    with case.lock:
                        case.active_reasoners -= 1
                    if context.get("step", {}).get("step_id", "").endswith((":direct", ":direct-setup")):
                        time.sleep(case.server_delay)
                elif role == "step_verifier":
                    case.verifier_gate.wait(case.reasoner_barrier_timeout)
                    if case.both_two_step_routes and context.get("step", {}).get("step_id", "").endswith((":direct", ":construction")):
                        case.second_reasoner_gate.wait(case.reasoner_barrier_timeout)
                    response = {
                        "goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": "", "classified_outcomes": [],
                        "obligation_evidence": [{
                            "obligation_id": ROOT_ID, "evidence_category": "format_check",
                            "claim_indexes": [0],
                        }],
                    }
                    if context.get("step", {}).get("step_id", "").endswith((":construction-setup", ":direct-setup")):
                        response["obligation_evidence"] = []
                        response["classified_outcomes"] = [{
                            "category": "Lemma", "statement": "1+1=2 by addition.",
                            "scope": "problem", "claim_indexes": [0], "receipt_ids": [],
                            "dependencies": [],
                        }]
                    if (case.reject_construction
                            and context.get("step", {}).get("step_id", "").endswith(":construction")):
                        response.update(goal_gate="NO", logic_gate="FAIL", verdict="REJECT",
                                        objection="Controlled alternate-route rejection.",
                                        obligation_evidence=[])
                elif role == "planner":
                    response = {
                        "version": 1,
                        "steps": [{"step_id": "direct", "title": "Direct addition",
                                   "objective": PROBLEM, "depends_on": [],
                                   "method_id": "direct", "obligation_ids": [ROOT_ID],
                                   "auxiliary_goal_ids": []}],
                        "alternative_plans": [{
                            "version": 1,
                            "steps": [{"step_id": "construction", "title": "Constructive addition",
                                       "objective": PROBLEM, "depends_on": [],
                                       "method_id": "construction", "obligation_ids": [ROOT_ID],
                                       "auxiliary_goal_ids": []}],
                        }],
                    }
                    if case.multi_step_construction:
                        steps = response["alternative_plans"][0]["steps"]
                        setup = {**steps[0], "step_id": "construction-setup", "depends_on": []}
                        steps[0]["depends_on"] = ["construction-setup"]
                        steps.insert(0, setup)
                    if case.both_two_step_routes:
                        steps = response["steps"]
                        setup = {**steps[0], "step_id": "direct-setup", "depends_on": []}
                        steps[0]["depends_on"] = ["direct-setup"]
                        steps.insert(0, setup)
                elif role == "final_generator":
                    response = {"final_response": "1+1=2 by addition."}
                elif role == "whole_solution_verifier":
                    case.whole_reviews += 1
                    response = {"verdict": "ACCEPT", "reason": "The computation and format are complete."}
                    if case.reject_first_final and case.whole_reviews == 1:
                        response = {"verdict": "REJECT", "reason": "Controlled rejection of the first candidate."}
                else:
                    response = {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
                body = json.dumps({
                    "id": "fixture-response", "model": "intern-s2",
                    "choices": [{"message": {"content": json.dumps(response)},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        provider = InternChatClient(retry=1, timeout=12)
        self.provider = provider
        provider.api_base = f"http://127.0.0.1:{self.server.server_port}"
        adapter = InternModelAdapter(provider, max_tokens=256)
        self.app = create_app({
            "TESTING": True,
            "SHOWCASE_DATA_DIR": self.temp.name,
            "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_STAR_ENABLED": False,
            "SHOWCASE_STAR_POPULATION_ENABLED": True,
            "SHOWCASE_STAR_POPULATION_CAPACITY": CAPACITY,
            "SHOWCASE_STAR_POPULATION_BUDGET": RunBudgetLimits(
                max_model_calls=20, max_http_attempts=20, max_tool_calls=0,
                max_tokens=2_000_000, max_runtime_seconds=120,
            ),
            "SHOWCASE_STAR_ADAPTER": adapter,
            "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
        })
        for name in ("loopback_store", "showcase_run_service", "showcase_workspace_service"):
            self.addCleanup(self.app.extensions[name].close)
        self.client = self.app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        self.session = self.client.post("/api/new_chat", headers=self.headers()).get_json()["new_session_id"]

    def create_population_job(self, *, idempotency_key=None, expected_status=202):
        response = self.client.post(
            "/api/agent/jobs",
            json={"message": PROBLEM, "session_id": self.session,
                  "solver_mode": "star_population", "problem_spec": SPEC},
            headers={"X-CSRF-Token": self.csrf,
                     "Idempotency-Key": idempotency_key or str(uuid.uuid4())},
        )
        self.assertEqual(expected_status, response.status_code, response.get_json())
        return response.get_json()["job_id"]

    def test_two_distinct_routes_overlap_and_deliver_from_persisted_root_evidence(self):
        key = str(uuid.uuid4())
        job_id = self.create_population_job(idempotency_key=key)
        final = self.terminal(job_id, timeout=35)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("1+1=2 by addition.", final["result"]["final_response"])
        self.assertEqual(2, self.reasoners,
                         (self.requests, final["result"]["solver"]["population"]))
        self.assertEqual(2, self.verifiers)
        self.assertGreaterEqual(self.max_active_reasoners, 2)
        self.assertEqual("star_population", final["result"]["solver_mode"])
        report = self.report(job_id)
        self.assertEqual("delivered", report["solver"]["solver"]["population"]["delivery"]["status"])
        self.assertEqual("settled", report["solver"]["solver"]["population"]["settlement"]["status"])
        self.assertEqual(1, report["solver"]["solver"]["progress"]["root_obligations"]["covered"])
        public = json.dumps(self.client.get(f"/api/agent/jobs/{job_id}").get_json(), ensure_ascii=False)
        for private in ("frontier_digest", "evidence_ref", "population_action_id"):
            self.assertNotIn(private, public)
        count = len(self.requests)
        self.assertEqual(job_id, self.create_population_job(idempotency_key=key, expected_status=200))
        exported = self.client.get(f"/api/runs/{job_id}/evidence").get_json()
        self.assertEqual("delivered", exported["solver"]["solver"]["population"]["delivery"]["status"])
        for private in ("frontier_digest", "evidence_ref", "population_action_id"):
            self.assertNotIn(private, json.dumps(exported))
        self.assertEqual(count, len(self.requests))
        replay = self.client.get(f"/api/agent/jobs/{job_id}/candidate-replay").get_json()
        self.assertGreater(replay["population"]["rating_count"], 0)
        self.assertTrue(replay["population"]["replay_matches"])
        connection = self.app.extensions["loopback_store"]._connection
        row = connection.execute("SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)).fetchone()
        state = json.loads(row[0])
        state["population"]["rating_history"][0]["rating"]["input_hash"] = "tampered"
        connection.execute("UPDATE solver_states SET state_json=? WHERE run_id=?", (json.dumps(state), job_id))
        connection.commit()
        tampered = self.client.get(f"/api/agent/jobs/{job_id}/candidate-replay").get_json()
        self.assertFalse(tampered["population"]["replay_matches"])
        self.assertEqual(count, len(self.requests))

    def test_delivery_can_settle_before_late_request_without_resending_or_changing_math(self):
        self.provider.timeout = 12
        self.server_delay = 5
        # Let the fast route verify immediately while the primary route's
        # reasoner request remains physically in flight.
        self.verifier_gate.set()
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.population_config["population_policy"]["request_timeout_seconds"] = 12
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=30)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("delivered", self.report(job_id)["solver"]["solver"]["population"]
                         ["delivery"]["status"])
        before = len(self.requests)
        initial = self.report(job_id)["solver"]["solver"]["population"]["settlement"]
        self.assertEqual("pending", initial["status"])
        self.wait_for(
            lambda: self.report(job_id)["solver"]["solver"]["population"]["settlement"]["status"]
            == "settled",
            timeout=12,
        )
        final_report = self.report(job_id)
        self.assertEqual("delivered", final_report["solver"]["solver"]["population"]
                         ["delivery"]["status"])
        self.assertEqual(before, len(self.requests))
        self.assertEqual("accepted", final_report["solver"]["solver"]["semantics"]["whole_review"])

    def test_bound_review_requires_its_physical_http_record(self):
        from showcase.solver_harness import population_delivery
        original = population_delivery.delivery_allowed
        def lose_review_http(connection, state):
            row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (state["run_id"],)).fetchone()
            ledger = json.loads(row[0])
            ledger["actions"] = [item for item in ledger["actions"]
                                 if not (item.get("kind") == "http" and item.get("role") == "whole_solution_verifier")]
            connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?", (json.dumps(ledger), state["run_id"]))
            connection.commit()
            return original(connection, state)
        with patch.object(population_delivery, "delivery_allowed", side_effect=lose_review_http):
            job_id = self.create_population_job()
            final = self.terminal(job_id, timeout=20)
        self.assertEqual("failed", final["status"], final)
        self.assertEqual("not_delivered", final["result"]["solver"]["population"]["delivery"]["status"])

    def test_bound_review_cannot_deliver_after_shared_budget_ledger_is_lost(self):
        from showcase.solver_harness import population_delivery
        original = population_delivery.delivery_allowed
        def lose_ledger(connection, state):
            connection.execute("UPDATE run_budgets SET ledger_json=json_set(ledger_json,'$.actions',json('[]')) WHERE run_id=?", (state["run_id"],))
            connection.commit()
            return original(connection, state)
        with patch.object(population_delivery, "delivery_allowed", side_effect=lose_ledger):
            job_id = self.create_population_job()
            final = self.terminal(job_id, timeout=20)
        self.assertEqual("failed", final["status"], final)
        self.assertEqual("not_delivered", final["result"]["solver"]["population"]["delivery"]["status"])
        self.assertNotEqual("1+1=2 by addition.", final["result"]["final_response"])

    def test_controller_registers_new_route_during_round_for_next_round_only(self):
        from showcase.solver_harness import population_runtime
        original = population_runtime._collect
        registered = []
        def add_route(harness, run):
            run = original(harness, run)
            pop = run["state"]["population"]
            if pop.get("round_members") and not registered:
                before = list(pop["round_members"])
                plan = {"version": 3, "steps": [{"step_id": "late", "title": "Late route",
                    "objective": PROBLEM, "depends_on": [], "method_id": "induction",
                    "obligation_ids": [ROOT_ID], "auxiliary_goal_ids": []}]}
                run = population_runtime.register_plans(harness, run, plan)
                added = set(run["state"]["population"]["routes"]) - set(pop["routes"])
                self.assertEqual(1, len(added))
                self.assertEqual(before, run["state"]["population"]["round_members"])
                registered.extend(added)
            return run
        with patch.object(population_runtime, "_collect", side_effect=add_route):
            job_id = self.create_population_job()
            final = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", final["status"], final)
        self.assertTrue(registered)

    def test_final_candidate_commit_tolerates_late_settlement_revision_only(self):
        from showcase.solver_harness import finalize
        from showcase.solver_harness.population_store import command

        original = finalize.commit
        def settle_between_dispatch_and_commit(harness, run, kind, updates, **details):
            if kind in {"final_candidate_generated", "final_candidate_reviewed"}:
                command(harness, run["run_id"], "patch", updates={"last_observed_at": time.time()})
            return original(harness, run, kind, updates, **details)
        with patch.object(finalize, "commit", side_effect=settle_between_dispatch_and_commit):
            job_id = self.create_population_job()
            final = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("1+1=2 by addition.", final["result"]["final_response"])

    def test_http_rate_limit_pauses_new_exploration_and_retains_other_inflight_request(self):
        self.multi_step_construction = True
        self.rate_limit_construction = True
        self.server_delay = 1
        self.verifier_gate.set()
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=15)
        self.assertEqual("failed", final["status"], final)
        self.assertTrue(final["result"]["solver"]["population"]["scheduler"]["paused"])
        self.wait_for(lambda: self.report(job_id)["solver"]["solver"]["population"]
                      ["resources"]["worker_slots_in_use"] == 0, timeout=10)
        self.assertEqual(2, self.reasoners)
        roles = [(role, context.get("step", {}).get("step_id", "")) for role, context in self.requests]
        self.assertFalse(any(role == "reasoner" and step.endswith(":construction") for role, step in roles), roles)
        self.assertGreater(self.report(job_id)["budget"]["reserved_tokens"], 0)

    def test_next_work_unit_adopts_other_route_verified_evidence_with_persisted_dependencies(self):
        self.multi_step_construction = True
        self.both_two_step_routes = True
        self.server_delay = 0.5
        self.verifier_gate.set()
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=25)
        self.assertEqual("succeeded", final["status"], final)
        second = next(context for role, context in self.requests
                      if role == "reasoner" and context.get("step", {}).get("step_id", "").endswith(":direct"))
        own_step = second["step"]["step_id"]
        adopted = second["role_context"]["state"]["verified_results_ledger"]
        foreign = [item for item in adopted if item["source"].split(":", 1)[0] != own_step.split(":", 1)[0]]
        self.assertTrue(foreign, adopted)
        row = self.app.extensions["loopback_store"]._connection.execute(
            "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
        ).fetchone()
        state = json.loads(row[0])
        actions = state["population"]["actions"].values()
        self.assertTrue(any(item["result_id"] in {dep["result_id"] for dep in action["dependencies"]}
                            for item in foreign for action in actions), state["population"])

    def test_rejected_final_candidate_resumes_legal_route_then_reviews_new_candidate(self):
        self.reject_first_final = True
        self.verifier_gate.set()
        self.server_delay = 1
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual(2, self.whole_reviews)
        self.assertEqual(2, self.reasoners)
        self.assertEqual("1+1=2 by addition.", final["result"]["final_response"])

    def test_fast_route_advances_second_work_unit_while_other_http_is_pending(self):
        self.server_delay = 5
        self.verifier_gate.set()
        self.multi_step_construction = True
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=25)
        self.assertEqual("succeeded", final["status"], final)
        roles = [(role, context.get("step", {}).get("step_id", "")) for role, context in self.requests]
        self.assertTrue(any(role == "reasoner" and step.endswith(":construction")
                            for role, step in roles), roles)
        self.assertFalse(any(role == "step_verifier" and step.endswith(":direct")
                             for role, step in roles), roles)
        self.assertEqual("pending", final["result"]["solver"]["population"]["settlement"]["status"])
        self.wait_for(lambda: self.report(job_id)["solver"]["solver"]["population"]
                      ["settlement"]["status"] == "settled", timeout=12)

    def test_resume_reuses_completed_receipt_after_owner_restart_without_resend(self):
        from showcase.solver_harness import population_runtime

        collect = population_runtime._collect
        def crash_before_accept(harness, run):
            latest = harness._state_store.get_run(run["run_id"])
            pop = latest["state"]["population"]
            if any(action.get("status") == "completed" and not action.get("accepted")
                   and any(step.get("verification", {}).get("verdict") == "ACCEPT"
                           for step in pop["routes"][action["route_id"]]["snapshot"].get("steps", {}).values())
                   for action in pop["actions"].values()):
                raise RuntimeError("controlled_crash_after_receipt_before_accept")
            return collect(harness, run)

        self.verifier_gate.set()
        with patch.object(population_runtime, "_collect", side_effect=crash_before_accept):
            job_id = self.create_population_job()
            failed = self.terminal(job_id, timeout=20)
        self.assertEqual("failed", failed["status"], failed)
        before = self.reasoners
        # A separate process acquires the persisted owner epoch before public recovery.
        script = """
import sys
from types import SimpleNamespace
from showcase.storage import SQLiteStore
from showcase.solver_harness.storage import SolverStateStore
from showcase.solver_harness.population_store import command
with SQLiteStore(sys.argv[1]) as store:
    harness = SimpleNamespace(_state_store=SolverStateStore(store._connection),
        _population_owner=None, _event_observer=None)
    command(harness, sys.argv[2], 'claim', owner_id='restart-process', takeover=True)
"""
        child = subprocess.run([sys.executable, "-c", script,
                                self.app.extensions["loopback_store"].database_path, job_id],
                               capture_output=True, text=True, timeout=15)
        self.assertEqual(0, child.returncode, child.stderr)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        resumed = self.terminal(job_id, timeout=20)
        self.assertEqual("succeeded", resumed["status"], resumed)
        self.assertEqual(before, self.reasoners)
        self.assertEqual("1+1=2 by addition.", resumed["result"]["final_response"])

    def test_original_deadline_fences_late_results(self):
        self.server_delay = 5
        job_id = self.create_population_job()
        self.wait_for(lambda: self.reasoners >= 2)
        # Fault injection expires the persisted original deadline while HTTP is in flight.
        connection = self.app.extensions["loopback_store"]._connection
        connection.execute(
            "UPDATE run_budgets SET ledger_json=json_set(ledger_json,'$.deadline_at',?) WHERE run_id=?",
            (time.time() - 1, job_id),
        )
        connection.commit()
        final = self.terminal(job_id, timeout=15)
        self.assertEqual("failed", final["status"], final)
        before = self.report(job_id)
        count = len(self.requests)
        self.wait_for(lambda: self.report(job_id)["solver"]["solver"]["population"]
                      ["settlement"]["status"] == "settled", timeout=12)
        after = self.report(job_id)
        self.assertEqual(count, len(self.requests))
        self.assertEqual(before["solver"]["solver"]["progress"]["root_obligations"],
                         after["solver"]["solver"]["progress"]["root_obligations"])
        self.assertNotEqual("delivered", after["solver"]["solver"]["population"]
                            ["delivery"]["status"])

    def test_cancel_fences_late_route_math_and_preserves_physical_settlement(self):
        self.server_delay = 5
        self.verifier_gate.set()
        self.reject_construction = True
        job_id = self.create_population_job()
        self.wait_for(lambda: self.reasoners >= 2)
        response = self.client.post(f"/api/agent/jobs/{job_id}/cancel", json={}, headers=self.headers())
        self.assertEqual(200, response.status_code, response.get_json())
        final = self.terminal(job_id)
        self.assertEqual("canceled", final["status"], final)
        before = self.report(job_id)
        count = len(self.requests)
        self.wait_for(lambda: self.report(job_id)["solver"]["solver"]["population"]
                      ["settlement"]["status"] == "settled", timeout=12)
        after = self.report(job_id)
        self.assertEqual(count, len(self.requests))
        self.assertEqual(before["solver"]["solver"]["progress"]["root_obligations"],
                         after["solver"]["solver"]["progress"]["root_obligations"])
        self.assertNotEqual("delivered", after["solver"]["solver"]["population"]
                            ["delivery"]["status"])

    def test_public_read_repairs_lost_settlement_callback_without_new_math_or_calls(self):
        from showcase.run_budget import RunBudgetLedger

        self.provider.timeout = 2
        self.server_delay = 5
        self.reject_construction = True
        self.verifier_gate.set()
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.population_config["population_policy"]["request_timeout_seconds"] = 2
        job_id = self.create_population_job()
        final = self.terminal(job_id, timeout=20)
        self.assertEqual("failed", final["status"], final)
        service = self.app.extensions["showcase_workspace_service"]
        ledger = service.budget_ledger
        row = ledger.connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)).fetchone()
        raw = json.loads(row[0])
        attempt = next(item for item in raw["actions"]
                       if item["kind"] == "http" and item.get("status") == "error")
        before = self.report(job_id)
        count = len(self.requests)
        with patch.object(RunBudgetLedger, "_settle_population_resource"):
            ledger.settle(job_id, attempt["id"], {"status": "success", "prompt_tokens": 20,
                          "completion_tokens": 10, "total_tokens": 30})
        after = self.report(job_id)
        self.assertEqual("settled", after["solver"]["solver"]["population"]["settlement"]["status"])
        self.assertEqual(before["solver"]["solver"]["progress"]["root_obligations"],
                         after["solver"]["solver"]["progress"]["root_obligations"])
        self.assertEqual(count, len(self.requests))

    def test_population_resume_retries_unknown_call_with_new_identity(self):
        self.provider.timeout = 2
        self.server_delay = 5
        self.reject_construction = True
        self.verifier_gate.set()
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.population_config["population_policy"]["request_timeout_seconds"] = 2
        job_id = self.create_population_job()
        failed = self.terminal(job_id, timeout=30)
        self.assertEqual("failed", failed["status"], failed)
        unknown = failed["result"]["solver"]["recovery"]["unknown_calls"]
        self.assertTrue(unknown, failed["result"]["solver"]["population"])
        old_public_id = unknown[0]["call_id"]

        requests_before_resume = len(self.requests)
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers(),
        )
        self.assertEqual(202, response.status_code, response.get_json())
        still_unknown = self.terminal(job_id, timeout=15)
        self.assertEqual("failed", still_unknown["status"], still_unknown)
        self.assertEqual(requests_before_resume, len(self.requests))

        self.server_delay = 0
        new_call_id = str(uuid.uuid4())
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": old_public_id, "new_call_id": new_call_id}},
            headers=self.headers(),
        )
        self.assertEqual(202, response.status_code, response.get_json())
        final = self.terminal(job_id, timeout=35)
        requests = [(role, context.get("step", {}).get("step_id"), context.get("call_id"))
                    for role, context in self.requests]
        self.assertEqual("succeeded", final["status"], (final.get("error"), requests))
        retries = final["result"]["solver"]["recovery"]["retries"]
        self.assertTrue(any(item["retry_of"] == old_public_id for item in retries), retries)
        retried = [context for role, context in self.requests
                   if role in {"reasoner", "step_verifier"} and context.get("call_id") == new_call_id]
        self.assertEqual(1, len(retried), self.requests)
        self.assertEqual("pending", final["result"]["solver"]["population"]["settlement"]["status"])
        self.assertGreater(final["result"]["budget"]["reserved_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
