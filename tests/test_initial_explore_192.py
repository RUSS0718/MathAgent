"""Initial Explore policy through public Jobs and controlled provider HTTP."""

import json
import os
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, SOLVED, StarJobFixture
from tests.test_faithful_s03_job import CAPACITY_POLICY, ENDPOINT, SPEC


class InitialExploreJobTest(StarJobFixture, unittest.TestCase):
    def open_initial(self, replies, **overrides):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        config = dict(
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(InternChatClient(retry=1), max_tokens=8192),
            SHOWCASE_STAR_ROUTING_POLICY_VERSION="objective-dependency-routing-v1",
            SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION="initial-explore-v1-2048",
            SHOWCASE_STAR_FEATURES=dict.fromkeys({"adaptive_solving", "auto_problem_spec",
                "problem_spec", "final_generation", "final_solution_review", "context_pack",
                "progress_scheduling"}, True),
            SHOWCASE_STAR_CONTEXT_CAPACITY=CAPACITY_POLICY,
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12))
        config.update(overrides)
        self.open_star(replies, **config)

    def payloads(self):
        return [json.loads(call.kwargs["data"]) for call in self.post.call_args_list]

    def test_simple_candidate_uses_request_cap_and_other_roles_keep_base(self):
        self.open_initial([SPEC, {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT])
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual([8192, 2048, 8192], [p["max_tokens"] for p in self.payloads()])
        self.assertEqual([8192, 2048, 8192],
                         [a["max_tokens"] for a in final["result"]["request_attempts"]])
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])

    def test_initial_admission_estimates_2048_while_preserving_base_review_capacity(self):
        self.enterContext(patch.dict(os.environ, {"INTERN_API_BASE": ENDPOINT}))
        self.open_initial([SPEC, {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT],
            SHOWCASE_STAR_ADAPTER=InternModelAdapter(InternChatClient(retry=1), max_tokens=32768),
            SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=12, max_http_attempts=12,
                                                max_tokens=220000))
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("result", {}).get("solver"))
        self.assertEqual([32768, 2048, 32768], [p["max_tokens"] for p in self.payloads()])

    def test_known_length_plans_without_repair_and_preserves_unverified_source(self):
        from copy import deepcopy

        from tests.test_faithful_s03_job import REPLIES

        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "direct"
        replies[0]["worked"] = ["PARTIAL_192: preliminary arithmetic"]
        self.open_initial([SPEC, *replies])
        original = self.post.side_effect

        def length_reply(*args, **kwargs):
            response = original(*args, **kwargs)
            context = self.outbound[-1]
            if context["role"] == "explore":
                original_json = response.json

                def truncated():
                    value = original_json()
                    value["choices"][0]["finish_reason"] = "length"
                    return value

                response.json = truncated
            return response

        self.post.side_effect = length_reply
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "planner", "reasoner", "step_verifier",
                          "final_generator", "whole_solution_verifier"],
                         [r["role"] for r in self.outbound])
        finding = next(r for r in self.outbound if r["role"] == "planner")["exploration_findings"][0]
        self.assertEqual("unverified_exploration", finding["provenance"])
        self.assertEqual(self.outbound[1]["call_id"], finding["source"]["call_id"])
        self.assertEqual("truncated_response", finding["end_reason"])
        self.assertEqual(["PARTIAL_192: preliminary arithmetic"], finding["worked"])
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("initial_explore_output_limit", events)

    def test_partial_exploration_is_short_and_plans_after_one_semantic_attempt(self):
        from copy import deepcopy

        from tests.test_faithful_s03_job import REPLIES

        replies = deepcopy(REPLIES)
        replies[0]["assessment"] = "PARTIALLY_SOLVED"
        replies[0]["worked"] = ["Reference only: a useful partial calculation"]
        replies[1]["steps"][0]["method_id"] = "direct"
        self.open_initial([SPEC, *replies])
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        explore = [r for r in self.outbound if r["role"] == "explore"]
        self.assertEqual(1, len(explore))
        self.assertIn("short exploration", explore[0]["instruction"])
        planner = next(r for r in self.outbound if r["role"] == "planner")
        self.assertIn("useful partial", planner["exploration_findings"][0]["worked"][0])
        self.assertIn("initial_explore_incomplete",
                      self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True))

    def test_normal_protocol_repair_inherits_cap(self):
        from tests.star_product_support import RawProviderContent

        self.open_initial([SPEC, RawProviderContent(""),
                           {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT])
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual([8192, 2048, 2048, 8192], [p["max_tokens"] for p in self.payloads()])
        self.assertTrue(self.outbound[2]["call_id"].endswith(":repair-1"))

    def test_concrete_whole_review_correction_retains_base_cap(self):
        candidate = {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}
        self.open_initial([SPEC, candidate, {"verdict": "REJECT", "reason": "Justify integer addition"},
                           candidate, ACCEPT])
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual([8192, 2048, 8192, 8192, 8192],
                         [p["max_tokens"] for p in self.payloads()])
        self.assertIn("review_feedback", self.outbound[3])

    def test_truncated_correction_also_plans_without_protocol_repair(self):
        from copy import deepcopy

        from tests.test_faithful_s03_job import REPLIES

        replies = deepcopy(REPLIES[1:])
        replies[0]["steps"][0]["method_id"] = "direct"
        candidate = {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}
        self.open_initial([SPEC, candidate, {"verdict": "REJECT", "reason": "Justify addition"},
                           candidate, *replies])
        original = self.post.side_effect

        def truncate_correction(*args, **kwargs):
            response = original(*args, **kwargs)
            if self.outbound[-1].get("review_feedback") and self.outbound[-1]["role"] == "explore":
                original_json = response.json

                def truncated():
                    value = original_json()
                    value["choices"][0]["finish_reason"] = "length"
                    return value

                response.json = truncated
            return response

        self.post.side_effect = truncate_correction
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual(["problem_intake", "explore", "whole_solution_verifier", "explore",
                          "planner", "reasoner", "step_verifier", "final_generator",
                          "whole_solution_verifier"], [r["role"] for r in self.outbound])
        self.assertEqual(8192, self.payloads()[3]["max_tokens"])

    def test_unknown_never_automatically_resends_plans_or_falls_back(self):
        import requests

        self.open_initial([SPEC, requests.ReadTimeout("unknown")])
        job_id = self.create_job()
        first = self.terminal(job_id)
        self.assertEqual("failed", first["status"])
        self.assertEqual(1, first["result"]["budget"]["unknown_attempts"])
        self.assertTrue(first["result"]["solver"]["recovery"]["unknown_calls"])
        self.job(job_id)
        self.report(job_id)
        response = self.client.post(f"/api/agent/jobs/{job_id}/resume", json={}, headers=self.headers())
        self.assertEqual(409, response.status_code)
        self.assertEqual(["problem_intake", "explore"], [r["role"] for r in self.outbound])
        self.assertEqual([8192, 2048], [p["max_tokens"] for p in self.payloads()])

    def test_compute_continuation_inherits_cap_and_one_semantic_round(self):
        from showcase.tools import ToolRegistry
        from tests.test_star_product_explore_compute import ENUMERATE

        registry = ToolRegistry()
        registry.register("polynomial_check", lambda args: 2)
        features = dict.fromkeys({"adaptive_solving", "auto_problem_spec", "problem_spec",
            "final_generation", "final_solution_review", "context_pack", "local_code_tool"}, True)
        self.open_initial([SPEC, ENUMERATE,
            {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT],
            SHOWCASE_STAR_REGISTRY=registry, SHOWCASE_STAR_FEATURES=features)
        final = self.terminal(self.create_job())
        self.assertEqual("succeeded", final["status"], final.get("error"))
        explores = [r for r in self.outbound if r["role"] == "explore"]
        self.assertEqual([1, 1], [r["round"] for r in explores])
        self.assertEqual(2, explores[1]["report"]["tool_receipts"][0]["output"])
        self.assertEqual([8192, 2048, 2048, 8192], [p["max_tokens"] for p in self.payloads()])
        self.assertEqual(1, final["result"]["budget"]["tool_calls"])

    def test_stream_first_run_only_initial_request_uses_explicit_nonstream(self):
        from showcase.adapters import InternStreamAdapter

        adapter = InternStreamAdapter(InternChatClient(retry=1), max_tokens=8192)
        self.open_initial([SPEC, {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT],
                          SHOWCASE_STAR_ADAPTER=adapter)
        job_id = self.create_job()
        final = self.terminal(job_id)
        self.assertEqual("succeeded", final["status"], final.get("error"))
        self.assertEqual([True, False, True], [p.get("stream", False) for p in self.payloads()])
        self.assertEqual([8192, 2048, 8192], [p["max_tokens"] for p in self.payloads()])
        self.assertEqual(8192, adapter.max_tokens)
        events = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn("initial_explore_explicit_nonstream", events)

    def test_old_and_new_jobs_resume_only_their_frozen_cap_policy(self):
        import uuid

        import requests

        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                options = {} if enabled else {"SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION": None}
                self.open_initial([SPEC, requests.ReadTimeout("unknown"),
                    {**SOLVED, "solution_candidate": "1+1=2 by integer addition."}, ACCEPT], **options)
                job_id = self.create_job()
                first = self.terminal(job_id)
                before = first["result"]["budget"]
                old_hashes = {p["config_hash"] for p in first["result"]["solver"]
                              ["semantics"]["context_capacity"]["packs"]}
                pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
                pipeline.initial_explore_policy_version = None if enabled else "initial-explore-v1-2048"
                old_call = first["result"]["solver"]["recovery"]["unknown_calls"][0]["call_id"]
                response = self.client.post(f"/api/agent/jobs/{job_id}/resume", headers=self.headers(),
                    json={"retry_call": {"call_id": old_call, "new_call_id": str(uuid.uuid4())}})
                self.assertEqual(202, response.status_code, response.get_json())
                final = self.terminal(job_id)
                self.assertEqual("succeeded", final["status"], final.get("error"))
                self.assertEqual([8192, 2048 if enabled else 8192,
                                  2048 if enabled else 8192, 8192],
                                 [p["max_tokens"] for p in self.payloads()])
                self.assertEqual(before["deadline_at"], final["result"]["budget"]["deadline_at"])
                self.assertEqual(before["limits"], final["result"]["budget"]["limits"])
                self.assertEqual(old_hashes, {p["config_hash"] for p in final["result"]["solver"]
                                 ["semantics"]["context_capacity"]["packs"]})

    def test_recovery_after_known_length_audit_does_not_redispatch_explore(self):
        from copy import deepcopy

        from showcase.solver_harness import SolverHarness
        from showcase.solver_harness.intern_port import InternModelPort
        from showcase.storage import SQLiteStore
        from tests.test_faithful_s03_job import REPLIES
        from tests.test_initial_explore_config_192 import INITIAL_CONFIG

        class Crash(BaseException):
            pass

        replies = deepcopy(REPLIES)
        replies[1]["steps"][0]["method_id"] = "direct"
        self.open_initial(replies)
        original = self.post.side_effect

        def truncate(*args, **kwargs):
            response = original(*args, **kwargs)
            if self.outbound[-1]["role"] == "explore":
                old_json = response.json

                def body():
                    value = old_json()
                    value["choices"][0]["finish_reason"] = "length"
                    return value

                response.json = body
            return response

        def crash_after_audit(run, event):
            if event["type"] == "call_audit" and event.get("outcome") == "protocol_failed":
                raise Crash()

        self.post.side_effect = truncate
        store = SQLiteStore()
        self.addCleanup(store.close)
        adapter = self.app.extensions["showcase_workspace_service"].star_pipeline.adapter
        port = InternModelPort(adapter)
        config = {**INITIAL_CONFIG, "max_model_calls": 12}
        with SolverHarness(store=store, config=config, model_port=port, verifier_port=port,
                           event_observer=crash_after_audit) as harness:
            with self.assertRaises(Crash):
                harness.solve("1+1", {"run_id": "length-crash", "problem_spec": SPEC})
        with SolverHarness(store=store, config=config, model_port=port, verifier_port=port) as harness:
            harness._product_recovery = True
            from showcase.star_product_recovery import resume_solver

            result = resume_solver(harness, "1+1", "length-crash", None)
        self.assertEqual("PLAN", result["state"]["phase"])
        self.assertEqual("truncated_response", result["state"]["exploration_findings"][0]["end_reason"])
        self.assertEqual(["explore"], [r["role"] for r in self.outbound])

    def test_known_incomplete_and_exhausted_protocol_repair_reach_planner(self):
        from copy import deepcopy

        from tests.star_product_support import RawProviderContent
        from tests.test_faithful_s03_job import REPLIES

        cases = (
            [{**SOLVED, "solution_candidate": " "}],
            [{"assessment": "UNKNOWN", "worked": [], "failed": [], "candidates": []}],
            [RawProviderContent("{"), RawProviderContent("{")],
        )
        for prefix in cases:
            with self.subTest(prefix=repr(prefix)):
                remaining = deepcopy(REPLIES[1:])
                remaining[0]["steps"][0]["method_id"] = "direct"
                self.open_initial([SPEC, *prefix, *remaining])
                job_id = self.create_job()
                final = self.terminal(job_id)
                self.assertEqual("succeeded", final["status"], final.get("error"))
                self.assertEqual(len(prefix), len([r for r in self.outbound if r["role"] == "explore"]))
                self.assertIn("planner", [r["role"] for r in self.outbound])
                self.assertTrue(all(p["max_tokens"] == 2048 for r, p in zip(self.outbound, self.payloads())
                                    if r["role"] == "explore"))
