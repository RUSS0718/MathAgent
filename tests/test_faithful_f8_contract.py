"""Focused F8 schema tests; fixtures perform no registration or file I/O."""

import copy
import hashlib
import importlib
import unittest

from showcase.experiment_manifest import canonical_json

GROUP_NAMES = tuple(f"faithful-{letter}" for letter in "ABCDEFG")
METRIC_NAMES = ("accuracy", "root_coverage", "valid_evidence", "route_efficiency",
                "latency_ms", "cost", "cache_recheck", "explanation_rubric")
VERSION = "faithful-f8-v1.1.1-engineering"
SOURCE = ("https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/"
          "5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d/problems/AIME2025/1.txt")


def manifest_fixture():
    """Return a small independent manifest, with synthetic source identities."""
    groups = {}
    for index, group in enumerate(GROUP_NAMES):
        groups[group] = {
            "parent": GROUP_NAMES[index - 1] if index else None,
            "policy": "harness-v1", "capability_status": "available",
            "reason": "registered", "config_sha256": "c" * 64,
        }
    for group, policy in (("faithful-C", "serial-aprs-v1"),
                          ("faithful-D", "concurrent-aprs-v1"),
                          ("faithful-F", "serial-intervention-v1")):
        groups[group]["policy"] = policy
    groups["faithful-F"]["parent"] = "faithful-C"
    return {
        "schema_version": "faithful-f8-manifest-v1", "protocol_version": VERSION,
        "protocol_sha256": "a" * 64, "batch_id": "schema-fixture",
        "source_revision": "1" * 40, "baseline_sha256": "b" * 64,
        "dataset": {"sha256": "d" * 64, "samples": [{
            "id": "AIME2025/1", "input_sha256": "e" * 64,
            "source_sha256": "f" * 64, "source_ref": SOURCE,
            "stratum": "AIME2025/answer", "development_history": "unknown",
            "targets": dict.fromkeys(GROUP_NAMES),
        }]},
        "model": {"provider": "none", "id": "scripted", "snapshot": "unknown"},
        "prompt_sha256": "a" * 64, "seed": "schema-fixture", "repetitions": 1,
        "environment": {"identity_sha256": "a" * 64, "tools_status": "not_run"},
        "resources": {"identity_sha256": "b" * 64, "limits_status": "unknown",
                      "stop_rules": ["unknown", "cancel", "hard_limit",
                                     "source_or_config_change", "ledger_or_binding_defect"]},
        "groups": groups,
    }


def record_fixture(manifest, **overrides):
    """Return an unexecuted record bound to the supplied manifest."""
    group = overrides.get("group", "faithful-A")
    config_group = group if group in manifest["groups"] else "faithful-A"
    sample = manifest["dataset"]["samples"][0]
    record = {
        "schema_version": "faithful-f8-record-v1",
        "manifest_sha256": hashlib.sha256(canonical_json(manifest)).hexdigest(),
        "group": group, "sample_id": sample["id"], "repetition": 0,
        "execution_status": "not_run", "reason": "missing_artifact", "run_id": None,
        "source_revision": manifest["source_revision"],
        "input_sha256": sample["input_sha256"],
        "config_sha256": manifest["groups"][config_group]["config_sha256"],
        "evidence_kind": "engineering", "snapshot_sha256": None,
        "metrics": dict.fromkeys(METRIC_NAMES), "formal": None, "pair": None,
    }
    record.update(overrides)
    return record


