"""Public Job regressions for S02 capacity rejection events and messaging."""

import hashlib
import json
import unittest
from unittest.mock import patch

from llm_client import InternChatClient
from showcase.adapters import InternStreamAdapter
from showcase.solver_harness.context_pack import (
    finalize_context_pack,
    frozen_policy,
    prepare_context_request,
)
from showcase.star_result_semantics import result_semantics
from tests.star_product_support import ACCEPT, POLISH, SOLVED, StarJobFixture

ENDPOINT = "http://127.0.0.1:5000/api/v1/chat/completions"


def policy(cap):
    return {
        "version": "context-capacity-v1", "profile_version": "s02-controlled-v1",
        "provider": "intern", "model": "intern-s2", "endpoint": ENDPOINT,
        "cap_source": "controlled_test_only", "cap_source_date": "2026-11-07",
        "input_cap_tokens": cap, "output_reserve_tokens": 256,
        "safety_margin_tokens": 10,
        "token_estimator_version": "utf8-bytes-per-three-v1",
    }


class FaithfulS02ReviewFixesTest(StarJobFixture, unittest.TestCase):
    def open_context(self):
        self.enterContext(patch.dict("os.environ", {"INTERN_API_BASE": ENDPOINT}))
        self.open_star(
            [SOLVED, POLISH, ACCEPT], stream_chunk_size=65536,
            SHOWCASE_STAR_ADAPTER=InternStreamAdapter(InternChatClient(retry=1), max_tokens=256),
            SHOWCASE_STAR_FEATURES={"context_pack": True},
            SHOWCASE_STAR_CONTEXT_CAPACITY=policy(20_000),
        )

    def solver_events(self, job_id):
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        return [
            json.loads(line[6:])
            for line in stream.splitlines()
            if line.startswith("data: ")
        ]

    def test_oversized_whole_review_has_one_call_rejection_and_clear_terminal_event(self):
        self.open_context()
        self.replies[:] = [SOLVED, {"solution_candidate": "x" * 100_000}, ACCEPT]

        job_id = self.create_job()
        completed = self.terminal(job_id)

        self.assertEqual("failed", completed["status"], completed)
        self.assertEqual(2, self.post.call_count)
        event_types = [event.get("solver_event_type") for event in self.solver_events(job_id)]
        self.assertEqual(1, event_types.count("context_capacity_rejected"), repr(event_types))
        self.assertEqual(1, event_types.count("context_capacity_terminal"))
        result = self.job(job_id)["result"]
        self.assertIn("This call was rejected before provider dispatch", result["final_response"])
        self.assertIn("Previously committed results and evidence are preserved", result["final_response"])
        self.assertIn("split the task into smaller parts", result["final_response"])


