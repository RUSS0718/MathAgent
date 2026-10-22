"""Run the credential-free V0.1 Showcase release gate."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / "docs" / "replay" / "showcase-replay-v0.1.json"
EVIDENCE_JSON = ROOT / "docs" / "evals" / "v0.2-release-evidence.json"
EVIDENCE_MD = ROOT / "docs" / "evals" / "v0.2-release-evidence.md"
BASELINE = ROOT / "BASELINE.json"
sys.path.insert(0, str(ROOT))

from showcase.redaction import sensitive_markers  # noqa: E402


def check_baseline() -> None:
    """Verify the frozen official runtime and its import boundary."""

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    for name, expected in baseline["files"].items():
        path = ROOT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"baseline_mismatch:{name}")
    probe = subprocess.run(
        [sys.executable, "-c", "import sys; import user_agent; print('showcase' in sys.modules)"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode or probe.stdout.strip() != "False":
        raise RuntimeError("official_import_boundary_failed")


def check_release_evidence() -> None:
    """Require a dated, machine-readable P0 decision with honest limits."""

    if not EVIDENCE_MD.is_file() or not EVIDENCE_JSON.is_file():
        raise RuntimeError("release_evidence_missing")
    payload = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))
    source_commit = payload.get("source_commit")
    if not isinstance(source_commit, str) or not source_commit:
        raise RuntimeError("release_source_commit_missing")
    resolved = subprocess.run(
        ["git", "cat-file", "-e", f"{source_commit}^{{commit}}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if resolved.returncode:
        raise RuntimeError("release_source_commit_unknown")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if ancestor.returncode:
        raise RuntimeError("release_source_commit_not_ancestor")
    if payload.get("release_status") not in {"engineering-preview", "unavailable"}:
        raise RuntimeError("release_status_overstated")
    required_labels = {"live", "fake", "replay", "experimental", "unavailable", "planned"}
    if not required_labels.issubset(set(payload.get("labels", []))):
        raise RuntimeError("release_labels_incomplete")
    acceptance = payload.get("acceptance", {})
    required = {f"AC-{number:02d}" for number in (*range(1, 7), *range(7, 12))}
    if set(acceptance) != required:
        raise RuntimeError("acceptance_matrix_incomplete")
    if acceptance["AC-06"].get("status") not in {"unavailable", "blocked"}:
        raise RuntimeError("ac06_status_overstated")
    math_eval = payload.get("math_effect_evaluation", {})
    if math_eval.get("status") not in {"planned", "unavailable"}:
        raise RuntimeError("math_evaluation_status_overstated")


def main() -> int:
    checks = [
        [sys.executable, "scripts/check_workspace.py", "--offline"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        [sys.executable, "demo_server.py", "--help"],
        [sys.executable, "showcase_server.py", "--help"],
        [sys.executable, "scripts/check_solver_release.py"],
    ]
    for command in checks:
        environment = os.environ.copy()
        if command[1:4] == ["-m", "unittest", "discover"]:
            environment["SHOWCASE_RELEASE_GATE"] = "1"
        completed = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, check=False, env=environment
        )
        if completed.returncode != 0:
            print(f"showcase_release=FAIL command={' '.join(command)}")
            print(completed.stdout)
            print(completed.stderr)
            return completed.returncode or 1
    try:
        check_baseline()
        check_release_evidence()
    except (OSError, UnicodeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"showcase_release=FAIL contract={exc}")
        return 1
    try:
        payload = json.loads(REPLAY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"showcase_release=FAIL replay={type(exc).__name__}")
        return 1
    markers = sensitive_markers(payload)
    if markers:
        print(f"showcase_release=FAIL sensitive_marker={markers[0]}")
        return 1
    if payload.get("run_mode") != "replay":
        print("showcase_release=FAIL replay_mode_missing")
        return 1
    print("showcase_release=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
