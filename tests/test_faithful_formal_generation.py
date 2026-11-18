"""Generated formal targets retain task ownership and public requirement failures."""

import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from showcase.formal import LeanTacticProver
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import ScriptedVerifierPort, SolverHarness
from showcase.solver_harness.formal_generation import AUTHORITY_QUESTION
from tests.star_product_support import StarJobFixture
from tests.test_faithful_auto_intake import (
    ACCEPT,
    CONFIG,
    POLISH,
    PROBLEM,
    SOLVED,
    SPEC,
    IntakePort,
)
from tests.test_faithful_s09_public_job import POLICY, TARGET, FakeTransport
from tests.test_faithful_s09_public_job import SPEC as RATIONAL_SPEC


class FormalGenerationTest(unittest.TestCase):
    def test_chinese_representation_selection_preserves_raw_source(self):
        from showcase.solver_harness.formal_generation import select_formalization
        from tests.test_formal_specification import (
            CHINESE_SPEC,
            PROBLEM_HASH,
            RATIONAL_TARGET,
            SPEC_HASH,
        )

        spec = deepcopy(CHINESE_SPEC)
        selection = select_formalization({"status": "proposed", "obligation_ids": ["O1"],
            "target": RATIONAL_TARGET}, spec, "intake:1")
        self.assertEqual("proposed", selection["status"])
        self.assertEqual({"problem_hash": PROBLEM_HASH, "specification_hash": SPEC_HASH,
            "obligation_ids": ["O1"], "generation_call_id": "intake:1"}, selection["source"])
        self.assertEqual(["forall x"], selection["target"]["quantifiers"])
        self.assertEqual(CHINESE_SPEC, spec)

    def test_legacy_required_selection_survives_clarification_without_new_metadata(self):
        from showcase.solver_harness.problem_intake import _apply_clarification
        from showcase.solver_harness.specification import normalize_problem_spec

        spec = normalize_problem_spec(SPEC)
        legacy = {"require_formal": True, "source": {"generation_call_id": "old-call"}}
        run = {"run_id": "legacy", "state_revision": 1, "state": {
            "clarification": {"answer": "x > 0"}, "problem_intake": {}, "formalization": legacy}}
        harness = Mock()
        with patch("showcase.solver_harness.problem_intake.answer_change", return_value={
                "updates": {"problem_spec": spec}, "event": {"event_id": "change"}}), patch(
                "showcase.solver_harness.formal_generation.explicit_requirement", return_value=None):
            _apply_clarification(harness, run, {"applicable_condition": "x > 0",
                "formalization": {"status": "unsupported", "require_formal": False}}, "new-call", 2)
        selection = harness.commit_event.call_args.kwargs["state_updates"]["formalization"]
        self.assertTrue(selection["require_formal"])
        self.assertEqual("legacy_frozen_selection", selection["requirement_authority"]["source"])
        self.assertEqual(legacy["source"], selection["requirement_authority"]["frozen_source"])
        self.assertNotIn("requirement_authority", legacy)

    def test_user_authority_ignores_false_missing_or_unsupported_proposal(self):
        from showcase.solver_harness.formal_generation import select_formalization
        from showcase.solver_harness.specification import normalize_problem_spec

        spec = normalize_problem_spec({**SPEC, "original_problem":
            PROBLEM + " Please provide a machine-checked proof."})
        for proposal in (None, {"status": "not_selected", "require_formal": False},
                         {"status": "unsupported", "require_formal": False}):
            with self.subTest(proposal=proposal):
                selected = select_formalization(proposal, spec, "intake:1")
                self.assertTrue(selected["require_formal"])
                self.assertEqual("original_problem", selected["requirement_authority"]["source"])

    def test_negated_quoted_conditional_and_unknown_machine_requests_need_clarification(self):
        from showcase.solver_harness.formal_generation import requirement_authority

        for text in ("No machine verification is requested.",
                     'Someone said "provide a machine-checked proof".',
                     "If useful, provide a machine-checked proof.",
                     'Someone said:\n"\nprovide a machine-checked proof.\n"',
                     "Explain Lean.", "用Lean验证结论", "Please certify this in Coq."):
            for proposed in (True, False):
                with self.subTest(text=text, proposed=proposed):
                    self.assertEqual("unresolved", requirement_authority(
                        text, {"require_formal": proposed})["status"])

    def test_only_raw_clarification_answer_can_authorize_machine_requirement(self):
        from showcase.solver_harness.formal_generation import (
            AUTHORITY_QUESTION,
            requirement_authority,
        )

        self.assertEqual("not_requested", requirement_authority(PROBLEM, {})["status"])
        self.assertEqual("unresolved", requirement_authority(PROBLEM, {
            "require_formal": True, "reason": "Please provide a machine-checked proof."},
            {"answer": "x > 0"})["status"])
        for answer, status in (("yes", "requested"), ("no", "not_requested"),
                               ("maybe", "unresolved")):
            self.assertEqual(status, requirement_authority(PROBLEM, {"require_formal": True},
                {**AUTHORITY_QUESTION, "answer": answer}, server_question_confirmed=True)["status"])
        self.assertEqual("requested", requirement_authority(PROBLEM, {"require_formal": False},
            {"answer": "请用Lean验证整个结论"})["status"])
        self.assertEqual("requested", requirement_authority("Please provide a machine-checked proof.",
            {"require_formal": False}, {**AUTHORITY_QUESTION, "answer": "no"})["status"])

    def test_intake_persists_generated_choice_without_extra_call(self):
        reply = deepcopy(SPEC)
        reply["original_problem"] += " Please provide a machine-checked proof."
        reply["formalization"] = {"status": "unsupported", "reason": "real root enumeration", "require_formal": True, "obligation_ids": [], "target": None}
        port = IntakePort([reply, SOLVED, POLISH])
        with SolverHarness(config=CONFIG, model_port=port, verifier_port=ScriptedVerifierPort([ACCEPT])) as harness:
            run = harness.solve(reply["original_problem"], {"run_id": "formal-generation"})
        selection = run["state"]["formalization"]
        self.assertEqual("unsupported", selection["status"])
        self.assertTrue(selection["require_formal"])
        self.assertEqual(3, len(port.requests))
        self.assertEqual("formal-generation:problem-intake:1", selection["source"]["generation_call_id"])


