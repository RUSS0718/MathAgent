"""Release reports expose skipped tests and enforce the Reference evidence gate."""

import io
import tempfile
import unittest
from pathlib import Path

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


def _flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item
