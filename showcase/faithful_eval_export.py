"""Export verified Faithful evidence and execute its fixed L1 regression contract."""

import hashlib
import json
import re
import shutil
import subprocess
import unittest
from datetime import UTC, datetime
from pathlib import Path

from .experiment_sources import source_identity
from .faithful_eval import PROTOCOL, ROOT, read_batch, replay
from .faithful_eval_store import canonical_json, read_sealed, write_sealed


def frozen_l1_ids():
    """Read the exact 25 expression/API regression IDs from the frozen protocol."""
    content = PROTOCOL.read_text(encoding="utf-8")
    identifiers = tuple(re.findall(r"^tests[.]test_[^\r\n]+", content, re.M))
    if len(identifiers) != 25 or len(set(identifiers)) != 25:
        raise ValueError("faithful_l1_manifest_invalid")
    return identifiers


def run_l1(batch_path):
    """Run the fixed regression once and retain failures instead of replacing them."""
    batch = Path(batch_path)
    manifest, _, _, source = read_batch(batch)
    if source_identity() != source:
        raise ValueError("faithful_l1_source_not_frozen")
    expected = frozen_l1_ids()
    suite = unittest.defaultTestLoader.loadTestsFromNames(
        ("tests.test_faithful_f6_presentation", "tests.test_s06_presentation")
    )
    if sorted(expected) != sorted(test.id() for test in _flatten(suite)):
        raise ValueError("faithful_l1_test_ids_drift")
    folder = batch / "l1"
    if any(folder.iterdir()):
        raise ValueError("faithful_l1_already_run")
    summary, diagnostics = folder / "summary.json", folder / "diagnostics.log"
    command = ["uv", "run", "python", "scripts/run_unittest_report.py", "--expect-count", "25",
               "--summary-json", str(summary), "--diagnostics", str(diagnostics),
               "tests.test_faithful_f6_presentation", "tests.test_s06_presentation"]
    started = datetime.now(UTC).isoformat()
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    console = folder / "console.log"
    console.write_text((completed.stdout or "") + (completed.stderr or ""), encoding="utf-8")
    payload = json.loads(summary.read_text(encoding="utf-8")) if summary.is_file() else None
    source_unchanged = source_identity() == source
    passed = bool(completed.returncode == 0 and source_unchanged
                  and payload and payload.get("testsRun") == 25 and payload.get("status") == "passed"
                  and not any(payload.get(key) for key in
                              ("skipped", "expectedFailures", "failures", "errors", "unexpectedSuccesses")))
    result = {
        "schema_version": "faithful-f8-l1-v1", "manifest_sha256": manifest_hash(manifest),
        "status": "pass" if passed else "fail", "expected_ids": list(expected),
        "source_identity": source, "command": command, "exit_code": completed.returncode,
        "source_unchanged": source_unchanged,
        "summary": payload, "files": {p.name: _file_hash(p) for p in (summary, diagnostics, console)},
        "started_at": started,
    }
    write_sealed(folder / "result.json", result)
    if not passed:
        raise ValueError("faithful_l1_failed_or_source_changed")
    return {"status": result["status"], "tests": 25}


def read_l1(batch, manifest):
    """Verify raw L1 reports and selector identity without executing a test."""
    folder = Path(batch) / "l1"
    if not any(folder.iterdir()):
        return {"registered": 25, "status": "not_run"}
    allowed = {"result.json", "result.json.sha256", "summary.json", "diagnostics.log", "console.log"}
    if any(p.is_dir() or p.is_symlink() or p.name not in allowed for p in folder.iterdir()):
        raise ValueError("faithful_l1_member_invalid")
    result = read_sealed(folder / "result.json")
    if (result["manifest_sha256"] != manifest_hash(manifest)
            or result["expected_ids"] != list(frozen_l1_ids())
            or any(_file_hash(folder / name) != sha for name, sha in result["files"].items())):
        raise ValueError("faithful_l1_integrity_failed")
    summary_path = folder / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
    if result["summary"] != summary or result["source_identity"]["revision"] != manifest["source_revision"]:
        raise ValueError("faithful_l1_report_identity_failed")
    actual_pass = bool(summary is not None and result["exit_code"] == 0 and result["source_unchanged"]
                       and summary.get("testsRun") == 25 and summary.get("status") == "passed"
                       and not any(summary.get(k) for k in
                                   ("skipped", "expectedFailures", "failures", "errors", "unexpectedSuccesses")))
    if result["status"] != ("pass" if actual_pass else "fail"):
        raise ValueError("faithful_l1_status_mismatch")
    return {"registered": 25, "status": result["status"], "summary": result["summary"],
            "source_revision": result["source_identity"]["revision"]}


