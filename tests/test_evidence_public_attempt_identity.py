"""Public attempt identities remain joinable across Job evidence projections."""

import unittest

from showcase.evidence import EvidencePackExporter


class EvidencePublicAttemptIdentityTest(unittest.TestCase):
    def _snapshot(self, call_id):
        return {
            "run_id": "public-run-1", "status": "COMPLETED", "final_response": "x=1",
            "result": {"request_attempts": [{
                "attempt_id": "attempt-1", "logical_call_id": "logical-1",
                "run_id": "public-run-1", "role": "explore",
                "solver_call_id": call_id, "status": "success",
            }]},
        }

    def test_existing_public_call_id_matches_export_and_report(self):
        public_id = "solver_call_0123456789abcdef0123456789abcdef"
        exporter = EvidencePackExporter()
        snapshot = self._snapshot(public_id)
        for projection in (exporter.export(snapshot), exporter.report(snapshot)):
            self.assertEqual(public_id, projection["request_attempts"][0]["solver_call_id"])

    def test_private_or_malformed_call_id_is_still_redacted(self):
        exporter = EvidencePackExporter()
        for private_id in ("private-problem-step", "solver_call_private-problem-step"):
            with self.subTest(call_id=private_id):
                for projection in (
                    exporter.export(self._snapshot(private_id)),
                    exporter.report(self._snapshot(private_id)),
                ):
                    public_id = projection["request_attempts"][0]["solver_call_id"]
                    self.assertRegex(public_id, r"^solver_call_[0-9a-f]{32}$")
                    self.assertNotIn("private", public_id)


if __name__ == "__main__":
    unittest.main()
