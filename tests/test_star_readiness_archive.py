"""#97 archive DTOs exclude raw prompts, reasoning and response bodies."""

import json
import unittest

from showcase.star_readiness_archive import (
    preflight_record,
    registration_record,
    run_record,
)


class StarReadinessArchiveTest(unittest.TestCase):
    def test_registration_archive_keeps_question_hash_but_drops_question_text(self):
        manifest = {
            "questions": [{
                "id": "simple-01",
                "source": "https://example.test/problem",
                "text_sha256": "a" * 64,
                "type": "simple_fastpath",
                "text": "DO-NOT-ARCHIVE-QUESTION",
            }],
        }

        record = registration_record(manifest)
        serialized = json.dumps(record)

        self.assertNotIn("DO-NOT-ARCHIVE-QUESTION", serialized)
        self.assertEqual("a" * 64, record["questions"][0]["text_sha256"])

    def test_run_archive_drops_raw_text_and_unlisted_nested_fields(self):
        bundle = {
            "job": {
                "job_id": "job-1",
                "status": "succeeded",
                "result": {
                    "final_response": "DO-NOT-ARCHIVE-ANSWER",
                    "prompt": "DO-NOT-ARCHIVE-PROMPT",
                    "reasoning_content": "DO-NOT-ARCHIVE-REASONING",
                    "authorization": "DO-NOT-ARCHIVE-CREDENTIAL",
                },
            },
            "run": {"run_id": "job-1", "status": "completed", "stage": "review"},
            "report": {
                "answer": "DO-NOT-ARCHIVE-ANSWER",
                "semantics": {
                    "transport": "complete", "execution": "completed",
                    "whole_review": "accepted", "binding": "same_artifact",
                    "full_prompt": "DO-NOT-ARCHIVE-PROMPT",
                },
                "budget": {
                    "logical_calls": 2, "http_attempts": 2, "tool_calls": 1,
                    "charged_tokens": 120, "reserved_tokens": 0,
                    "provider_known": {"total_tokens": 120, "secret": "DO-NOT-ARCHIVE-CREDENTIAL"},
                },
                "checks": {"status": "passed", "reasoning_content": "DO-NOT-ARCHIVE-REASONING"},
                "request_attempts": [{
                    "role": "planner", "status": "success", "total_tokens": 40,
                    "prompt": "DO-NOT-ARCHIVE-PROMPT",
                }],
            },
            "evidence": {
                "run": {"run_id": "job-1"},
                "verification": {"status": "passed"},
                "tools": [{
                    "name": "python_math", "status": "success",
                    "receipt": {
                        "status": "success", "receipt_ref": "artifact-1",
                        "stdout": "DO-NOT-ARCHIVE-ANSWER",
                        "authorization": "DO-NOT-ARCHIVE-CREDENTIAL",
                    },
                    "value": "DO-NOT-ARCHIVE-ANSWER",
                }],
            },
        }

        record = run_record(bundle, job_id="job-1")
        serialized = json.dumps(record)

        for forbidden in (
            "DO-NOT-ARCHIVE-ANSWER", "DO-NOT-ARCHIVE-PROMPT",
            "DO-NOT-ARCHIVE-REASONING", "DO-NOT-ARCHIVE-CREDENTIAL",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(record["answer_identity"]["present"])
        self.assertEqual({"present": True}, record["answer_identity"])
        self.assertEqual("artifact-1", record["tools"][0]["receipt"]["receipt_ref"])
        self.assertEqual(120, record["budget"]["charged_tokens"])

    def test_preflight_keeps_receipt_identity_and_drops_unlisted_values(self):
        record = preflight_record({
            "available": True,
            "identity": {"run_id": "preflight-1", "receipt_ref": "receipt-1", "private": "x"},
            "receipt": {"status": "success", "executed": True, "stdout": "private"},
            "budget": {"tool_calls": 1, "http_attempts": 0, "prompt": "private"},
        })

        self.assertEqual("receipt-1", record["identity"]["receipt_ref"])
        self.assertEqual("success", record["receipt"]["status"])
        self.assertNotIn("private", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
