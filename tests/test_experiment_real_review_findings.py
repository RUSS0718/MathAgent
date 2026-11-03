"""The read-only verifier understands findings emitted by the review producer."""

import json
import tempfile
import unittest
from pathlib import Path

from showcase.experiment_verification import export_experiment_report, verify_experiment_run
from showcase.solver_harness.final_binding import delivery_verification, review_record
from tests.test_showcase_experiment_verify import ReadOnlyShowcaseClient, prepare_run


def producer_review(answer, verdict="ACCEPT"):
    """Build a completed review with the real record and delivery serializers."""
    call_id = "review-call-internal"
    run = {
        "run_id": "job-1", "state_revision": 9,
        "state": {
            "plan_version": 2, "attempt_index": 1, "whole_solution_reviews": [],
            "calls": {call_id: {
                "status": "completed", "role": "whole_solution_verifier", "run_id": "job-1",
                "request": {"solution_candidate": answer}, "response": {"verdict": verdict},
            }},
        },
    }
    run["state"]["whole_solution_reviews"].append(review_record(
        run, answer, verdict, call_id=call_id, origin="whole_solution_verifier",
    ))
    return delivery_verification(run, answer)[1]


class ExperimentRealReviewFindingsTest(unittest.TestCase):
    def _fixture(self, root, *, verdict="ACCEPT", findings="producer"):
        output_root, run_dir, _digest, _manifest, responses = prepare_run(root)
        answer = responses["/api/agent/jobs/job-1/report"]["report"]["answer"]
        check = producer_review(answer, verdict)
        if findings != "producer":
            check["history"][-1]["findings"] = findings
        responses["/api/agent/jobs/job-1"]["result"]["verification"] = check
        responses["/api/agent/jobs/job-1/report"]["report"]["checks"] = check
        responses["/api/runs/job-1/evidence"]["verification"] = check
        return output_root, run_dir, ReadOnlyShowcaseClient(responses)

    def test_real_accept_history_passes_verify_and_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output_root, run_dir, client = self._fixture(root)
            result = verify_experiment_run("batch-1", output_root=output_root, read_client=client)
            self.assertEqual("PASS", result["checks"]["task"]["status"])
            exported = export_experiment_report(
                "batch-1", output_root=output_root, output=root / "export.json",
            )
            self.assertEqual("PASS", exported["status"])
            archived = json.loads(next((run_dir / "evidence").glob("*.json")).read_text())
            self.assertTrue(archived["whole_review"]["accepted"])
            self.assertTrue(all(method == "GET" for method, _path, _kwargs in client.calls))

    def test_rejected_missing_and_malformed_findings_cannot_pass(self):
        for verdict, findings in (("REJECT", "producer"), ("ACCEPT", []), ("ACCEPT", None)):
            with self.subTest(verdict=verdict, findings=findings), tempfile.TemporaryDirectory() as folder:
                output_root, run_dir, client = self._fixture(
                    Path(folder), verdict=verdict, findings=findings,
                )
                result = verify_experiment_run("batch-1", output_root=output_root, read_client=client)
                self.assertNotEqual("PASS", result["checks"]["task"]["status"])
                archived = json.loads(next((run_dir / "evidence").glob("*.json")).read_text())
                self.assertFalse(archived["whole_review"]["accepted"])


if __name__ == "__main__":
    unittest.main()
