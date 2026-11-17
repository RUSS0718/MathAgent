"""Review evidence at the public HTTP, Job and persisted budget seams."""

import hashlib
import json
import unittest
from unittest.mock import patch

from showcase.run_budget import RunBudget, RunBudgetLedger, RunBudgetLimits, bind_budget
from showcase.solver_harness.intern_port import InternModelPort
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import SPEC
from tests.test_initial_explore_192 import InitialExploreJobTest


class DependencyRoutingReviewTest(StarJobFixture, unittest.TestCase):
    open_initial = InitialExploreJobTest.open_initial

    def test_native_tools_http_body_matches_estimate_fingerprint_and_reservation(self):
        """Native tools must be included in the explicit nonstream identity."""
        self.open_initial([SOLVED, SOLVED])
        adapter = self.app.extensions["showcase_workspace_service"].star_pipeline.adapter
        port = InternModelPort(adapter)
        ledger = RunBudgetLedger()
        self.addCleanup(ledger.close)
        ledger.ensure("review", RunBudgetLimits())
        snapshots = []
        original = self.post.side_effect

        def observe(*args, **kwargs):
            snapshots.append(ledger.snapshot("review"))
            return original(*args, **kwargs)

        self.post.side_effect = observe
        tools = [{"type": "function", "function": {"name": "calculate",
                 "description": "整数计算", "parameters": {"type": "object"}}}]
        for index in range(2):
            request = {"role": "explore", "problem": "1+1", "run_id": "review",
                       "call_id": f"review:explore:{index}", "round": 1,
                       "max_output_tokens": 2048, "transport_override": "nonstream",
                       "provider_tools": tools}
            if index:
                request["report"] = {"tool_receipts": [{"output": 2}]}
            estimated = port.serialized_payload_size(request)
            prior_input = ledger.snapshot("review")["local_input_estimate"]
            with bind_budget(RunBudget(ledger, "review")):
                port.complete(request)
            raw = self.post.call_args.kwargs["data"]
            body = json.loads(raw)
            self.assertEqual(tools, body["tools"])
            self.assertEqual(len(raw), estimated)
            self.assertEqual(2048, body["max_tokens"])
            decision = port.invocations[-1]["transport"]
            expected = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False,
                                                separators=(",", ":")).encode()).hexdigest()
            self.assertEqual(expected, decision["payload_fingerprint"])
            self.assertEqual(2048, ledger.attempts("review")[-1]["max_tokens"])
            self.assertEqual(2048, snapshots[-1]["reserved_tokens"]
                             - (snapshots[-1]["local_input_estimate"] - prior_input))

    def test_public_compute_continuation_measures_actual_serialized_body(self):
        """Server tool continuation goes through a Job and the real port/HTTP path."""
        from showcase.tools import ToolRegistry
        from tests.test_star_product_explore_compute import ENUMERATE

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: 2)
        features = dict.fromkeys({"adaptive_solving", "auto_problem_spec", "problem_spec",
            "final_generation", "final_solution_review", "context_pack", "local_code_tool"}, True)
        self.open_initial([SPEC, ENUMERATE,
            {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT],
            SHOWCASE_STAR_REGISTRY=registry, SHOWCASE_STAR_FEATURES=features)
        observations = []
        original_complete = InternModelPort.complete

        def observe(port, request):
            estimate = port.serialized_payload_size(request)
            reply = original_complete(port, request)
            observations.append((request["role"], estimate, port.invocations[-1]["transport"]))
            return reply

        self.enterContext(patch.object(InternModelPort, "complete", observe))
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final)
        packs = final["result"]["solver"]["semantics"]["context_capacity"]["packs"]
        bodies = [call.kwargs["data"] for call in self.post.call_args_list]
        for raw in bodies[1:3]:
            body = json.loads(raw)
            self.assertEqual(2048, body["max_tokens"])
            pack = next(p for p in packs if p.get("payload_sha256") == hashlib.sha256(raw).hexdigest())
            self.assertEqual(len(raw), pack["serialized_utf8_bytes"])
            _, estimate, decision = observations[bodies.index(raw)]
            self.assertEqual(len(raw), estimate)
            canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            self.assertEqual(hashlib.sha256(canonical.encode()).hexdigest(),
                             decision["payload_fingerprint"])
        self.assertEqual([8192, 2048, 2048, 8192],
                         [a["max_tokens"] for a in final["result"]["request_attempts"]])

    def test_public_job_restart_reuses_known_length_and_latest_continuation_source(self):
        """Two separate processes share only a fresh persistent product directory."""
        import subprocess
        import sys
        import tempfile
        from pathlib import Path

        for scenario in ("length", "continuation", "protocol"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                for stage, code in (("crash", 71), ("resume", 0)):
                    result = subprocess.run([sys.executable, "-m", "tests.test_dependency_routing_review", directory,
                                             scenario, stage], capture_output=True, timeout=25)
                    self.assertEqual(code, result.returncode, result.stderr.decode(errors="replace"))
                before = json.loads((folder / "before.json").read_text())
                final = json.loads((folder / "final.json").read_text())
                sent = json.loads((folder / "sent.json").read_text())
                previous = json.loads((folder / "previous.json").read_text())
                evidence = Path("artifacts/issue189/reviewfix/restart-details") / scenario
                evidence.mkdir(parents=True, exist_ok=True)
                for name, value in (("before", before), ("final", final), ("sent", sent)):
                    (evidence / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
                self.assertEqual("succeeded", final["status"], [r["role"] for r in sent])
                self.assertEqual(before["job_id"], final["job_id"])
                for key in ("deadline_at", "limits"):
                    self.assertEqual(before["result"]["budget"][key], final["result"]["budget"][key])
                self.assertEqual(previous, sent[:len(previous)])
                self.assertEqual(["planner", "reasoner", "step_verifier", "final_generator",
                                  "whole_solution_verifier"],
                                 [r["role"] for r in sent[len(previous):]])
                self.assertEqual(len(sent), final["result"]["budget"]["http_attempts"])
                self.assertEqual(0, final["result"]["budget"]["unknown_attempts"])
                finding = sent[len(previous)]["exploration_findings"][0]
                self.assertEqual(previous[-1]["call_id"], finding["source"]["call_id"])
                if scenario in {"continuation", "protocol"}:
                    self.assertTrue(previous[-1]["call_id"].endswith(":tool-1"))
                self.assertEqual(["LATEST_REVIEW_PARTIAL"], finding["worked"])
                self.assertEqual("unverified_exploration", finding["provenance"])
                old = before["result"]["request_attempts"]
                self.assertEqual(old, final["result"]["request_attempts"][:len(old)])
                def hashes(job):
                    return {p["config_hash"] for p in job["result"]["solver"]["semantics"]
                            ["context_capacity"]["packs"]}
                self.assertEqual(hashes(before), hashes(final))


def restart_worker(directory, scenario, stage):
    """Small disposable crash/resume process, using existing product fixture APIs."""
    import os
    import time
    from copy import deepcopy
    from pathlib import Path

    from showcase.tools import ToolRegistry
    from showcase.workspace import WorkspaceStore
    from tests.test_faithful_s03_job import REPLIES
    from tests.test_star_product_explore_compute import ENUMERATE

    folder = Path(directory)
    case = DependencyRoutingReviewTest("test_public_compute_continuation_measures_actual_serialized_body")
    case.setUp()
    replies = deepcopy(REPLIES)
    replies[1]["steps"][0]["method_id"] = "direct"
    partial = {**replies[0], "worked": ["LATEST_REVIEW_PARTIAL"]}
    continuation = scenario in {"continuation", "protocol"}
    registry = ToolRegistry()
    registry.register("polynomial_check", lambda args: 2)
    features = dict.fromkeys({"adaptive_solving", "auto_problem_spec", "problem_spec",
        "final_generation", "final_solution_review", "context_pack", "local_code_tool",
        "progress_scheduling"}, True)
    prefix = [SPEC, *([ENUMERATE] if continuation else []), partial]
    if scenario == "protocol":
        prefix = [SPEC, {**ENUMERATE, "worked": ["STALE_REVIEW_PARTIAL"]},
                  {key: value for key, value in partial.items() if key != "candidates"}]
    case.open_initial(prefix if stage == "crash" else replies[1:],
        SHOWCASE_DATA_DIR=directory, SHOWCASE_STAR_REGISTRY=registry,
        SHOWCASE_STAR_FEATURES=features)
    original_post = case.post.side_effect

    def respond(*args, **kwargs):
        response = original_post(*args, **kwargs)
        if stage == "crash" and scenario != "protocol" and len(case.outbound) == len(prefix):
            original_json = response.json

            def truncated():
                body = original_json()
                body["choices"][0]["finish_reason"] = "length"
                return body

            response.json = truncated
        return response

    case.post.side_effect = respond
    if stage == "crash":
        original_append = WorkspaceStore.append_event

        def crash(store, job_id, event):
            value = original_append(store, job_id, event)
            if (event.get("solver_event_type") == "call_audit"
                    and len(case.outbound) == len(prefix)):
                while not (folder / "job_id").exists():
                    time.sleep(.01)
                (folder / "before.json").write_text(json.dumps(case.job(job_id)))
                (folder / "previous.json").write_text(json.dumps(case.outbound))
                os._exit(71)
            return value

        case.enterContext(patch.object(WorkspaceStore, "append_event", crash))
        job_id = case.create_job()
        (folder / "job_id").write_text(job_id)
        time.sleep(15)
        raise AssertionError("known protocol audit crash window not reached")
    job_id = (folder / "job_id").read_text()
    case.job(job_id)
    resumed = case.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=case.headers())
    case.assertEqual(202, resumed.status_code, resumed.get_json())
    final = case.terminal(job_id)
    (folder / "final.json").write_text(json.dumps(final))
    previous = json.loads((folder / "previous.json").read_text())
    (folder / "sent.json").write_text(json.dumps(previous + case.outbound))
    case.doCleanups()


if __name__ == "__main__":
    import sys

    restart_worker(*sys.argv[1:])
