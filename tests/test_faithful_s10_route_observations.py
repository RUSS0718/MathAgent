import json
import os
import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from unittest.mock import patch

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.aprs import evaluate, rate_routes, verified_gain
from showcase.solver_harness.faithful_memory import FaithfulMemoryStore, MemoryScope
from showcase.solver_harness.faithful_memory_capture import capture_population_observation
from showcase.solver_harness.faithful_memory_injection import load_population_memory
from showcase.solver_harness.route_projection import route_summary
from tests.star_product_support import StarJobFixture
from tests.test_faithful_s03_job import ENDPOINT, PROBLEM, REPLIES, SPEC


class RouteObservationTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE chat_sessions(session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
            CREATE TABLE workspace_jobs(job_id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                user_id TEXT NOT NULL, status TEXT NOT NULL);
            INSERT INTO chat_sessions VALUES ('session', 'owner');
            INSERT INTO workspace_jobs VALUES ('run', 'session', 'owner', 'succeeded');
        """)
        self.store = FaithfulMemoryStore(self.db)
        self.scope = MemoryScope("population", "session", "owner", "session")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_route_observations_have_independent_outcomes_and_provenance(self):
        self.store.set_injection_enabled(self.scope, True, actor_id="owner")
        self.db.commit()
        state = {
            "phase": "TERMINAL", "status": "completed_llm_reviewed", "state_revision": 7,
            "problem_spec": {"domain": "Algebra"},
            "route_registry": [
                {"route_id": "r1", "status": "completed", "frontier_digest": "digest-1",
                 "stop_reason": "final_answer_bound",
                 "graph_version": 3, "plan_version": 2, "attempt_index": 1,
                 "policy_version": "serial-aprs-v1", "unknown_observations": []},
                {"route_id": "r2", "status": "terminated", "frontier_digest": "digest-2",
                 "graph_version": 4, "plan_version": 3, "attempt_index": 2,
                 "policy_version": "serial-aprs-v1", "unknown_observations": ["unknown"]},
            ],
        }
        self.assertTrue(capture_population_observation(
            self.db, run_id="run", state=state, budget={}, reviewed=True))
        self.assertFalse(capture_population_observation(
            self.db, run_id="run", state=state, budget={}, reviewed=True))
        records = self.store.list_observations(self.scope)
        routes = {r["observation"]["content"]["route_id"]: r for r in records
                  if "route_id" in r["observation"]["content"]}
        self.assertEqual({"r1", "r2"}, set(routes))
        self.assertEqual("success", routes["r1"]["observation"]["outcome"])
        self.assertEqual("unknown", routes["r2"]["observation"]["outcome"])
        self.assertEqual("run", routes["r1"]["provenance"]["source_run_id"])
        self.assertEqual("digest-1", routes["r1"]["observation"]["content"]["frontier_digest"])
        self.assertEqual(3, routes["r1"]["observation"]["versions"]["graph_version"])
        self.assertEqual(1, routes["r1"]["observation"]["versions"]["attempt_index"])
        loaded = load_population_memory(
            self.db, run_id="run", problem_spec={"domain": "algebra"})
        injected_routes = {r["content"].get("route_id"): r for r in loaded["observations"]
                           if r["content"].get("route_id")}
        self.assertEqual("candidate_guidance", injected_routes["r1"]["use"])
        self.assertEqual("diagnostic_only", injected_routes["r2"]["use"])
        self.assertEqual("advisory_only", injected_routes["r1"]["authority"])
        current = {"run_id": "current", "route_policy": {"policy_version": "serial-aprs-v1"},
                   "route_registry": [{"route_id": "current-route", "status": "eligible"}]}
        before = rate_routes(current)
        current["population_memory_advisory"] = loaded
        after = rate_routes(current)
        self.assertEqual(before[0][0]["vector"], after[0][0]["vector"])
        self.assertEqual(before[1]["selected_route_id"], after[1]["selected_route_id"])
        self.assertEqual(before[1]["candidate_route_ids"], after[1]["candidate_route_ids"])
        self.assertEqual("advisory_only", after[0][0]["snapshot"]["memory_hits"][0]["authority"])
        self.assertEqual([], verified_gain(current))

    def test_only_the_route_bound_to_the_delivered_answer_records_success(self):
        self.store.set_injection_enabled(self.scope, True, actor_id="owner")
        self.db.commit()
        state = {
            "phase": "TERMINAL", "status": "completed_llm_reviewed", "state_revision": 8,
            "problem_spec": {"domain": "Algebra"},
            "route_registry": [
                {"route_id": "delivered", "status": "completed",
                 "stop_reason": "final_answer_bound", "frontier_digest": "digest-delivered"},
                {"route_id": "other-complete", "status": "completed",
                 "stop_reason": "route_completed", "frontier_digest": "digest-other"},
            ],
        }

        self.assertTrue(capture_population_observation(
            self.db, run_id="run", state=state, budget={}, reviewed=True))

        route_outcomes = {
            item["observation"]["content"]["route_id"]: item["observation"]["outcome"]
            for item in self.store.list_observations(self.scope)
            if "route_id" in item["observation"]["content"]
        }
        self.assertEqual({"delivered": "success", "other-complete": "unknown"}, route_outcomes)

    def test_disabled_consent_and_failed_write_leave_no_partial_records(self):
        state = {"phase": "TERMINAL", "problem_spec": {"domain": "Algebra"},
                 "route_registry": [{"route_id": "r1", "frontier_digest": "digest",
                                     "status": "terminated", "stop_reason": "run_failed"}]}
        self.assertFalse(capture_population_observation(
            self.db, run_id="run", state=state, budget={}, reviewed=False))
        self.assertEqual([], self.store.list_observations(self.scope))
        self.store.set_injection_enabled(self.scope, True, actor_id="owner")
        self.db.commit()
        original = FaithfulMemoryStore.record_observation
        calls = []

        def fail_on_route(store, *args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                raise ValueError("injected_failure")
            return original(store, *args, **kwargs)

        with patch.object(FaithfulMemoryStore, "record_observation", fail_on_route):
            self.assertFalse(capture_population_observation(
                self.db, run_id="run", state=state, budget={}, reviewed=False))
        self.assertEqual([], self.store.list_observations(self.scope))
        self.assertTrue(capture_population_observation(
            self.db, run_id="run", state=state, budget={}, reviewed=False))
        routes = [r for r in self.store.list_observations(self.scope)
                  if r["observation"]["content"].get("route_id") == "r1"]
        self.assertEqual("failure", routes[0]["observation"]["outcome"])
        self.assertEqual("run_failed", routes[0]["observation"]["content"]["stop_reason"])

    def test_unreviewed_completed_route_and_unknown_budget_are_not_success(self):
        from showcase.solver_harness.faithful_memory_capture import _route_observation

        route = {"route_id": "r", "frontier_digest": "digest", "status": "completed"}
        self.assertEqual("unknown", _route_observation(route, "Algebra", False, False)["outcome"])
        self.assertEqual("unknown", _route_observation(route, "Algebra", True, True)["outcome"])
        self.assertEqual({"status": "unknown"},
                         _route_observation(route, "Algebra", False, True)["cost"])
        route["stop_reason"] = "untrusted free text"
        route["elimination_reason"] = "budget_exhausted"
        self.assertEqual("other", _route_observation(route, "Algebra", False, True)
                         ["content"]["stop_reason"])
        self.assertEqual("budget_exhausted", _route_observation(route, "Algebra", False, True)
                         ["content"]["elimination_reason"])

    def test_terminal_route_cost_is_frozen_before_later_run_spend(self):
        from showcase.solver_harness.route_commits import rating_patch

        state = {
            "run_id": "run",
            "route_policy": {"enabled": True, "policy_version": "serial-aprs-v1"},
            "route_registry": [{
                "route_id": "route-a", "status": "terminated", "frontier": [],
                "frontier_digest": "digest-a", "budget_at_start": {
                    "charged_tokens": 10, "http_attempts": 1, "logical_calls": 1,
                    "tool_calls": 0, "wall_time_seconds": 2.0,
                    "tool_wall_time_seconds": 0.0,
                },
            }],
            "route_budget": {"current_snapshot": {
                "charged_tokens": 35, "http_attempts": 3, "logical_calls": 3,
                "tool_calls": 1, "wall_time_seconds": 7.0,
                "tool_wall_time_seconds": 1.5, "unknown_attempts": 0,
                "unresolved_attempts": 0, "unknown_tool_calls": 0,
                "reserved_tokens": 0,
            }},
        }

        patch = rating_patch(state, 8)
        boundary = patch["route_evaluations"][-1]["evaluations"][0]["snapshot"]
        self.assertEqual("route-a", boundary["route_id"])
        self.assertEqual(25, boundary["consumed_resources"]["charged_tokens"])
        self.assertEqual(2, boundary["consumed_resources"]["http_attempts"])
        self.assertEqual(5.0, boundary["consumed_resources"]["wall_time_seconds"])

        later = {**state, **patch}
        later["route_evaluations"] = patch["route_evaluations"]
        later["route_budget"] = {"current_snapshot": {
            "charged_tokens": 90, "http_attempts": 9, "logical_calls": 9,
            "tool_calls": 4, "wall_time_seconds": 20.0,
            "tool_wall_time_seconds": 6.0, "unknown_attempts": 0,
            "unresolved_attempts": 0, "unknown_tool_calls": 0,
            "reserved_tokens": 0,
        }}
        rated = evaluate(later, later["route_registry"][0])
        self.assertEqual(25, rated["vector"]["cost"])
        self.assertEqual(2, rated["vector"]["http_attempts"])

    def test_route_cost_without_a_start_snapshot_remains_unknown(self):
        from showcase.solver_harness.aprs import evaluate

        rated = evaluate(
            {"route_budget": {"current_snapshot": {
                "charged_tokens": 100, "unknown_attempts": 0,
            }}},
            {"route_id": "route-without-baseline", "status": "active"},
        )
        self.assertIsNone(rated["vector"]["cost"])

    def test_current_aprs_exposes_memory_provenance_without_using_it_as_gain(self):
        state = {
            "run_id": "current-run",
            "route_policy": {"policy_version": "serial-aprs-v1"},
            "route_registry": [{"route_id": "current-route", "status": "active",
                                "frontier": [], "frontier_digest": "current-digest"}],
            "route_budget": {"current_snapshot": {"charged_tokens": 0,
                                                     "unknown_attempts": 0}},
        }
        before, _ = rate_routes(state)
        state["population_memory_advisory"] = {
            "authority": "advisory_only",
            "observations": [{
                "record_id": "imported-record",
                "outcome": "success",
                "use": "candidate_guidance",
                "review_status": "requires_current_run_review",
                "provenance": {
                    "source_run_id": "source-run",
                    "imported_by": "owner",
                    "imported_from": {"record_id": "source-record"},
                },
            }],
        }
        state["calls"] = {
            "call-one": {"route_id": "current-route", "population_memory_cost": {
                "status": "estimated", "estimated_tokens": 7,
                "additional_utf8_bytes": 21, "estimator_version": "memory-estimator-v1",
            }},
            "call-two": {"route_id": "current-route", "population_memory_cost": {
                "status": "estimated", "estimated_tokens": 11,
                "additional_utf8_bytes": 33, "estimator_version": "memory-estimator-v1",
            }},
            "other-route-call": {"route_id": "other-route", "population_memory_cost": {
                "status": "estimated", "estimated_tokens": 100,
                "additional_utf8_bytes": 300, "estimator_version": "memory-estimator-v1",
            }},
        }

        evaluations, decision = rate_routes(state)
        state["route_evaluations"] = [{"evaluations": evaluations}]
        state["aprs_decisions"] = [decision]
        projected = route_summary(state)

        self.assertEqual(before[0]["vector"], evaluations[0]["vector"])
        memory_cost = evaluations[0]["snapshot"]["population_memory_cost"]
        self.assertEqual("estimated", memory_cost["status"])
        self.assertEqual(18, memory_cost["estimated_tokens"])
        self.assertEqual(54, memory_cost["additional_utf8_bytes"])
        self.assertEqual(2, memory_cost["call_count"])
        self.assertEqual(["memory-estimator-v1"], memory_cost["estimator_versions"])
        self.assertEqual("serial-aprs-v1", decision["policy_version"])
        hit = projected["evaluations"][0]["memory_hits"][0]
        self.assertEqual("imported-record", hit["record_id"])
        self.assertEqual("source-run", hit["source_run_id"])
        self.assertEqual("source-record", hit["imported_from"]["record_id"])
        self.assertEqual([], verified_gain(state))

    def test_aprs_marks_route_memory_cost_unknown_if_any_injection_estimate_is_unknown(self):
        from showcase.solver_harness.aprs import rater_snapshot

        state = {
            "run_id": "current-run",
            "route_policy": {"policy_version": "serial-aprs-v1"},
            "route_registry": [],
            "calls": {
                "known": {"route_id": "route-a", "population_memory_cost": {
                    "status": "estimated", "estimated_tokens": 8,
                    "additional_utf8_bytes": 24, "estimator_version": "memory-estimator-v1",
                }},
                "unknown": {"route_id": "route-a", "population_memory_cost": {
                    "status": "unknown", "estimated_tokens": None,
                    "additional_utf8_bytes": None, "estimator_version": "memory-estimator-v1",
                }},
            },
        }

        memory_cost = rater_snapshot(state, {"route_id": "route-a"})["population_memory_cost"]

        self.assertEqual("unknown", memory_cost["status"])
        self.assertIsNone(memory_cost["estimated_tokens"])
        self.assertIsNone(memory_cost["additional_utf8_bytes"])
        self.assertEqual(2, memory_cost["call_count"])

        unattributed = rater_snapshot({
            "route_policy": {"policy_version": "serial-aprs-v1"},
            "population_memory_advisory": {"authority": "advisory_only", "observations": [{
                "record_id": "memory-record",
            }]},
            "calls": {},
        }, {"route_id": "route-a"})["population_memory_cost"]
        self.assertEqual("unknown", unattributed["status"])
        self.assertIsNone(unattributed["estimated_tokens"])
        self.assertIsNone(unattributed["additional_utf8_bytes"])

    def test_route_population_observation_keeps_only_route_boundary_cost(self):
        self.store.set_injection_enabled(self.scope, True, actor_id="owner")
        self.db.commit()
        route = {"route_id": "route-costed", "frontier_digest": "frontier-costed",
                 "status": "terminated", "graph_version": 3}
        state = {
            "phase": "TERMINAL", "status": "partial_budget_exhausted",
            "problem_spec": {"domain": "Algebra"}, "route_registry": [route],
            "route_evaluations": [{"evaluations": [{"snapshot": {
                "route_id": "route-costed", "route_status": "terminated", "cost_known": True,
                "cost_basis": "route_delta",
                "consumed_resources": {"charged_tokens": 23, "http_attempts": 2,
                                        "tool_calls": 1, "wall_time_seconds": 4.5},
            }}]}],
        }
        self.assertTrue(capture_population_observation(
            self.db, run_id="run", state=state,
            budget={"charged_tokens": 99, "http_attempts": 9}, reviewed=False))
        records = self.store.list_observations(self.scope)
        route_record = next(item for item in records
                            if item["observation"]["content"].get("route_id") == "route-costed")
        self.assertEqual({"status": "measured", "basis": "route_delta", "charged_tokens": 23,
                          "http_attempts": 2, "tool_calls": 1, "wall_time_seconds": 4.5},
                         route_record["observation"]["cost"])


class RouteObservationJobTest(StarJobFixture, unittest.TestCase):
    def test_completed_serial_job_captures_the_bound_route(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "direct"
        self.open_star(
            replies * 2,
            SHOWCASE_STAR_FEATURES={"problem_spec": True, "progress_scheduling": True,
                                    "serial_routes": True, "final_generation": True,
                                    "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(
                max_model_calls=8, max_http_attempts=8, max_tool_calls=0,
                max_tokens=100_000, max_runtime_seconds=1_100),
            SHOWCASE_FAITHFUL_MEMORY_ENABLED=True,
            SHOWCASE_POPULATION_MEMORY_ENABLED=True,
        )
        url = f"/api/sessions/{self.session}/memory/population/{self.session}"
        self.assertEqual(200, self.client.put(
            url + "/injection", json={"enabled": True}, headers=self.headers()).status_code)
        def submit_job():
            created = self.client.post(
                "/api/agent/jobs", json={"message": PROBLEM, "session_id": self.session,
                                          "solver_mode": "star_limited", "problem_spec": SPEC},
                headers=self.headers())
            self.assertEqual(202, created.status_code, created.get_json())
            return created.get_json()["job_id"]

        source_run_id = submit_job()
        self.assertEqual("succeeded", self.terminal(source_run_id)["status"])
        job_id = submit_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        observations = self.client.get(url).get_json()["observations"]
        routes = [item for item in observations
                  if item["observation"]["content"].get("route_id")
                  and item["provenance"].get("source_run_id") == job_id]
        self.assertEqual(1, len(routes))
        self.assertEqual("success", routes[0]["observation"]["outcome"])
        self.assertEqual(job_id, routes[0]["provenance"]["source_run_id"])
        report = self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]
        self.assertEqual("same_artifact", report["semantics"]["binding"])
        with closing(sqlite3.connect(self.app.config["SHOWCASE_DATABASE_PATH"])) as db:
            raw_state = db.execute("SELECT state_json FROM solver_states WHERE run_id=?",
                                   (job_id,)).fetchone()[0]
        completed = [item for item in json.loads(raw_state)["route_registry"]
                     if item["status"] == "completed"]
        self.assertEqual([routes[0]["observation"]["content"]["route_id"]],
                         [item["route_id"] for item in completed])
        state = json.loads(raw_state)
        route_id = completed[0]["route_id"]
        route_calls = [item for item in state["calls"].values()
                       if item.get("route_id") == route_id]
        costed_calls = [item for item in route_calls
                        if "population_memory_cost" in item]
        self.assertTrue(costed_calls, [
            (item.get("role"), item.get("route_id"), "population_memory_cost" in item)
            for item in state["calls"].values()
        ])
        frozen = next(
            evaluation["snapshot"]
            for group in state["route_evaluations"]
            for evaluation in group["evaluations"]
            if evaluation["route_id"] == route_id
            and evaluation["snapshot"].get("route_status") == "completed"
        )
        memory_cost = frozen["population_memory_cost"]
        route_boundary_calls = [item for item in route_calls
                                if item["request_revision"] <= frozen["state_revision"]]
        boundary_costed_calls = [item for item in route_boundary_calls
                                 if "population_memory_cost" in item]
        self.assertEqual("estimated", memory_cost["status"])
        self.assertEqual(len(boundary_costed_calls), memory_cost["call_count"])
        self.assertEqual(sum(item["population_memory_cost"]["estimated_tokens"]
                             for item in boundary_costed_calls), memory_cost["estimated_tokens"])
        public_cost = next(item["population_memory_cost"]
                           for item in route_summary(state)["evaluations"]
                           if item["route_id"] == route_id)
        self.assertEqual(memory_cost, public_cost)


if __name__ == "__main__":
    unittest.main()
