"""The production executor fails closed before Docker dispatch."""

import json
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


class PythonExecutorContractTest(unittest.TestCase):
    def test_missing_image_cannot_fallback_to_host_python(self):
        from showcase.python_executor import DockerPythonExecutor

        with tempfile.TemporaryDirectory() as root:
            executor = DockerPythonExecutor(image="sha256:" + "0" * 64, artifact_root=root)
            with patch("subprocess.run", side_effect=FileNotFoundError("docker absent")):
                outcome = executor.execute("print(2)", run_id="run_public", call_id="tool_public",
                    input_payload={"code": "print(2)"})
            self.assertEqual("unavailable", outcome["status"])
            self.assertFalse(outcome["executed"])
            self.assertIsNone(outcome["exit_code"])
            store = executor.artifacts
            input_bytes = store.verify(outcome["input_ref"], run_id="run_public", call_id="tool_public")
            self.assertEqual({"code": "print(2)"}, json.loads(input_bytes))
            self.assertEqual(b"", store.verify(outcome["stdout_ref"], run_id="run_public", call_id="tool_public"))
            self.assertEqual(b"", store.verify(outcome["stderr_ref"], run_id="run_public", call_id="tool_public"))
            self.assertEqual("unavailable", json.loads(store.verify(
                outcome["receipt_ref"], run_id="run_public", call_id="tool_public"))["status"])

    def test_oversized_source_is_rejected_without_docker_or_false_artifacts(self):
        from showcase.python_executor import DockerPythonExecutor

        with tempfile.TemporaryDirectory() as root:
            executor = DockerPythonExecutor(image="sha256:" + "0" * 64, artifact_root=root)
            with patch("subprocess.run", side_effect=AssertionError("docker must not start")):
                result = executor.execute("x" * 32001, run_id="run_public", call_id="tool_public",
                    input_payload={"code": "x" * 32001})
            self.assertEqual("rejected", result["status"])
            self.assertFalse(result["executed"])
            self.assertIsNone(result["exit_code"])
            self.assertNotIn("code_ref", result)
            self.assertNotIn("input_ref", result)
            self.assertEqual(b"", executor.artifacts.verify(
                result["stdout_ref"], run_id="run_public", call_id="tool_public"))
            stored = json.loads(executor.artifacts.verify(
                result["receipt_ref"], run_id="run_public", call_id="tool_public"))
            self.assertEqual("rejected", stored["status"])
            self.assertFalse(stored["executed"])

    def test_image_id_and_policy_labels_fail_closed_before_container_create(self):
        from showcase.python_executor import DockerPythonExecutor

        with tempfile.TemporaryDirectory() as root:
            executor = DockerPythonExecutor(image="sha256:" + "1" * 64, artifact_root=root)
            bad_image = {"Id": executor.image, "Config": {"Labels": {"mathagent.python.policy": "wrong"}}}
            with patch.object(executor, "_command", return_value=CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(bad_image), stderr="")) as command:
                result = executor.execute("print(2)", run_id="run_public", call_id="tool_public")
            self.assertEqual("unavailable", result["status"])
            self.assertEqual("python_image_identity_invalid", result["error"])
            self.assertFalse(result["executed"])
            self.assertEqual(1, command.call_count)

    def test_artifact_store_rejects_tampered_content(self):
        from showcase.tool_artifacts import ToolArtifactError, ToolArtifactStore

        with tempfile.TemporaryDirectory() as root:
            store = ToolArtifactStore(root)
            reference = store.put("run_public", "tool_public", "code", b"print(2)")
            (Path(root) / "run_public" / reference["sha256"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ToolArtifactError, "artifact_integrity_failed"):
                store.verify(reference, run_id="run_public", call_id="tool_public")

    def test_pure_reasoning_and_meta_role_cannot_use_python(self):
        from showcase.python_executor import DockerPythonExecutor
        from showcase.solver_harness.tool_ports import RegistryToolPort
        from showcase.solver_harness.tool_precheck import _denial, allowed_tool_ids
        from showcase.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as root:
            registry = ToolRegistry()
            registry.register_container_python(DockerPythonExecutor(
                image="sha256:" + "2" * 64, artifact_root=root))
            port = RegistryToolPort(registry)
            config = {"features": {"local_code_tool": True}, "allowed_tools": ["python_math"]}
            request = {"tool": "python_math", "arguments": {"code": "print(2)"}}
            pure_run = {"reasoning_mode": "reason_noncoding"}
            self.assertEqual("pure_reasoning_denied", _denial(
                pure_run, "run_public", request, config, port))
            self.assertEqual([], allowed_tool_ids({"state": pure_run}, "reasoner", config, port))
            self.assertEqual([], allowed_tool_ids(
                {"state": {"reasoning_mode": "default"}}, "meta", config, port))

    def test_registry_rejection_is_not_reported_as_python_execution(self):
        from showcase.python_executor import DockerPythonExecutor
        from showcase.solver_harness.tool_ports import RegistryToolPort
        from showcase.tools import ToolRegistry

        with tempfile.TemporaryDirectory() as root:
            executor = DockerPythonExecutor(image="sha256:" + "3" * 64, artifact_root=root)
            registry = ToolRegistry(max_input_bytes=4)
            registry.register_container_python(executor)
            port = RegistryToolPort(registry)
            with patch.object(executor, "_command", side_effect=AssertionError("docker must not start")):
                result = port.execute({"run_id": "run_public", "call_id": "tool_public",
                    "tool": "python_math", "arguments": {"code": "print(2)"},
                    "timeout_seconds": 3, "max_output_bytes": 100})
            self.assertEqual("rejected", result["status"])
            self.assertFalse(result["executed"])


if __name__ == "__main__":
    unittest.main()
