"""Explicit, offline Faithful registration, immutable imports and read-only replay."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .faithful_eval_store import load_json, write_sealed

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/engineering/faithful-f8-protocol-20261111.md"


def main(argv=None):
    """Run only explicitly requested local evidence operations, without dispatch."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register")
    register.add_argument("--manifest", type=Path, required=True)
    register.add_argument("--sha256", required=True)
    register.add_argument("--root", type=Path, required=True)
    for name in ("record", "review", "replay", "export", "l1"):
        command = commands.add_parser(name)
        command.add_argument("--batch", type=Path, required=True)
        if name in {"record", "review"}:
            command.add_argument(f"--{name}", type=Path, required=True)
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "register":
            result = register_batch(args.manifest, args.sha256, args.root)
        elif args.command == "replay":
            result = replay(args.batch)
        elif args.command in {"record", "review"}:
            result = import_evidence(args.batch, getattr(args, args.command), args.command)
        else:
            from .faithful_eval_export import export_batch, run_l1

            result = export_batch(args.batch, args.output) if args.command == "export" else run_l1(args.batch)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Errors are fixed local categories, never echo caller-controlled payloads.
        print(json.dumps({"status": "rejected", "error": type(error).__name__}))
        return 1


def register_batch(manifest_path, expected_hash, output_root):
    """Freeze the entire sample/group product against a clean source identity."""
    from .experiment_sources import source_identity
    from .faithful_eval_contract import GROUPS, digest, validate_manifest

    manifest = validate_manifest(load_json(manifest_path))
    validate_pilot(manifest)
    if digest(manifest) != expected_hash:
        raise ValueError("faithful_manifest_hash_mismatch")
    if manifest["protocol_sha256"] != hashlib.sha256(PROTOCOL.read_bytes()).hexdigest():
        raise ValueError("faithful_protocol_mismatch")
    source = source_identity()
    if source["dirty_status"] != "clean" or source["revision"] != manifest["source_revision"]:
        raise ValueError("faithful_source_not_frozen")
    baseline = load_json(ROOT / "BASELINE.json")
    if manifest["baseline_sha256"] != hashlib.sha256((ROOT / "BASELINE.json").read_bytes()).hexdigest():
        raise ValueError("faithful_baseline_mismatch")
    if any(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha for name, sha in baseline["files"].items()):
        raise ValueError("faithful_baseline_bytes_changed")
    root = Path(output_root).resolve()
    batch = root / manifest["batch_id"]
    if batch.resolve().parent != root:
        raise ValueError("faithful_batch_path_invalid")
    root.mkdir(parents=True, exist_ok=True)
    batch.mkdir()
    for directory in ("records", "reviews", "l1"):
        (batch / directory).mkdir()
    registration = {
        "schema_version": "faithful-f8-registration-v1",
        "manifest_sha256": expected_hash,
        "slots": [
            {"group": group, "sample_id": sample["id"], "repetition": repetition,
             "execution_status": "unsupported" if manifest["groups"][group]["capability_status"] == "unsupported" else "not_run"}
            for group in GROUPS
            for sample in manifest["dataset"]["samples"]
            for repetition in range(manifest["repetitions"])
        ],
    }
    write_sealed(batch / "manifest.json", manifest)
    write_sealed(batch / "registration.json", registration)
    write_sealed(batch / "source.json", source)
    return {"status": "registered", "batch": str(batch), "registered": len(registration["slots"])}


