"""Cover the Track 1 salvage handoff and its shared request reservation."""

import json
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from ricl_runtime.providers.chat_completions import (
    ChatCompletionReply,
    ProviderConfigurationError,
    ProviderProtocolError,
    post_chat_completion,
)
from ricl_runtime.providers.track1 import Track1Provider
from ricl_runtime.track1 import (
    Candidate,
    _answers_equivalent,
    _parse_review_payload,
    _public_answer,
    _selection,
    solve,
)
from ricl_runtime.track1_budget import SharedBudget
from ricl_runtime.track1_scheduler import RouteState, Track1SharedState, select_aprs_action
from ricl_runtime.track1_verification import (
    Lemma,
    check_assertion,
    json_object,
    lemma_graph,
    prune_graph,
)


class Track1Tests(unittest.TestCase):
    def test_l2_salvage_uses_source_quote_instead_of_extractor_paraphrase(self):
        source = "The sum of the two residues is even."
        node = {"id": "L1", "step": 1, "claim": "Both residues are even.",
                "source_quote": source, "premises": [], "global_scope": True}
        graph = lemma_graph(json.dumps({"lemmas": [node]}), (source,))
        self.assertEqual(graph.nodes[0].claim, source)
        self.assertTrue(graph.nodes[0].matches_source)
        graph = lemma_graph(json.dumps({"lemmas": [node | {"source_quote": "Both are even."}]}),
                            (source,))
        self.assertFalse(graph.nodes[0].matches_source)

    def test_extraction_accepts_a_sparse_graph_and_reports_redacted_shape_errors(self):
        lemma = {"id": "L1", "step": 1, "claim": "Private fixture claim.", "premises": []}
        steps = (lemma["claim"],)
        parsed = lemma_graph(json.dumps({"lemmas": [lemma]}), steps)
        self.assertEqual((parsed.outcome, parsed.node_count, len(parsed.nodes)), ("parsed", 1, 1))
        for changes, expected in (
            ({"id": "unexpected"}, "node_id"),
            ({"step": 2}, "source_step"),
            ({"premises": ["L9"]}, "premise_shape"),
        ):
            with self.subTest(expected=expected):
                rejected = lemma_graph(json.dumps({"lemmas": [lemma | changes]}), steps)
                self.assertEqual((rejected.outcome, rejected.node_count, rejected.rejected_node),
                                 (expected, 1, 1))
                self.assertEqual(rejected.nodes, ())
                self.assertNotIn(lemma["claim"], repr(rejected))

    def test_official_profile_pins_destination_model_and_rates(self):
        with patch.dict(os.environ, {
            "BASE_URL": "https://api.deepseek.com", "MODEL": "deepseek-flash", "API_KEY": "fixture",
        }):
            provider = Track1Provider.from_environment(16384, "none")
            with patch.dict(os.environ, {"MODEL": "deepseek-v4.1-flash"}):
                with self.assertRaises(ProviderConfigurationError):
                    Track1Provider.from_environment(16384, "none")
        with patch("ricl_runtime.providers.track1.post_chat_completion") as post:
            provider.complete("fixture", json_mode=True, max_output_tokens=2048)
        self.assertEqual(post.call_args.args[0], "https://api.deepseek.com/chat/completions")
        self.assertEqual(post.call_args.kwargs["payload"]["model"], "deepseek-flash")
        self.assertEqual(provider.estimated_cost(1000, 1000), Decimal("0.0015"))

    def test_salvage_injects_labeled_independent_lemmas_under_auxiliary_caps(self):
        initial = (
            "**Step 1:** We compute lcm(6, 8) = 24.\n"
            "### Step 2: Every solution lies in a single residue class.\n"
            "Step 3: The route assumes an odd parameter.\n"
            "Step 4: The two counts are equal.\n"
            "Step 5: We divide by zero.\n"
            "Step 6: There are exactly three solutions.\nFinal answer: 3"
        )
        fused_review = {
            "verdict": "fail",
            "first_error": 5,
            "valid_prefix": 4,
            "lemmas": [
                {"id": "L1", "step": 1, "claim": "lcm(6, 8) = 24", "premises": [],
                 "global_scope": True, "check": {"step": 1, "lhs": "lcm(6, 8)", "rhs": "24"}},
                {"id": "L2", "step": 2, "claim": "Every solution lies in a single residue class.",
                 "premises": [], "global_scope": True},
                {"id": "L3", "step": 3, "claim": "The route assumes an odd parameter.",
                 "premises": [], "global_scope": False},
                {"id": "L4", "step": 4, "claim": "The two counts are equal.",
                 "premises": ["L3"], "global_scope": True},
                {"id": "L5", "step": 6, "claim": "There are exactly three solutions.",
                 "premises": [], "global_scope": True},
                {"id": "L6", "step": 2, "claim": "There is exactly one solution.",
                 "premises": [], "global_scope": True},
                {"id": "L7", "step": 3, "claim": "2 + 2 = 5", "premises": [],
                 "global_scope": True, "check": {"step": 3, "lhs": "2 + 2", "rhs": "5"}},
                {"id": "L8", "step": 4, "claim": "The two counts are equal.",
                 "premises": ["L7"], "global_scope": True},
                {"id": "L9", "step": 5, "claim": "We divide by zero.",
                 "premises": [], "global_scope": False},
            ],
        }
        replies = [initial, json.dumps(fused_review), initial, json.dumps(fused_review), ""]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 24000, 6, Decimal("0.20"), events.append)

        def respond(url, *, payload, **kwargs):
            text = replies.pop(0)
            if not text:
                supplied = events[-1]["lemmas_supplied"]
                if supplied:
                    text = f"Step 1: Apply [{supplied[-1]}].\nFinal answer: 2"
            return ChatCompletionReply(text, input_tokens=30, output_tokens=40, finish_reason="stop")

        with patch("ricl_runtime.providers.track1.post_chat_completion", side_effect=respond) as post:
            result = solve("Problem", "RiCL_v0.2", budget, stop_after_salvage_dispatch=True)

        started = [event for event in events if event["event"] == "request_started"]
        payloads = [call.kwargs["payload"] for call in post.call_args_list]
        self.assertEqual(result["stop_reason"], "nonempty_salvage_dispatched")
        self.assertEqual([p["max_tokens"] for p in payloads], [16384, 4096, 16384, 4096, 16384])
        self.assertEqual([p["max_tokens"] for p in payloads], [e["output_limit"] for e in started])
        self.assertEqual(["response_format" in p for p in payloads], [False, True, False, True, False])
        self.assertEqual(budget.reserved_cost, sum(
            budget.provider.estimated_cost(e["input_upper"], e["output_limit"]) for e in started
        ))
        graph_event, _ = [event for event in events if event["event"] == "lemma_graph"]
        self.assertTrue(graph_event["fused"])
        self.assertEqual(graph_event["eligible"], ["L1", "L2"])
        self.assertEqual(graph_event["pruned"], ["L7", "L8", "L9"])
        repair, switch = started[2], started[4]
        self.assertEqual(repair["action"], "pruned_repair")
        self.assertEqual(switch["action"], "salvage_switch")
        self.assertEqual(switch["lemmas_supplied"], repair["lemmas_supplied"])
        exact, reviewed = switch["lemmas_supplied"]
        prompt = payloads[4]["messages"][0]["content"]
        self.assertIn(f"[{exact}] [L1-Executable-Verified] lcm(6, 8) = 24", prompt)
        self.assertIn(f"[{reviewed}] [L2-Reviewed] Every solution lies in a single residue class.", prompt)
        self.assertEqual(graph_event["pool_evidence"], {
            exact: "L1-Executable-Verified", reviewed: "L2-Reviewed",
        })
        reuse = next(event for event in events if event["event"] == "lemma_reuse" and event["call"] == 5)
        self.assertEqual(reuse["cited"], [reviewed])

    def test_l1_checks_exact_algebra_number_theory_and_substitution(self):
        for check in (
            {"lhs": "(x+1)**2", "rhs": "x**2+2*x+1", "variable": "x"},
            {"lhs": "lcm(6,8)", "rhs": "24"},
            {"lhs": "gcd(2025,2026)", "rhs": "1"},
            {"lhs": "2*3+1", "rhs": "7"},
        ):
            with self.subTest(check=check):
                self.assertEqual(check_assertion(check), "pass")
        self.assertEqual(check_assertion({"lhs": "x**2", "rhs": "x", "at": {"x": 1}}), "uncheckable")
        self.assertEqual(check_assertion({"lhs": "x**2", "rhs": "x", "at": {"x": 2}}), "fail")

    def test_b2_truncates_trajectory_to_verified_prefix_on_fail(self):
        initial = (
            "Step 1: Keep this valid step.\n"
            "Step 2: Also valid.\n"
            "Step 3: Bad step to discard.\n"
            "Step 4: Downstream polluted step.\nFinal answer: 99"
        )
        review1 = '{"verdict":"fail","first_error":3,"valid_prefix":2,"error_constraint":"Avoid division by zero."}'
        repaired = "Step 1: Keep this valid step.\nStep 2: Also valid.\nStep 3: Fixed step.\nFinal answer: 4"
        review2 = '{"verdict":"pass","first_error":0,"valid_prefix":3}'
        replies = [initial, review1, repaired, review2]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 40000, 6, Decimal("0.50"), events.append)
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies.pop(0), input_tokens=20, output_tokens=30, finish_reason="stop"
            ),
        ) as post:
            result = solve("Problem", "B2", budget)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_answer"], "4")
        self.assertEqual(result["action_sequence"], ["initial", "within_route_prefix_repair"])
        repair_prompt = post.call_args_list[2].kwargs["payload"]["messages"][0]["content"]
        self.assertIn("Step 1: Keep this valid step.", repair_prompt)
        self.assertIn("Step 2: Also valid.", repair_prompt)
        self.assertNotIn("Bad step to discard", repair_prompt)
        self.assertNotIn("Downstream polluted step", repair_prompt)
        self.assertIn("Avoid division by zero.", repair_prompt)

    def test_b3_rse_uses_same_l1_l2_verifier_without_dag_pruning(self):
        initial = "Step 1: 2 + 2 = 4.\nStep 2: Bad step.\nFinal answer: 5"
        review1 = '{"verdict":"fail","first_error":2,"valid_prefix":1}'
        rse_extract = json.dumps({
            "positive_lemmas": [
                {"claim": "2 + 2 = 4", "check": {"step": 1, "lhs": "2 + 2", "rhs": "4"}},
                {"claim": "2 + 2 = 5", "check": {"step": 1, "lhs": "2 + 2", "rhs": "5"}},
                {"claim": "Even parity holds.", "check": None},
            ],
            "negative_lessons": ["Do not skip parity check."],
        })
        rse_verify = '{"valid_lemma_indices":[2],"valid_lesson_indices":[0]}'
        retry_solve = "Step 1: Reuse lemma.\nFinal answer: 4"
        review2 = '{"verdict":"pass","first_error":0,"valid_prefix":1}'
        replies = [initial, review1, rse_extract, rse_verify, retry_solve, review2]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 48000, 8, Decimal("0.50"), events.append)

        def respond(url, *, payload, **kwargs):
            text = replies.pop(0)
            if text == retry_solve:
                supplied = events[-1]["lemmas_supplied"]
                text = f"Step 1: Apply [{supplied[0]}].\nFinal answer: 4"
            return ChatCompletionReply(text, input_tokens=20, output_tokens=30, finish_reason="stop")

        with patch("ricl_runtime.providers.track1.post_chat_completion", side_effect=respond) as post:
            result = solve("Problem", "B3", budget)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_answer"], "4")
        self.assertEqual(result["action_sequence"], ["initial", "rse_retry"])
        payloads = [c.kwargs["payload"] for c in post.call_args_list]
        self.assertEqual([p["max_tokens"] for p in payloads], [16384, 2048, 4096, 2048, 16384, 2048])
        retry_prompt = payloads[4]["messages"][0]["content"]
        self.assertIn("[L1-Executable-Verified] 2 + 2 = 4", retry_prompt)
        self.assertIn("[L2-Reviewed] Even parity holds.", retry_prompt)
        self.assertNotIn("2 + 2 = 5", retry_prompt)
        self.assertIn("Do not skip parity check.", retry_prompt)
        bank_event = next(e for e in events if e["event"] == "rse_bank_updated")
        self.assertEqual(bank_event["l1_failed"], 1)
        self.assertEqual(bank_event["bank_size"], 2)
        self.assertEqual(bank_event["lessons_size"], 1)
        reuse_event = next(e for e in events if e["event"] == "lemma_reuse")
        self.assertEqual(len(reuse_event["cited"]), 1)

    def test_b4_switches_route_without_extract_or_lemmas(self):
        initial = "Step 1: Wrong start.\nFinal answer: 1"
        review1 = '{"verdict":"fail","first_error":1,"valid_prefix":0}'
        switched = "Step 1: Fresh distinct route.\nFinal answer: 4"
        review2 = '{"verdict":"pass","first_error":0,"valid_prefix":1}'
        replies = [initial, review1, switched, review2]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 40000, 6, Decimal("0.50"), events.append)
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies.pop(0), input_tokens=20, output_tokens=30, finish_reason="stop"
            ),
        ):
            result = solve("Problem", "B4", budget)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_answer"], "4")
        self.assertEqual(result["action_sequence"], ["initial", "switch_no_salvage"])
        started = [e for e in events if e["event"] == "request_started"]
        self.assertEqual([e["stage"] for e in started], ["solve", "review", "solve", "review"])
        self.assertFalse(any(e.get("lemmas_supplied") for e in started))

    def test_public_answer_and_selection_preserve_valid_answers_and_consensus(self):
        nested_inline = "Step 1: Compute.\nTherefore, the exact value is $\\boxed{\\frac{1}{2}}$."
        self.assertEqual(_public_answer(nested_inline), "\\frac{1}{2}")
        repeated = "Step 1: x=4.\nFinal answer: 4\nSummary:\nFinal answer: $4$."
        self.assertEqual(_public_answer(repeated), "4")
        conflicting = "Final answer: 4\nFinal answer: 5"
        self.assertIsNone(_public_answer(conflicting))

        c_first = Candidate("s1", "60", "fail", 8, 7, (), "uncheckable", "err1")
        c_longer_none = Candidate("s2", None, "fail", 18, 17, (), "uncheckable", "err2")
        c_consensus = Candidate("s3", "60", "fail", 4, 3, (), "uncheckable", "err3")
        self.assertEqual(_selection([c_first, c_longer_none], "RiCL_v0.2").answer, "60")
        c_alt = Candidate("s4", "99", "fail", 12, 11, (), "uncheckable", "err4")
        self.assertEqual(_selection([c_first, c_alt, c_consensus], "RiCL_v0.2").answer, "60")

    def test_sympy_l1_and_normalized_prune_graph_admission(self):
        for check, expected in (
            ({"lhs": "sqrt(8)", "rhs": "2*sqrt(2)"}, "pass"),
            ({"lhs": "sqrt(2)+sqrt(3)", "rhs": "sqrt(5)"}, "fail"),
            ({"lhs": "(x+y)**2", "rhs": "x**2+2*x*y+y**2", "variables": ["x", "y"]}, "pass"),
            ({"lhs": "sqrt(x**2)", "rhs": "x", "variable": "x"}, "fail"),
        ):
            with self.subTest(check=check):
                self.assertEqual(check_assertion(check), expected)

        source = ("We find that $a + b = 10$.", "Independent fact: gcd(12, 18) = 6.")
        nodes = {"lemmas": [
            {"id": "L1", "step": 1, "claim": "a+b=10", "source_quote": "**$a + b = 10$**",
             "premises": [], "global_scope": True},
            {"id": "L2", "step": 2, "claim": "gcd(12, 18) = 6", "premises": [], "global_scope": True,
             "check": {"step": 2, "lhs": "gcd(12, 18)", "rhs": "6"}},
        ]}
        graph = lemma_graph(json.dumps(nodes), source)
        self.assertTrue(graph.nodes[0].matches_source)
        self.assertEqual(graph.nodes[1].check, "pass")

        _, retained_unknown = prune_graph(graph.nodes, first_error=0, reviewed_prefix=0)
        self.assertEqual([(n.id, ev) for n, ev in retained_unknown], [("L2", "L1-Executable-Verified")])

        _, retained_incomplete = prune_graph(graph.nodes, first_error=0, reviewed_prefix=1)
        self.assertEqual(
            [(n.id, ev) for n, ev in retained_incomplete],
            [("L1", "L2-Reviewed"), ("L2", "L1-Executable-Verified")],
        )

    def test_ricl_v022_retains_prefix_post_error_l1_constraints_and_half_byte_budget(self):
        long_problem = "Find n. " + ("condition " * 1800)  # ~18 KB prompt
        initial = (
            "Step 1: Valid base setup.\n"
            "Step 2: Bad division.\n"
            "Step 3: Independent check 3*4 = 12.\n"
            "Final answer: 10"
        )
        repair_sol = "Step 1: Still missing tail.\nFinal answer: 11"
        switch_sol = "Step 1: Resolved cleanly.\nFinal answer: 12"
        review_pass = '{"verdict":"pass","first_error":0,"valid_prefix":1}'

        # 1) Half-byte budget check avoids false token_limit on long prompts + skips continue on l2="unknown"
        budget_extract = SharedBudget(
            Track1Provider("fixture", max_output_tokens=8192),
            32768, 4, Decimal("1.00"), [].append, tokens=14000,
        )
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            return_value=ChatCompletionReply("{}", input_tokens=5000, output_tokens=100, finish_reason="stop"),
        ) as direct_post:
            budget_extract.complete("review_extract", "x" * 20000)
        self.assertEqual(direct_post.call_count, 1)

        lemmas = [
            {"id": "L1", "step": 1, "claim": "Valid base setup.", "premises": [], "global_scope": True},
            {"id": "L2", "step": 2, "claim": "Bad division.", "premises": [], "global_scope": False},
            {"id": "L3", "step": 3, "claim": "3*4 = 12", "premises": [], "global_scope": True,
             "check": {"step": 3, "lhs": "3*4", "rhs": "12"}},
        ]
        # Disagreed scout -> R1 fails with l2=unknown (not JSON), R2 audited -> fail -> R2 repair -> pass
        fused_fail1 = json.dumps({
            "verdict": "fail", "first_error": 2, "valid_prefix": 1,
            "error_constraint": "Avoid d=0.", "lemmas": lemmas,
        })
        fused_fail2 = json.dumps({
            "verdict": "fail", "first_error": 1, "valid_prefix": 0,
            "error_constraint": "Check parity.", "lemmas": lemmas,
        })
        replies1 = [
            "Step 1: Setup only.\nFinal answer: 9",
            initial,
            fused_fail1,
            "not json",
            repair_sol,
            fused_fail2,
            switch_sol,
            review_pass,
        ]
        events1 = []
        budget1 = SharedBudget(
            Track1Provider("fixture", max_output_tokens=8192), 49152, 10, Decimal("1.00"), events1.append,
        )
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies1.pop(0), input_tokens=1500, output_tokens=300, finish_reason="stop"
            ),
        ) as post1:
            result1 = solve(long_problem, "RiCL_v0.2", budget1)

        self.assertEqual(result1["status"], "completed")
        self.assertEqual(result1["final_answer"], "12")
        self.assertNotIn("continue", result1["action_sequence"])
        self.assertEqual(
            result1["action_sequence"],
            ["initial", "scout_route", "pruned_repair", "salvage_switch"],
        )
        payloads = [c.kwargs["payload"]["messages"][0]["content"] for c in post1.call_args_list]
        repair_prompt = payloads[4]
        self.assertIn("Step 1: Valid base setup.", repair_prompt)
        self.assertIn("[L1-Executable-Verified] 3*4 = 12", repair_prompt)
        self.assertIn("Avoid d=0.", repair_prompt)
        switch_prompt = payloads[6]
        self.assertIn("[L1-Executable-Verified] 3*4 = 12", switch_prompt)
        self.assertIn("Avoid d=0.", switch_prompt)
        self.assertIn("Check parity.", switch_prompt)

        # 2) Genuine incomplete (no scout when first draft has no public answer) dispatches continue at most once
        fused_inc = json.dumps({
            "verdict": "incomplete", "first_error": 0, "valid_prefix": 1, "lemmas": lemmas,
        })
        replies2 = [
            "Step 1: Valid start.\nStep 2: Unfinished.",
            fused_inc,
            "Step 1: Valid start.\nStep 2: Still unfinished.",
            fused_inc,
            switch_sol,
            json.dumps({"verdict": "pass", "first_error": 0, "valid_prefix": 1, "lemmas": []}),
        ]
        events2 = []
        budget2 = SharedBudget(Track1Provider("fixture"), 32768, 12, Decimal("1.00"), events2.append)
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies2.pop(0), input_tokens=30, output_tokens=40, finish_reason="stop"
            ),
        ):
            result2 = solve("Problem", "RiCL_v0.2", budget2)

        self.assertEqual(result2["status"], "completed")
        self.assertEqual(result2["action_sequence"], ["initial", "continue", "salvage_switch"])

    def test_siliconflow_profile_configures_thinking_budget_and_json_no_thinking(self):
        with patch.dict(os.environ, {
            "BASE_URL": "https://api.siliconflow.cn/v1",
            "MODEL": "Qwen/Qwen3-14B",
            "API_KEY": "fixture",
        }):
            provider_high = Track1Provider.from_environment(16384, "high")
            provider_low = Track1Provider.from_environment(16384, "low")
        self.assertEqual(provider_high.timeout, 300.0)
        with patch("ricl_runtime.providers.track1.post_chat_completion") as post:
            provider_high.complete("solve", json_mode=False)
            provider_low.complete("solve-low", json_mode=False)
            provider_high.complete("audit", json_mode=True, max_output_tokens=4096)
        solve_high = post.call_args_list[0].kwargs["payload"]
        solve_low = post.call_args_list[1].kwargs["payload"]
        json_payload = post.call_args_list[2].kwargs["payload"]
        self.assertEqual(
            post.call_args_list[0].args[0], "https://api.siliconflow.cn/v1/chat/completions"
        )
        self.assertNotIn("thinking", solve_high)
        self.assertNotIn("reasoning_effort", solve_high)
        self.assertTrue(solve_high["enable_thinking"])
        self.assertTrue(solve_high["stream"])
        self.assertEqual(solve_high["stream_options"], {"include_usage": True})
        self.assertEqual(solve_high["thinking_budget"], 4096)
        self.assertEqual(solve_low["thinking_budget"], 2048)
        self.assertFalse(json_payload["enable_thinking"])
        self.assertTrue(json_payload["stream"])
        self.assertNotIn("thinking_budget", json_payload)
        self.assertEqual(json_payload["response_format"], {"type": "json_object"})
        self.assertEqual(provider_high.estimated_cost(1_000_000, 1_000_000), Decimal("0.35"))

        with patch.dict(os.environ, {
            "BASE_URL": "https://api.siliconflow.cn/v1",
            "MODEL": "Qwen/Qwen3-30B-A3B-Instruct-2507",
            "API_KEY": "fixture",
        }):
            inst = Track1Provider.from_environment(16384, "low")
        with patch("ricl_runtime.providers.track1.post_chat_completion") as post_inst:
            inst.complete("solve", json_mode=False)
        inst_payload = post_inst.call_args.kwargs["payload"]
        self.assertNotIn("enable_thinking", inst_payload)
        self.assertNotIn("thinking_budget", inst_payload)
        self.assertEqual(inst.estimated_cost(1_000_000, 1_000_000), Decimal("0.39"))

        with patch.dict(os.environ, {
            "BASE_URL": "https://api.siliconflow.cn/v1",
            "MODEL": "Qwen/unlisted-model",
            "API_KEY": "fixture",
        }):
            with self.assertRaises(ProviderConfigurationError):
                Track1Provider.from_environment(16384, "low")

    def test_disagreement_gate_exits_in_two_calls_on_consensus(self):
        replies = [
            "Step 1: Compute ratio.\nFinal answer: \\frac{1}{2}",
            "Step 1: Alternate proof.\nFinal answer: 1/2",
        ]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 32768, 8, Decimal("1.00"), events.append)
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies.pop(0), input_tokens=40, output_tokens=50, finish_reason="stop"
            ),
        ):
            result = solve("Problem", "RiCL_v0.2", budget)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["stop_reason"], "consensus_passed")
        self.assertEqual(result["api_calls"], 2)
        self.assertEqual(result["action_sequence"], ["initial", "scout_route"])
        self.assertEqual(result["verification"]["l2"], "consensus_pass")

    def test_aprs_multi_route_scheduler_and_srs_invalidation(self):
        srs = Track1SharedState()
        bad_l2 = (
            Lemma("L1", 1, "x = 5", (), "uncheckable", True, True),
            Lemma("L2", 2, "x + 1 = 6", ("L1",), "uncheckable", True, True),
        )
        admitted = srs.admit_pruned(bad_l2, ((bad_l2[0], "L2-Reviewed"), (bad_l2[1], "L2-Reviewed")), "R1")
        self.assertEqual(len(admitted), 2)
        self.assertEqual(len(srs.active_pool()), 2)
        srs.invalidate_claim("x = 5")
        self.assertEqual(srs.active_pool(), {})

        r1 = RouteState("R1", "initial", Candidate("s1", "10", "fail", 3, 1, ("a", "b", "c"), "uncheckable", "err1"), reviewed=True, spent_tokens=4000, l1_lemmas=0, l2_lemmas=1)
        r2 = RouteState("R2", "scout", Candidate("s2", "11", "fail", 3, 2, ("a", "b", "c"), "uncheckable", "err2"), reviewed=True, spent_tokens=1500, l1_lemmas=2, l2_lemmas=0)
        rid, act, trace = select_aprs_action([r1, r2], srs)
        self.assertEqual((rid, act), ("R2", "pruned_repair"))
        self.assertEqual(trace["priority_order"], ["R2", "R1"])

    def test_strip_thinking_tags_before_step_and_answer_parsing(self):
        text = "<think>Step 1: wrong scratch.\nFinal answer: 999</think>\nStep 1: Clean proof.\nFinal answer: 42"
        self.assertEqual(_public_answer(text), "42")

    def test_sse_chat_completion_assembles_content_usage_and_discards_reasoning_content(self):
        chunks = [
            b'data: {"id":"req_sse","model":"Qwen/Qwen3.5-35B-A3B","choices":[{"delta":{"reasoning_content":"secret-cot"}}]}\n',
            b'data: {"id":"req_sse","model":"Qwen/Qwen3.5-35B-A3B","choices":[{"delta":{"content":"Step 1: x = 4.\\n"}}]}\n',
            b'data: {"id":"req_sse","model":"Qwen/Qwen3.5-35B-A3B","choices":[{"delta":{"content":"Final answer: 4"},"finish_reason":"stop"}]}\n',
            b'data: {"id":"req_sse","model":"Qwen/Qwen3.5-35B-A3B","choices":[],"usage":{"prompt_tokens":20,"completion_tokens":35,"completion_tokens_details":{"reasoning_tokens":30}}}\n',
            b"data: [DONE]\n",
        ]

        class _FakeResponse:
            def __init__(self, lines: list[bytes]) -> None:
                self._lines = lines

            def __enter__(self) -> "_FakeResponse":
                return self

            def __exit__(self, *args: object) -> None:
                return None

            def __iter__(self):
                return iter(self._lines)

        class _FakeOpener:
            def __init__(self, lines: list[bytes]) -> None:
                self._lines = lines

            def open(self, request, timeout: float = 0):
                return _FakeResponse(self._lines)

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=_FakeOpener(chunks),
        ):
            reply = post_chat_completion(
                "https://api.siliconflow.cn/v1/chat/completions",
                api_key="sk-secret",
                payload={"model": "Qwen/Qwen3.5-35B-A3B", "messages": [], "stream": True},
                timeout=300.0,
                max_bytes=65536,
                track1_usage=True,
            )
        self.assertEqual(reply.text, "Step 1: x = 4.\nFinal answer: 4")
        self.assertNotIn("secret-cot", reply.text)
        self.assertEqual((reply.input_tokens, reply.output_tokens, reply.reasoning_tokens), (20, 35, 30))
        self.assertEqual((reply.finish_reason, reply.usage_source, reply.model), ("stop", "provider", "Qwen/Qwen3.5-35B-A3B"))

        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=_FakeOpener([chunks[1]]),
        ):
            with self.assertRaises(ProviderProtocolError):
                post_chat_completion(
                    "https://api.siliconflow.cn/v1/chat/completions",
                    api_key="sk-secret",
                    payload={"model": "Qwen/Qwen3.5-35B-A3B", "messages": [], "stream": True},
                    timeout=300.0,
                    max_bytes=20,
                    track1_usage=True,
                )

        leak_chunk = b'data: {"id":"req","model":"m","choices":[{"delta":{"content":"sk-secret"}}]}\n'
        with patch(
            "ricl_runtime.providers.chat_completions.urllib.request.build_opener",
            return_value=_FakeOpener([leak_chunk, b"data: [DONE]\n"]),
        ):
            with self.assertRaises(ProviderProtocolError):
                post_chat_completion(
                    "https://api.siliconflow.cn/v1/chat/completions",
                    api_key="sk-secret",
                    payload={"model": "m", "messages": [], "stream": True},
                    timeout=300.0,
                    max_bytes=65536,
                    track1_usage=True,
                )

    def test_14b_review_clamping_json_extraction_and_placeholder_guard(self):
        self.assertIsNone(_public_answer("Step 1: x.\nFinal answer: <exact_answer>"))
        self.assertIsNone(_public_answer("Step 1: x.\nFinal answer: <answer>"))
        self.assertEqual(json_object("Here is the JSON:\n{\"verdict\": \"pass\"}\nDone."), {"verdict": "pass"})
        self.assertEqual(json_object("not json"), {})

        steps = ("s1", "s2", "s3", "s4")
        sol = "Step 1: s1\nStep 2: s2\nStep 3: s3\nStep 4: s4\nFinal answer: 42"
        verdict, error, prefix, *_ = _parse_review_payload(
            '{"verdict":"fail","first_error":3,"valid_prefix":3}', "stop", sol, steps, False,
        )
        self.assertEqual((verdict, error, prefix), ("fail", 3, 2))
        verdict_p, err_p, pref_p, *_ = _parse_review_payload(
            '{"verdict":"pass","first_error":0,"valid_prefix":0}', "stop", sol, steps, False,
        )
        self.assertEqual((verdict_p, err_p, pref_p), ("pass", 0, 4))

    def test_boxed_unwrap_with_trailing_period_and_siliconflow_deepseek_allowlist(self):
        self.assertEqual(_public_answer("Final answer: \\boxed{\\dfrac{2}{1005}}."), "\\dfrac{2}{1005}")
        self.assertEqual(_public_answer("Final answer: $\\boxed{\\boxed{\\dfrac{2}{1005}}}$."), "\\dfrac{2}{1005}")
        self.assertTrue(_answers_equivalent("\\dfrac{2}{1005}", "\\tfrac{2}{1005}"))

        for model_name in ("deepseek-ai/DeepSeek-V4.1-Flash", "deepseek-ai/DeepSeek-V3.2"):
            with patch.dict(os.environ, {
                "BASE_URL": "https://api.siliconflow.cn/v1",
                "MODEL": model_name,
                "API_KEY": "fixture",
            }):
                provider = Track1Provider.from_environment(16384, "low")
                provider_high = Track1Provider.from_environment(16384, "high")
            self.assertEqual(provider.name, model_name)
            self.assertTrue(provider.supports_thinking)
            with patch("ricl_runtime.providers.track1.post_chat_completion") as post_ds:
                provider.complete("solve", json_mode=False)
                provider_high.complete("solve-high", json_mode=False)
            self.assertEqual(post_ds.call_args_list[0].kwargs["payload"]["thinking_budget"], 4096)
            self.assertEqual(post_ds.call_args_list[1].kwargs["payload"]["thinking_budget"], 8192)

    def test_empty_draft_skips_remote_review_and_does_not_burn_interventions(self):
        replies = [
            "Hmm.",
            "<think>long chain</think>\nWait.",
            "Step 1: x = 4.\nFinal answer: 4",
            json.dumps({"verdict": "pass", "first_error": 0, "valid_prefix": 1, "lemmas": []}),
        ]
        events = []
        budget = SharedBudget(Track1Provider("fixture"), 32768, 8, Decimal("1.00"), events.append)
        with patch(
            "ricl_runtime.providers.track1.post_chat_completion",
            side_effect=lambda *a, **kw: ChatCompletionReply(
                replies.pop(0), input_tokens=40, output_tokens=2053, reasoning_tokens=2049, finish_reason="stop"
            ),
        ):
            result = solve("Problem", "RiCL_v0.2", budget)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_answer"], "4")
        self.assertEqual(result["api_calls"], 4)
        self.assertEqual(sum(1 for e in events if e.get("local_empty_skip")), 2)

    def test_lemma_grounding_latex_overlap_and_l1_check_matching(self):
        steps = ("First, \\frac{a+b}{2} * c = 12 holds.", "Identity x^2 - 1 = (x-1)(x+1).")
        payload = json.dumps({
            "lemmas": [
                {
                    "id": "L1", "step": 1, "claim": "paraphrase",
                    "source_quote": "\\dfrac{a + b}{2} \\cdot c = 12",
                    "premises": [], "global_scope": True, "check": None,
                },
                {
                    "id": "L2", "step": 1, "claim": "bad digits",
                    "source_quote": "\\dfrac{a + b}{2} \\cdot c = 13",
                    "premises": [], "global_scope": True, "check": None,
                },
                {
                    "id": "L3", "step": 2, "claim": "x^2 - 1 = (x-1)(x+1)",
                    "source_quote": None, "premises": [], "global_scope": True,
                    "check": {"step": 2, "lhs": "x**2 - 1", "rhs": "(x-1)*(x+1)", "variable": "x"},
                },
                {
                    "id": "L4", "step": 2, "claim": "x = 5",
                    "source_quote": None, "premises": [], "global_scope": True,
                    "check": {"step": 2, "lhs": "1+1", "rhs": "2"},
                },
            ]
        })
        graph = lemma_graph(payload, steps)
        self.assertEqual(graph.outcome, "parsed")
        self.assertTrue(graph.nodes[0].matches_source)
        self.assertFalse(graph.nodes[1].matches_source)
        self.assertEqual(graph.nodes[2].check, "pass")
        self.assertEqual(graph.nodes[3].check, "uncheckable")
