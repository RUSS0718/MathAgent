"""Serialization repair preserves the research action consumed by its Verifier."""

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

from showcase.run_budget import RunBudgetLimits
from tests.format_repair_worker_100 import config
from tests.star_product_support import RawProviderContent, StarJobFixture
from tests.test_star_product_counterexample import (
    ACCEPT,
    FEATURES,
    FOUND,
    NEED_PLAN,
    NOT_FOUND,
    PLAN,
    PROBLEM,
    STEP,
)


class FormatRepairCounterexampleTest(StarJobFixture, unittest.TestCase):
    def test_completed_research_repair_resumes_original_review_before_next_reasoner(self):
        self.assert_research_recovery(double_repair=False)

    def test_double_verifier_and_research_repair_replays_original_roots_after_exit(self):
        self.assert_research_recovery(double_repair=True)

    def assert_research_recovery(self, *, double_repair):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as cleanup:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-B", "-m", "tests.format_repair_worker_100",
                directory, "double-research-completed" if double_repair else "research-completed"], capture_output=True, timeout=25)
            self.assertEqual(72, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            sent = [json.loads(line) for line in (folder / "requests.jsonl").read_text().splitlines()]
            self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                              *(["step_verifier"] if double_repair else []), "researcher", "researcher"],
                             [request["role"] for request in sent])
            if double_repair:
                self.assertEqual(sent[3]["call_id"] + ":serialization-1", sent[4]["call_id"])
            self.assertEqual(sent[3]["call_id"] + ":counterexample", sent[-2]["call_id"])
            self.assertEqual(sent[-2]["call_id"] + ":serialization-1", sent[-1]["call_id"])
            repaired = {"argument": "Every real x has a smaller real value x-1.",
                "claims": [{"statement": "There is no minimum.", "label": "hard-verify"}], "blocked": False}
            reviewed = {**ACCEPT, "answer_claim": {**ACCEPT["answer_claim"], "both_directions_proved": True}}
            self.open_star([repaired, reviewed, {"final_response": "There is no minimum."},
                            {"verdict": "ACCEPT"}], **config(folder, research=True))
            for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                cleanup.callback(self.app.extensions[name].close)
            original = self.job(job_id)["result"]["budget"]
            self.assertEqual(7 if double_repair else 6, original["http_attempts"])
            resumed = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
            self.assertEqual(202, resumed.status_code, resumed.get_json())
            final = self.terminal(job_id)
            self.assertEqual("succeeded", final["status"], final)
            self.assertEqual(["reasoner", "step_verifier", "final_generator", "whole_solution_verifier"],
                             [request["role"] for request in self.outbound])
            stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
            events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith("data: ")]
            reviews = [e for e in events if e.get("solver_event_type") == "step_reviewed"]
            self.assertEqual(["CHALLENGE", "ACCEPT"], [e["verdict"] for e in reviews])
            self.assertIn("x=-1", reviews[0]["objection_summary"])
            self.assertEqual(original["deadline_at"], final["result"]["budget"]["deadline_at"])
            self.assertEqual(11 if double_repair else 10, final["result"]["budget"]["http_attempts"])

    def test_repaired_research_is_consumed_with_its_claim_binding(self):
        self.assert_research_consumed(double_repair=False)

    def test_double_verifier_and_research_repair_is_consumed_with_original_binding(self):
        self.assert_research_consumed(double_repair=True)

    def assert_research_consumed(self, *, double_repair):
        for result, gate in ((FOUND, "FAIL"), (NOT_FOUND, "UNCERTAIN")):
            with self.subTest(verdict=result["verdict"]):
                self.open_star([
                    NEED_PLAN, PLAN, STEP,
                    *([RawProviderContent("```json\n" + json.dumps(ACCEPT) + "\n```")] if double_repair else []),
                    ACCEPT,
                    RawProviderContent("```json\n" + json.dumps(result) + "\n```"), result,
                ], SHOWCASE_STAR_FEATURES={**FEATURES, "serialization_repair": True},
                    SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=7 if double_repair else 6,
                                                       max_http_attempts=7 if double_repair else 6))
                created = self.client.post("/api/agent/jobs", json={"message": PROBLEM,
                    "session_id": self.session, "solver_mode": "star_limited"}, headers=self.headers())
                self.assertEqual(202, created.status_code)
                job_id = created.get_json()["job_id"]
                job = self.terminal(job_id)
                stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
                events = [json.loads(line[6:]) for line in stream.splitlines()
                          if line.startswith("data: ")]
                review = next(e for e in events if e.get("solver_event_type") == "step_reviewed")
                self.assertTrue(review["valid"], review)
                self.assertEqual(("CHALLENGE", gate), (review["verdict"], review["logic_gate"]))
                self.assertEqual("failed", job["status"])  # Missing proof still cannot pass.
                original, repair = self.outbound[-2:]
                self.assertEqual("researcher", repair["role"])
                self.assertEqual(original["call_id"] + ":serialization-1", repair["call_id"])
                self.assertNotIn("claim", repair)
                self.assertNotIn("original_problem", repair)
                self.assertNotIn(original["claim"], json.dumps(self.outbound_messages[-1]))
                self.assertEqual([], repair["allowed_tools"])
                budget = job["result"]["budget"]
                expected = (7, 7, 0, 0, 70) if double_repair else (6, 6, 0, 0, 60)
                self.assertEqual(expected, tuple(budget[key] for key in (
                    "logical_calls", "http_attempts", "tool_calls", "unknown_attempts", "charged_tokens")))


if __name__ == "__main__":
    unittest.main()
