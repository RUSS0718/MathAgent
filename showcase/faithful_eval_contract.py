"""Strict, side-effect-free schema validation for the frozen Faithful F8 pilot."""

from __future__ import annotations

import hashlib
import math
import re
from urllib.parse import unquote, urlsplit

from showcase.experiment_manifest import canonical_json

GROUPS = tuple(f"faithful-{letter}" for letter in "ABCDEFG")
STATUSES = ("completed", "failed", "unknown", "incomplete", "unsupported", "not_run")
METRICS = ("accuracy", "root_coverage", "valid_evidence", "route_efficiency",
           "latency_ms", "cost", "cache_recheck", "explanation_rubric")
PROTOCOL_VERSION = "faithful-f8-v1.1.1-engineering"
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_REVISION = re.compile(r"[0-9a-f]{40}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9._:/-]+\Z")
_UPSTREAM = "5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d"
_SOURCE_PREFIXES = (f"https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/{_UPSTREAM}/",
                    f"https://github.com/Julius-Woo/STAR-PolyaMath/blob/{_UPSTREAM}/")
_MANIFEST = {"schema_version", "protocol_version", "protocol_sha256", "batch_id",
             "source_revision", "baseline_sha256", "dataset", "model", "prompt_sha256",
             "seed", "repetitions", "environment", "resources", "groups"}
_SAMPLE = {"id", "input_sha256", "source_sha256", "source_ref", "stratum",
           "development_history", "targets"}
_TARGET = {"target_sha256", "scope", "environment_sha256"}
_GROUP = {"parent", "policy", "capability_status", "reason", "config_sha256"}
_RECORD = {"schema_version", "manifest_sha256", "group", "sample_id", "repetition",
           "execution_status", "reason", "run_id", "source_revision", "input_sha256",
           "config_sha256", "evidence_kind", "snapshot_sha256", "metrics", "formal", "pair"}
_FORMAL = {"target_sha256", "scope", "grade", "outcome", "environment_sha256"}
_PAIR = {"id", "checkpoint_sha256", "control_status", "intervention_status"}


def digest(value):
    try:
        return hashlib.sha256(canonical_json(value)).hexdigest()
    except (TypeError, ValueError, OverflowError):
        raise ValueError("faithful_f8_schema_invalid") from None


def _need(condition):
    if not condition:
        raise ValueError("faithful_f8_schema_invalid")


def _object(value, keys):
    _need(type(value) is dict and set(value) == keys)


def _hash(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _token(value):
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def _source_ref(value):
    if not isinstance(value, str) or value != value.strip() or not value.startswith(_SOURCE_PREFIXES):
        return False
    try:
        url = urlsplit(value)
        path = unquote(url.path)
        return (url.scheme == "https" and url.hostname in {"raw.githubusercontent.com", "github.com"}
                and url.port is None and url.username is None and url.password is None
                and not url.query and not url.fragment and "?" not in value and "#" not in value
                and "?" not in path and "#" not in path and "\\" not in path
                and re.fullmatch(r"/[A-Za-z0-9._/-]+", url.path) is not None
                and all(part not in {".", ".."} for part in path.split("/"))
                and bool(path.split("/")[-1]))
    except ValueError:
        return False


def validate_manifest(value):
    try:
        _object(value, _MANIFEST)
        _need(value["schema_version"] == "faithful-f8-manifest-v1"
              and value["protocol_version"] == PROTOCOL_VERSION)
        _need(_hash(value["protocol_sha256"]) and _hash(value["baseline_sha256"])
              and isinstance(value["source_revision"], str)
              and _REVISION.fullmatch(value["source_revision"]) is not None)
        _need(isinstance(value["batch_id"], str) and re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value["batch_id"]))
        _need(_token(value["seed"]) and type(value["repetitions"]) is int and value["repetitions"] > 0)
        dataset = value["dataset"]
        _object(dataset, {"sha256", "samples"})
        _need(_hash(dataset["sha256"]) and type(dataset["samples"]) is list and bool(dataset["samples"]))
        ids = set()
        for sample in dataset["samples"]:
            _object(sample, _SAMPLE)
            _need(_token(sample["id"]) and sample["id"] not in ids)
            ids.add(sample["id"])
            _need(all(_hash(sample[key]) for key in ("input_sha256", "source_sha256")))
            _need(_source_ref(sample["source_ref"]) and _token(sample["stratum"]))
            _need(sample["development_history"] in {"unknown", "development", "held_out"})
            targets = sample["targets"]
            _object(targets, set(GROUPS))
            for target in targets.values():
                if target is not None:
                    _object(target, _TARGET)
                    _need(_hash(target["target_sha256"]) and _hash(target["environment_sha256"])
                          and target["scope"] in {"formal_target", "original_problem"})
        model = value["model"]
        _object(model, {"provider", "id", "snapshot"})
        _need(all(_token(model[k]) for k in model) and _hash(value["prompt_sha256"]))
        _object(value["environment"], {"identity_sha256", "tools_status"})
        _need(_hash(value["environment"]["identity_sha256"])
              and value["environment"]["tools_status"] in {"unknown", "available", "not_run"})
        resources = value["resources"]
        _object(resources, {"identity_sha256", "limits_status", "stop_rules"})
        _need(_hash(resources["identity_sha256"])
              and resources["limits_status"] in {"unknown", "available", "not_run"})
        rules = resources["stop_rules"]
        required = {"unknown", "cancel", "hard_limit", "source_or_config_change", "ledger_or_binding_defect"}
        _need(type(rules) is list and len(rules) == len(set(rules)) and set(rules) == required)
        groups = value["groups"]
        _object(groups, set(GROUPS))
        parents = {}
        for group, config in groups.items():
            _object(config, _GROUP)
            parent = config["parent"]
            _need(parent is None or parent in groups and parent != group)
            parents[group] = parent
            _need(_token(config["policy"]) and config["capability_status"] in {"available", "unsupported"}
                  and _token(config["reason"]) and _hash(config["config_sha256"]))
        for group in GROUPS:
            seen, current = set(), group
            while current is not None:
                _need(current not in seen)
                seen.add(current)
                current = parents[current]
        _need(groups["faithful-C"]["policy"] == "serial-aprs-v1"
              and groups["faithful-D"]["policy"] == "concurrent-aprs-v1"
              and groups["faithful-F"]["policy"] == "serial-intervention-v1"
              and groups["faithful-F"]["parent"] == "faithful-C")
        digest(value)
        return value
    except (KeyError, TypeError, OverflowError):
        raise ValueError("faithful_f8_schema_invalid") from None


