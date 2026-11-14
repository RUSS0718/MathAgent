"""Provider response contract for task intake, distinct from proof or planning."""

from .specification import OBLIGATION_TYPES


def _object(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


_TEXT = {"type": "string"}
_TEXTS = {"type": "array", "items": _TEXT}
PROBLEM_SPEC_SCHEMA = _object({
    "specification_version": {"type": "integer", "enum": [1]},
    "original_problem": _TEXT, "domain": _TEXT,
    "quantifiers": _TEXTS, "assumptions": _TEXTS, "directions": _TEXTS,
    "output_requirements": _TEXTS,
    "root_obligations": {"type": "array", "minItems": 1, "items": _object({
        "obligation_type": {"enum": sorted(OBLIGATION_TYPES)},
        "statement": _TEXT, "obligation_id": _TEXT,
        "direction": {"oneOf": [_TEXT, {"enum": [None]}]}, "prerequisite_ids": _TEXTS,
    }, ["obligation_type", "statement"])},
    "auxiliary_goals": {"type": "array", "items": _object({
        "goal_id": _TEXT, "description": _TEXT, "dependencies": _TEXTS,
    }, ["goal_id", "description"])},
})


def _nonblank_text(max_length):
    return {"type": "string", "pattern": r"^[\s\S]*\S[\s\S]*$",
            "minLength": 1, "maxLength": max_length}


PROBLEM_SPEC_SCHEMA["properties"]["clarification"] = {"oneOf": [
    {"enum": [None]},
    _object({"question": _nonblank_text(1000), "reason": _nonblank_text(1000)}),
]}
PROBLEM_SPEC_SCHEMA["properties"]["applicable_condition"] = {"oneOf": [
    {"enum": [None]}, _nonblank_text(8000),
]}


def invalid_intake_phase_reply(reply, request):
    """Check the phase-specific combination after structural schema validation."""
    if request["role"] != "problem_intake":
        return False
    submitted = request.get("clarification_input")
    condition = reply.get("applicable_condition")
    followup = reply.get("clarification")
    if submitted is None:
        return condition is not None
    if condition is None:
        return followup is None
    return followup is not None or condition.strip() not in submitted["answer"]


PROBLEM_SPEC_SCHEMA["properties"]["formalization"] = _object({
    "status": {"enum": ["proposed", "unsupported", "not_selected"]},
    "reason": _TEXT, "require_formal": {"type": "boolean"},
    "obligation_ids": _TEXTS,
    "target": {"oneOf": [{"enum": [None]}, _object({
        "domain": _TEXT, "variables": _TEXTS, "lhs": _TEXT, "rhs": _TEXT,
        "quantifiers": _TEXTS, "assumptions": _TEXTS, "direction": _TEXT,
    })]},
})
