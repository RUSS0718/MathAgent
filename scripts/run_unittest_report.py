"""Run the full or explicitly selected unittest suite and report skipped tests."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REFERENCE_TESTS = {
    "tests.test_star_product_full_modes.StarFullModeTest."
    "test_reference_easy_problem_completes_fastpath_review_and_binding",
    "tests.test_star_product_full_modes.StarFullModeTest."
    "test_reference_runs_same_public_job_with_real_tool_and_whole_review",
    "tests.test_star_rb06_recovery.RobustRecoveryTest."
    "test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding",
}


def _canonical_test_id(test_id):
    return test_id[6:] if test_id.startswith("tests.") else test_id


def run_suite(suite, *, stream, required=frozenset()):
    """Require selected tests to be discovered and not skipped when requested."""

    class ReportingResult(unittest.TextTestResult):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.started = set()

        def startTest(self, test):
            self.started.add(test.id())
            super().startTest(test)

        def addSkip(self, test, reason):
            super().addSkip(test, reason)
            self.stream.writeln(f"\nSKIP {test.id()}: {reason}")

        def stopTestRun(self):
            started = {_canonical_test_id(test_id) for test_id in self.started}
            skipped = {_canonical_test_id(test.id()) for test, _ in self.skipped}
            expected_failures = {_canonical_test_id(test.id()) for test, _ in self.expectedFailures}
            required_ids = {_canonical_test_id(test_id) for test_id in required}
            missing = required_ids - started
            uncovered = missing | (required_ids & (skipped | expected_failures))
            if uncovered:
                marker = unittest.FunctionTestCase(lambda: None, description="Reference evidence")
                self.errors.append((marker, "Not covered: " + ", ".join(sorted(uncovered))))
            super().stopTestRun()

    return unittest.TextTestRunner(stream=stream, resultclass=ReportingResult).run(suite)


def discover_suite(tests_dir):
    """Discover the repository's non-package test directory."""
    return unittest.TestLoader().discover(str(tests_dir), pattern="test_*.py")