class FaithfulS02ContextReviewFixesTest(unittest.TestCase):
    def setUp(self):
        self.policy = frozen_policy({
            "features": {"context_pack": True},
            "context_capacity": {
                **policy(20_000), "recent_history_exchanges": 1,
                "history_input_limit_bytes": 32_768,
                "history_summary_limit_bytes": 2_048,
            },
        })
        self.history = [
            {"request": {"role": "reasoner", "text": "archived one"},
             "response": {"argument": "result one"}},
            {"request": {"call_id": "review-call-2", "role": "step_verifier"},
             "response": {"tool_request": {"name": "python_math", "arguments": {"x": 2}}}},
            {"request": {"role": "reasoner", "text": "archived three"},
             "response": {"argument": "result three"}},
            {"request": {"role": "reasoner", "text": "latest four"},
             "response": {"argument": "result four"}},
        ]

    @staticmethod
    def history_ref(entry):
        encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return "history:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def prepare(self, *, policy_override=None, summarizer=None):
        return prepare_context_request({
            "role": "step_verifier", "session_key": "review-session",
            "report": {"tool_receipts": [{"review_call_id": "review-call-2"}]},
            "session_history": self.history,
        }, policy_override or self.policy, run_id="review-run", state_revision=4,
           problem_hash="problem-hash", summarizer=summarizer)

    def test_noncontiguous_archive_has_exact_ranges_refs_and_original_excerpt(self):
        prepared = self.prepare()
        pack = prepared["_context_pack"]
        archive = pack["archived_history"]

        self.assertEqual(1, archive["index_base"])
        self.assertEqual("deduplicated_session_history", archive["index_scope"])
        self.assertEqual([{"from": 1, "to": 1}, {"from": 3, "to": 3}], archive["ranges"])
        self.assertEqual([1, 3], [item["index"] for item in archive["items"]])
        self.assertEqual([self.history_ref(self.history[0]), self.history_ref(self.history[2])],
                         [item["ref"] for item in archive["items"]])
        self.assertEqual("created", pack["summary_status"])
        self.assertEqual("original_excerpt", pack["summary_kind"])
        summary = prepared["session_history_summary"]
        self.assertIn("non-authoritative", summary.lower())
        self.assertIn(self.history_ref(self.history[0]), summary)
        self.assertIn("archived one", summary)
        self.assertIn("result three", summary)
        self.assertIn(self.history_ref(self.history[1]), pack["included_refs"])
        self.assertIn(self.history_ref(self.history[1]), pack["retained_history_refs"])
        self.assertNotIn(self.history_ref(self.history[1]), pack["archived_history_refs"])
        self.assertEqual([self.history_ref(self.history[0]), self.history_ref(self.history[2])],
                         pack["summary_source_refs"])
        self.assertNotIn(self.history_ref(self.history[2]), pack["included_refs"])
        self.assertIn("history-summary:" + pack["summary_sha256"], pack["included_refs"])
        self.assertEqual(
            {self.history_ref(entry) for entry in (self.history[0], self.history[1],
                                                    self.history[2], self.history[3])},
            set(pack["history_refs"]),
        )
        serialized = json.dumps({
            "model": "intern-s2", "messages": [{"role": "user", "content": "opaque"}],
        }).encode("utf-8")
        finalized_pack = finalize_context_pack(
            serialized, self.policy, role="step_verifier", run_id="review-run",
            state_revision=4, problem_hash="problem-hash", endpoint=ENDPOINT, source=pack,
        )
        semantics = result_semantics({"run_id": "review-run", "state": {
            "status": "partial_aborted", "phase": "TERMINAL", "calls": {},
            "whole_solution_reviews": [], "context_policy": {"enabled": True},
            "context_packs": [finalized_pack],
        }}, "")
        public_pack = semantics["context_capacity"]["packs"][0]
        self.assertEqual("original_excerpt", public_pack["summary_kind"])
        self.assertEqual(finalized_pack["retained_history_refs"], public_pack["retained_history_refs"])
        self.assertEqual(finalized_pack["archived_history_refs"], public_pack["archived_history_refs"])
        self.assertEqual(archive, public_pack["archived_history"])
        self.assertIn("payload.messages", public_pack["included_refs"])
        self.assertIn("history-summary:" + finalized_pack["summary_sha256"],
                      public_pack["included_refs"])
        self.assertNotIn(self.history_ref(self.history[0]), public_pack["included_refs"])
        self.assertNotIn("session_history_summary", public_pack)
        public_json = json.dumps(public_pack, ensure_ascii=False)
        self.assertNotIn("archived one", public_json)
        self.assertNotIn("result three", public_json)

    def test_provided_summarizer_is_attempted_once_and_identified_separately(self):
        calls = []

        def summarize(entries, source):
            calls.append((entries, source))
            return "provided summary text"

        prepared = self.prepare(summarizer=summarize)
        pack = prepared["_context_pack"]

        self.assertEqual(1, len(calls))
        self.assertEqual("created", pack["summary_status"])
        self.assertEqual("provided_summarizer_output", pack["summary_kind"])
        self.assertIn("Non-authoritative provided summary: provided summary text",
                      prepared["session_history_summary"])
        self.assertEqual([1, 3], [item["index"] for item in calls[0][1]["items"]])

    def test_input_limit_uses_reference_only_index_without_including_archived_history(self):
        calls = []

        def should_not_summarize(*_):
            calls.append(True)
            return "unexpected"

        limited = frozen_policy({
            "features": {"context_pack": True},
            "context_capacity": {**policy(20_000), "recent_history_exchanges": 1,
                                  "history_input_limit_bytes": 1,
                                  "history_summary_limit_bytes": 2_048},
        })
        prepared = self.prepare(policy_override=limited, summarizer=should_not_summarize)
        pack = prepared["_context_pack"]

        self.assertEqual([], calls)
        self.assertEqual("reference_only", pack["summary_status"])
        self.assertEqual("index", pack["summary_kind"])
        self.assertNotIn("session_history_summary", prepared)
        self.assertEqual(
            {self.history_ref(self.history[1]), self.history_ref(self.history[3])},
            set(pack["included_refs"]),
        )
        self.assertNotIn(self.history_ref(self.history[0]), pack["included_refs"])

    def test_excerpt_that_does_not_fit_falls_back_as_a_whole_to_reference_index(self):
        limited = frozen_policy({
            "features": {"context_pack": True},
            "context_capacity": {**policy(20_000), "recent_history_exchanges": 1,
                                  "history_input_limit_bytes": 32_768,
                                  "history_summary_limit_bytes": 200},
        })
        prepared = self.prepare(policy_override=limited)
        pack = prepared["_context_pack"]

        self.assertEqual("reference_only", pack["summary_status"])
        self.assertEqual("index", pack["summary_kind"])
        self.assertNotIn("session_history_summary", prepared)
        self.assertNotIn(self.history_ref(self.history[0]), pack["included_refs"])
        self.assertIn(self.history_ref(self.history[0]), pack["archived_history_refs"])

    def test_incomplete_archived_exchange_is_never_excerpted(self):
        self.history = [
            {"request": {"role": "reasoner", "text": "unfinished"}},
            {"request": {"role": "reasoner", "text": "latest"},
             "response": {"argument": "finished"}},
        ]
        prepared = self.prepare()
        pack = prepared["_context_pack"]

        self.assertEqual("reference_only", pack["summary_status"])
        self.assertEqual("index", pack["summary_kind"])
        self.assertNotIn("session_history_summary", prepared)
        self.assertEqual([], pack["summary_source_refs"])


if __name__ == "__main__":
    unittest.main()
