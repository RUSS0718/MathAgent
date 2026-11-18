"""Pure deterministic reporting, fixed review selection, and review validation."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from typing import Any

from showcase.faithful_eval_contract import (
    GROUPS,
    STATUSES,
    digest,
    validate_manifest,
    validate_record,
)

_LAYERS = ("engineering", "real_tool", "provider_live", "natural_problem", "independent_math")
_METRICS = ("accuracy", "root_coverage", "valid_evidence", "route_efficiency",
            "latency_ms", "cost", "cache_recheck", "explanation_rubric")
_RECORD_KEYS = {"schema_version", "manifest_sha256", "group", "sample_id", "repetition",
                "execution_status", "reason", "run_id", "source_revision", "input_sha256",
                "config_sha256", "evidence_kind", "snapshot_sha256", "metrics", "formal", "pair"}
_REVIEW_KEYS = {"schema_version", "reviewer", "model_id", "manifest_sha256",
                "input_review_sha256", "entries"}
_ENTRY_KEYS = {"group", "sample_id", "repetition", "verdict", "reason", "snapshot_sha256"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_COMPS = ("AIME2025", "HMMT2026", "Putnam2025", "IMO2025")


def _fail(message: str) -> None:
    raise ValueError(message)


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _slots(manifest: dict[str, Any]) -> list[tuple[str, str, int]]:
    samples = manifest["dataset"]["samples"]
    return [(group, sample["id"], repetition) for group in GROUPS for sample in samples
            for repetition in range(manifest["repetitions"])]


def _record_map(manifest: dict[str, Any], records: list[dict[str, Any]]) -> dict[tuple, dict]:
    expected, found = set(_slots(manifest)), {}
    for record in records:
        if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
            _fail("record keys do not match frozen schema")
        slot = (record["group"], record["sample_id"], record["repetition"])
        if slot not in expected or slot in found:
            _fail("duplicate or unregistered record slot")
        if record["execution_status"] not in STATUSES:
            _fail("invalid execution status")
        if isinstance(record["repetition"], bool) or not isinstance(record["repetition"], int):
            _fail("invalid repetition")
        found[slot] = record
    return found


def _metric_summary(name: str, values: list[tuple[str, Any]]) -> dict:
    observed = [v for status, v in values if v is not None
                and (name != "latency_ms" or status == "completed")]
    missing = Counter(status for status, value in values if value is None)
    statuses = Counter(status for status, _ in values)
    result = {"value": None, "status": "not_available" if not observed else "observed_subset",
              "eligible_count": len(observed), "unknown_count": statuses["unknown"],
              "censored_count": statuses["incomplete"],
              "missing_count": sum(missing.values()),
              "missing_by_status": {s: missing[s] for s in STATUSES}}
    if name in {"root_coverage", "valid_evidence", "route_efficiency", "cache_recheck"} and observed:
        result["mean"] = sum(observed) / len(observed)
    if name == "latency_ms":
        ordered = sorted(observed)
        result["censored_values"] = {
            status: sorted(v for s, v in values if s == status and v is not None)
            for status in ("unknown", "incomplete")}
        result.update(p50=ordered[math.ceil(.50 * len(ordered)) - 1] if ordered else None,
                      p95=ordered[math.ceil(.95 * len(ordered)) - 1] if ordered else None)
    return result


def _l2_rows(manifest: dict, rows: dict) -> list[dict]:
    output = []
    for group in GROUPS:
        targets = defaultdict(list)
        for sample in manifest["dataset"]["samples"]:
            target = sample["targets"][group]
            if target is not None:
                targets[(target["scope"], target["target_sha256"],
                         target["environment_sha256"])].append(sample["id"])
        for (scope, target_hash, environment_hash), ids in sorted(targets.items()):
            selected = [rows.get((group, sample_id, rep)) for sample_id in ids
                        for rep in range(manifest["repetitions"])]
            outcomes = [r["formal"] for r in selected if r and r["formal"]
                        and r["formal"].get("target_sha256") == target_hash
                        and r["formal"].get("environment_sha256") == environment_hash
                        and r["formal"].get("scope") == scope]
            passed = sum(x["outcome"] == "pass" for x in outcomes)
            failed = sum(x["outcome"] == "fail" for x in outcomes)
            decidable = passed + failed
            inherited = "unsupported" if manifest["groups"][group]["capability_status"] == "unsupported" else "not_run"
            counts = Counter((r["execution_status"] if r else inherited) for r in selected)
            for status in STATUSES:
                counts.setdefault(status, 0)
            registered = len(manifest["dataset"]["samples"]) * manifest["repetitions"]
            output.append({"group": group, "target_scope": scope, "target_sha256": target_hash,
                           "N_registered": registered,
                           "N_target_registered": len(selected), "N_decidable": decidable,
                           "N_pass": passed, "N_fail": failed,
                           "counts": dict(counts),
                           "primary_rate": {"value": passed / registered if registered else None,
                                            "denominator": registered},
                           "target_rate": {"value": passed / len(selected) if selected else None,
                                           "denominator": len(selected)},
                           "conditional_rate": {"value": passed / decidable if decidable else None,
                                                 "denominator": decidable},
                           "target_coverage": {"value": len(selected) / (len(manifest["dataset"]["samples"]) * manifest["repetitions"]),
                                                  "denominator": "N_registered"},
                           "pass_rate": {"value": passed / decidable if decidable else None,
                                            "denominator": "N_decidable" if decidable else None},
                           "environment_sha256": environment_hash,
                           "source_status": "imported_unverified"})
    return output


def _comparison(group: str, other: str | None, rows: dict, drift: dict) -> str:
    """Require matched completed slots or F's completed control/intervention pair."""
    if drift[group] or (other is not None and drift[other]):
        return "not_comparable"
    if other is None:
        return "not_available"
    for (record_group, sample, repetition), record in rows.items():
        if record_group != group or record["execution_status"] != "completed":
            continue
        if group == "faithful-F" and other == "faithful-C":
            pair = record["pair"]
            if pair and pair["control_status"] == pair["intervention_status"] == "completed":
                return "comparable"
        else:
            counterpart = rows.get((other, sample, repetition))
            if counterpart and counterpart["execution_status"] == "completed":
                return "comparable"
    return "not_available"