def read_batch(batch_path):
    """Read and validate every sealed member; do not repair or rewrite evidence."""
    from .faithful_eval_contract import GROUPS, digest, validate_manifest, validate_record
    from .faithful_eval_reporting import validate_review
    from .faithful_eval_store import read_sealed

    batch = Path(batch_path)
    if any(path.is_symlink() for path in (batch, *batch.parents)):
        raise ValueError("faithful_symlink")
    allowed_root = {"manifest.json", "registration.json", "source.json"}
    for member in batch.iterdir():
        if member.is_symlink():
            raise ValueError("faithful_symlink")
        if member.is_dir() and member.name in {"records", "reviews", "l1"}:
            continue
        if member.name.removesuffix(".sha256") not in allowed_root:
            raise ValueError("faithful_extra_member")
    manifest = validate_manifest(read_sealed(batch / "manifest.json"))
    registration = read_sealed(batch / "registration.json")
    source = read_sealed(batch / "source.json")
    expected_slots = [
        {"group": group, "sample_id": sample["id"], "repetition": repetition,
         "execution_status": "unsupported" if manifest["groups"][group]["capability_status"] == "unsupported" else "not_run"}
        for group in GROUPS for sample in manifest["dataset"]["samples"]
        for repetition in range(manifest["repetitions"])
    ]
    if registration != {"schema_version": "faithful-f8-registration-v1", "manifest_sha256": digest(manifest), "slots": expected_slots}:
        raise ValueError("faithful_registration_changed")
    if source["revision"] != manifest["source_revision"] or source["dirty_status"] != "clean":
        raise ValueError("faithful_source_identity_invalid")
    records = []
    for path in _members(batch / "records"):
        record = validate_record(read_sealed(path), manifest)
        if path.name != record_name(record):
            raise ValueError("faithful_record_identity_mismatch")
        records.append(record)
    if len({(r["group"], r["sample_id"], r["repetition"]) for r in records}) != len(records):
        raise ValueError("faithful_duplicate_record")
    reviews = {}
    for path in _members(batch / "reviews"):
        value = read_sealed(path)
        if path.name != value.get("reviewer", "") + ".json":
            raise ValueError("faithful_review_identity_mismatch")
        validate_review(value, manifest, records, reviews)
        reviews[value["reviewer"]] = value
    return manifest, records, reviews, source


def replay(batch_path):
    """Recompute reporting from immutable evidence; never contact providers or tools."""
    from .experiment_sources import source_identity
    from .faithful_eval_reporting import build_report

    manifest, records, reviews, source = read_batch(batch_path)
    report = build_report(manifest, records, source_matches=source == source_identity())
    from .faithful_eval_export import read_l1

    report["l1"] = read_l1(Path(batch_path), manifest)
    report["model_assisted"] = {
        "status": "complete" if set(reviews) == {"R1", "R2", "R3"} else "not_run",
        "registered": 28,
        "reviews": {key: {"entries": len(value["entries"]), "unresolved": sum(e["verdict"] == "unresolved" for e in value["entries"])} for key, value in reviews.items()},
    }
    return report


def import_evidence(batch_path, path, kind):
    """Add one sealed record without replacing prior failures, unknowns or reviews."""
    from .faithful_eval_contract import validate_record
    from .faithful_eval_reporting import validate_review

    manifest, records, reviews, _ = read_batch(batch_path)
    value = load_json(path)
    batch = Path(batch_path)
    if kind == "record":
        validate_record(value, manifest)
        target = batch / "records" / record_name(value)
    else:
        validate_review(value, manifest, records, reviews)
        target = batch / "reviews" / (value["reviewer"] + ".json")
    write_sealed(target, value)
    return {"status": "imported", "kind": kind}


def record_name(record):
    """Use a hash for opaque sample IDs instead of accepting sample paths."""
    sample_hash = hashlib.sha256(record["sample_id"].encode()).hexdigest()
    return f"{record['group']}-{sample_hash}-{record['repetition']}.json"


def validate_pilot(manifest):
    """Keep the actual registered pilot's denominator, seed and strata fixed."""
    samples = manifest["dataset"]["samples"]
    strata = Counter(sample["stratum"] for sample in samples)
    if (len(samples) != 14 or manifest["repetitions"] != 1
            or manifest["seed"] != "faithful-f8-pilot-20261111-v1"
            or manifest["dataset"]["sha256"] != "345b891e3c45f6a95a5b69107d294f7a2f61bd29843c5ba2a82b9c8cd4a0cd7f"
            or strata != {"AIME2025/answer": 4, "HMMT2026/answer": 3, "Putnam2025/proof": 3,
                          "IMO2025/proof": 2, "Apex2025/answer": 2}
            or any(s["development_history"] != "unknown" or any(s["targets"].values()) for s in samples)):
        raise ValueError("faithful_pilot_registration_drift")


def _members(directory):
    """Require the JSON/receipt pairing and reject extra nested artifacts."""
    result = []
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or path.is_dir():
            raise ValueError("faithful_invalid_member")
        if path.name.endswith(".json"):
            result.append(path)
        elif not path.name.endswith(".json.sha256") or not path.with_suffix("").is_file():
            raise ValueError("faithful_extra_member")
    return result


if __name__ == "__main__":
    raise SystemExit(main())
