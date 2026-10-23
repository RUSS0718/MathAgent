"""Explicit bounded local-tool adapters, including an offline scripted port."""

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Protocol


class ToolPort(Protocol):
    """An adapter must enforce timeout and output limits at its execution boundary."""

    source: str
    registered_tools: frozenset[str]

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ScriptedToolPort:
    """Deterministic fake execution; receipts are always marked scripted."""

    source = "scripted"

    def __init__(self, responses: Sequence[Mapping[str, Any]], *, tools=("polynomial_check",)):
        self.registered_tools = frozenset(tools)
        self._responses = [deepcopy(dict(value)) for value in responses]
        self.requests: list[dict[str, Any]] = []

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        self.requests.append(deepcopy(dict(request)))
        return self._responses.pop(0) if self._responses else {"status": "unknown_outcome"}


class RegistryToolPort:
    """Opt-in adapter to the reviewed product registry, never a shell/eval path."""

    source = "local_precheck"

    def __init__(self, registry):
        self._registry = registry
        self.owns_execution_limits = hasattr(registry, "container_python_executor")
        self.source = "docker_isolated" if self.owns_execution_limits else "local_precheck"
        self.registered_tools = frozenset(
            item["name"]
            for item in registry.describe()
            if item["name"] in {"polynomial_check", "python_math"}
        )

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        # The registry also applies its own tool schema, profile and subprocess limits.
        from ..container_tool import tool_request

        with tool_request(request):
            result = self._registry.invoke(
                request["tool"], request["arguments"], tool_call_id=request["call_id"]
            )
        if request["tool"] == "python_math" and self.owns_execution_limits and isinstance(result.value, Mapping):
            from ..tool_artifacts import ToolArtifactError

            try:
                store = self._registry.container_python_executor.artifacts
                required = ("stdout_ref", "stderr_ref", "receipt_ref")
                if result.value.get("executed"):
                    required = ("code_ref", "input_ref", *required)
                for key in required:
                    store.verify(result.value[key], run_id=request["run_id"], call_id=request["call_id"])
                for key in ("code_ref", "input_ref"):
                    if result.value.get(key) is not None:
                        store.verify(result.value[key], run_id=request["run_id"], call_id=request["call_id"])
            except (KeyError, ToolArtifactError):
                executed = result.value.get("executed") is True
                status = "unknown_outcome" if executed else result.value.get("status")
                if status not in {"unknown_outcome", "unavailable", "rejected"}:
                    status = "tool_error"
                return {"status": status, "exit_code": None, "output": None,
                    "error": "artifact_integrity_failed", "executed": executed,
                    "unknown_outcome": executed}
            return {**result.value, "output": result.value.get("stdout", ""), "error": result.error_category}
        if request["tool"] == "python_math" and self.owns_execution_limits:
            return {"status": "rejected" if result.status == "rejected" else "tool_error",
                "output": None, "exit_code": None, "error": result.error_category, "executed": False}
        status = (
            "success"
            if result.status == "success"
            else "timeout"
            if result.error_category == "timeout"
            else "tool_error"
        )
        return {
            "status": status,
            "output": result.value,
            "exit_code": 0 if result.status == "success" else None,
            "error": result.error_category,
        }