def build_report(manifest: dict, records: list, source_matches: bool = True) -> dict:
    """Build deterministic, denominator-preserving report without asserting evidence."""
    validate_manifest(manifest)
    if not isinstance(records, list) or not isinstance(source_matches, bool):
        _fail("invalid report inputs")
    for record in records:
        validate_record(record, manifest)
    rows = _record_map(manifest, records)
    by_group = {}
    dataset = {sample["id"]: sample for sample in manifest["dataset"]["samples"]}
    drift = {group: set() if source_matches else {"source_revision"} for group in GROUPS}
    for record in records:
        for field, expected in (("source_revision", manifest["source_revision"]),
                                ("input_sha256", dataset[record["sample_id"]]["input_sha256"]),
                                ("config_sha256", manifest["groups"][record["group"]]["config_sha256"])):
            if record[field] != expected:
                drift[record["group"]].add(field)
    for group in GROUPS:
        slots = [(group, sample["id"], rep) for sample in manifest["dataset"]["samples"]
                 for rep in range(manifest["repetitions"])]
        counts = Counter()
        metrics = defaultdict(list)
        pairs = []
        for slot in slots:
            record = rows.get(slot)
            if record is None:
                inherited = "unsupported" if manifest["groups"][group]["capability_status"] == "unsupported" else "not_run"
                counts[inherited] += 1
                for name in _METRICS:
                    metrics[name].append((inherited, None))
                continue
            counts[record["execution_status"]] += 1
            for name in _METRICS:
                value = record["metrics"].get(name)
                metrics[name].append((record["execution_status"], value))
            if record["pair"] is not None:
                pairs.append(record["pair"])
        for status in STATUSES:
            counts.setdefault(status, 0)
        config = manifest["groups"][group]
        parent = config["parent"]
        predecessor = GROUPS[GROUPS.index(group) - 1] if group != "faithful-A" else None
        comparison = _comparison(group, parent, rows, drift)
        reasons = drift[group] | (drift[parent] if parent is not None else set())
        by_group[group] = {"parent": config["parent"], "policy": config["policy"],
                           "capability_status": config["capability_status"],
                           "N_registered": len(slots), "counts": dict(counts),
                           "comparison_status": comparison,
                           "comparison_reasons": sorted(reasons),
                           "predecessor_comparison": {"group": predecessor,
                                                         "status": "not_comparable" if group == "faithful-F" else _comparison(group, predecessor, rows, drift)},
                           "parent_comparison": {"group": config["parent"],
                                                   "status": comparison},
                           "metrics": {n: _metric_summary(n, metrics[n]) for n in _METRICS},
                           "pairs": {"records": pairs, "comparable_count": sum(
                               r["execution_status"] == "completed" and r["pair"] is not None
                               and r["pair"]["control_status"] == r["pair"]["intervention_status"] == "completed"
                               for slot, r in rows.items() if slot[0] == group) if not reasons else 0},
                           "evidence_refs": [], "limitations": ["Imported records are not independently verified."]}
    layer_counts = Counter(r["evidence_kind"] for r in records)
    return {"schema_version": "faithful-f8-report-v1", "batch_id": manifest["batch_id"],
            "protocol_sha256": manifest["protocol_sha256"], "manifest_sha256": digest(manifest),
            "source_revision": manifest["source_revision"], "evidence_layers": {
                layer: {"status": "not_run", "imported_count": layer_counts.get(layer, 0)}
                for layer in _LAYERS}, "groups": by_group, "l1": {"status": "not_run"},
            "l2": _l2_rows(manifest, rows),
            "l3": {"status": "not_run", "model_assisted": "not_run"},
            "official_score": {"status": "not_run", "value": None},
            "limitations": ["Imported records establish registration only; evidence layers require independent source review."]}


