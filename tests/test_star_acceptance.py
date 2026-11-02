"""RB-01 acceptance through a real authenticated Job, with offline transport."""

import sqlite3
import unittest
from contextlib import closing
from copy import deepcopy
from pathlib import Path

from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness.storage import SolverStateStore
from showcase.star_acceptance import evaluate_delivery
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture
from tests.test_star_product_final_proof import ONE_STEP, VALID_STEP_1, step
from tests.test_star_product_planning import FEATURES
from tests.test_star_product_tools import VERDICT


class DeliveredReviewTest(StarJobFixture, unittest.TestCase):
    def test_early_reject_and_multiple_candidates_select_actual_delivery(self):
        self.open_star(
            [
                SOLVED,
                POLISH,
                {"verdict": "REJECT", "reason": "needs proof"},
                ONE_STEP,
                step(VALID_STEP_1),
                VERDICT,
                {"final_response": "draft"},
                {"verdict": "REJECT", "reason": "gap"},
                {"final_response": "final with proof"},
                ACCEPT,
            ],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=16, max_http_attempts=16),
        )
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        database = Path(self.data_dir) / "showcase.sqlite3"
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            run = SolverStateStore(connection).get_run(job_id)
        first_final = next(c for c in self.outbound if c["role"] == "final_generator")
        first_review = next(c for c in self.outbound if c["role"] == "whole_solution_verifier")
        self.assertNotEqual(first_final["step_proofs"], first_review.get("step_proofs"))
        result = evaluate_delivery(job, run, self.outbound)
        self.assertEqual(self.report(job_id)["semantics"], result.get("semantics"))
        self.assertTrue(result["review_bound"], result)
        self.assertTrue(result["proof_delivered"], result)
        self.assertTrue(result["nonfastpath"], result)
        self.assertEqual(self.outbound[-1]["call_id"], result["review_call_id"])
        self.assertEqual(self.outbound[-2]["call_id"], result["generator_call_id"])
        self.assertEqual(3, result["candidate_version"])
        self.assertEqual(1, result["proof_count"])
        # Counterfactuals use the same completed public Job and captured wire.
        for label, mutate in [
            ("changed_text", lambda j, r, c: j["result"].update(final_response="changed")),
            (
                "wrong_plan",
                lambda j, r, c: r["state"]["whole_solution_reviews"][-1]["source"].update(
                    plan_version=99
                ),
            ),
            (
                "wrong_attempt",
                lambda j, r, c: r["state"]["whole_solution_reviews"][-1]["source"].update(
                    attempt_index=99
                ),
            ),
            (
                "wrong_version",
                lambda j, r, c: r["state"]["whole_solution_reviews"][-1]["source"].update(
                    candidate_version=1
                ),
            ),
            (
                "wrong_run",
                lambda j, r, c: r["state"]["whole_solution_reviews"][-1]["source"].update(
                    run_id="other"
                ),
            ),
            (
                "forged_call",
                lambda j, r, c: r["state"]["whole_solution_reviews"][-1]["source"].update(
                    call_id="forged"
                ),
            ),
            (
                "incomplete_review",
                lambda j, r, c: r["state"]["calls"][c[-1]["call_id"]].update(
                    status="unknown_outcome"
                ),
            ),
            (
                "tool_only",
                lambda j, r, c: r["state"]["calls"][c[-1]["call_id"]]["response"].update(
                    tool_request={"tool": "python"}
                ),
            ),
        ]:
            with self.subTest(label=label):
                changed_job, changed_run, changed_contexts = deepcopy((job, run, self.outbound))
                mutate(changed_job, changed_run, changed_contexts)
                rejected = evaluate_delivery(changed_job, changed_run, changed_contexts)
                self.assertFalse(rejected["review_bound"], rejected)
                self.assertFalse(rejected["proof_delivered"], rejected)
        altered = deepcopy(self.outbound)
        altered[-1]["step_proofs"] = []
        self.assertFalse(evaluate_delivery(job, run, altered)["proof_delivered"])
        self.assertEqual(10, self.post.call_count)

    def test_saved_public_job_replay_is_zero_dispatch_and_detects_corruption(self):
        import hashlib
        import json
        import tempfile
        from unittest.mock import patch

        from showcase.star_replay import replay_saved_batch

        self.open_star([SOLVED, POLISH, {**ACCEPT, "tool_request": None}])
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"])
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory)
            (batch / "data").mkdir()
            with closing(sqlite3.connect(Path(self.data_dir, "showcase.sqlite3"))) as source:
                with closing(sqlite3.connect(batch / "data/showcase.sqlite3")) as target:
                    source.backup(target)
            for name, value in [
                ("job", job),
                ("report", self.report(job_id)),
                ("evidence", self.client.get(f"/api/runs/{job_id}/evidence").get_json()),
                ("role-contexts", self.outbound),
                ("acceptance", {"proof_delivered": False}),
            ]:
                (batch / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
            hashes = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in batch.iterdir()
                if p.is_file()
            }
            (batch / "hashes.json").write_text(json.dumps(hashes), encoding="utf-8")
            with patch(
                "llm_client.requests.post", side_effect=AssertionError("no dispatch")
            ) as post:
                result = replay_saved_batch(batch, original_runner_version="fixture-v0")
                self.assertEqual("verified", result["integrity"])
                self.assertTrue(result["selection"]["review_bound"], result)
                self.assertFalse(result["selection"]["nonfastpath"])
                self.assertEqual(0, result["external_dispatches"])
                post.assert_not_called()
                with closing(sqlite3.connect(batch / "data/showcase.sqlite3")) as connection:
                    raw = connection.execute(
                        "SELECT state_json FROM solver_states WHERE run_id=?", (job_id,)
                    ).fetchone()[0]
                    snapshot = json.loads(raw)
                    snapshot["whole_solution_reviews"][-1]["source"]["call_id"] = "forged"
                    connection.execute(
                        "UPDATE solver_states SET state_json=? WHERE run_id=?",
                        (json.dumps(snapshot), job_id),
                    )
                    connection.commit()
                forged = replay_saved_batch(batch, original_runner_version="fixture-v0")
                self.assertEqual("failed", forged["integrity"])
                self.assertFalse(forged["selection"]["review_bound"])
                (batch / "data/showcase.sqlite3").unlink()
                missing = replay_saved_batch(batch, original_runner_version="fixture-v0")
                self.assertEqual("failed", missing["integrity"])
                self.assertFalse(missing["selection"]["review_bound"])
                (batch / "role-contexts.json").write_text("[]", encoding="utf-8")
                damaged = replay_saved_batch(batch, original_runner_version="fixture-v0")
                self.assertEqual("failed", damaged["integrity"])
                self.assertFalse(damaged["selection"]["review_bound"])

    def test_same_candidate_text_in_distinct_versions_uses_candidate_lineage(self):
        from tests.test_star_product_tools import NEED_PLAN

        self.open_star(
            [
                NEED_PLAN,
                ONE_STEP,
                step(VALID_STEP_1),
                VERDICT,
                {"final_response": "same answer"},
                {"verdict": "REJECT", "reason": "recheck"},
                {"final_response": "same answer"},
                ACCEPT,
            ],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12),
        )
        job_id = self.create_job()
        job = self.terminal(job_id)
        with closing(
            sqlite3.connect(Path(self.data_dir, "showcase.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            run = SolverStateStore(connection).get_run(job_id)
        result = evaluate_delivery(job, run, self.outbound)
        self.assertTrue(result["proof_delivered"], result)
        self.assertEqual(self.outbound[-2]["call_id"], result["generator_call_id"])

    def test_replan_and_repaired_review_with_computation_select_completed_lineage(self):
        from showcase.tools import ToolRegistry
        from tests.star_product_support import RawProviderContent
        from tests.test_star_product_continue_identity import PROPOSE_REPLAN
        from tests.test_star_product_tools import NEED_PLAN
        from tests.test_star_product_verifier_compute import REQUEST

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: 2)
        second_plan = deepcopy(ONE_STEP)
        second_plan["version"] = 2
        ruling = {
            "decision": "APPROVE_REPLAN",
            "reason_summary": "replace failed route",
            "plan_summary": "direct addition",
            "forbidden_directions": ["old route"],
            "reusable_results": [],
            "trace_back_to": None,
        }
        self.open_star(
            [
                NEED_PLAN,
                ONE_STEP,
                step("dead route"),
                PROPOSE_REPLAN,
                ruling,
                second_plan,
                step(VALID_STEP_1),
                VERDICT,
                {"final_response": "final with proof"},
                RawProviderContent("{"),
                {"verdict": "ACCEPT", "reason": "compute first", "tool_request": REQUEST},
                ACCEPT,
            ],
            SHOWCASE_STAR_FEATURES={**FEATURES, "local_code_tool": True},
            SHOWCASE_STAR_REGISTRY=registry,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=20, max_http_attempts=20),
        )
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        with closing(
            sqlite3.connect(Path(self.data_dir, "showcase.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            run = SolverStateStore(connection).get_run(job_id)
        result = evaluate_delivery(job, run, self.outbound)
        self.assertTrue(result["proof_delivered"], result)
        self.assertEqual(2, run["state"]["plan_version"])
        self.assertEqual(self.outbound[-1]["call_id"], result["review_call_id"])
        self.assertIn(":tool-1", result["review_call_id"])
        self.assertEqual(1, self.report(job_id)["budget"]["tool_calls"])

    def test_explicit_retry_selects_new_completed_review_and_keeps_unknown(self):
        import uuid

        import requests

        from tests.test_star_product_tools import NEED_PLAN

        self.open_star(
            [
                NEED_PLAN,
                ONE_STEP,
                step(VALID_STEP_1),
                VERDICT,
                {"final_response": "final with proof"},
                requests.Timeout("unknown"),
                ACCEPT,
            ],
            SHOWCASE_STAR_FEATURES=FEATURES,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12),
        )
        job_id = self.create_job()
        first = self.terminal(job_id)
        self.assertEqual("failed", first["status"])
        old = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
        response = self.client.post(
            f"/api/agent/jobs/{job_id}/resume",
            json={"retry_call": {"call_id": old, "new_call_id": str(uuid.uuid4())}},
            headers=self.headers(),
        )
        self.assertEqual(202, response.status_code, response.get_json())
        job = self.terminal(job_id)
        self.assertEqual("succeeded", job["status"], job)
        with closing(
            sqlite3.connect(Path(self.data_dir, "showcase.sqlite3").as_uri() + "?mode=ro", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            run = SolverStateStore(connection).get_run(job_id)
        result = evaluate_delivery(job, run, self.outbound)
        self.assertTrue(result["proof_delivered"], result)
        self.assertNotEqual(old, result["review_call_id"])
        self.assertEqual(old, run["state"]["calls"][result["review_call_id"]]["retry_of"])
        self.assertEqual("unknown_outcome", run["state"]["calls"][old]["status"])
        self.assertEqual(
            first["result"]["budget"]["deadline_at"], job["result"]["budget"]["deadline_at"]
        )

    def test_public_jobs_reject_changed_forged_stale_or_incomplete_reviews(self):
        from unittest.mock import patch

        from showcase.solver_harness.final_binding import review_record
        from tests.test_star_product_tools import NEED_PLAN

        for corruption in ["changed_text", "wrong_version", "forged_call", "incomplete_review"]:
            with self.subTest(corruption=corruption):
                replies = [
                    NEED_PLAN,
                    ONE_STEP,
                    step(VALID_STEP_1),
                    VERDICT,
                    {"final_response": "final with proof"},
                    ACCEPT,
                ]
                self.open_star(
                    replies,
                    SHOWCASE_STAR_FEATURES=FEATURES,
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12),
                )

                def corrupt_record(*args, **kwargs):
                    record = review_record(*args, **kwargs)
                    if corruption == "wrong_version":
                        record["source"]["candidate_version"] = 77
                    elif corruption == "forged_call":
                        record["source"]["call_id"] = "forged"
                    elif corruption == "incomplete_review":
                        record["source"]["call_id"] = self.outbound[-2]["call_id"]
                    return record

                with patch(
                    "showcase.solver_harness.finalize.review_record", side_effect=corrupt_record
                ):
                    if corruption == "changed_text":
                        with patch(
                            "showcase.star_product_pipeline.export_result",
                            return_value={"final_response": "unreviewed rewrite"},
                        ):
                            job_id = self.create_job()
                            job = self.terminal(job_id)
                    else:
                        job_id = self.create_job()
                        job = self.terminal(job_id)
                with closing(
                    sqlite3.connect(
                        Path(self.data_dir, "showcase.sqlite3").as_uri() + "?mode=ro", uri=True
                    )
                ) as connection:
                    connection.row_factory = sqlite3.Row
                    run = SolverStateStore(connection).get_run(job_id)
                result = evaluate_delivery(job, run, self.outbound)
                self.assertFalse(result["review_bound"], result)
                self.assertFalse(result["proof_delivered"], result)
                self.assertEqual(6, self.post.call_count)
