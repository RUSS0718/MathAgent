"""Public native result adoption preserves source grade and parent authority."""

import unittest

from tests import test_faithful_s10_native_checkpoint as native_support
from tests.star_product_support import StarJobFixture


class SerialAdoptionTest(unittest.TestCase):
    setUp = native_support.NativeCheckpointTest.setUp
    reserve = native_support.NativeCheckpointTest.reserve

    def test_native_children_are_independently_reviewed_and_parent_is_unchanged(self):
        native_support.NativeCheckpointTest.test_native_children_are_independently_reviewed_and_parent_is_unchanged(
            self
        )
        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.serial_intervention import adopt_result, result_reference

        with SolverHarness(
            store=self.store,
            config={
                "max_model_calls": 20,
                "features": {
                    "problem_spec": True,
                    "progress_scheduling": True,
                    "serial_routes": True,
                    "proof_graph": True,
                    "stream_recovery": True,
                    "persistent_sessions": True,
                    "final_generation": True,
                    "final_solution_review": True,
                },
            },
        ) as harness:
            parent = harness.get_run("native-parent")
            # Enabling the service later must not authorize an existing Run or
            # change its identity hash on resume.
            from showcase.solver_harness.serial_intervention import advance
            from tests.test_faithful_s03_job import SPEC
            with SolverHarness(store=self.store, config=harness._config,
                               intervention_enabled=True) as reopened:
                resumed = reopened.solve(SPEC["original_problem"], {
                    "run_id": "native-parent", "problem_spec": SPEC,
                    "plan": parent["state"]["plan"]})
                self.assertEqual(parent["state"]["config_hash"], resumed["state"]["config_hash"])
                self.assertNotIn("serial_intervention_permission", resumed["state"])
                self.assertEqual(resumed, advance(reopened, resumed, SPEC["original_problem"]))
            reference = result_reference(self.engine, "native-pair", "intervention")
            before = parent["state"].get("verified_results_ledger", [])
            adopted = adopt_result(harness, parent, self.engine, reference)
            self.assertEqual(
                "adopted", adopted["state"]["serial_intervention"]["adoptions"][-1]["status"]
            )
            self.assertEqual(before, adopted["state"].get("verified_results_ledger", []))
            self.assertEqual(
                "llm_reviewed",
                adopted["state"]["serial_intervention"]["adoptions"][-1]["evidence_grade"],
            )
            from copy import deepcopy

            from showcase.solver_harness.serial_intervention import applicable_results
            from tests.test_faithful_s03_job import SPEC
            foreign = harness.solve(SPEC["original_problem"], {
                "run_id": "foreign-parent", "problem_spec": SPEC,
                "plan": parent["state"]["plan"]})
            foreign = harness.commit_event("foreign-parent",
                expected_revision=foreign["state_revision"],
                event={"event_id": "seed-adopted-reference", "type": "test_seed"},
                state_updates={key: deepcopy(adopted["state"][key]) for key in (
                    "serial_intervention", "steps", "current_step", "plan", "plan_version",
                    "problem_spec", "specification_version", "accepted_results")
                    if key in adopted["state"]})
            rejected_foreign = adopt_result(harness, foreign, self.engine, reference)
            self.assertEqual("scope_changed", rejected_foreign["state"]["serial_intervention"]["adoptions"][-1]["reason"])
            self.assertEqual([], applicable_results(harness, rejected_foreign))

            from showcase.solver_harness.serial_intervention import public_projection

            public = public_projection(adopted["state"]["serial_intervention"])
            self.assertEqual(
                {"pair_id", "arm", "source_version", "scope"},
                set(public["adoptions"][-1]["reference"]),
            )
            invalid = dict(reference, result_id="missing-proof")
            rejected_proof = adopt_result(harness, adopted, self.engine, invalid)
            self.assertEqual(
                "source_proof_not_applicable",
                rejected_proof["state"]["serial_intervention"]["adoptions"][-1]["reason"],
            )
            adopted = rejected_proof
            stale = dict(reference, source_version="stale")
            rejected = adopt_result(harness, adopted, self.engine, stale)
            self.assertEqual(
                "source_version_changed",
                rejected["state"]["serial_intervention"]["adoptions"][-1]["reason"],
            )


