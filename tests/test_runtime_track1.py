"""Cover the Track 1 salvage handoff and its shared request reservation."""

import json
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from ricl_runtime.providers.chat_completions import ChatCompletionReply, ProviderConfigurationError
from ricl_runtime.providers.track1 import Track1Provider
from ricl_runtime.track1 import solve
from ricl_runtime.track1_budget import SharedBudget
from ricl_runtime.track1_verification import check_assertion, lemma_graph


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
        review = '{"verdict":"fail","first_error":5,"valid_prefix":4}'
        graph = {"lemmas": [
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
        ]}
        replies = [initial, review, json.dumps(graph), initial, review, ""]
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
        self.assertEqual([p["max_tokens"] for p in payloads], [16384, 2048, 4096, 16384, 2048, 16384])
        self.assertEqual([p["max_tokens"] for p in payloads], [e["output_limit"] for e in started])
        self.assertEqual(["response_format" in p for p in payloads], [False, True, True, False, True, False])
        self.assertEqual(budget.reserved_cost, sum(
            budget.provider.estimated_cost(e["input_upper"], e["output_limit"]) for e in started
        ))
        graph_event, reused_pool = [event for event in events if event["event"] == "lemma_graph"]
        self.assertEqual(graph_event["eligible"], ["L1", "L2"])
        self.assertEqual(graph_event["pruned"], ["L7", "L8", "L9"])
        self.assertEqual(reused_pool["extraction_outcome"], "reuse_verified_pool")
        repair, switch = started[3], started[5]
        self.assertEqual(repair["action"], "pruned_repair")
        self.assertEqual(switch["action"], "salvage_switch")
        self.assertEqual(switch["lemmas_supplied"], repair["lemmas_supplied"])
        exact, reviewed = switch["lemmas_supplied"]
        prompt = payloads[5]["messages"][0]["content"]
        self.assertIn(f"[{exact}] [L1-Executable-Verified] lcm(6, 8) = 24", prompt)
        self.assertIn(f"[{reviewed}] [L2-Reviewed] Every solution lies in a single residue class.", prompt)
        self.assertEqual(graph_event["pool_evidence"], {
            exact: "L1-Executable-Verified", reviewed: "L2-Reviewed",
        })
        reuse = next(event for event in events if event["event"] == "lemma_reuse" and event["call"] == 6)
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
