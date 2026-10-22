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
        self.registered_tools = frozenset(
            item["name"]
            for item in registry.describe()
            if item["name"] in {"polynomial_check", "python_math"}
        )

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        # The registry also applies its own tool schema, profile and subprocess limits.
        result = self._registry.invoke(
            request["tool"], request["arguments"], tool_call_id=request["call_id"]
        )
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
