"""Offline acceptance for the paired Runtime experiment matrix."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ricl_runtime.experiments import _FixtureResources, run_offline_pilot
from ricl_runtime.population import PopulationBudget
from ricl_runtime.providers.deepseek import ProviderTimeoutError


class RuntimeExperimentTests(unittest.TestCase):
    def test_conditions_share_budgets_and_collect_mechanism_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = run_offline_pilot(output_root=root / "first", order_seed=17)
            repeated = run_offline_pilot(output_root=root / "second", order_seed=17)
            self.assertEqual(manifest["condition_order"], repeated["condition_order"])
            self.assertEqual(manifest["model_seed"], "unavailable")
            self.assertEqual(set(manifest["condition_order"]), {"ordinary", "repair"})

            ordinary = self._read_case(manifest, "ordinary")
            repair = self._read_case(manifest, "repair")
            conditions = {
                "baseline",
                "ricl-state",
                "ricl-search",
                "ricl-full",
                "ricl-without-search",
                "plain-search",
                "aprs",
                "random-repair",
                "diagnostic-repair",
            }
            self.assertEqual(set(ordinary), conditions)
            self.assertEqual(set(repair), conditions)
            expected_limits = ordinary["baseline"][0]["config"]["budget"]
            for run, trace in (*ordinary.values(), *repair.values()):
                self.assertEqual(run["config"]["budget"], expected_limits)
                self.assertEqual(run["model"]["requested"], "paired-offline-fixture")
                self.assertTrue(run["source"]["revision"])
                self.assertEqual(trace[0]["run_id"], run["run_id"])
                self.assertEqual(trace[0]["trace_schema_version"], 1)
                self.assertEqual(sum(item["event"] == "run_started" for item in trace), 1)
                self.assertEqual(sum(item["event"] == "run_stopped" for item in trace), 1)
                self.assertEqual(
                    len({r["request_id"] for r in run["provider_requests"]}),
                    len(run["provider_requests"]),
                )
                self.assertNotIn("Compute", json.dumps(trace))

            baseline, baseline_trace = ordinary["baseline"]
            self.assertEqual(baseline["budget"]["tools"]["used"], 1)
            self.assertTrue(any(e["event"] == "tool_receipt_accepted" for e in baseline_trace))
            state, state_trace = ordinary["ricl-state"]
            self.assertTrue(any(e.get("referenced_evidence_ids") for e in state_trace))
            self.assertNotIn("intervention", state)

            full, full_trace = repair["ricl-full"]
            self.assertEqual(full["verification"]["status"], "verified")
            self.assertIn("population", full)
            self.assertTrue(full["intervention"]["feedback_consumed_by_parent"])
            self.assertEqual(full["budget"]["model_requests"]["used"], 5)
            self.assertTrue(any(e["event"] == "candidate_expanded" for e in full_trace))
            self.assertTrue(any(e["event"] == "parent_continuation_recorded" for e in full_trace))
            self.assertNotIn("population", repair["ricl-without-search"][0])
            self.assertNotIn("intervention", repair["ricl-search"][0])

            for arms in (ordinary, repair):
                plain, aprs = arms["plain-search"][0], arms["aprs"][0]
                self.assertEqual(
                    plain["population"]["candidate_ids"], aprs["population"]["candidate_ids"]
                )
                self.assertEqual(
                    plain["budget"]["model_requests"], aprs["budget"]["model_requests"]
                )
            self.assertEqual(
                ordinary["plain-search"][0]["population"]["selected_candidate_id"], "direct"
            )
            self.assertEqual(ordinary["aprs"][0]["population"]["selected_candidate_id"], "regroup")
            random_run, diagnostic = repair["random-repair"][0], repair["diagnostic-repair"][0]
            self.assertEqual(random_run["checkpoint"], diagnostic["checkpoint"])
            self.assertNotEqual(
                random_run["intervention"]["selected_repair_id"],
                diagnostic["intervention"]["selected_repair_id"],
            )
            self.assertEqual(manifest["counts"]["planned"], 18)
            self.assertEqual(sum(manifest["counts"]["verification"].values()), 18)
            self.assertEqual(manifest["rollback_pair"]["status"], "completed")
            rollback = json.loads(
                Path(manifest["rollback_pair"]["run"]).read_text(encoding="utf-8")
            )
            baseline_repair = rollback["arms"]["baseline"]
            state_repair = rollback["arms"]["ricl_state"]
            self.assertEqual(
                baseline_repair["checkpoint_sha256"], state_repair["checkpoint_sha256"]
            )
            self.assertTrue(baseline_repair["evidence_use"]["continued_using_invalidated_evidence"])
            self.assertFalse(state_repair["evidence_use"]["continued_using_invalidated_evidence"])
            self.assertGreater(baseline_repair["rework_tokens"], state_repair["rework_tokens"])

    def test_budget_stops_remain_in_the_paired_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = run_offline_pilot(
                output_root=Path(directory),
                budget=PopulationBudget(
                    model_requests=5, tokens=0, tools=1, elapsed_ms=30_000, cost_usd=0
                ),
            )
            self.assertEqual(manifest["counts"]["status"], {"stopped": 18})
            self.assertEqual(manifest["counts"]["verification"], {"unknown": 18})
            for entry in manifest["runs"]:
                self.assertIn(entry["stop_reason"], {"budget_exhausted", "budget_insufficient"})
                record = json.loads(Path(entry["run"]).read_text(encoding="utf-8"))
                self.assertEqual(record["budget"]["model_requests"]["used"], 0)
                self.assertEqual(record["budget"]["tokens"]["used"], 0)

    def test_timeout_preserves_prior_trace_and_failed_run(self) -> None:
        generate = _FixtureResources._generate

        def timed_out_on_second_candidate(fixture, prompt, input_tokens):
            if fixture.case_id == "ordinary" and "Check the arithmetic by grouping." in prompt:
                raise ProviderTimeoutError("offline timeout fixture")
            return generate(fixture, prompt, input_tokens)

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(_FixtureResources, "_generate", timed_out_on_second_candidate),
        ):
            manifest = run_offline_pilot(output_root=Path(directory))
            run, trace = self._read_case(manifest, "ordinary")["ricl-search"]
            self.assertEqual(run["run"]["status"], "failed")
            self.assertEqual(run["run"]["stop_reason"], "timeout")
            self.assertEqual(run["verification"]["status"], "verified")
            self.assertFalse(run["state_reused"])
            self.assertEqual(run["budget"]["model_requests"]["used"], 2)
            self.assertEqual(run["budget"]["tokens"]["used"], "unknown")
            self.assertEqual(run["provider_requests"][1]["status"], "timeout")
            self.assertEqual(manifest["counts"]["stop_reason"]["timeout"], 4)
            self.assertEqual(sum(event["event"] == "candidate_expanded" for event in trace), 1)
            self.assertTrue(any(event["event"] == "model_request_failed" for event in trace))

    @staticmethod
    def _read_case(manifest, case_id):
        runs = {}
        for entry in manifest["runs"]:
            if entry["problem_id"] != case_id:
                continue
            run = json.loads(Path(entry["run"]).read_text(encoding="utf-8"))
            trace = [
                json.loads(line)
                for line in Path(entry["trace"]).read_text(encoding="utf-8").splitlines()
            ]
            runs[entry["condition_id"]] = run, trace
        return runs


if __name__ == "__main__":
    unittest.main()
