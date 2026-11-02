"""Public resume of sourced historical identities; no invented review evidence."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from showcase.final_evidence import artifact_identity
from showcase.flask_app import create_app
from tests.result_history_worker import STATEMENTS
from tests.star_product_support import StarJobFixture
from tests.star_recovery_worker import config, provider


class ResultHistoryTest(StarJobFixture, unittest.TestCase):
    def test_sourced_legacy_snapshot_resumes_without_merging_or_reviving_history(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            process = subprocess.run([sys.executable, "-m", "tests.result_history_worker",
                                      directory, "classified"], capture_output=True, timeout=90)
            self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))
            job_id = (folder / "job_id").read_text()
            # Fixture migration changes identities/validity only. Every statement
            # below was actually established by the recorded Verifier response.
            with sqlite3.connect(folder / "showcase.sqlite3") as db:
                run_id, text = db.execute("SELECT run_id,state_json FROM solver_states").fetchone()
                state = json.loads(text)
                entries = state["verified_results_ledger"]
                self.assertEqual(STATEMENTS, [entry["statement"] for entry in entries])
                original_reviews = {entry["review_call_id"] for entry in entries}
                self.assertEqual(1, len(original_reviews))
                for entry in entries[:2]:
                    entry.pop("result_id")
                entries[3]["result_id"] = entries[2]["result_id"]
                entries[5]["result_id"] = entries[4]["result_id"]
                entries[4]["invalidated"] = True
                entries[7]["dependencies"] = [entries[6]["result_id"]]
                # Preserve an invalid earlier duplicate in accepted history.
                state["accepted_results"] = [entries[4].copy()]
                # A sourced record already archived by a historical ruling
                # stays excluded; this does not manufacture a review.
                entries[6]["invalidated"] = True
                state["failure_records"].append({"kind": "replan",
                    "invalidated_results": [entries[6].copy()], "rescued_results": []})
                db.execute("UPDATE solver_states SET state_json=? WHERE run_id=?",
                           (json.dumps(state), run_id))
            db.close()
            from tests import star_recovery_worker as worker
            original_reply = worker.reply_value
            replanned = []
            def reply(window, context, path):
                role = context["role"]
                if role == "step_verifier" and not replanned:
                    replanned.append(True)
                    return worker.PROPOSE_REPLAN
                if role == "meta":
                    return {**worker.REPLAN_RULING,
                            "reusable_results": STATEMENTS[:6] + [STATEMENTS[7]]}
                if role == "planner":
                    return {"version": 2, "steps": [
                        {"step_id": "new", "title": "Finish", "objective": "Conclude"}]}
                return original_reply(window, context, path)
            resumed = []
            def transport(*args, **kwargs):
                context = json.loads(json.loads(kwargs["data"])["messages"][-1]["content"])
                resumed.append(context)
                return provider(folder, kwargs)
            with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}), patch(
                    "llm_client.requests.post", side_effect=transport), patch.object(
                        worker, "reply_value", side_effect=reply):
                self.app = create_app(config(folder))
                try:
                    self.client = self.app.test_client()
                    self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                                headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    # Use the bounded 45-second observation of the dedup contract.
                    import time
                    deadline = time.monotonic() + 45
                    while time.monotonic() < deadline:
                        job = self.job(job_id)
                        if job["status"] in {"succeeded", "failed", "canceled"}:
                            break
                        time.sleep(.02)
                    self.assertEqual("succeeded", job["status"], job)
                    planner = next(r for r in resumed if r["role"] == "planner")
                    rescued = [fact["statement"] for fact in planner["accepted_results"]]
                    for statement in STATEMENTS[:3] + [STATEMENTS[5]]:
                        self.assertEqual(1, rescued.count(statement), planner)
                    for statement in [STATEMENTS[3], STATEMENTS[4], *STATEMENTS[6:]]:
                        self.assertNotIn(statement, rescued)
                    final = next(r for r in resumed if r["role"] == "final_generator")
                    facts = final["accepted_results"]
                    statements = [fact["statement"] for fact in facts]
                    for statement in STATEMENTS[:3]:
                        self.assertEqual(1, statements.count(statement), facts)
                    for statement in STATEMENTS[3:]:
                        self.assertNotIn(statement, statements)
                    for fact in facts:
                        if fact["statement"] in STATEMENTS:
                            self.assertIn(fact["review_call_id"], original_reviews)
                            self.assertEqual("llm_reviewed", fact["evidence_level"])
                    review = next(r for r in resumed if r["role"] == "whole_solution_verifier")
                    self.assertEqual(facts, review["accepted_results"])
                    count = len(resumed)
                    evidence = self.client.get(f"/api/runs/{job_id}/evidence")
                    self.assertEqual(200, evidence.status_code)
                    replay = self.client.get(f"/api/runs/{job_id}/replay")
                    self.assertEqual(200, replay.status_code)
                    saved = self.client.post("/api/evidence/replay", json=evidence.get_json(),
                                             headers=self.headers())
                    self.assertEqual(200, saved.status_code, saved.get_json())
                    self.assertEqual(count, len(resumed))
                    self.assertFalse((folder / "tool_runs.txt").exists())
                    self.assertEqual("2", job["result"]["final_response"])
                    self.assertEqual("2", review["solution_candidate"])
                    self.assertEqual(["Addition"],
                                     [proof["argument"] for proof in final["step_proofs"]])
                    checks = self.report(job_id)["checks"]
                    self.assertEqual("same_artifact", checks["binding"])
                    self.assertEqual(artifact_identity(job["result"]["final_response"]),
                                     checks["history"][-1]["artifact"])
                finally:
                    for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
                        self.app.extensions[name].close()
