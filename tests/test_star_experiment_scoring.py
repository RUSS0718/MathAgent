"""Independent conclusion checks use synthetic rational arithmetic only."""
import unittest

from showcase.run_budget import RunBudgetLimits
from showcase.star_experiment_scoring import score
from tests.star_experiment_support import independent_review, synthetic_registration
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_final_proof import ONE_STEP, VALID_STEP_1, step
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import NEED_PLAN, VERDICT


class ExperimentScoringTest(unittest.TestCase):
    def bundle(self, answer):
        semantics=dict(execution="completed",whole_review="accepted",binding="same_artifact")
        checks=dict(proof_sources=[dict(step_ordinal=None)],source=dict(origin="unknown"))
        budget=dict(logical_calls=3,provider_known=dict(total_tokens=30))
        return dict(job=dict(status="succeeded",job_id="r",result=dict(final_response=answer)),
            report=dict(answer=answer,semantics=semantics,checks=checks,budget=budget),
            evidence=dict(semantics=semantics,verification=checks,budget=budget,run=dict(run_id="r")),
            run=dict(run_id="r"),delivery_wall_time_seconds=1)

    def test_rational_conclusions_not_spelling(self):
        q=synthetic_registration()["questions"]["short_b"]
        for answer, expected in [(r"Common denominator. Final answer: \frac{3}{4}","pass"),
                                 (r"Common denominator. Final answer: \dfrac{6}{8}","pass"),
                                 ("Common denominator. Final answer: 6 / 8","pass"),
                                 ("Intermediate 3/4. Final answer: 2/3","reject"),
                                 ("Final answer: cos(0)","undecided")]:
            with self.subTest(answer=answer):
                bundle=self.bundle(answer)
                result=score("short_b",q,bundle,independent_review("short_b",q,bundle),expected="3/4",stage="E1")
                self.assertEqual(expected,result["mathematics"])
        bundle=self.bundle("Final answer: 3/4")
        review=independent_review("short_b",q,bundle)
        review["obligations"]["explanation"]="reject"
        self.assertEqual("reject",score("short_b",q,bundle,review,expected="3/4")["mathematics"])

    def test_hash_bound_reviewer_identifies_conclusion_in_explained_answers(self):
        cases = [
            ("二加二等于四，因此结果是4。", "4", "4", "pass"),
            (r"\(\frac{1}{2}+\frac{1}{4}=\frac{3}{4}\)。通分后相加。", r"\frac{3}{4}", "3/4", "pass"),
            ("通分得到 **6/8**，约分得 **3/4**。", "**3/4**", "3/4", "pass"),
            (r"经通分相加，结果为 $\dfrac{6}{8}$。", r"$\dfrac{6}{8}$", "3/4", "pass"),
            ("中间候选3/4，重新计算的最终结果是2/3。", "2/3", "3/4", "reject"),
            ("Intermediate 3/4. Final answer: 2/3", "3/4", "3/4", "reject"),
            (r"结果是 \sqrt{1}，由定义得到。", r"\sqrt{1}", "3/4", "undecided"),
        ]
        for answer, conclusion, expected, verdict in cases:
            q=synthetic_registration()["questions"]["short_a" if expected == "4" else "short_b"]
            bundle=self.bundle(answer)
            review=independent_review("short_b",q,bundle)
            start=answer.rindex(conclusion)
            review["conclusion_span"]=dict(start=start,end=start+len(conclusion))
            with self.subTest(answer=answer):
                result=score("short_b",q,bundle,review,expected=expected,stage="E1")
                self.assertEqual(verdict,result["mathematics"])
                self.assertEqual(review["conclusion_span"],result["independent_review"]["conclusion_span"])
        answer="通分后，结果是3/4。"
        bundle=self.bundle(answer)
        review=independent_review("short_b",q,bundle)
        self.assertEqual("undecided",score("short_b",q,bundle,review,expected="3/4")["mathematics"])
        for span in [dict(start=-1,end=5),dict(start=0,end=999),dict(start=True,end=5),dict(start=0,end=0)]:
            review["conclusion_span"]=span
            self.assertEqual("undecided",score("short_b",q,bundle,review,expected="3/4")["mathematics"])
        start=answer.index("3/4")
        review["conclusion_span"]=dict(start=start,end=start+3)
        review["answer_sha256"]="wrong-answer"
        self.assertEqual("undecided",score("short_b",q,bundle,review,expected="3/4")["mathematics"])
        review=independent_review("short_b",q,bundle)
        review["conclusion_span"]=dict(start=start,end=start+3)
        review["obligations"]["explanation"]="reject"
        self.assertEqual("reject",score("short_b",q,bundle,review,expected="3/4")["mathematics"])

    def test_nonempty_public_sources_cannot_substitute_for_trusted_provenance(self):
        q=synthetic_registration()["questions"]["bound"]
        bundle=self.bundle("A square is nonnegative.")
        self.assertFalse(score("bound",q,bundle,independent_review("bound",q,bundle))["nonfastpath"])


class ExperimentProvenanceJobTest(StarJobFixture, unittest.TestCase):
    def test_score_reuses_same_run_snapshot_and_actual_outbound_chain(self):
        import sqlite3
        from contextlib import closing
        from copy import deepcopy
        from pathlib import Path

        from showcase.solver_harness.storage import SolverStateStore
        self.open_star([NEED_PLAN, ONE_STEP, step(VALID_STEP_1), VERDICT,
                        {"final_response":"A square is nonnegative."}, ACCEPT], SHOWCASE_STAR_FEATURES=FEATURES,
                        SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12,max_http_attempts=12))
        run_id=self.create_job()
        job=self.terminal(run_id)
        self.assertEqual("succeeded",job["status"],job)
        with closing(sqlite3.connect(Path(self.data_dir)/"showcase.sqlite3")) as connection:
            connection.row_factory=sqlite3.Row
            snapshot=SolverStateStore(connection).get_run(run_id)
        bundle=dict(job=job,report=self.report(run_id),
                    evidence=self.client.get(f"/api/runs/{run_id}/evidence").get_json(),
                    run=self.client.get(f"/api/runs/{run_id}").get_json())
        q=synthetic_registration()["questions"]["bound"]
        review=independent_review("bound",q,bundle)
        valid=score("bound",q,bundle,review,provenance=(snapshot,self.outbound))
        self.assertTrue(valid["nonfastpath"],valid)
        for mutation in ("missing_generator_proofs","wrong_wire","unknown_origin","malformed_proof"):
            changed,wire=deepcopy((snapshot,self.outbound))
            if mutation=="missing_generator_proofs":
                next(c for c in changed["state"]["calls"].values() if c["role"]=="final_generator")["request"].pop("step_proofs")
            elif mutation=="wrong_wire":
                next(c for c in wire if c["role"]=="final_generator")["step_proofs"]=[]
            elif mutation=="unknown_origin":
                changed["state"]["whole_solution_reviews"][-1]["source"]["origin"]="unrecognized"
            else:
                changed["state"]["whole_solution_reviews"][-1]["proof_sources"]=[None]
            with self.subTest(mutation=mutation):
                result=score("bound",q,bundle,review,provenance=(changed,wire))
                self.assertFalse(result["nonfastpath"],result)
                self.assertFalse(result["delivery"]["proof_delivered"],result)
