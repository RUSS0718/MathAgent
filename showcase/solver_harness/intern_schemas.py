"""Strict structured replies for the explicit Intern Solver ports."""


def obj(properties, required=None):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


TEXT = {"type": "string"}
TEXTS = {"type": "array", "items": TEXT}
TARGET = {"oneOf": [{"type": "integer", "minimum": 1}, {"enum": [None]}]}
TOOL = obj(
    {
        "tool": {"enum": ["polynomial_check", "python_math"]},
        "arguments": {"type": "object"},
        "scope": {"enum": ["finite_computation"]},
        "expected_output": {},
    },
    ["tool", "arguments", "scope"],
)
CLAIM = obj(
    {
        "statement": TEXT,
        "label": {"enum": ["verified", "easy-verify", "hard-verify"]},
        "tool_request": {"oneOf": [TOOL, {"enum": [None]}]},
        "tool_evidence_refs": TEXTS,
    },
    ["statement", "label"],
)
STEP = obj(
    {"argument": TEXT, "claims": {"type": "array", "items": CLAIM}, "blocked": {"type": "boolean"}}
)
SCHEMAS = {
    "explore": obj(
        {
            "assessment": {"enum": ["SOLVED", "PARTIALLY_SOLVED", "NEED_PLAN", "UNKNOWN"]},
            "worked": TEXTS,
            "failed": TEXTS,
            "candidates": TEXTS,
            "solution_candidate": TEXT,
        },
        ["assessment", "worked", "failed", "candidates"],
    ),
    "explore_polish": obj({"solution_candidate": TEXT}),
    "reasoner": STEP,
    "reason_noncoding": STEP,
    "step_verifier": obj(
        {
            "goal_gate": {"enum": ["YES", "PARTIAL", "NO"]},
            "logic_gate": {"enum": ["PASS", "FAIL", "UNCERTAIN"]},
            "verdict": {"enum": ["ACCEPT", "CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN"]},
            "objection": TEXT,
            "trace_back_to": TARGET,
        },
        ["goal_gate", "logic_gate", "verdict", "objection"],
    ),
    "whole_solution_verifier": obj(
        {"verdict": {"enum": ["ACCEPT", "REJECT"]}, "reason": TEXT}, ["verdict"]
    ),
    "final_generator": obj({"final_response": TEXT}),
    "meta": obj(
        {
            "decision": {"enum": ["CONTINUE", "TRACE_BACK", "APPROVE_REPLAN", "ABORT"]},
            "reason_summary": TEXT,
            "plan_summary": TEXT,
            "forbidden_directions": TEXTS,
            "reusable_results": TEXTS,
            "trace_back_to": TARGET,
        }
    ),
    "research_delegation": obj(
        {
            "tasks": {
                "type": "array",
                "maxItems": 8,
                "items": obj(
                    {
                        "prompt": TEXT,
                        "permitted_tools": {"type": "array", "maxItems": 0},
                        "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                    }
                ),
            }
        }
    ),
    "meta_guidance": obj(
        {
            "action_type": {
                "enum": ["explore_more", "retry_different_method", "trace_back", "replan"]
            },
            "specific_task": TEXT,
            "use_pure_reasoning": {"type": "boolean"},
            "trace_back_to": TARGET,
            "rationale": TEXT,
        }
    ),
    "planner": obj(
        {
            "version": {"type": "integer", "minimum": 1},
            "steps": {
                "type": "array",
                "minItems": 1,
                "items": obj(
                    {"step_id": TEXT, "title": TEXT, "objective": TEXT, "depends_on": TEXTS},
                    ["step_id", "title", "objective"],
                ),
            },
        }
    ),
    "researcher": obj({"findings": TEXTS}),
}


def response_schema(request):
    role = request["role"]
    if role in {"meta", "meta_strategist"} and request.get("action") == "delegate_research_task":
        return SCHEMAS["research_delegation"]
    if role in {"meta", "meta_strategist"} and request.get("action") == "preplan_hint":
        return obj({"hint": TEXT})
    if role in {"meta", "meta_strategist"} and request.get("action") == "partial_exploration":
        return obj({"decision": {"enum": ["RETRY", "PLAN"]}, "reason": TEXT})
    if role in {"meta", "meta_strategist"}:
        return SCHEMAS["meta_guidance" if request.get("guidance_request") else "meta"]
    if role not in SCHEMAS:
        raise ValueError("unsupported_intern_role")
    return SCHEMAS[role]
