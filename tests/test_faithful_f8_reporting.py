"""Public report/review contracts using literal inputs and the validated schema."""

import copy
import hashlib
import importlib
import json
import unittest

GROUPS = tuple(f"faithful-{letter}" for letter in "ABCDEFG")
STATUSES = ("completed", "failed", "unknown", "incomplete", "unsupported", "not_run")
H = "a" * 64


def digest(value):
    """Independent canonical file digest, without a terminal newline."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def manifest_fixture():
    """Four sampled competitions plus unsampled Apex, with 14 registered inputs."""
    samples = []
    for competition, scope, count in (("AIME2025", "answer", 3), ("HMMT2026", "answer", 3),
                                      ("Putnam2025", "proof", 3), ("IMO2025", "proof", 3),
                                      ("Apex2025", "answer", 2)):
        for number in range(count):
            samples.append({"id": f"{competition}/{number}", "input_sha256": H,
                            "source_sha256": H, "source_ref": (
                                "https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/"
                                "5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d/fixed.json"),
                            "stratum": f"{competition}/{scope}", "development_history": "unknown",
                            "targets": dict.fromkeys(GROUPS)})
    groups = {}
    for index, group in enumerate(GROUPS):
        groups[group] = {"parent": GROUPS[index - 1] if index else None,
                         "policy": "harness-v1", "capability_status": "available",
                         "reason": "available", "config_sha256": H}
    groups["faithful-C"]["policy"] = "serial-aprs-v1"
    groups["faithful-D"]["policy"] = "concurrent-aprs-v1"
    groups["faithful-F"].update(parent="faithful-C", policy="serial-intervention-v1")
    return {"schema_version": "faithful-f8-manifest-v1",
            "protocol_version": "faithful-f8-v1.1.1-engineering", "protocol_sha256": H,
            "batch_id": "literal-pilot", "source_revision": "b" * 40, "baseline_sha256": H,
            "dataset": {"sha256": H, "samples": samples},
            "model": {"provider": "none", "id": "scripted", "snapshot": "unknown"},
            "prompt_sha256": H, "seed": "faithful-f8-pilot-20261111-v1", "repetitions": 1,
            "environment": {"identity_sha256": H, "tools_status": "not_run"},
            "resources": {"identity_sha256": H, "limits_status": "unknown", "stop_rules": [
                "unknown", "cancel", "hard_limit", "source_or_config_change", "ledger_or_binding_defect"]},
            "groups": groups}


def record_fixture(manifest, group="faithful-A", index=0, status="completed"):
    """A public imported record, without implied verification authority."""
    return {"schema_version": "faithful-f8-record-v1", "manifest_sha256": digest(manifest),
            "group": group, "sample_id": manifest["dataset"]["samples"][index]["id"],
            "repetition": 0, "execution_status": status, "reason": "fixture", "run_id": "run-1",
            "source_revision": manifest["source_revision"], "input_sha256": H,
            "config_sha256": H, "evidence_kind": "engineering", "snapshot_sha256": H,
            "metrics": dict.fromkeys(("accuracy", "root_coverage", "valid_evidence",
                                      "route_efficiency", "latency_ms", "cost",
                                      "cache_recheck", "explanation_rubric")),
            "formal": None, "pair": None}


def load_reporting():
    """Use the producer now that its minimal schema checks have passed."""
    return importlib.import_module("showcase.faithful_eval_reporting")


class FaithfulReportingTest(unittest.TestCase):
    """Pure public report and review behaviors against the shared contract."""

    def setUp(self):
        self.api = load_reporting()
        self.manifest = manifest_fixture()

    def review(self, role="R1", records=None):
        """Prepare a complete missing-artifact review."""
        return {"schema_version": "faithful-f8-review-v1", "reviewer": role,
                "model_id": "unknown", "manifest_sha256": digest(self.manifest),
                "input_review_sha256": [], "entries": [
                    dict(slot, verdict="unresolved", reason="missing_artifact", snapshot_sha256=None)
                    for slot in self.api.review_selection(self.manifest)]}

    def test_registered_denominator_and_unsupported_are_preserved(self):
        self.manifest["groups"]["faithful-E"]["capability_status"] = "unsupported"
        report = self.api.build_report(self.manifest, [])
        self.assertEqual(sum(g["N_registered"] for g in report["groups"].values()), 98)
        for group, stats in report["groups"].items():
            self.assertEqual(sum(stats["counts"].values()), 14)
            self.assertEqual(stats["counts"]["unsupported" if group == "faithful-E" else "not_run"], 14)

    def test_selection_is_same_four_across_groups(self):
        selected = self.api.review_selection(self.manifest)
        self.assertEqual(len(selected), 28)
        self.assertEqual(len({tuple(sorted(item.items())) for item in selected}), 28)
        by_group = [{x["sample_id"] for x in selected if x["group"] == g} for g in GROUPS]
        self.assertTrue(all(ids == by_group[0] for ids in by_group))
        self.assertEqual({s.split("/")[0] for s in by_group[0]},
                         {"AIME2025", "HMMT2026", "Putnam2025", "IMO2025"})

    def test_selection_is_order_independent_and_missing_stratum_not_replaced(self):
        expected = self.api.review_selection(self.manifest)
        self.manifest["dataset"]["samples"].reverse()
        self.assertEqual(self.api.review_selection(self.manifest), expected)
        self.manifest["dataset"]["samples"] = [s for s in self.manifest["dataset"]["samples"]
                                                if not s["id"].startswith("IMO2025/")]
        self.assertEqual(len(self.api.review_selection(self.manifest)), 21)

    def test_all_six_statuses_are_counted(self):
        records = [record_fixture(self.manifest, index=i, status=s) for i, s in enumerate(STATUSES)]
        counts = self.api.build_report(self.manifest, records)["groups"]["faithful-A"]["counts"]
        self.assertEqual(counts, dict(completed=1, failed=1, unknown=1, incomplete=1,
                                      unsupported=1, not_run=9))

    def test_drift_preserves_execution_and_rejects_comparability(self):
        for field in ("source_revision", "input_sha256", "config_sha256"):
            with self.subTest(field=field):
                record = record_fixture(self.manifest)
                record[field] = "c" * len(record[field])
                stats = self.api.build_report(self.manifest, [record])["groups"]["faithful-A"]
                self.assertEqual(stats["counts"]["completed"], 1)
                self.assertEqual(stats["comparison_status"], "not_comparable")
                self.assertIn(field, stats["comparison_reasons"])
        report = self.api.build_report(self.manifest, [], source_matches=False)
        self.assertTrue(all(g["comparison_status"] == "not_comparable" for g in report["groups"].values()))

    def test_f_predecessor_not_comparable_and_pair_unknown_preserved(self):
        record = record_fixture(self.manifest, "faithful-F", status="unknown")
        record["pair"] = {"id": "pair-1", "checkpoint_sha256": H,
                          "control_status": "completed", "intervention_status": "unknown"}
        stats = self.api.build_report(self.manifest, [record])["groups"]["faithful-F"]
        self.assertEqual(stats["predecessor_comparison"]["status"], "not_comparable")
        self.assertEqual(stats["pairs"]["records"][0], record["pair"])
        self.assertEqual(stats["pairs"]["comparable_count"], 0)

    def test_metrics_use_observed_subset_and_nearest_rank(self):
        records = [record_fixture(self.manifest, index=i) for i in range(4)]
        for rec, latency in zip(records, (40, 10, 30, 20)):
            rec["metrics"]["latency_ms"] = latency
        records.append(record_fixture(self.manifest, index=4, status="unknown"))
        stats = self.api.build_report(self.manifest, records)["groups"]["faithful-A"]
        latency = stats["metrics"]["latency_ms"]
        self.assertEqual((latency["eligible_count"], latency["p50"], latency["p95"]), (4, 20, 40))
        self.assertEqual(latency["unknown_count"], 1)
        self.assertEqual(stats["metrics"]["cost"]["value"], None)
        self.assertEqual(stats["metrics"]["accuracy"]["status"], "not_available")

    def test_imports_never_upgrade_layers_or_invent_scores(self):
        record = record_fixture(self.manifest)
        record["evidence_kind"] = "provider_live"
        report = self.api.build_report(self.manifest, [record])
        self.assertEqual(len(report["evidence_layers"]), 5)
        self.assertTrue(all(layer["status"] == "not_run" for layer in report["evidence_layers"].values()))
        self.assertEqual(report["evidence_layers"]["provider_live"]["imported_count"], 1)
        self.assertEqual(report["official_score"]["status"], "not_run")

    def test_l2_target_denominator_keeps_missing_results(self):
        sample = self.manifest["dataset"]["samples"][0]
        sample["targets"]["faithful-E"] = {"target_sha256": H, "scope": "formal_target",
                                            "environment_sha256": H}
        rows = self.api.build_report(self.manifest, [])["l2"]
        row = next(row for row in rows if row["group"] == "faithful-E" and row["target_scope"] == "formal_target")
        self.assertEqual((row["N_registered"], row["N_target_registered"], row["N_decidable"]), (14, 1, 0))
        self.assertEqual(row["counts"]["not_run"], 1)
        self.assertEqual(row["target_coverage"]["value"], 1 / 14)

    def test_duplicate_or_unregistered_records_rejected(self):
        record = record_fixture(self.manifest)
        with self.assertRaises(ValueError):
            self.api.build_report(self.manifest, [record, record])
        record["repetition"] = 9
        with self.assertRaises(ValueError):
            self.api.build_report(self.manifest, [record])

    def test_valid_missing_artifact_review_returns_same_object(self):
        review = self.review()
        self.assertIs(self.api.validate_review(review, self.manifest, [], {}), review)

    def test_review_exact_keys_and_unique_complete_slots(self):
        for change in ("extra", "entry_extra", "duplicate", "missing", "wrong_manifest", "bool_rep"):
            review = self.review()
            if change == "extra":
                review["raw"] = "forbidden"
            elif change == "entry_extra":
                review["entries"][0]["answer"] = "forbidden"
            elif change == "duplicate":
                review["entries"][-1] = copy.deepcopy(review["entries"][0])
            elif change == "missing":
                review["entries"].pop()
            elif change == "wrong_manifest":
                review["manifest_sha256"] = "0" * 64
            else:
                review["entries"][0]["repetition"] = False
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.api.validate_review(review, self.manifest, [], {})

    def test_missing_snapshot_cannot_pass_or_fail(self):
        for verdict in ("pass", "fail"):
            review = self.review()
            review["entries"][0]["verdict"] = verdict
            with self.assertRaises(ValueError):
                self.api.validate_review(review, self.manifest, [], {})

    def test_pilot_reviews_reject_math_verdicts_even_with_matching_imported_hash(self):
        prior = {role: self.review(role) for role in ("R1", "R2")}
        for role in ("R1", "R2", "R3"):
            for verdict, reason, snapshot in (("pass", "review_pass", H),
                                               ("fail", "review_fail", H),
                                               ("unresolved", "missing_artifact", H),
                                               ("unresolved", "review_unresolved", None)):
                review = self.review(role)
                if role == "R3":
                    review["input_review_sha256"] = [digest(prior[r]) for r in ("R1", "R2")]
                entry = review["entries"][0]
                record = record_fixture(self.manifest, entry["group"])
                record["sample_id"] = entry["sample_id"]
                entry.update(verdict=verdict, reason=reason, snapshot_sha256=snapshot)
                with self.subTest(role=role, verdict=verdict, reason=reason), self.assertRaises(ValueError):
                    self.api.validate_review(review, self.manifest, [record], prior)

    def test_initial_reviews_require_empty_input_hashes(self):
        for role in ("R1", "R2"):
            review = self.review(role)
            review["input_review_sha256"] = [H]
            with self.assertRaises(ValueError):
                self.api.validate_review(review, self.manifest, [], {})

    def test_r3_requires_both_valid_reviews_and_canonical_ordered_hashes(self):
        prior = {role: self.review(role) for role in ("R1", "R2")}
        review = self.review("R3")
        review["input_review_sha256"] = [digest(prior[role]) for role in ("R1", "R2")]
        self.assertIs(self.api.validate_review(review, self.manifest, [], prior), review)
        for bad_prior, hashes in (({}, review["input_review_sha256"]),
                                  (prior, list(reversed(review["input_review_sha256"]))),
                                  (prior, [H, H])):
            bad = copy.deepcopy(review)
            bad["input_review_sha256"] = hashes
            with self.assertRaises(ValueError):
                self.api.validate_review(bad, self.manifest, [], bad_prior)
        prior["R1"]["entries"].pop()
        with self.assertRaises(ValueError):
            self.api.validate_review(review, self.manifest, [], prior)

    def test_inputs_not_mutated(self):
        before = copy.deepcopy(self.manifest)
        self.api.build_report(self.manifest, [])
        self.api.review_selection(self.manifest)
        self.assertEqual(self.manifest, before)

    def test_parent_and_predecessor_comparisons_include_identity(self):
        stats = self.api.build_report(self.manifest, [])["groups"]["faithful-F"]
        self.assertEqual(stats["parent_comparison"]["group"], "faithful-C")
        self.assertEqual(stats["predecessor_comparison"]["group"], "faithful-E")
        self.assertEqual(stats["predecessor_comparison"]["status"], "not_comparable")

    def test_l2_has_all_rates_and_source_claim_qualification(self):
        target = {"target_sha256": H, "scope": "formal_target", "environment_sha256": H}
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-E"] = target
        row = self.api.build_report(self.manifest, [])["l2"][0]
        self.assertEqual(row["primary_rate"]["denominator"], 14)
        self.assertEqual(row["target_rate"]["denominator"], 1)
        self.assertEqual(row["conditional_rate"]["value"], None)
        self.assertEqual(row["source_status"], "imported_unverified")
        self.assertEqual(set(row["counts"]), set(STATUSES))

    def test_latency_has_unknown_and_censored_and_missing_counts(self):
        records = [record_fixture(self.manifest, index=i, status=status)
                   for i, status in enumerate(("unknown", "incomplete", "completed"))]
        stats = self.api.build_report(self.manifest, records)["groups"]["faithful-A"]
        latency = stats["metrics"]["latency_ms"]
        self.assertEqual((latency["unknown_count"], latency["censored_count"], latency["missing_count"]), (1, 1, 14))
        self.assertIsNone(latency["p50"])
        self.assertEqual(latency["missing_by_status"]["not_run"], 11)

    def test_selection_uses_stratum_rather_than_identifier_prefix(self):
        for sample in self.manifest["dataset"]["samples"]:
            sample["id"] = "public/" + sample["id"]
        self.assertEqual(len(self.api.review_selection(self.manifest)), 28)

    def test_r3_revalidates_prior_snapshot_bindings_and_initial_empty_hashes(self):
        prior = {role: self.review(role) for role in ("R1", "R2")}
        prior["R1"]["input_review_sha256"] = [H]
        review = self.review("R3")
        review["input_review_sha256"] = [digest(prior[r]) for r in ("R1", "R2")]
        with self.assertRaises(ValueError):
            self.api.validate_review(review, self.manifest, [], prior)
        prior["R1"]["input_review_sha256"] = []
        prior["R1"]["entries"][0].update(verdict="pass", snapshot_sha256=H, reason="review_pass")
        review["input_review_sha256"] = [digest(prior[r]) for r in ("R1", "R2")]
        with self.assertRaises(ValueError):
            self.api.validate_review(review, self.manifest, [], prior)

    def test_review_invalid_types_always_raise_value_error(self):
        for field, value in (("reviewer", []), ("model_id", "unsafe model text"),
                             ("entries", {}), ("input_review_sha256", None)):
            review = self.review()
            review[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.api.validate_review(review, self.manifest, [], {})

    def test_build_report_validates_record_payload_before_aggregation(self):
        for key, value in (("accuracy", 1), ("root_coverage", 2),
                           ("cost", -1), ("latency_ms", float("nan")),
                           ("cache_recheck", True), ("raw", "private")):
            record = record_fixture(self.manifest)
            record["metrics"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.api.build_report(self.manifest, [record])
        record = record_fixture(self.manifest)
        record["manifest_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.api.build_report(self.manifest, [record])

    def test_metric_missing_by_status_excludes_observed_values(self):
        records = [record_fixture(self.manifest, index=i, status=s)
                   for i, s in enumerate(("completed", "completed", "unknown"))]
        records[0]["metrics"].update(latency_ms=0, cost=0)
        records[2]["metrics"]["latency_ms"] = 10
        metrics = self.api.build_report(self.manifest, records)["groups"]["faithful-A"]["metrics"]
        self.assertEqual(metrics["latency_ms"]["missing_by_status"]["completed"], 1)
        self.assertEqual(metrics["latency_ms"]["missing_by_status"]["unknown"], 0)
        self.assertEqual(sum(metrics["latency_ms"]["missing_by_status"].values()), 12)
        self.assertEqual(metrics["cost"]["missing_by_status"]["unknown"], 1)

    def test_no_executed_comparable_pairs_are_not_available(self):
        reports = [self.api.build_report(self.manifest, []), self.api.build_report(
            self.manifest, [record_fixture(self.manifest, "faithful-B")])]
        for report in reports:
            self.assertTrue(all(g["comparison_status"] == "not_available"
                                for g in report["groups"].values()))
            self.assertEqual(report["groups"]["faithful-B"]["parent_comparison"]["status"], "not_available")

    def test_matched_completed_parent_pair_and_parent_drift(self):
        records = [record_fixture(self.manifest, group) for group in ("faithful-A", "faithful-B")]
        self.assertEqual(self.api.build_report(self.manifest, records)["groups"]["faithful-B"]["comparison_status"], "comparable")
        records[0]["config_sha256"] = "0" * 64
        self.assertEqual(self.api.build_report(self.manifest, records)["groups"]["faithful-B"]["parent_comparison"]["status"], "not_comparable")

    def test_f_valid_dual_arm_parent_comparison_separate_from_predecessor(self):
        record = record_fixture(self.manifest, "faithful-F")
        record["pair"] = {"id": "pair-1", "checkpoint_sha256": H,
                          "control_status": "completed", "intervention_status": "completed"}
        report = self.api.build_report(self.manifest, [record])
        stats = report["groups"]["faithful-F"]
        self.assertEqual(stats["parent_comparison"]["status"], "comparable")
        self.assertEqual(stats["predecessor_comparison"]["status"], "not_comparable")
        self.assertEqual(stats["pairs"]["comparable_count"], 1)
        record["source_revision"] = "0" * 40
        stats = self.api.build_report(self.manifest, [record])["groups"]["faithful-F"]
        self.assertEqual(stats["parent_comparison"]["status"], "not_comparable")
        self.assertEqual(stats["pairs"]["comparable_count"], 0)

    def test_l2_unsupported_and_missing_claim_do_not_become_mathematical_failure(self):
        self.manifest["groups"]["faithful-E"]["capability_status"] = "unsupported"
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-E"] = {
            "target_sha256": H, "scope": "formal_target", "environment_sha256": H}
        row = self.api.build_report(self.manifest, [])["l2"][0]
        self.assertEqual((row["counts"]["unsupported"], row["N_fail"], row["N_decidable"]), (1, 0, 0))
        record = record_fixture(self.manifest, "faithful-E", status="failed")
        row = self.api.build_report(self.manifest, [record])["l2"][0]
        self.assertEqual((row["N_fail"], row["N_decidable"]), (0, 0))
        self.assertIsNone(row["conditional_rate"]["value"])

    def test_unknown_and_censored_counts_independent_of_observation(self):
        records = [record_fixture(self.manifest, index=i, status=s)
                   for i, s in enumerate(("completed", "unknown", "incomplete", "failed"))]
        for record, latency in zip(records, (20, 900, 800, 700)):
            record["metrics"].update(latency_ms=latency, cost=1)
        metrics = self.api.build_report(self.manifest, records)["groups"]["faithful-A"]["metrics"]
        for metric in metrics.values():
            self.assertEqual((metric["unknown_count"], metric["censored_count"]), (1, 1))
        latency = metrics["latency_ms"]
        self.assertEqual((latency["eligible_count"], latency["p50"], latency["p95"]), (1, 20, 20))
        self.assertEqual(latency["censored_values"], {"unknown": [900], "incomplete": [800]})
        self.assertEqual(latency["missing_count"], 10)

    def test_no_completed_latency_does_not_report_completion_percentiles(self):
        record = record_fixture(self.manifest, status="unknown")
        record["metrics"]["latency_ms"] = 42
        latency = self.api.build_report(self.manifest, [record])["groups"]["faithful-A"]["metrics"]["latency_ms"]
        self.assertEqual((latency["eligible_count"], latency["p50"], latency["p95"]), (0, None, None))
        self.assertEqual(latency["status"], "not_available")

    def test_review_requires_all_four_strata_and_exact_28_slots(self):
        for competition in ("AIME2025", "HMMT2026", "Putnam2025", "IMO2025"):
            self.manifest = manifest_fixture()
            self.manifest["dataset"]["samples"] = [s for s in self.manifest["dataset"]["samples"]
                                                    if not s["stratum"].startswith(competition + "/")]
            review = self.review()
            self.assertEqual(len(review["entries"]), 21)
            with self.subTest(competition=competition), self.assertRaises(ValueError):
                self.api.validate_review(review, self.manifest, [], {})
