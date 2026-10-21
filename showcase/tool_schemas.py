"""Single source for registered tool argument schemas and offline validation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_RATIONAL = r"-?(?:0|[1-9][0-9]*)(?:/(?:[1-9][0-9]*))?"

POLYNOMIAL_CHECK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "schema_version": {"const": 1, "type": "integer"},
        "variable": {"type": "string", "pattern": r"[A-Za-z_][A-Za-z0-9_]*"},
        "coefficients": {
            "type": "array",
            "minItems": 2,
            "maxItems": 5,
            "items": {"type": "string", "pattern": _RATIONAL},
        },
        "domain": {
            "type": "object",
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"kind": {"const": "real"}},
                    "required": ["kind"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "kind": {"const": "interval"},
                        "left": {"type": "string", "pattern": _RATIONAL},
                        "right": {"type": "string", "pattern": _RATIONAL},
                        "left_closed": {"type": "boolean"},
                        "right_closed": {"type": "boolean"},
                    },
                    "required": ["kind", "left", "right"],
                    "additionalProperties": False,
                },
            ]
        },
        "candidates": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "pattern": _RATIONAL},
        },
    },
    "required": ["schema_version", "variable", "coefficients", "domain", "candidates"],
    "additionalProperties": False,
}

PYTHON_MATH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"code": {"type": "string"}},
    "required": ["code"],
    "additionalProperties": False,
}


def schema_error(value: Any, schema: Mapping[str, Any]) -> str | None:
    """Return a stable error category when a value violates a trusted JSON schema."""

    choices = schema.get("oneOf")
    if isinstance(choices, Sequence) and not isinstance(choices, (str, bytes)):
        if sum(schema_error(value, choice) is None for choice in choices) != 1:
            return "tool_schema_invalid"
        return None

    expected_type = schema.get("type")
    types = {
        "object": lambda item: isinstance(item, Mapping),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    if expected_type in types and not types[expected_type](value):
        return "tool_schema_invalid"
    if "const" in schema and value != schema["const"]:
        return "tool_schema_invalid"
    allowed = schema.get("enum")
    if isinstance(allowed, Sequence) and value not in allowed:
        return "tool_schema_invalid"

    if isinstance(value, Mapping):
        required = schema.get("required", ())
        properties = schema.get("properties", {})
        if any(name not in value for name in required):
            return "tool_schema_invalid"
        if schema.get("additionalProperties") is False and any(name not in properties for name in value):
            return "tool_schema_invalid"
        for name, child_schema in properties.items():
            if name in value and schema_error(value[name], child_schema) is not None:
                return "tool_schema_invalid"
    elif isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            return "tool_schema_invalid"
        if len(value) > schema.get("maxItems", len(value)):
            return "tool_schema_invalid"
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping) and any(
            schema_error(item, item_schema) is not None for item in value
        ):
            return "tool_schema_invalid"
    elif isinstance(value, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return "tool_schema_invalid"
    return None


__all__ = ["POLYNOMIAL_CHECK_SCHEMA", "PYTHON_MATH_SCHEMA", "schema_error"]