class FaithfulF8ContractTest(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module("showcase.faithful_eval_contract")
        self.manifest = manifest_fixture()

    def reject_manifest(self, path, value):
        manifest = copy.deepcopy(self.manifest)
        obj = manifest
        for key in path[:-1]:
            obj = obj[key]
        obj[path[-1]] = value
        with self.assertRaises(ValueError):
            self.api.validate_manifest(manifest)

    def reject_record(self, **overrides):
        with self.assertRaises(ValueError):
            self.api.validate_record(record_fixture(self.manifest, **overrides), self.manifest)

    def test_public_constants(self):
        self.assertEqual(self.api.GROUPS, GROUP_NAMES)
        self.assertEqual(self.api.METRICS, METRIC_NAMES)
        self.assertEqual(self.api.STATUSES, ("completed", "failed", "unknown", "incomplete",
                                            "unsupported", "not_run"))
        self.assertEqual(self.api.PROTOCOL_VERSION, VERSION)

    def test_digest_canonical_and_nan_rejection(self):
        self.assertEqual(self.api.digest({}),
                         "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")
        self.assertEqual(self.api.digest({"z": "数学", "a": 1}),
                         hashlib.sha256(canonical_json({"a": 1, "z": "数学"})).hexdigest())
        with self.assertRaises(ValueError):
            self.api.digest(float("nan"))

    def test_manifest_returns_same_object_without_mutation(self):
        before = copy.deepcopy(self.manifest)
        self.assertIs(self.api.validate_manifest(self.manifest), self.manifest)
        self.assertEqual(self.manifest, before)

    def test_manifest_exact_keys_at_every_level(self):
        paths = [(), ("dataset",), ("dataset", "samples", 0), ("model",),
                 ("environment",), ("resources",), ("groups", "faithful-A")]
        for path in paths:
            for extra in (True, False):
                with self.subTest(path=path, extra=extra):
                    manifest = copy.deepcopy(self.manifest)
                    obj = manifest
                    for key in path:
                        obj = obj[key]
                    if extra:
                        obj["prompt"] = "private"
                    else:
                        del obj[next(iter(obj))]
                    with self.assertRaises(ValueError):
                        self.api.validate_manifest(manifest)

    def test_manifest_hashes_and_revision_are_strict(self):
        for path in [("baseline_sha256",), ("source_revision",), ("protocol_sha256",),
                     ("dataset", "sha256"), ("dataset", "samples", 0, "source_sha256")]:
            for value in (None, 42, "A" * 64, "a" * 63, "private text"):
                self.reject_manifest(path, value)

    def test_manifest_identifiers_repetitions_and_enums(self):
        for value in ("../x", "x/y", ".", "a.b", "", "a" * 81):
            self.reject_manifest(("batch_id",), value)
        for value in (True, 0, -1, 1.0, "1"):
            self.reject_manifest(("repetitions",), value)
        for path, value in [(("seed",), ""), (("model", "id"), "private text"),
                            (("protocol_version",), "old"),
                            (("environment", "tools_status"), "completed"),
                            (("resources", "limits_status"), "unbounded"),
                            (("dataset", "samples", 0, "development_history"), "independent")]:
            self.reject_manifest(path, value)

    def test_stop_rules_are_exact_unique_array(self):
        rules = self.manifest["resources"]["stop_rules"]
        for value in (rules[:-1], rules + [rules[0]], rules + ["other"], "unknown", [True]):
            self.reject_manifest(("resources", "stop_rules"), value)

    def test_samples_unique_and_nonempty_and_all_groups_present(self):
        sample = self.manifest["dataset"]["samples"][0]
        for samples in ([], [sample, sample], {}, [None]):
            self.reject_manifest(("dataset", "samples"), samples)
        self.reject_manifest(("groups",), {})
        self.reject_manifest(("dataset", "samples", 0, "targets"), {})

    def test_source_ref_fixed_public_https_only(self):
        for value in (SOURCE + "?token=secret", SOURCE + "#fragment", SOURCE + "?",
                      SOURCE.replace("https://", "http://"),
                      SOURCE.replace("https://", "https://name:secret@"),
                      SOURCE.replace("raw.githubusercontent.com", "127.0.0.1"),
                      SOURCE.replace("raw.githubusercontent.com", "evil.example"),
                      SOURCE.replace("5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d", "main"),
                      SOURCE.replace("/problems/", "/../"), SOURCE + "%3Fsecret", SOURCE + "\n"):
            self.reject_manifest(("dataset", "samples", 0, "source_ref"), value)

    def test_parent_cycles_and_unknown_parent_rejected(self):
        self.reject_manifest(("groups", "faithful-A", "parent"), "faithful-G")
        self.reject_manifest(("groups", "faithful-A", "parent"), "faithful-A")
        self.reject_manifest(("groups", "faithful-A", "parent"), "faithful-X")

    def test_policy_and_f_parent_are_frozen(self):
        for group in ("faithful-C", "faithful-D", "faithful-F"):
            self.reject_manifest(("groups", group, "policy"), "other-v1")
        self.reject_manifest(("groups", "faithful-F", "parent"), "faithful-E")

    def test_record_returns_same_object_and_all_states(self):
        for status in self.api.STATUSES:
            identity = ({"run_id": "run-1", "snapshot_sha256": "a" * 64}
                        if status not in {"not_run", "unsupported"} else {})
            record = record_fixture(self.manifest, execution_status=status, **identity)
            before = copy.deepcopy(record)
            self.assertIs(self.api.validate_record(record, self.manifest), record)
            self.assertEqual(record, before)

    def test_record_exact_keys_and_sensitive_fields_rejected(self):
        record = record_fixture(self.manifest)
        for key in record:
            partial = dict(record)
            del partial[key]
            with self.assertRaises(ValueError):
                self.api.validate_record(partial, self.manifest)
        self.reject_record(prompt="secret")
        self.reject_record(metrics={**record["metrics"], "answer": "secret"})

    def test_record_binding_and_types(self):
        for overrides in ({"manifest_sha256": "0" * 64}, {"group": "A"},
                          {"sample_id": "missing"}, {"repetition": True},
                          {"repetition": 1}, {"execution_status": "running"},
                          {"evidence_kind": "independent_math"}, {"run_id": "private text"},
                          {"reason": []}, {"source_revision": "a" * 64}):
            self.reject_record(**overrides)

    def test_started_states_require_run_and_snapshot(self):
        for status in ("completed", "failed", "unknown", "incomplete"):
            self.reject_record(execution_status=status)
            self.reject_record(execution_status=status, run_id="run-1")
            self.reject_record(execution_status=status, snapshot_sha256="a" * 64)

    def test_source_config_input_drift_is_retained(self):
        record = record_fixture(self.manifest, source_revision="2" * 40,
                                config_sha256="0" * 64, input_sha256="0" * 64)
        self.assertIs(self.api.validate_record(record, self.manifest), record)

    def test_metrics_ranges_and_reserved_scores(self):
        identity = {"execution_status": "completed", "run_id": "run-1", "snapshot_sha256": "a" * 64}
        for key in METRIC_NAMES:
            for value in (True, -1, float("inf"), float("nan"), "1", {}):
                metrics = dict.fromkeys(METRIC_NAMES)
                metrics[key] = value
                self.reject_record(metrics=metrics, **identity)
        for key, value in (("accuracy", 1), ("explanation_rubric", 0), ("root_coverage", 1.01)):
            metrics = dict.fromkeys(METRIC_NAMES)
            metrics[key] = value
            self.reject_record(metrics=metrics, **identity)
        metrics = dict.fromkeys(METRIC_NAMES)
        metrics.update(root_coverage=1, cost=0, latency_ms=2.5, valid_evidence=3)
        self.api.validate_record(record_fixture(self.manifest, metrics=metrics, **identity), self.manifest)

    def test_formal_requires_registered_target(self):
        self.reject_record(formal={"target_sha256": "a" * 64, "scope": "formal_target",
                                   "grade": "L2", "outcome": "pass", "environment_sha256": "b" * 64},
                           execution_status="completed", run_id="run-1", snapshot_sha256="a" * 64)

    def test_unstarted_records_require_all_metrics_null_including_zero(self):
        for status in ("not_run", "unsupported"):
            record = record_fixture(self.manifest, execution_status=status)
            self.assertIs(self.api.validate_record(record, self.manifest), record)
            for key in METRIC_NAMES:
                for metric in (0, 1):
                    with self.subTest(status=status, key=key, metric=metric):
                        metrics = dict.fromkeys(METRIC_NAMES)
                        metrics[key] = metric
                        self.reject_record(execution_status=status, metrics=metrics)

    def test_unstarted_formal_requires_matching_outcome_and_null_grade(self):
        target = {"target_sha256": "a" * 64, "scope": "original_problem",
                  "environment_sha256": "b" * 64}
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-A"] = target
        for status in ("not_run", "unsupported"):
            for outcome in ("pass", "fail", "unknown", "incomplete", "unsupported", "not_run"):
                for grade in (None, "L2", "L3"):
                    with self.subTest(status=status, outcome=outcome, grade=grade):
                        record = record_fixture(
                            self.manifest, execution_status=status,
                            formal={**target, "outcome": outcome, "grade": grade})
                        if outcome == status and grade is None:
                            self.assertIs(self.api.validate_record(record, self.manifest), record)
                        else:
                            with self.assertRaises(ValueError):
                                self.api.validate_record(record, self.manifest)

    def test_started_formal_pass_requires_completed_and_grade_nonpass_has_no_grade(self):
        target = {"target_sha256": "a" * 64, "scope": "original_problem",
                  "environment_sha256": "b" * 64}
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-A"] = target
        for status in ("completed", "failed", "unknown", "incomplete"):
            for outcome in ("pass", "fail", "unknown", "incomplete", "unsupported", "not_run"):
                for grade in (None, "L2", "L3"):
                    with self.subTest(status=status, outcome=outcome, grade=grade):
                        record = record_fixture(
                            self.manifest, execution_status=status, run_id="run-1",
                            snapshot_sha256="a" * 64,
                            formal={**target, "outcome": outcome, "grade": grade})
                        valid = ((status == "completed" and grade in ("L2", "L3"))
                                 if outcome == "pass" else grade is None)
                        if valid:
                            self.assertIs(self.api.validate_record(record, self.manifest), record)
                        else:
                            with self.assertRaises(ValueError):
                                self.api.validate_record(record, self.manifest)

    def test_formal_identity_scope_environment_and_grade(self):
        target = {"target_sha256": "a" * 64, "scope": "formal_target",
                  "environment_sha256": "b" * 64}
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-A"] = target
        formal = {**target, "grade": "L2", "outcome": "pass"}
        identity = {"execution_status": "completed", "run_id": "run-1", "snapshot_sha256": "a" * 64}
        record = record_fixture(self.manifest, formal=formal, **identity)
        self.assertIs(self.api.validate_record(record, self.manifest), record)
        for key, value in (("target_sha256", "0" * 64), ("environment_sha256", "0" * 64),
                           ("scope", "original_problem"), ("grade", "L3"),
                           ("outcome", "completed"), ("private_proof", "secret")):
            self.reject_record(formal={**formal, key: value}, **identity)
        self.reject_manifest(("dataset", "samples", 0, "targets", "faithful-A"),
                             {**target, "grade": "L3"})

    def test_original_scope_l3_is_preserved_as_source_claim(self):
        target = {"target_sha256": "a" * 64, "scope": "original_problem",
                  "environment_sha256": "b" * 64}
        self.manifest["dataset"]["samples"][0]["targets"]["faithful-A"] = target
        record = record_fixture(self.manifest, formal={**target, "grade": "L3", "outcome": "pass"},
                                execution_status="completed", run_id="run-1", snapshot_sha256="a" * 64)
        self.assertIs(self.api.validate_record(record, self.manifest), record)
        self.assertNotIn("independently_verified", record)

    def test_f_pair_required_for_started_states_and_other_groups_null(self):
        pair = {"id": "pair-1", "checkpoint_sha256": "a" * 64,
                "control_status": "completed", "intervention_status": "unknown"}
        for status in self.api.STATUSES:
            identity = ({"run_id": "run-1", "snapshot_sha256": "b" * 64}
                        if status not in {"not_run", "unsupported"} else {})
            record = record_fixture(self.manifest, group="faithful-F", execution_status=status,
                                    pair=pair, **identity)
            self.api.validate_record(record, self.manifest)
            record["pair"] = None
            if status in ("not_run", "unsupported"):
                self.api.validate_record(record, self.manifest)
            else:
                with self.assertRaises(ValueError):
                    self.api.validate_record(record, self.manifest)
        self.reject_record(pair=pair)
        for key, value in (("id", "private text"), ("checkpoint_sha256", None),
                           ("control_status", "running"), ("answer", "secret")):
            self.reject_record(group="faithful-F", pair={**pair, key: value})

    def test_invalid_container_types_raise_value_error(self):
        for value in (None, [], True, "{}"):
            with self.assertRaises(ValueError):
                self.api.validate_manifest(value)
            with self.assertRaises(ValueError):
                self.api.validate_record(value, self.manifest)
        self.reject_manifest(("groups", "faithful-A", "capability_status"), [])
        self.reject_manifest(("dataset", "samples", 0, "targets", "faithful-A"), [])


if __name__ == "__main__":
    unittest.main()