def review_selection(manifest: dict) -> list[dict]:
    """Select up to one fixed-seed sample per competition across all seven groups."""
    validate_manifest(manifest)
    samples = manifest["dataset"]["samples"]
    selected = []
    for competition in _COMPS:
        scope = "answer" if competition in {"AIME2025", "HMMT2026"} else "proof"
        candidates = [s for s in samples if s["stratum"] == f"{competition}/{scope}"]
        if candidates:
            sample = min(candidates, key=lambda s: hashlib.sha256(
                f"{manifest['seed']}:{s['id']}:0".encode()).digest())
            selected.extend({"group": group, "sample_id": sample["id"], "repetition": 0}
                            for group in GROUPS)
    return selected


def _validate_review_shape(review: Any, manifest: dict, role: str) -> list[dict]:
    if not isinstance(review, dict) or set(review) != _REVIEW_KEYS:
        _fail("review keys do not match schema")
    if review["schema_version"] != "faithful-f8-review-v1" or review["reviewer"] != role:
        _fail("invalid review identity")
    if not isinstance(review["model_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}|unknown", review["model_id"]):
        _fail("invalid review model identity")
    if review["manifest_sha256"] != digest(manifest):
        _fail("review manifest hash mismatch")
    expected = {tuple(x[k] for k in ("group", "sample_id", "repetition"))
                for x in review_selection(manifest)}
    if len(expected) != 28:
        _fail("pilot review requires four complete strata and exactly 28 selected slots")
    if not isinstance(review["entries"], list) or len(review["entries"]) != len(expected):
        _fail("review must contain the complete selection")
    seen = set()
    for entry in review["entries"]:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            _fail("review entry keys do not match schema")
        slot = (entry["group"], entry["sample_id"], entry["repetition"])
        if slot in seen or slot not in expected or isinstance(entry["repetition"], bool) or not isinstance(entry["repetition"], int):
            _fail("duplicate or invalid review slot")
        if (entry["verdict"] != "unresolved" or entry["reason"] != "missing_artifact"
                or entry["snapshot_sha256"] is not None):
            _fail("engineering pilot requires unresolved/missing_artifact/null; hashes do not prove artifacts")
        seen.add(slot)
    if seen != expected:
        _fail("review selection incomplete")
    return review["entries"]


def validate_review(review: dict, manifest: dict, records: list, prior_reviews: dict) -> dict:
    """Validate sealed engineering-only reviews; imported hashes cannot authorize math verdicts."""
    validate_manifest(manifest)
    _validate_review_shape(review, manifest, review.get("reviewer") if isinstance(review, dict) else "")
    role = review["reviewer"]
    if not isinstance(role, str) or role not in {"R1", "R2", "R3"}:
        _fail("invalid reviewer role")
    hashes = review["input_review_sha256"]
    if not isinstance(hashes, list) or any(not _is_hash(h) for h in hashes):
        _fail("invalid prior review hashes")
    if role in {"R1", "R2"}:
        if hashes:
            _fail("initial reviews require empty input hashes")
    elif role == "R3":
        if not isinstance(prior_reviews, dict) or set(prior_reviews) != {"R1", "R2"}:
            _fail("R3 requires both initial reviews")
        for prior_role in ("R1", "R2"):
            prior = prior_reviews[prior_role]
            _validate_review_shape(prior, manifest, prior_role)
            if prior["input_review_sha256"] != []:
                _fail("initial reviews require empty input hashes")
        if hashes != [digest(prior_reviews[r]) for r in ("R1", "R2")]:
            _fail("R3 input review hash mismatch")
    else:
        _fail("invalid reviewer role")
    _record_map(manifest, records)
    return review
