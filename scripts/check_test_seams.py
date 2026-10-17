"""Reject private implementation seams in public contract tests."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_TESTS = (
    ROOT / "tests" / "test_sse_contract.py",
    ROOT / "tests" / "test_job_control.py",
    ROOT / "tests" / "test_workspace_jobs.py",
)
BANNED_ATTRIBUTES = {"_execute", "store", "start_job", "complete_job", "mark_waiting_input"}


def main() -> int:
    failures: list[str] = []
    for path in CONTRACT_TESTS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in BANNED_ATTRIBUTES:
                failures.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.attr}")
    if failures:
        print("contract_test_private_seam=" + ",".join(failures))
        return 1
    print("contract_test_seams=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