def _atomic_write(path, content):
    """Write text through a same-directory temporary file and replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _records(records):
    return [{"test": test.id(), "traceback": traceback} for test, traceback in records]


def _result_payload(result, *, elapsed, start_time):
    return {
        "testsRun": result.testsRun,
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "failures": _records(result.failures),
        "errors": _records(result.errors),
        "expectedFailures": _records(result.expectedFailures),
        "unexpectedSuccesses": [test.id() for test in result.unexpectedSuccesses],
        "elapsed": elapsed,
        "status": "passed" if result.wasSuccessful() else "failed",
        "pid": os.getpid(),
        "start_time": start_time,
    }


def _expected_diagnostics(result):
    lines = []
    for item in result["skipped"]:
        lines.append(f"SKIP {item['test']}: {item['reason']}")
    for item in result["expectedFailures"]:
        lines.append(f"EXPECTED_FAILURE {item['test']}:")
        lines.extend(item["traceback"].rstrip().splitlines())
    return lines


def _observed_diagnostics(result):
    lines = []
    for label in ("FAILURE", "ERROR"):
        for item in result[label.lower() + "s"]:
            lines.append(f"{label} {item['test']}:")
            lines.extend(item["traceback"].rstrip().splitlines())
    for test in result["unexpectedSuccesses"]:
        lines.append(f"UNEXPECTED_SUCCESS {test}")
    return lines


def _diagnostics_text(result, worker_output):
    sections = [
        ("worker stdout and stderr", worker_output),
        ("expected diagnostics", "\n".join(_expected_diagnostics(result))),
        ("observed diagnostics", "\n".join(_observed_diagnostics(result))),
    ]
    return "\n".join(f"=== {name} ===\n{content.rstrip()}" for name, content in sections) + "\n"


def _summary(result, *, diagnostic_lines):
    return {
        "testsRun": result["testsRun"],
        "skipped": len(result["skipped"]),
        "failures": len(result["failures"]),
        "errors": len(result["errors"]),
        "expectedFailures": len(result["expectedFailures"]),
        "unexpectedSuccesses": len(result["unexpectedSuccesses"]),
        "elapsed": result["elapsed"],
        "status": result["status"],
        "pid": result["pid"],
        "start_time": result["start_time"],
        "diagnostic_lines": diagnostic_lines,
    }


def _load_suite(test_names, *, loader=None):
    loader = loader or unittest.defaultTestLoader
    return loader.loadTestsFromNames(test_names) if test_names else discover_suite(ROOT / "tests")


def _append_problem(problem, detail):
    return "\n".join(part for part in (problem, detail) if part)


def _selection_error(suite, *, test_names, load_errors=(), expected_count=None, problem=None):
    """Reject broken or incomplete explicit test selections before running them."""
    if load_errors:
        problem = _append_problem(
            problem, "could not load selected tests:\n" + "\n".join(load_errors)
        )
    actual_count = suite.countTestCases()
    if test_names and actual_count == 0:
        problem = _append_problem(problem, "selected tests contain no runnable test cases")
    if expected_count is not None and actual_count != expected_count:
        detail = f"expected {expected_count} test cases, loaded {actual_count}"
        problem = _append_problem(problem, detail)
    return problem


def _load_selected_suite(test_names):
    loader = unittest.defaultTestLoader
    loader.errors.clear()
    suite = _load_suite(test_names, loader=loader)
    return suite, _selection_error(suite, test_names=test_names, load_errors=loader.errors)


def _run_worker(args, suite):
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    result = run_suite(
        suite,
        stream=sys.stderr,
        required=REFERENCE_TESTS if args.require_reference else frozenset(),
    )
    payload = _result_payload(result, elapsed=time.perf_counter() - started, start_time=started_at)
    _atomic_write(
        args._worker_result_json,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return 0 if result.wasSuccessful() else 1


def _run_supervised(args):
    args.diagnostics.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="unittest-report-") as directory:
        directory = Path(directory)
        output_path = directory / "worker-output.log"
        result_path = directory / "worker-result.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--_worker-result-json",
            str(result_path),
        ]
        if args.require_reference:
            command.append("--require-reference")
        if args.expect_count is not None:
            command.extend(["--expect-count", str(args.expect_count)])
        command.extend(args.test_names)
        with output_path.open("wb") as output:
            completed = subprocess.run(
                command,
                stdout=output,
                stderr=subprocess.STDOUT,
                check=False,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
        worker_output = output_path.read_text(encoding="utf-8", errors="replace")
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            result = {
                "testsRun": 0,
                "skipped": [],
                "failures": [],
                "errors": [
                    {
                        "test": "unittest report worker",
                        "traceback": f"Worker exited with status {completed.returncode}",
                    }
                ],
                "expectedFailures": [],
                "unexpectedSuccesses": [],
                "elapsed": 0.0,
                "status": "failed",
                "pid": None,
                "start_time": datetime.now(UTC).isoformat(),
            }
        diagnostics = _diagnostics_text(result, worker_output)
        _atomic_write(args.diagnostics, diagnostics)
    if args.summary_json:
        summary = _summary(result, diagnostic_lines=len(diagnostics.splitlines()))
        _atomic_write(
            args.summary_json,
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    _print_result(result, sys.stderr)
    if args.summary_json:
        print(f"summary_json={args.summary_json}", file=sys.stderr)
    print(f"diagnostics={args.diagnostics}", file=sys.stderr)
    return completed.returncode or (0 if result["status"] == "passed" else 1)


def _print_result(result, stream):
    print(f"Ran {result['testsRun']} tests in {result['elapsed']:.3f}s", file=stream)
    if result["status"] == "passed":
        details = []
        if result["skipped"]:
            details.append(f"skipped={len(result['skipped'])}")
        if result["expectedFailures"]:
            details.append(f"expected failures={len(result['expectedFailures'])}")
        suffix = f" ({', '.join(details)})" if details else ""
        print(f"OK{suffix}", file=stream)
        return
    for label in ("failures", "errors"):
        for item in result[label]:
            print(f"{label[:-1].upper()}: {item['test']}", file=stream)
            print(item["traceback"].rstrip(), file=stream)
    print(
        f"FAILED (failures={len(result['failures'])}, errors={len(result['errors'])})",
        file=stream,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-reference", action="store_true")
    parser.add_argument("--expect-count", type=int)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--diagnostics", type=Path)
    parser.add_argument("--_worker-result-json", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("test_names", nargs="*")
    args = parser.parse_args()
    if args.expect_count is not None and args.expect_count < 1:
        print("test_selection=INVALID expected count must be positive", file=sys.stderr)
        return 2
    if args.expect_count is not None and not args.test_names:
        print("test_selection=INVALID --expect-count requires explicit test names", file=sys.stderr)
        return 2
    if args.diagnostics:
        return _run_supervised(args)

    suite = None
    problem = None
    if args.test_names:
        suite, problem = _load_selected_suite(args.test_names)
        if args.expect_count is not None:
            problem = _selection_error(
                suite,
                test_names=args.test_names,
                expected_count=args.expect_count,
                problem=problem,
            )
        if problem:
            print(f"test_selection=INVALID\n{problem}", file=sys.stderr)
            return 2
    if args._worker_result_json:
        return _run_worker(args, suite if suite is not None else _load_suite([]))
    suite = suite if suite is not None else _load_suite([])
    required = REFERENCE_TESTS if args.require_reference else frozenset()
    terminal_stream = sys.stderr
    started_at = datetime.now(UTC).isoformat()
    started = time.perf_counter()
    result = run_suite(suite, stream=terminal_stream, required=required)
    elapsed = time.perf_counter() - started

    if args.summary_json:
        payload = _result_payload(result, elapsed=elapsed, start_time=started_at)
        summary = _summary(payload, diagnostic_lines=0)
        _atomic_write(
            args.summary_json,
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
    if args.summary_json:
        print(f"summary_json={args.summary_json}", file=terminal_stream)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