class GeneratedFormalPublicTest(StarJobFixture, unittest.TestCase):
    def test_explicit_client_policy_stays_required_without_authority_question(self):
        spec = deepcopy(RATIONAL_SPEC)
        spec["formalization"] = {"status": "unsupported", "reason": "not selected",
                                 "require_formal": False, "obligation_ids": [], "target": None}
        self.open_star([spec, SOLVED, POLISH, ACCEPT],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2),
            SHOWCASE_FORMAL_BACKEND=LeanTacticProver(FakeTransport()),
            SHOWCASE_FORMAL_VERIFICATION_CONFIG=POLICY)
        response = self.client.post("/api/agent/jobs", json={
            "message": spec["original_problem"], "session_id": self.session,
            "solver_mode": "star_limited", "formal_policy": {**POLICY, "require_formal": True}},
            headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(response.get_json()["job_id"])
        self.assertEqual("failed", job["status"])
        self.assertTrue(job["result"]["formal_verification"]["policy"]["require_formal"])
        self.assertEqual("unmet", job["result"]["formal_verification"]["assessment"]["status"])
        self.assertEqual(4, self.post.call_count)

    def test_unattributed_machine_requirement_asks_instead_of_imposing_l3(self):
        spec = deepcopy(RATIONAL_SPEC)
        spec["formalization"] = {"status": "unsupported", "reason": "unsupported_assumptions",
                                 "require_formal": True, "obligation_ids": [], "target": None}
        self.open_star([spec, SOLVED, POLISH, ACCEPT],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                "final_generation": True, "final_solution_review": True},
            SHOWCASE_FORMAL_GENERATION_REQUIRED=True,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        response = self.client.post("/api/agent/jobs", json={
            "message": spec["original_problem"], "session_id": self.session,
            "solver_mode": "star_limited"}, headers=self.headers())
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        job = self.wait_for(lambda: j if (j := self.job(job_id))["status"]
                            in {"waiting_input", "failed", "succeeded"} else None)
        self.assertEqual("waiting_input", job["status"])
        self.assertEqual(1, self.post.call_count)
        self.assertEqual("waiting", job["result"]["faithful"]["clarification"]["status"])
        question = job["result"]["faithful"]["clarification"]
        # The raw answer wins even when the next intake repeats its false claim.
        self.replies.insert(0, {**deepcopy(spec), "applicable_condition": "no"})
        answer = self.client.post(
            f"/api/agent/jobs/{job_id}/clarifications/{question['request_id']}",
            json={"task_id": job_id, "input_version": question["input_version"], "answer": "no"},
            headers=self.headers())
        self.assertEqual(202, answer.status_code, answer.get_json())
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final)
        self.assertEqual("default", final["result"]["formal_verification"]["assessment"]["status"])
        self.assertEqual(5, self.post.call_count)

    def test_ordinary_input_freezes_policy_or_keeps_required_unsupported(self):
        for supported in (True, False):
            with self.subTest(supported=supported):
                spec = deepcopy(RATIONAL_SPEC)
                spec["original_problem"] += " 请用Lean验证整个结论。"
                if not supported:
                    spec["domain"] = "reals"
                spec["formalization"] = {
                    "status": "proposed", "reason": "identity", "require_formal": False,
                    "obligation_ids": ["root:identity"], "target": {
                        k: v for k, v in TARGET.items() if k not in {"hash", "_lean_lhs", "_lean_rhs"}},
                }
                transport = FakeTransport()
                self.open_star([spec, SOLVED, POLISH, ACCEPT],
                    SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                        "final_generation": True, "final_solution_review": True},
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8,max_http_attempts=8,max_tool_calls=2),
                    SHOWCASE_FORMAL_GENERATION_REQUIRED=True,
                    SHOWCASE_FORMAL_BACKEND=LeanTacticProver(transport),
                    SHOWCASE_FORMAL_VERIFICATION_CONFIG=POLICY)
                response = self.client.post("/api/agent/jobs", json={
                    "message": spec["original_problem"], "session_id": self.session,
                    "solver_mode": "star_limited"}, headers=self.headers())
                self.assertEqual(202, response.status_code, response.get_json())
                job_id = response.get_json()["job_id"]
                job = self.terminal(job_id)
                result = job["result"]
                self.assertEqual(POLISH["solution_candidate"], result["final_response"])
                self.assertEqual("failed", job["status"])
                self.assertEqual("needs_review", result["solver"]["semantics"]["execution"])
                formal = result["formal_verification"]
                self.assertEqual("unmet", formal["assessment"]["status"])
                self.assertIn("schema_version", formal)
                service = self.app.extensions["showcase_workspace_service"]
                if supported:
                    identity = service.store.job_identity(job_id)
                    self.assertIn("source", identity["formal_policy"])
                    self.assertEqual(1, len(transport.calls))
                else:
                    self.assertEqual("unsupported", formal["status"])
                    self.assertEqual([], transport.calls)
                self.assertEqual(4, self.post.call_count)


