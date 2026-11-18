"""S02 context contracts at the public Harness and serialized request seams."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from llm_client import InternChatClient
from showcase.adapters import AdapterError, InternModelAdapter
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import SolverHarness
from showcase.solver_harness.context_pack import (
    ContextCapacityExceeded,
    finalize_context_pack,
    frozen_policy,
    prepare_context_request,
)
from showcase.star_product_config import CORE_FEATURES, core_gaps, full_config
from showcase.star_result_semantics import result_semantics


def capacity_policy(*, cap=500, output=100, margin=25):
    return {
        "version": "context-capacity-v1",
        "profile_version": "intern-s2-managed-v1",
        "provider": "intern",
        "model": "intern-s2",
        "endpoint": "https://api.example.test/v1/chat/completions",
        "cap_source": "provider_profile",
        "cap_source_date": "2026-11-07",
        "input_cap_tokens": cap,
        "output_reserve_tokens": output,
        "safety_margin_tokens": margin,
        "token_estimator_version": "utf8-bytes-per-three-v1",
    }


class FaithfulS02ContextTest(unittest.TestCase):
    def test_context_pack_is_not_a_default_full_core_feature(self):
        default = full_config(RunBudgetLimits(max_model_calls=3, max_http_attempts=3,
                                              max_tool_calls=0))
        self.assertNotIn("context_pack", CORE_FEATURES)
        self.assertIsNot(default["features"].get("context_pack"), True)
        self.assertNotIn("context_capacity", default)
        self.assertFalse(any(gap == "feature:context_pack" for gap in core_gaps(default)))

    def test_legacy_semantics_shape_is_unchanged_without_explicit_context_policy(self):
        run = {"run_id": "legacy", "state": {
            "status": "partial_aborted", "phase": "TERMINAL", "calls": {},
            "whole_solution_reviews": [],
        }}
        self.assertEqual({
            "version": "star-result-semantics-v1", "execution": "needs_review",
            "transport": "unavailable", "whole_review": "not_reviewed",
            "binding": "unbound", "formal_verification": "not_verified",
            "verification_requirement": "default",
        }, result_semantics(run, "answer"))

    def test_default_off_and_new_run_policy_survives_configuration_disable(self):
        problem = "证明 x 属于实数"
        config = {"features": {"context_pack": True}, "context_capacity": capacity_policy()}
        request = {"role": "reasoner", "call_id": "s02", "problem": problem}
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "context.db"
            with SolverHarness(config=config, database_path=database) as harness:
                created = harness.solve(problem, {"run_id": "s02-frozen"})
                prepared = harness.prepare_request(created, request)
                self.assertTrue(prepared["_context_policy"]["enabled"])

            disabled = {"features": {"context_pack": False}}
            with SolverHarness(config=disabled, database_path=database) as restored:
                run = restored.get_run("s02-frozen", problem=problem)
                prepared = restored.prepare_request(run, request)
                self.assertTrue(prepared["_context_policy"]["enabled"])

        with SolverHarness(config={}) as default_harness:
            default_run = default_harness.solve("默认不启用", {"run_id": "s02-default"})
            self.assertFalse(default_run["state"]["context_policy"]["enabled"])

    def test_frozen_policy_digest_binds_profile_and_limits(self):
        first = frozen_policy({"features": {"context_pack": True},
                               "context_capacity": capacity_policy()})
        second = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy(cap=600)})
        self.assertEqual(first["policy_sha256"], frozen_policy({
            "features": {"context_pack": True}, "context_capacity": capacity_policy(),
        })["policy_sha256"])
        self.assertNotEqual(first["policy_sha256"], second["policy_sha256"])

    def test_frozen_policy_rejects_versions_without_an_implemented_estimator(self):
        invalid_cases = (("version", "context-capacity-v2"),
                         ("token_estimator_version", "exact-tokenizer-v2"),
                         ("recent_history_exchanges", 0))
        for key, value in invalid_cases:
            with self.subTest(key=key):
                invalid = capacity_policy()
                invalid[key] = value
                with self.assertRaises(ValueError):
                    frozen_policy({"features": {"context_pack": True},
                                   "context_capacity": invalid})

    def test_unknown_capacity_is_reported_uncalibrated_and_full_payload_is_counted(self):
        policy = {**capacity_policy(cap=None), "enabled": True}
        payload = json.dumps(
            {"model": "intern-s2", "messages": [{"role": "system", "content": "定义"}],
             "tools": [{"name": "python_math", "schema": {"输入": "整数"}}],
             "max_tokens": 100},
            ensure_ascii=False,
        ).encode("utf-8")
        pack = finalize_context_pack(
            payload, policy, role="reasoner", run_id="r1", state_revision=7,
            problem_hash="p", endpoint=policy["endpoint"],
        )
        self.assertEqual("uncalibrated", pack["capacity_status"])
        self.assertEqual(len(payload), pack["serialized_utf8_bytes"])
        self.assertIn("payload.messages", pack["included_refs"])
        self.assertIn("payload.tools", pack["included_refs"])
        self.assertIn("Heuristic", pack["token_estimate_error"])

    def test_known_cap_reserves_output_and_margin_once_then_refuses(self):
        policy = {**capacity_policy(cap=100, output=20, margin=10), "enabled": True}
        payload = b'{"model":"intern-s2","messages":[]}'
        pack = finalize_context_pack(
            payload, policy, role="reasoner", run_id="r1", state_revision=2,
            problem_hash="p", endpoint=policy["endpoint"],
        )
        self.assertEqual(30, pack["reserved_tokens"])
        self.assertEqual(70, pack["available_input_tokens"])
        too_large = b'{"model":"intern-s2","messages":[{"content":"' + b'x' * 500 + b'"}]}'
        with self.assertRaises(ContextCapacityExceeded):
            finalize_context_pack(
                too_large, policy, role="whole_solution_verifier", run_id="r1",
                state_revision=3, problem_hash="p", endpoint=policy["endpoint"],
            )

    def test_history_is_deduplicated_and_archived_once_with_stable_sources(self):
        repeated = {"request": {"role": "reasoner", "step": {"objective": "证题"}},
                    "response": {"argument": "推导"}}
        request = {"role": "reasoner", "problem": "完整原题", "session_key": "s",
                   "session_history": [repeated, repeated,
                                       {"request": {"role": "step_verifier"},
                                        "response": {"objection": "边界"}}]}
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy()})
        packed = prepare_context_request(request, policy, run_id="r1",
                                         state_revision=9, problem_hash="p")
        self.assertEqual(1, len(packed["session_history"]))
        self.assertEqual(1, packed["_context_pack"]["archived_history"]["count"])
        self.assertEqual("完整原题", packed["problem"])
        self.assertTrue(packed["_context_pack"]["archived_history"]["sha256"])

    def test_recent_tool_receipt_retains_its_request_from_the_prior_exchange(self):
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": {
                                    **capacity_policy(), "recent_history_exchanges": 1,
                                }})
        tool_request = {
            "tool": "python_math", "arguments": {"expression": "2+2"},
            "scope": "finite_computation",
        }
        receipt = {
            "receipt_id": "receipt-1", "review_call_id": "review-call-1",
            "request_digest": "digest-1", "status": "success", "output": "4",
        }
        source_exchange = {
            "request": {"call_id": "review-call-1", "role": "step_verifier"},
            "response": {"tool_request": tool_request},
        }
        receipt_exchange = {
            "request": {"call_id": "review-call-1:tool-1", "role": "step_verifier",
                        "report": {"tool_receipts": [receipt]}},
            "response": {"verdict": "ACCEPT"},
        }
        prepared = prepare_context_request({
            "role": "step_verifier", "session_history": [source_exchange, receipt_exchange],
        }, policy, run_id="r", state_revision=13, problem_hash="p")
        retained = prepared["session_history"]
        self.assertEqual(2, len(retained))
        self.assertEqual(tool_request, retained[0]["response"]["tool_request"])
        self.assertEqual(receipt, retained[1]["request"]["report"]["tool_receipts"][0])
        self.assertEqual("review-call-1", retained[0]["request"]["call_id"])

    def test_current_report_receipt_retains_its_older_source_tool_request(self):
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy()})
        tool_request = {
            "tool": "python_math", "arguments": {"expression": "3+4"},
            "scope": "finite_computation",
        }
        receipt = {"receipt_id": "receipt-current", "review_call_id": "review-call-old",
                   "status": "success", "output": "7"}
        source_exchange = {
            "request": {"call_id": "review-call-old", "role": "step_verifier"},
            "response": {"tool_request": tool_request},
        }
        latest_exchange = {
            "request": {"call_id": "other-call", "role": "step_verifier"},
            "response": {"verdict": "REJECT"},
        }
        prepared = prepare_context_request({
            "role": "step_verifier", "report": {"tool_receipts": [receipt]},
            "session_history": [source_exchange, latest_exchange],
        }, policy, run_id="r", state_revision=14, problem_hash="p")
        retained = prepared["session_history"]
        self.assertEqual(2, len(retained))
        self.assertEqual("review-call-old", retained[0]["request"]["call_id"])
        self.assertEqual(tool_request, retained[0]["response"]["tool_request"])
        self.assertEqual([receipt], prepared["report"]["tool_receipts"])

    def test_current_problem_objection_tool_pair_and_whole_answer_remain_exact(self):
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy()})
        request = {
            "role": "whole_solution_verifier", "problem": "原题：对所有实数 x ...",
            "problem_spec_version": "spec-v2",
            "original_problem": "原题：对所有实数 x ...", "requirements": ["完整证明", "中文"],
            "current_target": "证明平方非负", "assumptions": ["x∈R"],
            "quantifiers": "对所有 x 属于实数", "domain": "实数",
            "unresolved_objection": "检查等号条件", "role_permissions": ["只审查"],
            "solution_candidate": "完整" + ("推导" * 10_000),
            "tool_request": {"tool_call_id": "tc-1", "name": "python_math", "arguments": {"x": 2}},
            "tool_receipt": {"tool_call_id": "tc-1", "status": "success", "output": "4"},
            "session_history": [],
        }
        prepared = prepare_context_request(request, policy, run_id="r", state_revision=3,
                                          problem_hash="p", config_hash="config-v2")
        for key, value in request.items():
            if key != "session_history":
                self.assertEqual(value, prepared[key], key)
        self.assertEqual("spec-v2", prepared["_context_pack"]["specification_version"])
        self.assertEqual("config-v2", prepared["_context_pack"]["config_hash"])

    def test_final_serialized_body_hook_counts_all_client_fields_before_http(self):
        endpoint = capacity_policy()["endpoint"]
        with patch.dict(os.environ, {"INTERN_API_KEY": "unit-test-token",
                                     "INTERN_API_BASE": endpoint, "INTERN_MODEL": "intern-s2",
                                     "INTERN_RETRY_COUNT": "1"}):
            client = InternChatClient(timeout=2, retry=1)
            response = Mock()
            response.status_code = 200
            response.json.return_value = {
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {},
            }
            order, observed = [], []
            def record_post(*_args, **_kwargs):
                order.append("http")
                return response

            def admission(body, url, provider):
                order.append("admission")
                observed.append((body, url, provider))

            with patch("llm_client.requests.post", side_effect=record_post) as post:
                InternModelAdapter(client, max_tokens=256).complete(
                    [{"role": "system", "content": "中文协议"},
                     {"role": "user", "content": "原题"}],
                    tools=[{"type": "function", "function": {"name": "check"}}],
                    metadata={"context_admission": admission},
                )
            body, url, provider = observed[0]
            payload = json.loads(body)
            self.assertEqual(["admission", "http"], order)
            self.assertEqual(1, post.call_count)
            self.assertEqual(endpoint, url)
            self.assertEqual("intern", provider)
            self.assertEqual("intern-s2", payload["model"])
            self.assertEqual(256, payload["max_tokens"])
            self.assertIn("tools", payload)
            self.assertEqual(body, post.call_args.kwargs["data"])

    def test_serialized_body_capacity_error_is_no_dispatch(self):
        endpoint = capacity_policy()["endpoint"]
        with patch.dict(os.environ, {"INTERN_API_KEY": "unit-test-token",
                                     "INTERN_API_BASE": endpoint, "INTERN_MODEL": "intern-s2",
                                     "INTERN_RETRY_COUNT": "1"}):
            client = InternChatClient(timeout=2, retry=1)
            rejection = ContextCapacityExceeded("context_capacity_exceeded", {"pack_sha256": "x"})
            with patch("llm_client.requests.post") as post:
                with self.assertRaises(AdapterError) as raised:
                    InternModelAdapter(client).complete(
                        [{"role": "user", "content": "原题"}],
                        metadata={"context_admission": lambda *_: (_ for _ in ()).throw(rejection)},
                    )
            self.assertTrue(raised.exception.no_dispatch)
            self.assertEqual("context_capacity_exceeded", raised.exception.category)
            self.assertEqual("x", raised.exception.context_pack["pack_sha256"])
            self.assertEqual(0, post.call_count)

    def test_rebuild_discards_stale_summary_when_history_is_empty_or_summary_is_disabled(self):
        empty_policy = frozen_policy({"features": {"context_pack": True},
                                      "context_capacity": capacity_policy()})
        empty = prepare_context_request({
            "role": "reasoner", "problem": "原题", "session_history": [],
            "session_history_summary": "STALE OLD SUMMARY",
            "_context_pack": {"summary_status": "created", "summary_sha256": "old"},
            "context_pack": {"summary_status": "created", "summary_sha256": "older"},
            "_context_policy": {"enabled": False, "version": "old"},
            "problem_spec_version": "problem-spec-v2",
        }, empty_policy, run_id="r", state_revision=8, problem_hash="p", config_hash="c")
        self.assertNotIn("session_history_summary", empty)
        self.assertNotIn("context_pack", empty)
        self.assertNotIn("_context_policy", empty)
        self.assertEqual("not_needed", empty["_context_pack"]["summary_status"])
        self.assertEqual("none", empty["_context_pack"]["summary_kind"])
        self.assertEqual({
            "problem_hash": "p", "specification_version": "problem-spec-v2", "config_hash": "c",
            "source_state_revision": 8, "run_id": "r", "role": "reasoner",
        }, {key: empty["_context_pack"][key] for key in (
            "problem_hash", "specification_version", "config_hash",
            "source_state_revision", "run_id", "role",
        )})

        no_summary_policy = frozen_policy({"features": {"context_pack": True},
                                           "context_capacity": {
                                               **capacity_policy(),
                                               "history_input_limit_bytes": 1,
                                               "history_summary_limit_bytes": 0,
                                           }})
        fallback = prepare_context_request({
            "role": "reasoner", "problem": "原题",
            "session_history_summary": "STALE OLD SUMMARY",
            "session_history": [
                {"request": {"role": "reasoner", "session_history_summary": "recursive"},
                 "response": {"argument": "old"}},
                {"request": {"role": "step_verifier"}, "response": {"objection": "now"}},
            ],
        }, no_summary_policy, run_id="r", state_revision=9, problem_hash="p")
        self.assertNotIn("session_history_summary", fallback)
        self.assertEqual("reference_only", fallback["_context_pack"]["summary_status"])
        self.assertEqual("index", fallback["_context_pack"]["summary_kind"])
        self.assertNotIn("recursive", json.dumps(fallback["session_history"], ensure_ascii=False))

    def test_archived_history_drops_nested_old_summaries_before_one_summary_attempt(self):
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy()})
        archived = {
            "request": {
                "session_history_summary": "NESTED STALE SUMMARY",
                "_context_pack": {"summary": "OLD PACK"},
                "session_history": [{"session_history_summary": "DEEP STALE SUMMARY"}],
            },
            "response": {"argument": "已结束推导"},
        }
        observed, calls = [], []

        def summarize(entries, _source):
            calls.append(1)
            observed.extend(entries)
            return "bounded archive reference"

        prepared = prepare_context_request({
            "role": "reasoner", "session_history": [archived,
                {"request": {"role": "reasoner"}, "response": {"argument": "最新"}}],
        }, policy, run_id="r", state_revision=11, problem_hash="p", summarizer=summarize)
        serialized = json.dumps(observed, ensure_ascii=False)
        self.assertEqual(1, len(calls))
        self.assertNotIn("NESTED STALE SUMMARY", serialized)
        self.assertNotIn("DEEP STALE SUMMARY", serialized)
        self.assertNotIn("OLD PACK", serialized)
        self.assertIn("Non-authoritative provided summary: bounded archive reference",
                      prepared["session_history_summary"])
        self.assertEqual("provided_summarizer_output", prepared["_context_pack"]["summary_kind"])

    def test_failed_summary_matrix_never_revives_old_derived_text(self):
        history = [
            {"request": {"session_history_summary": "NESTED OLD"},
             "response": {"argument": "old"}},
            {"request": {"role": "reasoner"}, "response": {"argument": "new"}},
        ]
        cases = (
            ("summarizer_exception", {"history_input_limit_bytes": 10_000,
                                       "history_summary_limit_bytes": 2_048},
            lambda *_: (_ for _ in ()).throw(RuntimeError("summary failed")), "reference_only"),
            ("summary_too_large", {"history_input_limit_bytes": 10_000,
                                    "history_summary_limit_bytes": 2},
             lambda *_: "oversized", "reference_only"),
            ("input_too_large", {"history_input_limit_bytes": 1,
                                  "history_summary_limit_bytes": 0},
             lambda *_: self.fail("input-over-limit history must not be summarized"),
             "reference_only"),
        )
        for label, limits, summarizer, expected_status in cases:
            with self.subTest(label=label):
                policy = frozen_policy({"features": {"context_pack": True},
                                        "context_capacity": {**capacity_policy(), **limits}})
                prepared = prepare_context_request({
                    "role": "reasoner", "session_history_summary": "STALE TOP SUMMARY",
                    "_context_pack": {"summary": "STALE PACK SUMMARY"},
                    "session_history": history,
                }, policy, run_id="r", state_revision=12, problem_hash="p",
                   summarizer=summarizer)
                self.assertEqual(expected_status, prepared["_context_pack"]["summary_status"])
                self.assertEqual("index" if expected_status == "reference_only" else
                                 "provided_summarizer_output",
                                 prepared["_context_pack"]["summary_kind"])
                projection = json.dumps(prepared, ensure_ascii=False)
                self.assertNotIn("STALE", projection)
                self.assertNotIn("NESTED OLD", projection)
                self.assertNotIn("session_history_summary", prepared)

    def test_changed_history_source_rebuilds_hash_without_reusing_old_summary(self):
        policy = frozen_policy({"features": {"context_pack": True},
                                "context_capacity": capacity_policy()})
        prior = {"request": {"role": "reasoner"}, "response": {"argument": "old"}}
        latest = {"request": {"role": "reasoner"}, "response": {"argument": "current"}}
        first = prepare_context_request({
            "role": "reasoner", "session_history": [prior, latest],
        }, policy, run_id="r", state_revision=1, problem_hash="p")
        changed = {"request": {"role": "reasoner"}, "response": {"argument": "recovered"}}
        rebuilt = prepare_context_request({
            "role": "reasoner", "session_history_summary": first["session_history_summary"],
            "_context_pack": first["_context_pack"], "session_history": [changed, latest],
        }, policy, run_id="r", state_revision=2, problem_hash="p")
        self.assertNotEqual(first["_context_pack"]["archived_history"]["sha256"],
                            rebuilt["_context_pack"]["archived_history"]["sha256"])
        self.assertNotIn("old", rebuilt["session_history_summary"])


if __name__ == "__main__":
    unittest.main()
