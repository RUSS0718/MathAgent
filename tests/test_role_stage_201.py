"""Focused saved findings contract; fixtures never dispatch a solver."""
import copy
import unittest

from showcase.role_stage_findings import collect

FORMULA = r"对任意实数 x，当 x >= 1 时，(x-1)^2 >= 0；等号当且仅当 x=1。"


def fixture(role="explore"):
    state = dict(run_id="run-a", problem_hash="problem-a", specification_version=1,
                 plan_version=1, attempt_index=0, state_revision=12, calls={})
    call = dict(call_id="call-a", role=role, status="completed", run_id="run-a",
                problem_hash="problem-a", plan_version=1, attempt_index=0,
                request_revision=10, request={"problem_spec_version": 1, "round": 1},
                response={"worked": [FORMULA], "failed": ["尚未处理 x<1"],
                          "candidates": ["下界候选"], "assessment": "SOLVED"})
    state["calls"]["call-a"] = call
    state["exploration_findings"] = [{**call["response"], "round": 1,
        "source": {"call_id": "call-a", "state_revision": 10,
                   "specification_version": 1, "round": 1},
        "provenance": "unverified_exploration"}]
    return state, {"event_id": "save-a", "type": "explore_assessed", "round": 1}


class FindingsTest(unittest.TestCase):
    def test_explore_keeps_complete_units_and_candidate_grade(self):
        state, event = fixture()
        before = copy.deepcopy(state)
        result, = collect(state, event)
        self.assertEqual(result["role"], "explore")
        self.assertEqual(result["sections"], [
            {"label": "探索尝试（未验证）", "text": FORMULA},
            {"label": "受阻方向", "text": "尚未处理 x<1"},
            {"label": "候选结论（未检查）", "text": "下界候选"}])
        self.assertEqual(result["check"], {"scope": "exploration_candidate",
            "status": "unreviewed", "label": "探索候选，未检查；不构成整题证明"})
        self.assertEqual(result["binding"]["call_id"], "call-a")
        self.assertEqual(result["binding"]["round"], 1)
        self.assertEqual(result["binding"]["event_id"], "save-a")
        self.assertEqual(state, before)
        self.assertEqual(collect(state, event), [result])

    def test_reasoner_extracts_claims_without_reading_argument(self):
        state, event = fixture("reason_noncoding")
        report = {"objective": "核对平方非负", "claims": [{"statement": FORMULA}],
                  "argument": "private argument", "blocked": True}
        state["steps"] = {"step-a": {"report": report, "status": "VERIFYING"}}
        state["calls"]["call-a"]["request"]["step"] = {
            "step_id": "step-a", "objective": "核对平方非负"}
        state["calls"]["call-a"]["response"] = {
            "claims": [{"statement": FORMULA}], "blocked": True,
            "argument": "private argument"}
        event.update(type="step_reported", step_id="step-a")
        result, = collect(state, event)
        self.assertEqual(result["role"], "reasoner")
        self.assertEqual(result["sections"], [
            {"label": "步骤目标", "text": "核对平方非负"},
            {"label": "阶段主张（待检查）", "text": FORMULA},
            {"label": "阻塞状态", "text": "该步骤已记录阻塞，具体原因未记录"}])
        self.assertEqual(result["check"]["status"], "unreviewed")
        self.assertEqual(result["check"]["scope"], "step_submission")
        self.assertEqual(result["binding"]["step_id"], "step-a")
        self.assertNotIn("private argument", str(result))

    def test_research_findings_require_saved_task_and_completed_source(self):
        state, event = fixture("researcher")
        state["calls"]["call-a"].update(
            session_key="research:run-a:task-a",
            response={"findings": [FORMULA, "该发现仅适用于 x>=1"]})
        state["reexploration_tasks"] = [{"task_id": "task-a", "status": "complete",
            "output_ref": "task-a", "prompt": "private task prompt"}]
        state["reexploration_findings"] = [{"task_id": "task-a",
            "provenance": "unverified_exploration",
            "output": {"findings": [FORMULA, "该发现仅适用于 x>=1"],
                       "report": "private report", "argument": "private argument"}}]
        event["type"] = "reexploration_completed"
        result, = collect(state, event)
        self.assertEqual(result["role"], "researcher")
        self.assertEqual(result["sections"], [
            {"label": "研究发现（未验证）", "text": FORMULA},
            {"label": "研究发现（未验证）", "text": "该发现仅适用于 x>=1"}])
        self.assertEqual(result["binding"]["task_id"], "task-a")
        self.assertNotIn("private", str(result))
        del state["reexploration_tasks"][0]["output_ref"]
        self.assertEqual(collect(state, event), [])

    def test_counterexample_not_found_preserves_search_scope_without_proof(self):
        state, event = fixture("researcher")
        result = {"verdict": "NOT_FOUND", "counterexample": "",
                  "assumptions_checked": ["x为实数且x>=1"],
                  "violated_conclusion": "", "searched_scope": "仅考察 1<=x<=2 的有限情形"}
        target = {"claim_index": 0, "claim": FORMULA,
                  "assumptions": ["x为实数且x>=1"], "approach": "平方非负"}
        state["calls"]["call-a"]["request"].update(
            action="counterexample_check", claim=FORMULA,
            assumptions=["x为实数且x>=1"], forbidden_direction="平方非负")
        state["calls"]["call-a"]["response"] = result
        state["calls"]["review-a"] = {
            **copy.deepcopy(state["calls"]["call-a"]), "call_id": "review-a",
            "role": "step_verifier", "request": {"problem_spec_version": 1,
                "step": {"step_id": "step-a"}, "report": {"claims": [{"statement": FORMULA}]}},
            "response": {"verdict": "CHALLENGE"}}
        state["steps"] = {"step-a": {"report": {"claims": [{"statement": FORMULA}]},
            "counterexample_checks": {"review-a": {"call_id": "call-a",
                "verifier_call_id": "review-a", "target": target,
                "status": "completed", "result": result}}}}
        event.update(type="counterexample_completed", step_id="step-a",
                     counterexample_verdict="NOT_FOUND")
        draft, = collect(state, event)
        self.assertEqual(draft["check"], {"scope": "counterexample_search",
            "status": "unreviewed", "label": "有限反例搜索未找到反例，不代表命题成立"})
        self.assertIn({"label": "反例搜索范围", "text": result["searched_scope"]}, draft["sections"])
        self.assertEqual(draft["binding"]["verifier_call_id"], "review-a")
        self.assertEqual(draft["binding"]["claim_index"], 0)
        state["calls"]["review-a"]["plan_version"] = 2
        self.assertEqual(collect(state, event), [])
        state["calls"]["review-a"]["plan_version"] = 1
        state["calls"]["call-a"]["request"]["claim"] = "另一主张"
        self.assertEqual(collect(state, event), [])

    def test_rejects_cross_task_role_version_or_ambiguous_source(self):
        for key, value in (("run_id", "run-b"), ("problem_hash", "problem-b"),
                           ("plan_version", 2), ("attempt_index", 1),
                           ("role", "planner"), ("status", "dispatched")):
            with self.subTest(key=key):
                state, event = fixture()
                state["calls"]["call-a"][key] = value
                self.assertEqual(collect(state, event), [])
        for field in ("run_id", "problem_hash", "specification_version", "plan_version", "attempt_index"):
            state, event = fixture()
            del state[field]
            self.assertEqual(collect(state, event), [])
        state, event = fixture()
        state["calls"]["call-a"]["request"]["problem_spec_version"] = 2
        self.assertEqual(collect(state, event), [])
        state, event = fixture()
        event["run_id"] = "other-run"
        self.assertEqual(collect(state, event), [])
        state, event = fixture()
        state["exploration_findings"][0]["source"]["call_id"] = "missing-call"
        self.assertEqual(collect(state, event), [])
        state, event = fixture()
        state["exploration_findings"].append(copy.deepcopy(state["exploration_findings"][0]))
        self.assertEqual(collect(state, event), [])

    def test_missing_or_private_content_never_becomes_a_summary(self):
        state, event = fixture()
        finding = state["exploration_findings"][0]
        response = state["calls"]["call-a"]["response"]
        for record in (finding, response):
            record.update(worked=["api_key=synthetic-private-value", FORMULA],
                          failed=[], candidates=[], argument="private argument",
                          report="private report", solution_candidate="private candidate",
                          full_prompt="private prompt", personal_data="private user")
        draft, = collect(state, event)
        self.assertNotIn("private", str(draft))
        self.assertEqual(draft["sections"][0]["text"], "[redacted]")
        self.assertEqual(draft["sections"][1]["text"], FORMULA)
        for record in (finding, response):
            record.update(worked=[], failed=[], candidates=[])
        self.assertEqual(collect(state, event), [])
        event["type"] = "call_audit"
        self.assertEqual(collect(state, event), [])

    def test_finite_computation_keeps_receipt_scope_and_unreviewed_grade(self):
        state, event = fixture()
        receipt = {"receipt_id": "receipt-a", "source_role": "explore", "step_id": None,
                   "review_round": 1, "attempt_index": 0, "plan_version": 1,
                   "specification_version": 1, "status": "success", "executed": True,
                   "output": "有限代入 x=1 得到 0", "tool": "python"}
        state["tool_receipts"] = [receipt]
        state["exploration_findings"][0]["computation"] = {
            "scope": "finite_computation", "receipts": [receipt]}
        draft, = collect(state, event)
        self.assertIn({"label": "有限计算结果（仅覆盖该计算）", "text": receipt["output"]},
                      draft["sections"])
        self.assertEqual(draft["binding"]["receipt_ids"], ["receipt-a"])
        self.assertEqual(draft["check"]["status"], "unreviewed")
        state["tool_receipts"][0] = {**receipt, "attempt_index": 2}
        self.assertNotIn(receipt["output"], str(collect(state, event)))

    def test_incomplete_nested_records_are_unavailable(self):
        for patch in ({"calls": None}, {"exploration_findings": None}):
            state, event = fixture()
            state.update(patch)
            self.assertEqual(collect(state, event), [])
        for step in (None, {"report": None}, {"report": {"claims": None}}):
            state, event = fixture("reasoner")
            state["steps"] = {"step-a": step}
            event.update(type="step_reported", step_id="step-a")
            self.assertEqual(collect(state, event), [])

    def test_explicit_unknown_source_and_foreign_checkpoint_never_publish(self):
        state, event = fixture()
        state["exploration_findings"][0]["source"] = {"status": "unknown"}
        self.assertEqual(collect(state, event), [])
        state, event = fixture("reasoner")
        state["calls"]["call-a"]["request"]["step"] = {"step_id": "step-a", "objective": "目标"}
        checkpoint = {"checkpoint_id": "cp-a", "claims": [{"statement": FORMULA}],
                      "blocked": True, "gaps": ["尚待核对取等条件"], "argument": "private"}
        state["calls"]["call-a"]["response"] = {"checkpoint": checkpoint}
        state["steps"] = {"step-a": {"report": {"objective": "目标", "claims": [{"statement": FORMULA}],
                                                     "blocked": True}, "checkpoint_id": "cp-a"}}
        event.update(type="step_reported", step_id="step-a", checkpoint_id="cp-a")
        draft, = collect(state, event)
        self.assertIn({"label": "未解决点", "text": "尚待核对取等条件"}, draft["sections"])
        self.assertNotIn("具体原因未记录", str(draft))
        event["checkpoint_id"] = "cp-b"
        self.assertEqual(collect(state, event), [])

    def test_reasoner_never_reuses_same_claim_from_another_step_or_version(self):
        state, event = fixture("reasoner")
        report = {"objective": "目标", "claims": [{"statement": FORMULA}], "blocked": False}
        state["steps"] = {"step-a": {"report": report}}
        call = state["calls"]["call-a"]
        call["response"] = report
        call["request"]["step"] = {"step_id": "step-b", "objective": "目标"}
        event.update(type="step_reported", step_id="step-a")
        self.assertEqual(collect(state, event), [])
        call["request"]["step"]["step_id"] = "step-a"
        self.assertEqual(len(collect(state, event)), 1)
        call["plan_version"] = 2
        self.assertEqual(collect(state, event), [])

    def test_all_saved_research_units_remain_in_save_order(self):
        state, event = fixture("researcher")
        state.update(calls={}, reexploration_tasks=[], reexploration_findings=[])
        event["type"] = "reexploration_completed"
        for i in range(4):
            task_id = f"task-{i}"
            text = f"成果{i}：" + FORMULA * 30
            state["calls"][f"call-{i}"] = {
                "call_id": f"call-{i}", "role": "researcher", "status": "completed",
                "run_id": "run-a", "problem_hash": "problem-a", "plan_version": 1,
                "attempt_index": 0, "request_revision": i + 1,
                "request": {"problem_spec_version": 1},
                "session_key": f"research:run-a:{task_id}", "response": {"findings": [text]}}
            state["reexploration_tasks"].append(
                {"task_id": task_id, "status": "complete", "output_ref": task_id})
            state["reexploration_findings"].append(
                {"task_id": task_id, "output": {"findings": [text]}})
        before = copy.deepcopy(state)
        drafts = collect(state, event)
        self.assertEqual(len(drafts), 4)
        for i, draft in enumerate(drafts):
            self.assertEqual(draft["sections"][0]["text"], f"成果{i}：" + FORMULA * 30)
        self.assertEqual(state, before)
        self.assertEqual(collect(state, {**event, "type": "status_changed"}), [])

    def test_explicit_event_role_is_bound_and_aliases_use_original_node(self):
        state, event = fixture("explore_polish")
        event["role"] = "explore_polish"
        draft, = collect(state, event)
        self.assertEqual(draft["role"], "explore")
        event["role"] = "researcher"
        self.assertEqual(collect(state, event), [])
