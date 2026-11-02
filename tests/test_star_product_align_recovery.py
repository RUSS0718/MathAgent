"""ALIGN-09: old and new Runs recover and review safely in the new flows.

One public Run crosses every new persistent boundary (guidance consumption,
new action submission, compute receipt, classified outcome acceptance, final
candidate/review) with a real process exit at each, then resumes through the
authenticated public resume into a bound S4 delivery. Runs persisted by the
pre-ALIGN build stay readable, reviewable and exportable without fabricating
evidence grades, and resume with an explicit new identity under the original
Run, ledger and deadline.
"""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import StarJobFixture
from tests.star_recovery_worker import config as worker_config
from tests.star_recovery_worker import provider as worker_provider

# The documented pre-ALIGN review base (spec #70): its persisted Runs are the
# representative historical records the new build must stay compatible with.
REVIEW_BASE = "89e9ff5"

APP_EXTENSIONS = ("showcase_workspace_service", "showcase_run_service", "loopback_store")


def close_app(app):
    for name in APP_EXTENSIONS:
        app.extensions[name].close()


def requests_logged(folder):
    path = folder / "requests.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def tool_runs(folder):
    path = folder / "tool_runs.txt"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


class StarAlignChainRecoveryTest(unittest.TestCase):
    """ALIGN-AC-04/07/15: combination recovery across all new boundaries."""

    def run_worker(self, folder, window):
        process = subprocess.run(
            [sys.executable, "-m", "tests.star_recovery_worker", str(folder), window],
            capture_output=True, timeout=120)
        self.assertEqual(71, process.returncode, process.stderr.decode(errors="replace"))

    @contextmanager
    def opened(self, folder):
        # A fresh app instance re-runs startup recovery, exactly like a real
        # process restart between the crash and the operator's inspection.
        with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}):
            app = create_app(worker_config(folder))
        self.client = app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        try:
            yield app
        finally:
            close_app(app)

    def headers(self):
        return {"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())}

    def job(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}").get_json()

    def report(self, job_id):
        return self.client.get(f"/api/agent/jobs/{job_id}/report").get_json()["report"]

    def sse_events(self, job_id, last_id=None):
        url = f"/api/agent/jobs/{job_id}/events"
        if last_id is not None:
            url += f"?last_event_id={last_id}"
        stream = self.client.get(url).get_data(as_text=True)
        events, current_id = [], None
        for line in stream.splitlines():
            if line.startswith("id: "):
                current_id = int(line[4:])
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if data.get("solver_event_type"):
                    events.append({**data, "id": current_id})
        return events

    def wait_terminal(self, job_id):
        for _ in range(1500):
            job = self.job(job_id)
            if job["status"] in {"succeeded", "failed", "canceled"}:
                return job
            time.sleep(.01)
        self.fail("public STAR resume did not terminate")

    def assert_prefix_kept(self, folder, previous):
        sent = requests_logged(folder)
        self.assertEqual(previous, sent[:len(previous)])
        return sent

    def test_chain_resume_crosses_every_new_persistent_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            log = folder / "requests.jsonl"

            # 1) 干预消费边界：die right after the Guidance commits, before any
            #    executor consumes it.
            self.run_worker(folder, "chain_a")
            job_id = (folder / "job_id").read_text()
            sent = requests_logged(folder)
            self.assertEqual(["explore", "planner", "reasoner", "step_verifier",
                              "reasoner", "meta"], [item["role"] for item in sent])
            with self.opened(folder):
                job = self.job(job_id)
                self.assertEqual("failed", job["status"], job)
                self.assertEqual("safe", job["result"]["solver"]["recovery"]["status"])
                self.assertNotIn("REDO_CHAIN_SENTINEL", json.dumps(self.report(job_id)))
                deadlines = {job["result"]["budget"]["deadline_at"]}

            # 2) 计算回执边界：the resumed redo claims its own computation and the
            #    process dies after the receipt commits, before the review.
            self.run_worker(folder, "chain_b")
            self.assertEqual("202", (folder / "resume_status").read_text())
            sent = self.assert_prefix_kept(folder, sent)
            self.assertEqual("reasoner", sent[-1]["role"])
            self.assertEqual("s1", sent[-1]["step"]["step_id"])
            self.assertEqual(1, len(tool_runs(folder)))
            with self.opened(folder):
                job = self.job(job_id)
                self.assertEqual("failed", job["status"], job)
                self.assertEqual("safe", job["result"]["solver"]["recovery"]["status"])
                self.assertEqual(1, job["result"]["budget"]["tool_calls"])
                deadlines.add(job["result"]["budget"]["deadline_at"])

            # 3) 成果接受边界：the review classifies its Lemma and the process dies
            #    right after that ledger commit; the computation is not repeated.
            self.run_worker(folder, "chain_c")
            self.assertEqual("202", (folder / "resume_status").read_text())
            sent = self.assert_prefix_kept(folder, sent)
            self.assertEqual("step_verifier", sent[-1]["role"])
            self.assertEqual(1, len(tool_runs(folder)))
            with self.opened(folder):
                job = self.job(job_id)
                self.assertEqual("failed", job["status"], job)
                classified = self.report(job_id)["solver"]["solver"]["progress"][
                    "classified_results"]
                self.assertEqual(1, len(classified), classified)
                self.assertEqual("Lemma", classified[0]["category"])
                self.assertTrue(classified[0]["proven"])
                deadlines.add(job["result"]["budget"]["deadline_at"])

            # 4) 新动作提交边界：the redo is accepted, s3 proposes replan, Meta rules
            #    CONTINUE and the process dies after the ruling commits.
            self.run_worker(folder, "chain_d")
            self.assertEqual("202", (folder / "resume_status").read_text())
            sent = self.assert_prefix_kept(folder, sent)
            self.assertEqual("meta", sent[-1]["role"])
            # One guidance request and one ruling; the ruling was never re-sent.
            self.assertEqual(2, sum(item["role"] == "meta" for item in sent))
            with self.opened(folder):
                deadlines.add(self.job(job_id)["result"]["budget"]["deadline_at"])

            # 5) 最终候选/审查边界：the new s3 action completes, the final candidate
            #    is generated and the process dies before the whole review.
            self.run_worker(folder, "chain_e")
            self.assertEqual("202", (folder / "resume_status").read_text())
            sent = self.assert_prefix_kept(folder, sent)
            self.assertEqual("final_generator", sent[-1]["role"])
            with self.opened(folder):
                job = self.job(job_id)
                self.assertEqual("failed", job["status"], job)
                before_stream = self.sse_events(job_id)
                last_id = before_stream[-1]["id"]
                deadlines.add(job["result"]["budget"]["deadline_at"])

            # 6) Public resume completes the last leg: the persisted candidate is
            #    reviewed once and bound to the delivered answer.
            post_calls = []
            with patch("llm_client.requests.post",
                       side_effect=lambda *a, **kw: self.counted(
                           post_calls, worker_provider(folder, kw))):
                with self.opened(folder):
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                                headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    final = self.wait_terminal(job_id)
                    after = requests_logged(folder)
                    self.assertEqual(sent, after[:len(sent)])
                    self.assertEqual(19, len(after), [item["role"] for item in after])
                    # No completed action was re-dispatched, re-executed, re-accepted
                    # or re-billed anywhere in the chain.
                    self.assertEqual(["explore", "planner",
                                      "reasoner", "step_verifier", "reasoner", "meta",
                                      "reasoner", "step_verifier",
                                      "reasoner", "step_verifier",
                                      "reasoner", "step_verifier",
                                      "reasoner", "step_verifier", "meta",
                                      "reasoner", "step_verifier", "final_generator",
                                      "whole_solution_verifier"],
                                     [item["role"] for item in after])
                    self.assertEqual(1, len(tool_runs(folder)))
                    self.assertEqual("succeeded", final["status"], final)
                    self.assertEqual("1+1=2 CHAIN-ANSWER", final["result"]["final_response"])
                    # S4 bound the delivered answer to the accepted whole review.
                    self.assertEqual("same_artifact",
                                     final["result"]["verification"]["binding"])
                    self.assertEqual("completed_llm_reviewed",
                                     final["result"]["solver"]["status"])
                    recovery = final["result"]["solver"]["recovery"]
                    self.assertEqual("safe", recovery["status"])
                    self.assertEqual([], recovery["unknown_calls"])
                    self.assertEqual([], recovery["protocol_failures"])
                    budget = final["result"]["budget"]
                    self.assertEqual(19, budget["logical_calls"])
                    self.assertEqual(19, budget["http_attempts"])
                    self.assertEqual(1, budget["tool_calls"])
                    self.assertEqual(0, budget["unknown_attempts"])
                    self.assertEqual({"prompt_tokens": 133, "completion_tokens": 57,
                                      "total_tokens": 190}, budget["provider_known"])
                    deadlines.add(budget["deadline_at"])
                    # The original Run, ledger and deadline survived every crash.
                    self.assertEqual(1, len(deadlines))
                    # New actions never collide with old identities: both s3 reasoner
                    # actions exist with distinct call ids and no event conflict arose.
                    s3_actions = [item["call_id"] for item in after
                                  if item["role"] == "reasoner"
                                  and item["step"]["step_id"] == "s3"]
                    self.assertEqual(2, len(s3_actions), s3_actions)
                    self.assertNotEqual(s3_actions[0], s3_actions[1])
                    # The classified Lemma was appended exactly once across the crash.
                    sightings = [
                        item for request in after
                        if request.get("role") == "reasoner"
                        and isinstance(request.get("role_context"), dict)
                        for item in request["role_context"]["state"][
                            "verified_results_ledger"]
                        if item.get("category") == "Lemma"]
                    self.assertEqual(1, len({item["result_id"] for item in sightings}),
                                     sightings)
                    # State Revision, Job projection and checkpoint association agree.
                    connection = sqlite3.connect(str(folder / "showcase.sqlite3"))
                    try:
                        stored_revision = connection.execute(
                            "SELECT state_revision FROM solver_states WHERE run_id=?",
                            (job_id,)).fetchone()[0]
                        terminals = connection.execute(
                            "SELECT thread FROM run_graph_terminals WHERE thread=?",
                            (job_id,)).fetchall()
                        checkpoints = connection.execute(
                            "SELECT 1 FROM run_graph_checkpoints WHERE thread=? LIMIT 1",
                            (job_id,)).fetchall()
                    finally:
                        connection.close()
                    self.assertEqual(stored_revision,
                                     final["result"]["solver"]["state_revision"])
                    self.assertEqual(job_id,
                                     final["result"]["solver"]["checkpoint_thread_id"])
                    self.assertEqual(1, len(terminals))
                    self.assertEqual(1, len(checkpoints))
                    # SSE reconnection shows the actual persisted progress: the full
                    # stream is strictly ordered, and a cursor reconnect after the
                    # last pre-resume event replays only the resumed leg.
                    events = self.sse_events(job_id)
                    self.assertEqual([event["id"] for event in events],
                                     sorted(event["id"] for event in events))
                    kinds = [event.get("solver_event_type") for event in events]
                    self.assertEqual(1, kinds.count("trace_back_applied"))
                    self.assertIn("finalization_completed", kinds)
                    resumed_only = self.sse_events(job_id, last_id=last_id)
                    self.assertTrue(resumed_only)
                    self.assertTrue(all(event["id"] > last_id for event in resumed_only))
                    self.assertIn("whole_solution_verifier",
                                  {event.get("role") for event in resumed_only})
                    # Report, Evidence and replay reads never start new solving.
                    reads_before = len(post_calls)
                    self.report(job_id)
                    self.client.get(f"/api/runs/{job_id}/evidence")
                    self.client.get(f"/api/agent/jobs/{job_id}/candidate-replay")
                    self.job(job_id)
                    self.assertEqual(reads_before, len(post_calls))
                    # The guidance sentinel stays out of every public surface.
                    public = json.dumps([final, self.report(job_id),
                                         self.client.get(
                                             f"/api/runs/{job_id}/evidence").get_json()])
                    self.assertNotIn("REDO_CHAIN_SENTINEL", public)

    def counted(self, calls, reply):
        calls.append(1)
        return reply

    def test_exhausted_shared_budget_stops_resumed_continuation_before_dispatch(self):
        """ALIGN-AC-07: a resumed continuation under an exhausted shared ledger
        commits its terminal budget result with zero further dispatch."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.run_worker(folder, "chain_a")
            self.run_worker(folder, "chain_b")
            job_id = (folder / "job_id").read_text()
            sent = requests_logged(folder)
            connection = sqlite3.connect(str(folder / "showcase.sqlite3"))
            try:
                ledger = json.loads(connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?",
                    (job_id,)).fetchone()[0])
                # Freeze the shared ledger at exactly what the crashed legs spent.
                ledger["limits"]["max_model_calls"] = sum(
                    action["kind"] == "logical" for action in ledger["actions"])
                ledger["limits"]["max_http_attempts"] = sum(
                    action["kind"] == "http" for action in ledger["actions"])
                connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
                                   (json.dumps(ledger), job_id))
                connection.commit()
            finally:
                connection.close()
            with self.opened(folder):
                response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                            headers=self.headers())
                self.assertEqual(202, response.status_code, response.get_json())
                final = self.wait_terminal(job_id)
                self.assertEqual("failed", final["status"], final)
                self.assertEqual("partial_budget_exhausted",
                                 final["result"]["solver"]["status"])
                # Zero illegal dispatch after the budget gate: nothing new left
                # the process and the committed computation never repeated.
                self.assertEqual(sent, requests_logged(folder))
                self.assertEqual(1, len(tool_runs(folder)))

    def test_bypassing_receipt_recovery_reexecutes_the_computation(self):
        """ALIGN-AC-16: the no-repeat acceptance is sensitive to the recovery
        gate; disabling it really does re-run the recorded computation."""
        from showcase.solver_harness import tool_precheck

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.run_worker(folder, "chain_a")
            self.run_worker(folder, "chain_b")
            job_id = (folder / "job_id").read_text()
            sent = requests_logged(folder)
            self.assertEqual(1, len(tool_runs(folder)))
            with patch.object(tool_precheck, "_recover_receipt",
                              return_value=None), patch(
                    "llm_client.requests.post",
                    side_effect=lambda *a, **kw: worker_provider(folder, kw)):
                with self.opened(folder):
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume",
                                                json={}, headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    job = self.wait_terminal(job_id)
                    # The resumed leg re-ran the computation it should have reused;
                    # the duplicate burned the shared tool budget and the run that
                    # resumes cleanly with the gate active instead ends exhausted.
                    self.assertEqual(2, len(tool_runs(folder)))
                    self.assertEqual("failed", job["status"], job)
                    self.assertEqual("partial_budget_exhausted",
                                     job["result"]["solver"]["status"])
                    self.assertEqual(sent, requests_logged(folder))

    def test_expired_original_deadline_refuses_resumed_compute_continuation(self):
        """ALIGN-AC-07: after the deadline passes, resume is refused and the
        recorded computation is never re-dispatched."""
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            self.run_worker(folder, "tool")
            job_id = (folder / "job_id").read_text()
            self.assertEqual(1, len(tool_runs(folder)))
            connection = sqlite3.connect(str(folder / "showcase.sqlite3"))
            try:
                ledger = json.loads(connection.execute(
                    "SELECT ledger_json FROM run_budgets WHERE run_id=?",
                    (job_id,)).fetchone()[0])
                ledger["deadline_at"] = time.time() - 1
                connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?",
                                   (json.dumps(ledger), job_id))
                connection.commit()
            finally:
                connection.close()
            with self.opened(folder):
                response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                            headers=self.headers())
                self.assertEqual(409, response.status_code)
                self.assertEqual("run_deadline_exhausted", response.get_json()["error"])
                self.assertEqual(1, len(tool_runs(folder)))
                self.assertEqual(0, len(requests_logged(folder)[5:]))

    def test_canceled_run_refuses_resume_and_never_redispatches(self):
        """ALIGN-AC-07: cancel during a resumed compute continuation stops every
        later dispatch, and the late reply cannot override the terminal state."""
        import threading

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            # Seed the Run and cross the compute-receipt boundary first: the
            # continuation under test resumes from that committed receipt.
            self.run_worker(folder, "chain_a")
            self.run_worker(folder, "chain_b")
            job_id = (folder / "job_id").read_text()
            sent = requests_logged(folder)
            release = threading.Event()

            def transport(*args, **kwargs):
                context = json.loads(json.loads(kwargs["data"])["messages"][-1]["content"])
                # Hold the resumed review reply until the Job is canceled.
                if context.get("role") == "step_verifier":
                    release.wait(timeout=60)
                return worker_provider(folder, kwargs)

            with patch("llm_client.requests.post", side_effect=transport):
                with self.opened(folder):
                    response = self.client.post(f"/api/agent/jobs/{job_id}/resume",
                                                json={}, headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    for _ in range(1500):
                        if any(item.get("role") == "step_verifier"
                               for item in requests_logged(folder)[len(sent):]):
                            break
                        time.sleep(.01)
                    canceled = self.client.post(f"/api/agent/jobs/{job_id}/cancel",
                                                json={}, headers=self.headers())
                    self.assertEqual(200, canceled.status_code, canceled.get_json())
                    release.set()
                    for _ in range(1500):
                        if self.job(job_id)["status"] == "canceled":
                            break
                        time.sleep(.01)
                    time.sleep(.5)
                    job = self.job(job_id)
                    self.assertEqual("canceled", job["status"], job)
                    # The resumed continuation dispatched exactly one request; the
                    # late review reply committed nothing and nothing followed it.
                    after = requests_logged(folder)
                    self.assertEqual(len(sent) + 1, len(after),
                                     [item["role"] for item in after])
                    self.assertEqual("step_verifier", after[-1]["role"])
                    self.assertEqual(1, len(tool_runs(folder)))
                    # A terminal Job never resumes again: zero further dispatch.
                    rejected = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={},
                                                headers=self.headers())
                    self.assertEqual(409, rejected.status_code)
                    self.assertEqual("job_not_resumable", rejected.get_json()["error"])
                    self.assertEqual(len(sent) + 1, len(requests_logged(folder)))


class StarAlignHistoryCompatibilityTest(unittest.TestCase):
    """ALIGN-AC-15: pre-ALIGN Runs read, review, export and resume safely."""

    @classmethod
    def setUpClass(cls):
        cls._archive = tempfile.TemporaryDirectory()
        cls.old_tree = Path(cls._archive.name) / "old"
        root = Path(__file__).resolve().parents[1]
        archive = subprocess.run(
            ["git", "archive", REVIEW_BASE, "--", "showcase", "llm_client.py",
             "llm_response.py", "presentation_pages.py"],
            capture_output=True, check=True, cwd=str(root))
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            try:
                tar.extractall(cls.old_tree, filter="data")
            except TypeError:
                tar.extractall(cls.old_tree)

    @classmethod
    def tearDownClass(cls):
        cls._archive.cleanup()

    def run_old_build(self, folder, mode):
        root = Path(__file__).resolve().parents[1]
        worker = Path(__file__).resolve().parent / "star_history_worker.py"
        env = {**os.environ, "PYTHONPATH": str(self.old_tree),
               "INTERN_API_KEY": "scripted-only"}
        process = subprocess.run([sys.executable, str(worker), str(folder), mode],
                                 capture_output=True, env=env, timeout=120, cwd=str(root))
        self.assertEqual(0, process.returncode, process.stderr.decode(errors="replace"))
        return (folder / f"old_{mode}_id").read_text()

    @contextmanager
    def opened(self, folder):
        with patch.dict(os.environ, {"INTERN_API_KEY": "scripted-only"}):
            app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": str(folder),
                "SHOWCASE_JOB_DELAY_SECONDS": 0, "SHOWCASE_STAR_ENABLED": True,
                "SHOWCASE_STAR_ADAPTER": InternModelAdapter(
                    InternChatClient(retry=1), max_tokens=256),
                "SHOWCASE_STAR_EVIDENCE_KIND": "fault_injection",
                "SHOWCASE_STAR_BUDGET": RunBudgetLimits(
                    max_model_calls=8, max_http_attempts=8)})
        self.client = app.test_client()
        self.csrf = self.client.get("/api/check_auth").get_json()["csrf_token"]
        try:
            yield app
        finally:
            close_app(app)

    def headers(self):
        return {"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())}

    def test_old_build_completed_run_reads_and_exports_without_fabrication(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            completed = self.run_old_build(folder, "completed")

            def refuse(*args, **kwargs):
                raise AssertionError("reading a historical Run must not solve")

            with patch("llm_client.requests.post", side_effect=refuse):
                with self.opened(folder):
                    job = self.client.get(f"/api/agent/jobs/{completed}").get_json()
                    self.assertEqual("succeeded", job["status"], job)
                    self.assertEqual("1+1=2 as recorded by the old build",
                                     job["result"]["final_response"])
                    solver = job["result"]["solver"]
                    self.assertEqual("completed_llm_reviewed", solver["status"])
                    self.assertEqual("safe", solver["recovery"]["status"])
                    # Records that predate the classified ledger are never dressed up
                    # as classified or receipt-backed results.
                    self.assertEqual([], solver["progress"]["classified_results"])
                    evidence = self.client.get(
                        f"/api/runs/{completed}/evidence").get_json()
                    self.assertEqual("COMPLETED", evidence["run"]["status"])
                    self.assertEqual("same_artifact",
                                     evidence["verification"]["binding"])
                    self.assertNotIn("proof_sources",
                                     json.dumps(evidence["verification"]["history"]))
                    report = self.client.get(
                        f"/api/agent/jobs/{completed}/report").get_json()["report"]
                    self.assertEqual("1+1=2 as recorded by the old build",
                                     report["answer"])
                    stream = self.client.get(
                        f"/api/agent/jobs/{completed}/events").get_data(as_text=True)
                    self.assertIn("event:", stream)
                    replay = self.client.get(
                        f"/api/agent/jobs/{completed}/candidate-replay")
                    self.assertEqual(200, replay.status_code, replay.get_json())

    def test_old_build_interrupted_run_resumes_with_explicit_new_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            interrupted = self.run_old_build(folder, "interrupted")
            outbound = []
            POLISH = {"solution_candidate": "1+1=2 as recorded by the old build"}
            ACCEPT = {"verdict": "ACCEPT", "reason": "Addition"}
            replies = [POLISH, ACCEPT]

            def respond(*args, **kwargs):
                value = replies.pop(0)
                outbound.append(json.loads(
                    json.loads(kwargs["data"])["messages"][-1]["content"]))

                class Reply:
                    status_code = 200

                    def raise_for_status(self):
                        pass

                    def json(self):
                        return {"choices": [{"finish_reason": "stop",
                                             "message": {"content": json.dumps(value)}}],
                                "model": "intern-s2",
                                "usage": {"prompt_tokens": 5, "completion_tokens": 5,
                                          "total_tokens": 10}}
                return Reply()

            with patch("llm_client.requests.post", side_effect=respond):
                with self.opened(folder):
                    job = self.client.get(f"/api/agent/jobs/{interrupted}").get_json()
                    self.assertEqual("failed", job["status"], job)
                    recovery = job["result"]["solver"]["recovery"]
                    self.assertEqual("needs_review", recovery["status"])
                    self.assertEqual(1, len(recovery["unknown_calls"]))
                    self.assertEqual("explore_polish",
                                     recovery["unknown_calls"][0]["role"])
                    old_budget = job["result"]["budget"]
                    old_id = recovery["unknown_calls"][0]["call_id"]
                    rejected = self.client.post(
                        f"/api/agent/jobs/{interrupted}/resume",
                        json={}, headers=self.headers())
                    self.assertEqual(409, rejected.status_code)
                    self.assertEqual("star_retry_decision_required",
                                     rejected.get_json()["error"])
                    response = self.client.post(
                        f"/api/agent/jobs/{interrupted}/resume",
                        json={"retry_call": {
                            "call_id": old_id,
                            "new_call_id": str(uuid.uuid4())}},
                        headers=self.headers())
                    self.assertEqual(202, response.status_code, response.get_json())
                    for _ in range(1500):
                        job = self.client.get(
                            f"/api/agent/jobs/{interrupted}").get_json()
                        if job["status"] in {"succeeded", "failed", "canceled"}:
                            break
                        time.sleep(.01)
                    self.assertEqual("succeeded", job["status"], job)
                    self.assertEqual("1+1=2 as recorded by the old build",
                                     job["result"]["final_response"])
                    # The historical Run, ledger, reservation and deadline survive;
                    # the explore phase is never repeated and the old unknown stays.
                    budget = job["result"]["budget"]
                    self.assertEqual(old_budget["deadline_at"], budget["deadline_at"])
                    self.assertEqual(old_budget["reserved_tokens"],
                                     budget["reserved_tokens"])
                    self.assertEqual(4, budget["http_attempts"])
                    self.assertEqual(1, budget["unknown_attempts"])
                    self.assertEqual(["explore_polish", "whole_solution_verifier"],
                                     [item.get("role") for item in outbound])
                    self.assertEqual(old_id,
                                     job["result"]["solver"]["recovery"]["retries"][0][
                                         "retry_of"])
                    self.assertEqual(
                        [], job["result"]["solver"]["progress"]["classified_results"])
                    reads_before = len(outbound)
                    self.client.get(f"/api/agent/jobs/{interrupted}/report")
                    self.client.get(f"/api/runs/{interrupted}/evidence")
                    self.assertEqual(reads_before, len(outbound))


FULL_IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")


@unittest.skipUnless(FULL_IMAGE, "requires independently validated local Docker image ID")
class StarFullReferenceChainTest(StarJobFixture, unittest.TestCase):
    """The same combination under the complete reference preset with the real
    isolated executor: one public Run crosses every new flow and delivers a
    bound answer without repeating any completed action."""

    def test_reference_chain_completes_with_real_isolated_computation(self):
        from tests.star_recovery_worker import META_CONTINUE_DECISION, PLAN

        ACCEPT_VERDICT = {"goal_gate": "YES", "logic_gate": "PASS",
                          "verdict": "ACCEPT", "objection": ""}
        PROPOSE_REPLAN = {"goal_gate": "NO", "logic_gate": "FAIL",
                          "verdict": "PROPOSE_REPLAN",
                          "objection": "The conclusion does not follow"}
        code = "print(1+1)"

        def chain_reply(context):
            def seen(role, step_id=None):
                return sum(
                    1 for item in self.outbound
                    if item.get("role") == role
                    and (step_id is None
                         or item.get("step", {}).get("step_id") == step_id))

            role = context.get("role")
            step_id = context.get("step", {}).get("step_id")
            if role == "explore":
                return {"assessment": "NEED_PLAN", "worked": [], "failed": [],
                        "candidates": []}
            if role == "planner":
                return PLAN
            if role == "reasoner":
                if step_id == "s1":
                    attempt = seen("reasoner", "s1")
                    if attempt == 2:
                        return {"argument": "Redo with its own isolated computation",
                                "claims": [{
                                    "statement": "1+1=2 by the isolated check",
                                    "label": "easy-verify",
                                    "tool_request": {
                                        "tool": "python_math",
                                        "arguments": {"code": code},
                                        "expected_output": "2\n",
                                        "scope": "finite_computation"}}],
                                "blocked": False}
                    if attempt > 2:
                        return {"argument": "Boundary case handled", "claims": [],
                                "blocked": False}
                    return {"argument": "Attempt one", "claims": [], "blocked": False}
                if step_id == "s2":
                    if seen("reasoner", "s2") == 1:
                        return {"argument": "Stuck second attempt", "claims": [],
                                "blocked": True}
                    return {"argument": "Second fact", "claims": [], "blocked": False}
                if seen("reasoner", "s3") == 1:
                    return {"argument": "Conclusion attempt", "claims": [],
                            "blocked": False}
                return {"argument": "Conclusion", "claims": [], "blocked": False}
            if role == "step_verifier":
                if step_id == "s1":
                    if seen("step_verifier", "s1") == 2:
                        return {
                            "goal_gate": "PARTIAL", "logic_gate": "UNCERTAIN",
                            "verdict": "CHALLENGE",
                            "objection": "The computation must precede the conclusion.",
                            "classified_outcomes": [{
                                "category": "Lemma",
                                "statement": "Forward addition identity holds",
                                "scope": "forward direction of the base step",
                                "claim_indexes": [0]}],
                        }
                    return ACCEPT_VERDICT
                if step_id == "s3" and seen("step_verifier", "s3") == 1:
                    return PROPOSE_REPLAN
                return ACCEPT_VERDICT
            if role == "meta":
                if context.get("guidance_request") is not None:
                    return {"action_type": "trace_back",
                            "specific_task": "Rebuild the base step",
                            "use_pure_reasoning": False, "trace_back_to": 1,
                            "rationale": "Rebuild the base step with its own computation"}
                return META_CONTINUE_DECISION
            if role == "final_generator":
                return {"final_response": "1+1=2 CHAIN-ANSWER"}
            return {"verdict": "ACCEPT", "reason": "Addition"}

        self.open_star([chain_reply] * 24, SHOWCASE_STAR_FULL_ENABLED=True,
                       SHOWCASE_STAR_PYTHON_IMAGE_ID=FULL_IMAGE)
        response = self.client.post("/api/agent/jobs", json={
            "message": "1+1", "session_id": self.session,
            "solver_mode": "star_reference"}, headers=self.headers())
        self.assertEqual(202, response.status_code, response.get_json())
        job_id = response.get_json()["job_id"]
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        tool_timeout = pipeline.registry.container_python_executor.timeout_seconds
        self.assertEqual(20, tool_timeout)
        # This real Docker chain may use its entire registered tool envelope;
        # reserve 20s more to observe its 19 model actions and SQLite commits.
        observation_deadline = time.monotonic() + tool_timeout + 20
        while True:
            job = self.job(job_id)
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            if time.monotonic() >= observation_deadline:
                self.fail({"status": job["status"], "budget": self.report(job_id)["budget"]})
            time.sleep(.01)
        self.assertEqual("succeeded", job["status"], job)
        self.assertEqual("star_reference", job["result"]["execution_mode"])
        self.assertEqual([], job["result"]["missing_capabilities"])
        self.assertEqual("1+1=2 CHAIN-ANSWER", job["result"]["final_response"])
        self.assertEqual("same_artifact", job["result"]["verification"]["binding"])
        roles = [item["role"] for item in self.outbound]
        self.assertEqual(["explore", "planner",
                          "reasoner", "step_verifier", "reasoner", "meta",
                          "reasoner", "step_verifier",
                          "reasoner", "step_verifier",
                          "reasoner", "step_verifier",
                          "reasoner", "step_verifier", "meta",
                          "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"], roles, roles)
        budget = self.report(job_id)["budget"]
        self.assertEqual(19, budget["logical_calls"])
        self.assertEqual(19, budget["http_attempts"])
        self.assertEqual(1, budget["tool_calls"])
        self.assertEqual(48, budget["limits"]["max_model_calls"])
        self.assertEqual(1100, budget["limits"]["max_runtime_seconds"])
        self.assertLessEqual(budget["tool_wall_time_seconds"], budget["wall_time_seconds"])
        self.assertLess(budget["wall_time_seconds"], budget["limits"]["max_runtime_seconds"])
        # The redo's computation really executed in the contract image, and
        # the classified Lemma rests on that isolated receipt.
        review = next(item for item in self.outbound
                      if item["role"] == "step_verifier"
                      and item.get("step", {}).get("step_id") == "s1"
                      and item["report"]["tool_receipts"])
        receipt = review["report"]["tool_receipts"][0]
        self.assertEqual("success", receipt["status"])
        self.assertTrue(receipt["executed"] and receipt["cleanup_verified"])
        self.assertEqual(FULL_IMAGE, receipt["image"])
        classified = self.report(job_id)["solver"]["solver"]["progress"][
            "classified_results"]
        self.assertEqual(["Lemma"], [item["category"] for item in classified])
        self.assertEqual([True], [item["proven"] for item in classified])
        # The delivered proof basis carries the actual computation receipt.
        whole = next(item for item in self.outbound
                     if item["role"] == "whole_solution_verifier")
        proof = next(item for item in whole["step_proofs"]
                     if item.get("step_id") == "s1")
        self.assertEqual([receipt["receipt_id"]],
                         [item["receipt_id"] for item in proof["tool_receipts"]])
        stream = self.client.get(
            f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        kinds = [json.loads(line[6:]).get("solver_event_type")
                 for line in stream.splitlines() if line.startswith("data: ")]
        self.assertEqual(1, kinds.count("trace_back_applied"))
        self.assertIn("finalization_completed", kinds)


if __name__ == "__main__":
    unittest.main()
