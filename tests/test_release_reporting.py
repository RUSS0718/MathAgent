"""Release reports expose skipped tests and enforce the Reference evidence gate."""

import io
import tempfile
import unittest
from pathlib import Path

from scripts.run_unittest_report import discover_suite, run_suite


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