class SerialPublicJobTest(StarJobFixture, unittest.TestCase):
    def test_ordinary_obstacle_runs_native_pair_and_continues_with_whole_review(self):
        self.run_intervention()

    def test_unknown_arm_is_not_resent_by_refresh(self):
        self.run_intervention("unknown")

    def test_cancel_in_first_arm_stops_all_further_dispatch(self):
        self.run_intervention("cancel")

    def test_two_jobs_share_store_without_sharing_experiment(self):
        self.run_intervention(shared=True)

    def test_adoption_after_two_rejected_challenges_gets_fresh_review(self):
        from unittest.mock import patch

        from showcase.solver_harness import SolverHarness

        dispatch = SolverHarness.dispatch
        replayed = []

        def replay_receipt(harness, run, port, request):
            reply = dispatch(harness, run, port, request)
            if "-adoption-" in request["call_id"] and not harness._product_recovery:
                before = len(self.outbound)
                latest = harness.get_run(run["run_id"])
                self.assertEqual(reply, dispatch(harness, latest, port, request))
                self.assertEqual(before, len(self.outbound))
                run.update(harness.get_run(run["run_id"]))
                replayed.append(request["call_id"])
            return reply

        self.enterContext(patch.object(SolverHarness, "dispatch", replay_receipt))
        # Isolate the challenge-limit obstacle from the independent progress
        # policy, which normally escalates after the first failed challenge.
        with patch("showcase.solver_harness.progress.review_progress", return_value={}):
            self.run_intervention(rounds=2)
        self.assertEqual(1, len(replayed))

    def test_disabled_intervention_permission_keeps_ordinary_calls(self):
        self.run_intervention(enabled=False)

    def run_intervention(self, fault=None, shared=False, rounds=1, enabled=True):
        from copy import deepcopy

        from tests.test_faithful_service_population import FaithfulPopulationJobTest

        original_open = self.open_star

        def opened(replies, **config):
            proposal_runs = set()

            def provider(request):
                if request.get("serial_intervention_decision"):
                    proposal_runs.add(request["run_id"])
                    return {
                        "decision": "intervene",
                        "reason": "Direct approach stalled",
                        "hypothesis": "Construction establishes the missing value",
                        "method_id": "construction",
                    }
                if request.get("execution_mode_decision"):
                    return {"mode": "keep", "reason": "Continue serial"}
                if request["role"] == "meta":
                    return {
                        "decision": "CONTINUE",
                        "reason_summary": "Use the experiment result",
                        "plan_summary": "",
                        "forbidden_directions": [],
                        "reusable_results": [],
                        "trace_back_to": None,
                    }
                if request["role"] == "step_verifier" and request["run_id"] not in proposal_runs:
                    return {
                        "goal_gate": "NO",
                        "logic_gate": "FAIL",
                        "verdict": "CHALLENGE",
                        "objection": "The direct argument does not establish the value",
                        "obligation_evidence": [],
                    }
                if request["run_id"] in proposal_runs and request["role"] == "reasoner" and fault:
                    if fault == "unknown":
                        from requests.exceptions import ConnectionError

                        raise ConnectionError("unknown experiment arm")
                    canceled = self.client.post(
                        f"/api/agent/jobs/{request['run_id']}/cancel",
                        json={},
                        headers=self.headers(),
                    )
                    self.assertEqual(200, canceled.status_code)
                reply = deepcopy(replies[0](request))
                if rounds == 2 and request["role"] == "reasoner":
                    reply["argument"] = f"Attempt {request.get('round', 0)}: direct addition gives 2"
                if request["run_id"] in proposal_runs and request["role"] == "reasoner":
                    reply["argument"] = "Construction proves 1+1=2"
                if request["role"] == "planner":
                    reply["alternative_plans"] = []
                return reply

            original_open([provider] * 80, SHOWCASE_FAITHFUL_INTERVENTION_ENABLED=enabled, **config)
            pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
            pipeline.full_config["max_challenge_rounds"] = rounds
            pipeline.population_config["max_challenge_rounds"] = rounds
            pipeline.full_config["population_policy"]["max_challenge_rounds"] = rounds

        self.open_star = opened
        job_id, final, _ = FaithfulPopulationJobTest.run_plain_submission(
            self,
            selection_mode="serial",
            fault="cancel" if fault == "cancel" else "mode_unknown" if fault or not enabled else None,
        )
        solver = final["result"]["solver"]
        if not enabled:
            self.assertFalse(any(r.get("serial_intervention_decision") or ":pair:" in r["call_id"]
                                 for r in self.outbound))
            self.assertFalse(solver.get("serial_intervention"))
            self.assertEqual(40, final["result"]["budget"]["limits"]["max_model_calls"])
            before = len(self.outbound)
            self.job(job_id)
            self.report(job_id)
            self.assertEqual(before, len(self.outbound))
            return
        if fault:
            arms = [
                r["call_id"]
                for r in self.outbound
                if r["role"] == "reasoner" and ":pair:" in r["call_id"]
            ]
            self.assertEqual(1 if fault == "cancel" else 2, len(arms))
            self.assertEqual(len(arms), len(set(arms)))
            before = len(self.outbound)
            self.job(job_id)
            self.report(job_id)
            self.assertEqual(before, len(self.outbound))
            return
        self.assertEqual("completed", solver["serial_intervention"]["status"], solver)
        self.assertEqual("adopted", solver["serial_intervention"]["adoptions"][0]["status"])
        self.assertEqual(solver["serial_intervention"], solver["progress"]["serial_intervention"])
        self.assertGreaterEqual(sum(r["role"] == "step_verifier" for r in self.outbound), 5)
        self.assertTrue(any(r["role"] == "whole_solution_verifier" for r in self.outbound))
        before = len(self.outbound)
        self.job(job_id)
        self.report(job_id)
        self.assertEqual(before, len(self.outbound))

        if rounds == 2:
            parent_reviews = [r for r in self.outbound if r["role"] == "step_verifier"
                              and ":pair:" not in r["call_id"]]
            self.assertEqual([0, 1, 2], [r["round"] for r in parent_reviews[:3]])
            self.assertEqual(4, len(parent_reviews))
            self.assertNotEqual(parent_reviews[2]["report"], parent_reviews[3]["report"])
            self.assertEqual(len(parent_reviews), len({r["call_id"] for r in parent_reviews}))

        if shared:
            from unittest.mock import patch

            from tests.test_star_population_runtime import PROBLEM

            pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
            with patch.object(pipeline, "full_gaps", return_value=[]):
                response = self.client.post("/api/agent/jobs", headers=self.headers(),
                    json={"message": PROBLEM, "session_id": self.session})
                self.assertEqual(202, response.status_code)
                second_id = response.get_json()["job_id"]
                second = self.terminal(second_id, timeout=20)
            second_solver = second["result"]["solver"]
            self.assertEqual("completed", second_solver["serial_intervention"]["status"])
            self.assertEqual("adopted", second_solver["serial_intervention"]["adoptions"][0]["status"])
            self.assertNotEqual(solver["serial_intervention"]["pair_id"],
                                second_solver["serial_intervention"]["pair_id"])
            for identity in (job_id, second_id):
                arms = [r for r in self.outbound if r["run_id"] == identity
                        and r["role"] == "reasoner" and ":pair:" in r["call_id"]]
                self.assertEqual(2, len(arms))
                self.assertEqual(40, self.job(identity)["result"]["budget"]["limits"]["max_model_calls"])