def validate_record(value, manifest):
    try:
        validate_manifest(manifest)
        _object(value, _RECORD)
        _need(value["schema_version"] == "faithful-f8-record-v1"
              and value["manifest_sha256"] == digest(manifest))
        group = value["group"]
        _need(group in GROUPS and type(value["repetition"]) is int
              and 0 <= value["repetition"] < manifest["repetitions"]
              and value["execution_status"] in STATUSES)
        sample = next((s for s in manifest["dataset"]["samples"] if s["id"] == value["sample_id"]), None)
        _need(sample is not None and _token(value["reason"]))
        _need(isinstance(value["source_revision"], str) and _REVISION.fullmatch(value["source_revision"]))
        _need(_hash(value["input_sha256"]) and _hash(value["config_sha256"]))
        _need(value["evidence_kind"] in {"engineering", "real_tool", "provider_live", "natural_problem"})
        status = value["execution_status"]
        started = status not in {"not_run", "unsupported"}
        _need((value["run_id"] is None or _token(value["run_id"]))
              and (value["snapshot_sha256"] is None or _hash(value["snapshot_sha256"])))
        _need(not started or _token(value["run_id"]) and _hash(value["snapshot_sha256"]))
        metrics = value["metrics"]
        _object(metrics, set(METRICS))
        _need(started or all(metric is None for metric in metrics.values()))
        for metric in metrics.values():
            _need(metric is None or type(metric) in {int, float} and math.isfinite(metric) and metric >= 0)
        _need(metrics["accuracy"] is None and metrics["explanation_rubric"] is None
              and (metrics["root_coverage"] is None or metrics["root_coverage"] <= 1))
        target, formal = sample["targets"][group], value["formal"]
        if formal is not None:
            _object(formal, _FORMAL)
            _need(target is not None and all(formal[k] == target[k] for k in _TARGET))
            _need(formal["grade"] in {None, "L2", "L3"}
                  and (formal["scope"] != "formal_target" or formal["grade"] != "L3")
                  and formal["outcome"] in {"pass", "fail", "unknown", "incomplete", "unsupported", "not_run"})
            _need(started or formal["outcome"] == status)
            if formal["outcome"] == "pass":
                _need(status == "completed" and formal["grade"] in {"L2", "L3"})
            else:
                _need(formal["grade"] is None)
        pair = value["pair"]
        if group == "faithful-F":
            if pair is None:
                _need(status in {"not_run", "unsupported"})
            else:
                _object(pair, _PAIR)
                _need(_token(pair["id"]) and _hash(pair["checkpoint_sha256"])
                      and pair["control_status"] in STATUSES and pair["intervention_status"] in STATUSES)
        else:
            _need(pair is None)
        return value
    except (KeyError, TypeError, OverflowError):
        raise ValueError("faithful_f8_schema_invalid") from None
