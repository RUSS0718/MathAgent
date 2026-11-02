"""Release reports expose skipped tests and enforce the Reference evidence gate."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_showcase_release, run_unittest_report
from scripts.run_unittest_report import REFERENCE_TESTS, discover_suite, run_suite


class ReleaseReportingTest(unittest.TestCase):
    def test_discovers_tests_in_directory_without_package_initializer(self):
        with tempfile.TemporaryDirectory() as directory:
            tests_dir = Path(directory) / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_standalone.py").write_text(
                "import unittest\nclass Case(unittest.TestCase):\n"
                "    def test_ok(self): pass\n",
                encoding="utf-8",
            )
            result = run_suite(discover_suite(tests_dir), stream=io.StringIO())
        self.assertEqual(1, result.testsRun)
        self.assertTrue(result.wasSuccessful())

    def test_skips_include_test_identity_and_reason(self):
        class Skipped(unittest.TestCase):
            @unittest.skip("image missing")
            def test_reference(self):
                pass

        stream = io.StringIO()
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Skipped)
        result = run_suite(suite, stream=stream)
        self.assertTrue(result.wasSuccessful())
        self.assertIn("test_reference", stream.getvalue())
        self.assertIn("image missing", stream.getvalue())

    def test_required_reference_skips_and_missing_tests_fail(self):
        class Skipped(unittest.TestCase):
            @unittest.skip("image missing")
            def test_reference(self):
                pass

        test = Skipped("test_reference")
        result = run_suite(unittest.TestSuite([test]), stream=io.StringIO(), required={test.id()})
        self.assertFalse(result.wasSuccessful())
        result = run_suite(unittest.TestSuite(), stream=io.StringIO(), required={test.id()})
        self.assertFalse(result.wasSuccessful())

    def test_required_reference_passes_when_executed(self):
        class Passed(unittest.TestCase):
            def test_reference(self):
                pass

        test = Passed("test_reference")
        result = run_suite(unittest.TestSuite([test]), stream=io.StringIO(), required={test.id()})
        self.assertTrue(result.wasSuccessful())

    def test_required_reference_expected_failure_is_not_coverage(self):
        class ExpectedFailure(unittest.TestCase):
            @unittest.expectedFailure
            def test_reference(self):
                self.fail("unavailable")

        test = ExpectedFailure("test_reference")
        result = run_suite(unittest.TestSuite([test]), stream=io.StringIO(), required={test.id()})
        self.assertFalse(result.wasSuccessful())

    def test_reference_markers_use_package_qualified_unittest_ids(self):
        expected = {
            "tests.test_star_product_full_modes.StarFullModeTest.test_reference_easy_problem_completes_fastpath_review_and_binding",
            "tests.test_star_product_full_modes.StarFullModeTest.test_reference_runs_same_public_job_with_real_tool_and_whole_review",
            "tests.test_star_rb06_recovery.RobustRecoveryTest.test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding",
        }
        self.assertEqual(expected, REFERENCE_TESTS)
        selected = unittest.defaultTestLoader.loadTestsFromName(
            "tests.test_release_reporting.ReleaseReportingTest.test_required_reference_passes_when_executed"
        )
        test = next(iter(selected))
        result = run_suite(unittest.TestSuite([test]), stream=io.StringIO(), required={test.id()})
        self.assertTrue(result.wasSuccessful())

    def test_reference_coverage_matches_explicit_and_discovered_loader_ids(self):
        marker = next(iter(REFERENCE_TESTS))
        explicit = unittest.defaultTestLoader.loadTestsFromName(marker)
        explicit_ids = {test.id() for test in _flatten(explicit)}
        self.assertIn(marker, explicit_ids)

        discovered = discover_suite(Path("tests"))
        discovered_ids = {test.id() for test in _flatten(discovered)}
        self.assertIn(marker.removeprefix("tests."), discovered_ids)

        class Passed(unittest.TestCase):
            def test_reference(self):
                pass

        Passed.__module__ = "test_reference_identity"
        test = Passed("test_reference")
        result = run_suite(
            unittest.TestSuite([test]),
            stream=io.StringIO(),
            required={"tests." + test.id()},
        )
        self.assertTrue(result.wasSuccessful())

    def test_strict_release_command_is_parseable_by_report_cli(self):
        completed = unittest.mock.Mock(returncode=0, stdout="", stderr="")
        commands = []

        def fake_run(command, **_kwargs):
            commands.append(command)
            return completed

        with (
            patch.object(check_showcase_release.subprocess, "run", side_effect=fake_run),
            patch.object(check_showcase_release, "check_baseline"),
            patch.object(check_showcase_release, "check_release_evidence"),
            patch("sys.argv", ["check_showcase_release.py", "--require-reference"]),
        ):
            self.assertEqual(0, check_showcase_release.main())

        command = next(
            command for command in commands if "scripts/run_unittest_report.py" in command
        )
        with (
            patch.object(run_unittest_report.unittest.defaultTestLoader,
                         "loadTestsFromNames", return_value=unittest.TestSuite()) as load,
            patch.object(run_unittest_report, "run_suite") as run_suite_mock,
            patch.object(run_unittest_report, "sys", sys),
            patch.object(sys, "argv", command[1:]),
        ):
            run_suite_mock.return_value.wasSuccessful.return_value = True
            self.assertEqual(0, run_unittest_report.main())
        load.assert_called_once_with(command[3:])

    def test_cli_captures_python_and_child_output_with_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module_path = root / "test_reporting_fixture.py"
            module_path.write_text(
                "import subprocess, sys, unittest\n"
                "class Sample(unittest.TestCase):\n"
                "    def test_pass(self):\n"
                "        print('sample-python-stdout')\n"
                "        print('sample-python-stderr', file=sys.stderr)\n"
                "        subprocess.run([sys.executable, '-c', \"import sys; "
                "print('sample-child-stdout 中文子进程'); "
                "print('sample-child-stderr', file=sys.stderr)\"], check=True)\n"
                "    @unittest.skip('optional dependency missing')\n"
                "    def test_skip(self): pass\n"
                "    @unittest.expectedFailure\n"
                "    def test_expected_failure(self): self.fail('known limitation')\n",
                encoding="utf-8",
            )
            summary_path = root / "nested" / "reports" / "summary.json"
            diagnostics_path = root / "nested" / "reports" / "diagnostics.log"
            completed = _run_report_cli(
                module_path,
                "--summary-json",
                str(summary_path),
                "--diagnostics",
                str(diagnostics_path),
                "test_reporting_fixture",
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            diagnostics = diagnostics_path.read_text(encoding="utf-8")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(
            {
                "testsRun": 3,
                "skipped": 1,
                "failures": 0,
                "errors": 0,
                "expectedFailures": 1,
                "unexpectedSuccesses": 0,
                "status": "passed",
            },
            {
                key: summary[key]
                for key in (
                    "testsRun",
                    "skipped",
                    "failures",
                    "errors",
                    "expectedFailures",
                    "unexpectedSuccesses",
                    "status",
                )
            },
        )
        self.assertIsInstance(summary["elapsed"], float)
        self.assertGreater(summary["pid"], 0)
        self.assertTrue(summary["start_time"])
        self.assertNotIn("expected_failures", summary)
        self.assertGreater(summary["diagnostic_lines"], 0)
        self.assertIn("sample-python-stdout", diagnostics)
        self.assertIn("sample-python-stderr", diagnostics)
        self.assertIn("sample-child-stdout", diagnostics)
        self.assertIn("中文子进程", diagnostics)
        self.assertIn("sample-child-stderr", diagnostics)
        self.assertIn("SKIP ", diagnostics)
        self.assertIn("EXPECTED_FAILURE", diagnostics)
        self.assertIn(str(summary_path), completed.stderr)
        self.assertIn(str(diagnostics_path), completed.stderr)
        self.assertNotIn("sample-child-stdout", completed.stdout + completed.stderr)

    def test_cli_diagnostics_alone_keeps_failure_and_unknown_child_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module_path = root / "test_reporting_failure_fixture.py"
            module_path.write_text(
                "import subprocess, sys, unittest\n"
                "class Failing(unittest.TestCase):\n"
                "    def test_failure(self):\n"
                "        print('failure-python-stdout')\n"
                "        print('unknown-python-diagnostic', file=sys.stderr)\n"
                "        subprocess.run([sys.executable, '-c', \"import sys; "
                "print('failure-child-stdout'); "
                "print('unknown-child-diagnostic', file=sys.stderr)\"], check=True)\n"
                "        self.fail('intentional failure')\n",
                encoding="utf-8",
            )
            diagnostics_path = root / "nested" / "diagnostics.log"
            completed = _run_report_cli(
                module_path,
                "--diagnostics",
                str(diagnostics_path),
                "test_reporting_failure_fixture",
            )
            diagnostics = diagnostics_path.read_text(encoding="utf-8")

        self.assertEqual(1, completed.returncode)
        self.assertIn("FAILED", completed.stderr)
        self.assertIn("intentional failure", completed.stderr)
        self.assertIn("Traceback", completed.stderr)
        self.assertIn(str(diagnostics_path), completed.stderr)
        self.assertIn("failure-python-stdout", diagnostics)
        self.assertIn("unknown-python-diagnostic", diagnostics)
        self.assertIn("failure-child-stdout", diagnostics)
        self.assertIn("unknown-child-diagnostic", diagnostics)
        self.assertIn("intentional failure", diagnostics)
        expected_section = diagnostics.split("=== expected diagnostics ===", 1)[1].split(
            "=== observed diagnostics ===", 1
        )[0]
        self.assertNotIn("unknown-python-diagnostic", expected_section)
        self.assertNotIn("unknown-child-diagnostic", expected_section)


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def _run_report_cli(module_path, *arguments):
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp936"
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(module_path.parent), existing_pythonpath) if part
    )
    return subprocess.run(
        [
            sys.executable,
            str(Path(run_unittest_report.__file__).resolve()),
            *arguments,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        check=False,
    )
