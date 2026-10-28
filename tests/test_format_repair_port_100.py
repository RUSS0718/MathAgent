"""F05/F06/F10 through the public role port; no provider network."""

import json
import tempfile
import unittest
from pathlib import Path

from showcase.adapters import InternModelAdapter
from showcase.solver_harness.intern_port import InternModelPort, InternPortError
from tests.test_solver_harness_intern import FakeClient

USAGE = {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}


class FormatRepairPortTest(unittest.TestCase):
    def port(self, replies):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        client = FakeClient([{"content": text, "finish_reason": "stop", "usage": USAGE}
                             for text in replies])
        port = InternModelPort(InternModelAdapter(client), original_problem="private problem",
                               restricted_reply_dir=Path(folder.name) / "restricted")
        return port, client

    def request(self, **extra):
        return {"run_id": "run-a", "call_id": "root", "role": "reasoner",
                "problem": "private problem", "problem_hash": "problem-a",
                "serialization_repair": True, **extra}

    def test_f05_complete_fenced_proof_has_private_reference_and_exact_repair(self):
        proof = "For every n, induction yields n(n+1)/2.\n" * 200
        value = {"argument": proof, "claims": [], "blocked": False}
        raw = "```json\n" + json.dumps(value) + "\n```"
        port, client = self.port([raw, json.dumps(value)])
        with self.assertRaises(InternPortError) as failed:
            port.complete(self.request())
        ref = failed.exception.response_ref
        self.assertEqual(64, len(ref["sha256"]))
        self.assertNotIn(proof, json.dumps(port.invocations))
        result = port.complete(self.request(call_id="root:serialization-1",
            serialization_source=ref))
        self.assertEqual(value, result)
        messages = client.requests[1][0]
        self.assertNotIn("private problem", json.dumps(messages))
        self.assertEqual(raw, json.loads(messages[-1]["content"])["visible_reply"])
        self.assertEqual([], json.loads(messages[-1]["content"])["allowed_tools"])


if __name__ == "__main__":
    unittest.main()
