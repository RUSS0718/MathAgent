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
    "root_obligations": {"type": "array", "items": _object({
        "obligation_type": {"enum": sorted(OBLIGATION_TYPES)},
        "statement": _TEXT, "obligation_id": _TEXT,
        "direction": {"oneOf": [_TEXT, {"enum": [None]}]}, "prerequisite_ids": _TEXTS,
    }, ["obligation_type", "statement"])},
    "auxiliary_goals": {"type": "array", "items": _object({
        "goal_id": _TEXT, "description": _TEXT, "dependencies": _TEXTS,
    }, ["goal_id", "description"])},
})