class FormalSourceReviewPublicTest(StarJobFixture, unittest.TestCase):
    def start(self, spec, replies, transport=None):
        self.open_star([spec, *replies],
            SHOWCASE_STAR_FEATURES={"auto_problem_spec": True, "problem_spec": True,
                "final_generation": True, "final_solution_review": True},
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8, max_tool_calls=2),
            SHOWCASE_FORMAL_GENERATION_REQUIRED=True,
            SHOWCASE_FORMAL_BACKEND=LeanTacticProver(transport or FakeTransport()),
            SHOWCASE_FORMAL_VERIFICATION_CONFIG=POLICY)
        created = self.client.post('/api/agent/jobs', json={
            'message': spec['original_problem'], 'session_id': self.session,
            'solver_mode': 'star_limited'}, headers=self.headers())
        self.assertEqual(202, created.status_code, created.get_json())
        return created.get_json()['job_id']

    def settled(self, job_id):
        return self.wait_for(lambda: j if (j := self.job(job_id))['status']
                             in {'waiting_input', 'failed', 'succeeded'} else None)

    def answer(self, job_id, before):
        q = before['result']['faithful']['clarification']
        response = self.client.post(f"/api/agent/jobs/{job_id}/clarifications/{q['request_id']}",
            json={'task_id': job_id, 'input_version': q['input_version'], 'answer': 'yes'},
            headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())

    def choice(self, required=False):
        return {'status': 'unsupported', 'reason': 'unsupported_assumptions',
                'require_formal': required, 'obligation_ids': [], 'target': None}

    def test_model_reason_and_full_question_copy_cannot_authorize_yes(self):
        for question in ('Is x positive?', AUTHORITY_QUESTION['question']):
            with self.subTest(question=question):
                first = deepcopy(RATIONAL_SPEC)
                first['formalization'] = self.choice()
                first['clarification'] = {**AUTHORITY_QUESTION, 'question': question}
                second = deepcopy(RATIONAL_SPEC)
                second.update(applicable_condition='yes', formalization=self.choice(True))
                job_id = self.start(first, [second, SOLVED, POLISH, ACCEPT])
                before = self.settled(job_id)
                self.assertEqual('waiting_input', before['status'])
                self.answer(job_id, before)
                after = self.settled(job_id)
                self.assertEqual('waiting_input', after['status'])
                self.assertEqual(2, self.post.call_count)

    def test_conditional_newline_does_not_grant_hard_authority(self):
        for prefix in ('If useful:', 'Never:', 'Do not:'):
            with self.subTest(prefix=prefix):
                first = deepcopy(RATIONAL_SPEC)
                first['original_problem'] += f' {prefix}\nprovide a machine-checked proof.'
                first['formalization'] = self.choice()
                job_id = self.start(first, [SOLVED, POLISH, ACCEPT])
                self.assertEqual('waiting_input', self.settled(job_id)['status'])
                self.assertEqual(1, self.post.call_count)

    def test_server_authority_yes_does_not_become_math_assumption(self):
        first = deepcopy(RATIONAL_SPEC)
        first['formalization'] = self.choice(True)
        second = deepcopy(RATIONAL_SPEC)
        second.update(applicable_condition='yes', formalization={
            'status': 'proposed', 'reason': 'identity', 'require_formal': False,
            'obligation_ids': ['root:identity'], 'target': {k:v for k,v in TARGET.items()
                if k not in {'hash', '_lean_lhs', '_lean_rhs'}}})
        transport = FakeTransport()
        job_id = self.start(first, [second, SOLVED, POLISH, ACCEPT], transport)
        before = self.settled(job_id)
        self.assertEqual('waiting_input', before['status'])
        self.answer(job_id, before)
        final = self.settled(job_id)
        self.assertEqual(1, len(transport.calls))
        formal = final['result']['formal_verification']
        self.assertTrue(formal['policy']['require_formal'])
        self.assertNotEqual('spec_target_mismatch', formal.get('reason'))
        # L2 alone still cannot meet original-problem L3.
        self.assertEqual('unmet', formal['assessment']['status'])
        self.assertEqual('failed', final['status'])