def export_batch(batch_path, output_path):
    """Create a redacted package and an external receipt without circular hashing."""
    batch, output = Path(batch_path), Path(output_path)
    receipt = output.with_name(output.name + "-export-receipt.json")
    if any(path.resolve().is_relative_to(batch.resolve()) for path in (output, receipt)):
        raise ValueError("faithful_export_inside_source_batch")
    if output.exists() or receipt.exists():
        raise ValueError("faithful_export_exists")
    manifest, records, reviews, _ = read_batch(batch)
    report = replay(batch)
    report["l1"] = read_l1(batch, manifest)
    output.mkdir(parents=True)
    for name in ("records", "reviews", "l1", "configs", "verification", "api-browser", "failures", "gates"):
        (output / name).mkdir()
    for path in batch.iterdir():
        if path.is_file():
            shutil.copyfile(path, output / path.name)
    for directory in ("records", "reviews"):
        for path in (batch / directory).iterdir():
            if path.is_symlink() or not path.is_file():
                raise ValueError("faithful_export_invalid_member")
            shutil.copyfile(path, output / directory / path.name)
    _copy_l1(batch / "l1", output / "l1")
    (output / "report.json").write_bytes(canonical_json(report))
    (output / "report.md").write_text(_markdown(report), encoding="utf-8")
    members = [{"path": p.relative_to(output).as_posix(), "bytes": p.stat().st_size,
                "sha256": _file_hash(p)} for p in sorted(output.rglob("*")) if p.is_file()]
    index_bytes = canonical_json({"schema_version": "faithful-f8-integrity-v1", "members": members})
    (output / "integrity.json").write_bytes(index_bytes)
    index_hash = hashlib.sha256(index_bytes).hexdigest()
    write_sealed(receipt, {"schema_version": "faithful-f8-export-receipt-v1",
                          "batch_id": manifest["batch_id"],
                          "protocol_sha256": manifest["protocol_sha256"],
                          "manifest_sha256": manifest_hash(manifest), "integrity_sha256": index_hash})
    return {"status": "exported", "output": str(output), "integrity_sha256": index_hash,
            "receipt_path": str(receipt), "records": len(records), "reviews": len(reviews)}


def manifest_hash(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _copy_l1(source, target):
    """Export only fixed diagnostic counts and hashes; retain raw logs privately."""
    result_path = source / "result.json"
    if not result_path.is_file():
        return
    result = read_sealed(result_path)
    summary = result.get("summary") or {}
    safe_summary = {key: summary.get(key) for key in
                    ("testsRun", "status", "failures", "errors", "skipped",
                     "expectedFailures", "unexpectedSuccesses", "elapsed")}
    if any(value is not None and not isinstance(value, (int, float, str, bool))
           for value in safe_summary.values()):
        raise ValueError("faithful_l1_summary_not_scalar")
    projection = {"schema_version": result["schema_version"], "status": result["status"],
                  "manifest_sha256": result["manifest_sha256"], "expected_ids": result["expected_ids"],
                  "source_identity": result["source_identity"], "exit_code": result["exit_code"],
                  "source_unchanged": result["source_unchanged"], "summary": safe_summary,
                  "original_files": result["files"]}
    write_sealed(target / "public-result.json", projection)


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def _file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _markdown(report):
    lines = ["# Faithful F8 engineering report", "", "Batch: " + report["batch_id"], "",
             "| Group | Registered | Completed | Failed | Unknown | Incomplete | Unsupported | Not run |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, stats in report["groups"].items():
        counts = stats["counts"]
        lines.append("| " + name + " | " + str(stats["N_registered"]) + " | "
                     + " | ".join(str(counts[k]) for k in
                                  ("completed", "failed", "unknown", "incomplete", "unsupported", "not_run")) + " |")
    lines.extend(["", "## Evidence layers", "", "| Layer | Status |", "| --- | --- |"])
    lines.extend(f"| {name} | {value['status']} |" for name, value in report["evidence_layers"].items())
    lines.extend(["", "Mathematical correctness and improvement remain unverified.",
                  "Independent mathematics, provider-live, natural execution and official scoring: not_run.", ""])
    return "\n".join(lines)
