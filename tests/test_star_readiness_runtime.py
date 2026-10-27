"""Runtime cleanup must keep late-settlement work alive until it is safe."""

import tempfile
import unittest
from unittest.mock import patch

from showcase.star_readiness_runtime import cleanup_runtime_storage


class StarReadinessRuntimeCleanupTest(unittest.TestCase):
    def test_deferred_cleanup_thread_keeps_process_alive_for_late_settlement(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = tempfile.TemporaryDirectory(dir=directory)
            self.addCleanup(storage.cleanup)
            with (
                patch("showcase.star_readiness_runtime._has_unresolved_attempts", return_value=True),
                patch("showcase.star_readiness_runtime.threading.Thread") as thread,
            ):
                self.assertEqual(
                    "deferred",
                    cleanup_runtime_storage(storage, ["run-1"], grace_seconds=2),
                )

            self.assertFalse(thread.call_args.kwargs["daemon"])


if __name__ == "__main__":
    unittest.main()
