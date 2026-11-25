"""Verify authorized copies of the research-method Pilot archives offline."""

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath

ANCHOR = Path(__file__).resolve().parents[1] / "docs/evals/runtime-method-pilot-anchor.json"


class EvidenceError(ValueError):
    """One archive does not match the published evidence anchor."""


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _require(ok, message):
    if not ok:
        raise EvidenceError(message)


def _archive_path(root, relative):
    path = PurePosixPath(relative)
    _require(not path.is_absolute() and ".." not in path.parts and "\\" not in relative,
             f"invalid archive path: {relative}")
    candidate = (root / path).resolve()
    _require(candidate.is_relative_to(root.resolve()), f"path outside archive: {relative}")
    return candidate


def check_archive(root, anchor, revision):
    """Validate indexed bytes, Run/Trace coverage, source, and recalculated configuration hashes."""
    index_bytes = _archive_path(root, "archive-index.json").read_bytes()
    _require(_sha(index_bytes) == anchor["index_sha256"], "index digest mismatch")
    index = json.loads(index_bytes)
    _require(index["schema_version"] == 1 and index["revision"] == revision
             and index["phase"] == anchor["phase"], "unexpected archive schema, source, or phase")
    files = index["files_sha256"]
    entries = index["run_config_hashes"]
    configs = {row["id"]: row for row in entries}
    _require(len(files) == anchor["files"] and len(configs) == len(entries) == anchor["runs"],
             "unexpected indexed file or Run count")
    seen = set()
    for relative, expected in files.items():
        contents = _archive_path(root, relative).read_bytes()
        _require(_sha(contents) == expected, f"digest mismatch: {relative}")
        path = PurePosixPath(relative)
        if path.name != "run.json":
            continue
        record = json.loads(contents)
        run_id = record["run_id"]
        _require(run_id not in seen and run_id in configs and path.parent.name == run_id,
                 f"unexpected or duplicate Run identity: {relative}")
        row = configs[run_id]
        _require(row["batch"] == path.parts[0] and row["problem_id"] == record["problem"]["id"]
                 and row["condition"] == record["condition_id"] and record["source"]["revision"] == revision,
                 f"Run provenance mismatch: {relative}")
        config = json.dumps(record["config"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        _require(_sha(config.encode()) == row["sha256"] == record["config_sha256"],
                 f"configuration mismatch: {relative}")
        _require(path.with_name("trace.jsonl").as_posix() in files, f"trace missing: {relative}")
        seen.add(run_id)
    _require(seen == set(configs), "indexed Run records missing")
    return {"files": len(files), "runs": len(seen)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive_parent", type=Path, help="directory containing both named archive roots")
    args = parser.parse_args(argv)
    try:
        anchor = json.loads(ANCHOR.read_bytes())
        _require(anchor["schema_version"] == 1, "unsupported evidence anchor schema")
        verified = {}
        for row in anchor["archives"]:
            name = row["archive"]
            try:
                verified[name] = check_archive(args.archive_parent / name, row, anchor["source_revision"])
            except (EvidenceError, OSError, KeyError, TypeError) as error:
                raise EvidenceError(f"{name}: {error}") from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Pilot archive verification failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"source_revision": anchor["source_revision"], "verified": verified}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
