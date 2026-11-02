"""Tool Registry and experimental subprocess-backed Python math tool."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from contextvars import copy_context
from dataclasses import dataclass
from typing import Any

from .graph import ToolExecutionResult
from .polynomial import PolynomialChecker
from .profile import SHOWCASE_PROFILE
from .redaction import summarize_parameters
from .run_budget import budgeted_tool, current_budget
from .tool_schemas import POLYNOMIAL_CHECK_SCHEMA, PYTHON_MATH_SCHEMA, schema_error

MAX_TOOL_INPUT_BYTES = 32_000
MAX_SUMMARY_CHARS = 1_000
_ALLOWED_MODULES = {"sympy", "mpmath"}
_ALLOWED_BUILTINS = {"abs", "float", "int", "len", "max", "min", "pow", "print", "round", "sum"}
_FORBIDDEN_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "input",
    "open",
}
_FORBIDDEN_ATTRIBUTES = {
    "eval",
    "exec",
    "lambdify",
    "parse_expr",
    "sympify",
}


@dataclass(frozen=True)
class ToolSpec:
    """Public capability and permission metadata for one tool."""

    name: str
    capabilities: tuple[str, ...]
    allowed_profiles: tuple[str, ...]
    timeout_seconds: float
    experimental: bool
    parameters_schema: Mapping[str, Any]


class ToolRegistry:
    """Register and invoke approved tools through one bounded product seam."""

    def __init__(
        self,
        *,
        profile: str = SHOWCASE_PROFILE,
        max_calls: int = 8,
        max_input_bytes: int = MAX_TOOL_INPUT_BYTES,
    ) -> None:
        self.profile = profile
        self.max_calls = max_calls
        self.max_input_bytes = max_input_bytes
        self._handlers: dict[str, tuple[ToolSpec, Callable[[Mapping[str, Any]], Any]]] = {}
        self._call_count = 0

    def register(
        self,
        name: str,
        handler: Callable[[Mapping[str, Any]], Any],
        *,
        capabilities: tuple[str, ...] = (),
        allowed_profiles: tuple[str, ...] = (SHOWCASE_PROFILE,),
        timeout_seconds: float = 3.0,
        experimental: bool = False,
        parameters_schema: Mapping[str, Any] | None = None,
    ) -> ToolSpec:
        """Register a callable and return its observable declaration."""

        if not name or not name.replace("_", "").isalnum():
            raise ValueError("tool_name_invalid")
        if timeout_seconds <= 0:
            raise ValueError("tool_timeout_must_be_positive")
        spec = ToolSpec(
            name=name,
            capabilities=tuple(capabilities),
            allowed_profiles=tuple(allowed_profiles),
            timeout_seconds=float(timeout_seconds),
            experimental=experimental,
            parameters_schema=dict(parameters_schema or {"type": "object"}),
        )
        self._handlers[name] = (spec, handler)
        return spec

    def register_python_math(self, *, timeout_seconds: float = 3.0) -> ToolSpec:
        """Register the experimental PythonMathTool under its stable name."""

        return self.register(
            "python_math",
            PythonMathTool(timeout_seconds=timeout_seconds).invoke,
            capabilities=("calculation", "symbolic_math"),
            timeout_seconds=timeout_seconds,
            experimental=True,
            parameters_schema=PYTHON_MATH_SCHEMA,
        )

    def register_container_python(self, executor) -> ToolSpec:
        """Explicit isolated Python registration; never changes legacy host mode."""
        from .container_tool import ContainerPythonTool
        from .python_executor import DockerPythonExecutor

        if not isinstance(executor, DockerPythonExecutor):
            raise TypeError("container_executor_required")
        self.container_python_executor = executor
        return self.register("python_math", ContainerPythonTool(executor).invoke,
            capabilities=("calculation", "isolated_mathematical_python"),
            timeout_seconds=executor.timeout_seconds, experimental=True,
            parameters_schema=PYTHON_MATH_SCHEMA)

    def register_polynomial_check(self, *, timeout_seconds: float = 3.0) -> ToolSpec:
        """Register the bounded exact polynomial candidate checker."""

        return self.register(
            "polynomial_check",
            PolynomialChecker().check,
            capabilities=("verification", "polynomial_candidates"),
            timeout_seconds=timeout_seconds,
            parameters_schema=POLYNOMIAL_CHECK_SCHEMA,
        )

    def describe(self) -> list[dict[str, Any]]:
        """Return safe capability declarations for the Demo and Agent prompt."""

        return [
            {
                "name": spec.name,
                "capabilities": list(spec.capabilities),
                "allowed_profiles": list(spec.allowed_profiles),
                "timeout_seconds": spec.timeout_seconds,
                "experimental": spec.experimental,
            }
            for spec, _handler in self._handlers.values()
        ]

    def allowed_schemas(self) -> list[dict[str, Any]]:
        """Return argument schemas for registered tools allowed by this Profile."""

        return [
            {
                "name": spec.name,
                "description": ", ".join(spec.capabilities) or spec.name,
                "parameters": json.loads(json.dumps(spec.parameters_schema)),
            }
            for spec, _handler in self._handlers.values()
            if self.profile in spec.allowed_profiles
        ]

    def provider_schemas(self) -> list[dict[str, Any]]:
        """Wrap the authoritative schemas in provider-native function declarations."""

        return [
            {
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"],
                },
            }
            for schema in self.allowed_schemas()
        ]

    @budgeted_tool
    def invoke(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        tool_call_id: str | None = None,
    ) -> ToolExecutionResult:
        """Invoke one registered, permitted tool after checking its schema."""

        started = time.monotonic()
        entry = self._handlers.get(name)
        if entry is None:
            return _result("rejected", "tool_not_registered", started, arguments, tool_call_id)
        spec, handler = entry
        if self.profile not in spec.allowed_profiles:
            return _result("rejected", "tool_not_permitted_for_profile", started, arguments, tool_call_id)
        if not isinstance(arguments, Mapping):
            return _result("rejected", "tool_arguments_must_be_object", started, tool_call_id=tool_call_id)
        try:
            encoded = json.dumps(arguments, ensure_ascii=False, default=str).encode("utf-8")
        except (TypeError, ValueError):
            return _result("rejected", "tool_arguments_not_serializable", started, arguments, tool_call_id)
        if len(encoded) > self.max_input_bytes:
            return _result("rejected", "tool_input_too_large", started, arguments, tool_call_id)
        if schema_error(arguments, spec.parameters_schema):
            return _result("rejected", "tool_schema_invalid", started, arguments, tool_call_id)
        if current_budget() is None and self._call_count >= self.max_calls:
            return _result("rejected", "tool_budget_exhausted", started, arguments, tool_call_id)
        self._call_count += 1
        executor = ThreadPoolExecutor(max_workers=1)
        try:
            if getattr(getattr(handler, "__self__", None), "owns_execution_limits", False):
                value = handler(dict(arguments))
                future = None
            else:
                future = executor.submit(copy_context().run, handler, dict(arguments))
            budget = current_budget()
            timeout = min(spec.timeout_seconds, budget.remaining_seconds()) if budget else spec.timeout_seconds
            if future is not None:
                value = future.result(timeout=timeout)
        except FutureTimeoutError:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return _result("timeout", "tool_timeout", started, arguments, tool_call_id)
        except Exception as exc:  # noqa: BLE001 - tool failures become product data
            executor.shutdown(wait=False, cancel_futures=True)
            return ToolExecutionResult(
                status="error",
                parameter_summary=summarize_parameters(arguments),
                result_summary=type(exc).__name__,
                error_category="tool_execution_error",
                duration_seconds=_duration(started),
                tool_call_id=tool_call_id,
            )
        else:
            executor.shutdown(wait=True)
        if isinstance(value, ToolExecutionResult):
            return ToolExecutionResult(
                status=value.status,
                parameter_summary=value.parameter_summary or summarize_parameters(arguments),
                result_summary=value.result_summary,
                value=value.value,
                error_category=value.error_category,
                duration_seconds=value.duration_seconds or _duration(started),
                tool_call_id=tool_call_id,
            )
        return ToolExecutionResult(
            status="success",
            parameter_summary=summarize_parameters(arguments),
            value=value,
            result_summary=_summary(value),
            duration_seconds=_duration(started),
            tool_call_id=tool_call_id,
        )


class PythonMathTool:
    """Experimental AST-checked math execution in a separate Python process.

    This is a bounded demonstration tool, not a production-grade arbitrary
    code sandbox.  Container or remote isolation remains a later decision.
    """

    def __init__(self, *, timeout_seconds: float = 3.0, max_source_chars: int = 4_000) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_source_chars = max_source_chars

    def invoke(self, arguments: Mapping[str, Any]) -> ToolExecutionResult:
        started = time.monotonic()
        if not isinstance(arguments, Mapping):
            return _result("rejected", "arguments_must_be_object", started)
        source = arguments.get("code", arguments.get("expression"))
        if not isinstance(source, str) or not source.strip():
            return _result("rejected", "code_must_be_non_empty", started, arguments)
        source = source.strip()
        if len(source) > self.max_source_chars:
            return _result("rejected", "code_too_large", started, arguments)
        try:
            _validate_source(source)
        except ValueError as exc:
            return _result("rejected", str(exc), started, arguments)
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", _WORKER_SCRIPT],
                input=source,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _result("timeout", "python_timeout", started, arguments)
        except OSError as exc:
            return ToolExecutionResult(
                status="error",
                parameter_summary=summarize_parameters(arguments),
                result_summary=type(exc).__name__,
                error_category="python_process_error",
                duration_seconds=_duration(started),
            )
        if completed.returncode != 0:
            return ToolExecutionResult(
                status="error",
                parameter_summary=summarize_parameters(arguments),
                result_summary=_summary(completed.stderr),
                error_category="python_execution_error",
                duration_seconds=_duration(started),
            )
        output = completed.stdout.strip()
        return ToolExecutionResult(
            status="success",
            parameter_summary=summarize_parameters(arguments),
            value=output,
            result_summary=_summary(output),
            duration_seconds=_duration(started),
        )


def _validate_source(source: str) -> None:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise ValueError("syntax_error") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name.split(".", 1)[0] for alias in node.names]
            if any(module not in _ALLOWED_MODULES for module in modules):
                raise ValueError("import_not_allowed")
        elif isinstance(node, ast.Name):
            if node.id in _FORBIDDEN_NAMES or node.id.startswith("__"):
                raise ValueError("name_not_allowed")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in _FORBIDDEN_ATTRIBUTES:
                raise ValueError("attribute_not_allowed")
        elif isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Name) and function.id not in _ALLOWED_BUILTINS:
                raise ValueError("call_not_allowed")
            if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                if function.value.id not in {"sp", "sympy", "mp", "mpmath"}:
                    raise ValueError("call_not_allowed")
            elif not isinstance(function, ast.Name):
                raise ValueError("call_not_allowed")
        elif isinstance(node, (ast.With, ast.AsyncWith, ast.Try, ast.FunctionDef, ast.ClassDef,
                               ast.Lambda, ast.Delete, ast.Raise, ast.While, ast.For, ast.AsyncFor)):
            raise ValueError("syntax_not_allowed")


def _result(
    status: str,
    category: str,
    started: float,
    arguments: Mapping[str, Any] | None = None,
    tool_call_id: str | None = None,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        status=status,  # type: ignore[arg-type]
        parameter_summary=summarize_parameters(arguments) if isinstance(arguments, Mapping) else "",
        error_category=category,
        result_summary=category,
        duration_seconds=_duration(started),
        tool_call_id=tool_call_id,
    )


def _duration(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _summary(value: Any) -> str:
    if isinstance(value, Mapping):
        value = {str(name): _summary(item) for name, item in value.items()}
    elif isinstance(value, (list, tuple)):
        value = [_summary(item) for item in value]
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text[:MAX_SUMMARY_CHARS]

_WORKER_SCRIPT = r'''
import builtins
import sys
import sympy as sp
import mpmath as mp

source = sys.stdin.read()
allowed_modules = {"sympy": sp, "mpmath": mp}

def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".", 1)[0]
    if root not in allowed_modules:
        raise ImportError("import_not_allowed")
    return allowed_modules[root]

safe_builtins = {name: getattr(builtins, name) for name in (
    "abs", "float", "int", "len", "max", "min", "pow", "print", "round", "sum"
)}
safe_builtins["__import__"] = safe_import
globals_dict = {"__builtins__": safe_builtins, "sp": sp, "sympy": sp, "mp": mp, "mpmath": mp}
exec(compile(source, "<python_math>", "exec"), globals_dict, {})
'''


__all__ = ["PolynomialChecker", "PythonMathTool", "ToolRegistry", "ToolSpec"]
