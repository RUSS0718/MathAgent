"""Keep unrelated, stale, and incomplete receipts out of Meta context."""

import unittest
from copy import deepcopy

from showcase.solver_harness.context_injection import prepare_role_context
from tests.test_meta_evidence_context_127 import evidence_run


def _receipt_with(**changes):
    receipt = {
        "receipt_id": "rejected",
        "run_id": "meta-evidence",
        "step_id": "step1",
        "plan_version": 1,
        "attempt_index": 0,
        "tool": "python_math",
        "executed": True,
        "status": "success",
        "exit_code": 0,
        "unknown_outcome": False,
        "output": "252",
    }
    receipt.update(changes)
    return receipt


class MetaEvidenceGuards127Test(unittest.TestCase):
    def test_unrelated_or_incomplete_receipts_are_excluded(self):
        cases = (
            ("other run", {"run_id": "another-run"}, False),
            ("other plan", {"plan_version": 2}, False),
            ("other attempt", {"attempt_index": 1}, False),
            ("invalidated step", {}, True),
            ("failed", {"status": "failed"}, False),
            ("nonzero exit", {"exit_code": 1}, False),
            ("not executed", {"executed": False}, False),
            ("unknown outcome", {"unknown_outcome": True}, False),
            ("missing output", {"output": None}, False),
        )

        for label, changes, invalidate_step in cases:
            with self.subTest(receipt=label):
                run = evidence_run()
                current = _receipt_with(
                    receipt_id="current-step",
                    step_id=run["state"]["current_step"],
                )
                rejected = _receipt_with(**changes)
                if invalidate_step:
                    run["state"]["steps"]["step1"]["verification"]["valid"] = False
                run["state"]["tool_receipts"] = [current, rejected]
                before = deepcopy(run)

                projected = prepare_role_context(run, {"role": "meta"})["state"]

                self.assertEqual(["current-step"], [
                    receipt["receipt_id"] for receipt in projected["tool_receipts"]
                ])
                self.assertEqual(before, run)


if __name__ == "__main__":
    unittest.main()
