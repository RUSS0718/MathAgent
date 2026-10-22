"""Credential-free Solver v1.2 evidence and release decision gate."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/evals/showcase-solver-v1.2-matrix.json"
sys.path.insert(0, str(ROOT))


def test_ids():
    found = set()
    for path in (ROOT / "tests").glob("test_*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8-sig")).body:
            if isinstance(node, ast.ClassDef):
                found.update(
                    f"tests.{path.stem}.{node.name}.{method.name}"
                    for method in node.body
                    if isinstance(method, ast.FunctionDef) and method.name.startswith("test_")
                )
    return found


def check_matrix(payload):
    available = test_ids()
    for key, prefix, count in (("star_ac", "AC", 44), ("sc", "SC", 43)):
        expected = {
            f"{prefix}-{number:0{2 if prefix == 'AC' else 3}}" for number in range(1, count + 1)
        }
        if set(payload.get(key, {})) != expected:
            raise ValueError(f"matrix_coverage:{key}")
        for identity, record in payload[key].items():
            owner = record.get("owner", "")
            if not re.fullmatch(r"SH-\d{2}", owner) or record.get("issue") != 32 + int(owner[3:]):
                raise ValueError(f"matrix_owner:{identity}")
            if record.get("status") not in {"covered", "needs_review", "unavailable"}:
                raise ValueError(f"matrix_status:{identity}")
            if record.get("evidence_mode") not in {"scripted", "replay", "live", "unavailable"}:
                raise ValueError(f"matrix_evidence_mode:{identity}")
            if not record.get("tests") or any(test not in available for test in record["tests"]):
                raise ValueError(f"matrix_test_missing:{identity}")
    live = payload.get("live_gate", {})
    if (
        live.get("status") != "needs_review"
        or live.get("legacy_v02_ac06") != "unavailable"
        or live.get("tool_calls") != 0
    ):
        raise ValueError("live_evidence_overstated")
    print("acceptance_matrix=PASS ac=44 sc=43")


def check_doc_links():
    # Local Markdown links only; web links are source references, never network probes.
    paths = [
        ROOT / "docs/README.md",
        *[
            ROOT / name
            for name in (
                "docs/evals/showcase-solver-v1.2-release.md",
                "docs/evals/showcase-solver-intern-live-sh21.md",
                "docs/evals/showcase-solver-paired-report-sh22.md",
                "docs/evals/showcase-solver-result-replay-sh20.md",
            )
        ],
    ]
    for path in paths:
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = unquote(target.split("#", 1)[0].strip("<>"))
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            if not (path.parent / target).exists():
                raise ValueError(f"documentation_link_missing:{path.name}:{target}")
    print("solver_document_links=PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix-only", action="store_true")
    parser.add_argument("--require-live", action="store_true")
    args = parser.parse_args()
    try:
        payload = json.loads(MATRIX.read_text(encoding="utf-8"))
        check_matrix(payload)
        if args.matrix_only:
            return 0
        check_doc_links()
        from scripts.check_showcase_release import check_baseline

        check_baseline()
        print(
            "official_baseline=PASS sha256="
            + hashlib.sha256((ROOT / "BASELINE.json").read_bytes()).hexdigest()
        )
        if args.require_live:
            print("live_release=BLOCKED status=needs_review legacy_v02_ac06=unavailable tools=0")
            return 1
        pending = [
            identity
            for group in ("star_ac", "sc")
            for identity, record in payload[group].items()
            if record["status"] != "covered" and identity != "SC-019"
        ]
        if pending:
            print("solver_engineering_release=BLOCKED pending=" + ",".join(pending))
            return 1
        selected = sorted({test for group in ("star_ac", "sc") for record in payload[group].values() for test in record["tests"]})
        result = subprocess.run([sys.executable, "-m", "unittest", *selected], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            print(result.stdout)
            print(result.stderr)
            print("solver_engineering_release=FAIL mapped_tests")
            return 1
        print(f"mapped_acceptance_tests=PASS count={len(selected)}")
        print("solver_engineering_release=PASS live_release=BLOCKED status=engineering-preview")
        return 0
    except (OSError, ValueError, KeyError) as exc:
        print(f"solver_release=FAIL contract={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
