"""A deliberately narrow, deterministic proof of serialization-only changes."""

import json
import re

from ..tool_schemas import POLYNOMIAL_CHECK_SCHEMA, PYTHON_MATH_SCHEMA, schema_error


def strict_object(text):
    """Reject duplicate keys, non-JSON constants and non-object roots."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def constant(_value):
        raise ValueError("non_json_constant")

    result = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(result, dict):
        raise ValueError("object_required")
    return result


def visible_values(text, schema):
    """Recover only an entire strict object, optionally in one exact JSON fence."""
    source = text.strip()
    match = re.fullmatch(r"```(?:json)?\r?\n(.*)\r?\n```", source, re.DOTALL)
    value = strict_object(match[1] if match else source)
    validate_values(value, schema)
    return value


def validate_values(value, schema):
    """Check role fields and conservative proposal/evidence semantics, without tools."""
    if schema_error(value, schema):
        raise ValueError("invalid_role_schema")
    proposals = []

    def walk(item):
        if isinstance(item, dict):
            proposal = item.get("tool_request")
            if proposal is not None:
                proposals.append(proposal)
                if item.get("label", "easy-verify") != "easy-verify":
                    raise ValueError("tool_proposal_not_evidence")
                argument_schema = {"python_math": PYTHON_MATH_SCHEMA,
                                   "polynomial_check": POLYNOMIAL_CHECK_SCHEMA}[proposal["tool"]]
                if schema_error(proposal["arguments"], argument_schema):
                    raise ValueError("invalid_tool_arguments")
            # This candidate cannot establish or invent receipt provenance.
            if item.get("tool_evidence_refs") or item.get("receipt_ids"):
                raise ValueError("unconfirmed_evidence_reference")
            if item.get("label") == "verified":
                raise ValueError("unconfirmed_verified_claim")
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
    if len(proposals) > 1:
        raise ValueError("multiple_tool_proposals")


def canonical(value):
    """Type-sensitive all-field equality, including code, whitespace and parameters."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":"))
