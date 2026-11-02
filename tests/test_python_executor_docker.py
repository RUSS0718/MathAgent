"""Opt-in real Docker failures at the production executor seam, never host Python."""

import json
import os
import subprocess
import tempfile
import unittest
from threading import Event

from showcase.python_executor import DockerPythonExecutor

IMAGE = os.environ.get("MATHAGENT_TEST_PYTHON_IMAGE")


@unittest.skipUnless(IMAGE, "set MATHAGENT_TEST_PYTHON_IMAGE to a validated local exact image ID")
class DockerExecutorTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.executor = DockerPythonExecutor(image=IMAGE, artifact_root=folder.name,
            timeout_seconds=3, max_output_bytes=8192)

    def execute(self, code):
        result = self.executor.execute(code, run_id="run_docker", call_id="actual_tool",
            input_payload={"code": code})
        self.assertTrue(result["executed"], result)
        self.assertTrue(result["cleanup_verified"], result)
        self.assertLessEqual(result["retained_output_bytes"], 8192)
        containers = subprocess.run(["docker", "ps", "-a", "-q", "--filter",
            "label=mathagent.run_id=run_docker"], capture_output=True, text=True, timeout=5, check=False)
        self.assertEqual(0, containers.returncode, containers.stderr)
        self.assertEqual("", containers.stdout.strip())
        return result

    def test_fixed_mathematical_environment_actually_executes(self):
        result = self.execute("import sympy,numpy,mpmath; print(sympy.__version__,numpy.__version__,mpmath.__version__); print(sympy.factorint(360))")
        self.assertEqual("success", result["status"])
        self.assertIn("1.14.0 2.3.4 1.3.0", result["stdout"])
        self.assertIn("{2: 3, 3: 2, 5: 1}", result["stdout"])
        self.assertEqual("3.11.17", result["environment"]["python"])
        self.assertEqual("b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377",
            result["environment"]["base_sha256"])
        input_bytes = self.executor.artifacts.verify(
            result["input_ref"], run_id="run_docker", call_id="actual_tool")
        self.assertEqual({"code": "import sympy,numpy,mpmath; print(sympy.__version__,numpy.__version__,mpmath.__version__); print(sympy.factorint(360))"},
            json.loads(input_bytes))

    def test_external_guard_catches_direct_fd_and_combined_streams(self):
        for code in (
            "import os; os.write(1,b'B'*16384)",
            "import os; os.dup2(1,10); os.write(10,b'B'*16384)",
            "import os; os.write(1,b'A'*5000); os.write(2,b'B'*5000)",
            "import os; f=os.open('/proc/1/fd/1',os.O_WRONLY); os.write(f,b'B'*16384)",
            "import os; os.write(1,b'\\xff'*16384)",
            "import os\nwhile True: os.write(1,b'B'*4096)",
        ):
            with self.subTest(code=code):
                result = self.execute(code)
                self.assertEqual("output_limit", result["status"], result)
                self.assertGreater(result["observed_output_bytes"], 8192)

    def test_container_restrictions_have_actual_failure_examples(self):
        for code in (
            "open('/denied','w').write('x')",
            "open('/host/sp01-canary').read()",
            "open('/other-task/sp01-canary').read()",
            "import socket; socket.create_connection(('1.1.1.1',443),.2)",
            "x=bytearray(512*1024*1024)",
            "import subprocess; p=[subprocess.Popen(['sleep','10']) for _ in range(50)]",
        ):
            with self.subTest(code=code):
                result = self.execute(code)
                self.assertNotEqual("success", result["status"], result)
                self.assertNotEqual(0, result["exit_code"])

    def test_timeout_kills_container_with_descendant(self):
        self.executor.timeout_seconds = 8
        result = self.execute("import subprocess,time; subprocess.Popen(['sleep','60']); time.sleep(60)")
        self.assertEqual("timeout", result["status"])
        self.assertNotEqual(0, result["exit_code"])
        self.assertTrue(result["timeout"])
        self.assertFalse(result["unknown_outcome"])

    def test_cpu_limit_terminates_a_busy_loop(self):
        self.executor.timeout_seconds = 8
        result = self.execute("while True: pass")
        self.assertNotEqual("success", result["status"])
        self.assertNotEqual(0, result["exit_code"])
        self.assertLess(result["duration_seconds"], 8)

    def test_cancellation_kills_a_sleeping_container(self):
        cancelled = Event()

        def is_cancelled():
            if cancelled.is_set():
                return True
            cancelled.set()
            return False

        result = self.executor.execute("import time; time.sleep(60)", run_id="run_docker",
            call_id="actual_tool", input_payload={"code": "import time; time.sleep(60)"},
            canceled=is_cancelled)
        self.assertTrue(result["executed"])
        self.assertEqual("canceled", result["status"])
        self.assertTrue(result["cleanup_verified"])
        self.assertFalse(result["unknown_outcome"])


if __name__ == "__main__":
    unittest.main()
