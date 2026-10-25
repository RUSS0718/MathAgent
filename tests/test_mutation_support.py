"""The mutation verdict must reject a probe that crashes instead of failing."""

import unittest

from tests.mutation_support import require_assertion_failure, run_case


class ProbeVerdictTest(unittest.TestCase):
    def test_a_creash_in_the_patched_callable_is_not_a_detected_bypass(self):
        class Crashing(unittest.TestCase):
            def test_never_reaches_the_invariant(self):
                raise TypeError("build_entries() takes 2 positional arguments but 3 were given")

        result = run_case(Crashing("test_never_reaches_the_invariant"))
        with self.assertRaisesRegex(AssertionError, "probe crashed instead of failing"):
            require_assertion_failure(result, "simulated probe bug")

    def test_a_failing_assertion_counts_as_a_detected_bypass(self):
        class Failing(unittest.TestCase):
            def test_invariant_holds(self):
                self.assertEqual("proven", "unproven")

        result = run_case(Failing("test_invariant_holds"))
        self.assertEqual(1, require_assertion_failure(result, "simulated real bypass"))

    def test_a_passing_test_means_the_bypass_was_not_detected(self):
        class Passing(unittest.TestCase):
            def test_invariant_holds(self):
                self.assertTrue(True)

        result = run_case(Passing("test_invariant_holds"))
        with self.assertRaisesRegex(AssertionError, "was not detected"):
            require_assertion_failure(result, "simulated undetected bypass")


if __name__ == "__main__":
    unittest.main()
