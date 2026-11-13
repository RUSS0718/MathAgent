"""Strict structured replies for the explicit Intern Solver ports."""

from copy import deepcopy

from .problem_intake_schema import PROBLEM_SPEC_SCHEMA


def obj(properties, required=None, *, additional_properties=False):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": additional_properties,
    }


TEXT = {"type": "string"}
TEXTS = {"type": "array", "items": TEXT}
TARGET = {"oneOf": [{"type": "integer", "minimum": 1}, {"enum": [None]}]}
# A live NEED_PLAN reply or an intermediate step report naturally states the
# optional candidate as an explicit null ("no complete solution yet"); the
# reply protocol accepts that empty value instead of failing the whole run.
OPTIONAL_TEXT = {"oneOf": [TEXT, {"enum": [None]}]}
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
# Reviewer-classified outcome: the verifier explicitly rules what a review
# established (or left unproven); the controller verifies the declaration.
OUTCOME = obj(
    {
        "category": {"enum": ["Lemma", "Conjecture", "Computation", "Definition", "Answer"]},
        "statement": TEXT,
        "scope": TEXT,
        "claim_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "receipt_ids": TEXTS,
        "dependencies": TEXTS,
    },
    ["category", "statement", "scope"],
)
STEP = obj(
    {"argument": TEXT, "claims": {"type": "array", "items": CLAIM}, "blocked": {"type": "boolean"},
     "solution_candidate": OPTIONAL_TEXT, "answer_completeness": {"enum": ["complete", "partial"]}},
    ["argument", "claims", "blocked"],
)
SCHEMAS = {
    "problem_intake": PROBLEM_SPEC_SCHEMA,
    "explore": obj(
        {
            "assessment": {"enum": ["SOLVED", "PARTIALLY_SOLVED", "NEED_PLAN", "UNKNOWN"]},
            "worked": TEXTS,
            "failed": TEXTS,
            "candidates": TEXTS,
            "solution_candidate": OPTIONAL_TEXT,
            "tool_request": {"oneOf": [TOOL, {"enum": [None]}]},
        },
        ["assessment", "worked", "failed", "candidates"],
    ),
    "explore_polish": obj({"solution_candidate": TEXT}),
    "reasoner": obj(STEP["properties"], STEP["required"]),
    "reason_noncoding": obj(STEP["properties"], STEP["required"]),
    "step_verifier": obj(
        {
            "goal_gate": {"enum": ["YES", "PARTIAL", "NO"]},
            "logic_gate": {"enum": ["PASS", "FAIL", "UNCERTAIN"]},
            "verdict": {"enum": ["ACCEPT", "CHALLENGE", "TRACE_BACK", "PROPOSE_REPLAN"]},
            "objection": TEXT,
            "trace_back_to": TARGET,
            "answer_claim": obj({
                "claim_index": {"type": "integer", "minimum": 0},
                "both_directions_proved": {"type": "boolean"},
                "assumptions": TEXTS,
                "approach": TEXT,
                "claim_type": {"enum": ["numerical_evaluation", "sharp_bound", "extremum",
                                         "necessary_and_sufficient", "general_proof"]},
            }, ["claim_index", "both_directions_proved", "assumptions", "approach"]),
            "tool_request": {"oneOf": [TOOL, {"enum": [None]}]},
            "classified_outcomes": {"type": "array", "items": OUTCOME},
        },
        ["goal_gate", "logic_gate", "verdict", "objection"],
    ),
    "whole_solution_verifier": obj(
        {
            "verdict": {"enum": ["ACCEPT", "REJECT"]},
            "reason": TEXT,
            "tool_request": {"oneOf": [TOOL, {"enum": [None]}]},
        },
        ["verdict"],
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

SCHEMAS["reasoner_checkpoint"] = obj(
    {
        "checkpoint": obj(
            {
                "protocol_version": {"type": "integer", "minimum": 1},
                "checkpoint_id": TEXT,
                "status": {"enum": ["YIELD", "FINAL", "BLOCKED", "FAILED"]},
                "objective": TEXT,
                "argument": TEXT,
                "claims": {"type": "array", "items": CLAIM},
                "blocked": {"type": "boolean"},
                "dependencies": TEXTS,
                "evidence": TEXTS,
                "gaps": TEXTS,
                "next_action": TEXT,
            },
            ["protocol_version", "checkpoint_id", "status", "objective", "argument",
             "claims", "blocked", "dependencies", "evidence", "gaps", "next_action"],
        ),
    },
    ["checkpoint"],
)

# The provider contract must reject exactly the gap/status combinations that
# the checkpoint parser rejects, so known failures reach bounded format repair.
_REASONER_CHECKPOINT = SCHEMAS["reasoner_checkpoint"]["properties"]["checkpoint"]
_REASONER_CHECKPOINT["properties"]["protocol_version"] = {"type": "integer", "const": 1}
for _field in ("checkpoint_id", "objective", "argument", "next_action"):
    _REASONER_CHECKPOINT["properties"][_field] = {"type": "string", "pattern": r"[\s\S]*\S[\s\S]*"}
_REASONER_CHECKPOINT["properties"]["claims"] = deepcopy(_REASONER_CHECKPOINT["properties"]["claims"])
_REASONER_CHECKPOINT["properties"]["claims"]["items"]["properties"]["statement"] = {
    "type": "string", "pattern": r"[\s\S]*\S[\s\S]*",
}
_REASONER_BRANCHES = []
for _statuses, _gap_limits in ((["YIELD"], {"minItems": 1}), (["FINAL"], {"maxItems": 0}),
                              (["BLOCKED", "FAILED"], {})):
    _branch = deepcopy(_REASONER_CHECKPOINT)
    _branch["properties"]["status"] = {"enum": _statuses}
    _branch["properties"]["gaps"] = {"type": "array", "items": TEXT, **_gap_limits}
    _REASONER_BRANCHES.append(_branch)
SCHEMAS["reasoner_checkpoint"]["properties"]["checkpoint"] = {"oneOf": _REASONER_BRANCHES}

_PLANNER_CHECKPOINT_PROPERTIES = {
    "protocol_version": {"type": "integer", "minimum": 1},
    "checkpoint_id": TEXT,
    "objective": TEXT,
    "dependencies": TEXTS,
    "evidence": TEXTS,
    "next_action": TEXT,
    "plan": {"oneOf": [SCHEMAS["planner"], {"enum": [None]}]},
}
_PLANNER_CHECKPOINT_REQUIRED = [
    "protocol_version",
    "checkpoint_id",
    "status",
    "objective",
    "dependencies",
    "evidence",
    "gaps",
    "next_action",
]
_PLANNER_CHECKPOINT_YIELD = obj(
    {
        **_PLANNER_CHECKPOINT_PROPERTIES,
        "status": {"const": "YIELD", "type": "string"},
        "gaps": {"type": "array", "minItems": 1, "items": {"type": "string", "pattern": r".*\S.*"}},
    },
    _PLANNER_CHECKPOINT_REQUIRED,
)
_PLANNER_CHECKPOINT_TERMINAL = obj(
    {
        **_PLANNER_CHECKPOINT_PROPERTIES,
        "status": {"enum": ["FINAL", "BLOCKED", "FAILED"]},
        "gaps": TEXTS,
    },
    _PLANNER_CHECKPOINT_REQUIRED,
)
SCHEMAS["planner_checkpoint"] = obj(
    {
        "checkpoint": {
            "oneOf": [_PLANNER_CHECKPOINT_YIELD, _PLANNER_CHECKPOINT_TERMINAL],
        },
        "plan": {"oneOf": [SCHEMAS["planner"], {"enum": [None]}]},
    },
    ["checkpoint"],
)


def response_schema(request):
    if request.get("execution_mode_decision") is True and request.get("role") == "meta":
        return obj({"mode": {"enum": ["serial", "population", "keep"]}, "reason": TEXT})
    role = request["role"]
    if role == "reasoner" and request.get("checkpoint_protocol"):
        schema = deepcopy(SCHEMAS["reasoner_checkpoint"])
        if isinstance(request.get("current_goal"), str):
            for branch in schema["properties"]["checkpoint"]["oneOf"]:
                branch["properties"]["objective"] = {"type": "string", "const": request["current_goal"]}
        return schema
    if role == "planner" and request.get("checkpoint_protocol"):
        role = "planner_checkpoint"
    if role == "researcher" and request.get("action") == "counterexample_check":
        return obj({
            "verdict": {"enum": ["FOUND_COUNTEREXAMPLE", "NOT_FOUND"]},
            "counterexample": TEXT, "assumptions_checked": TEXTS,
            "violated_conclusion": TEXT, "searched_scope": TEXT,
            "usage": {},
        }, ["verdict", "counterexample", "assumptions_checked",
            "violated_conclusion", "searched_scope"])
    if role in {"meta", "meta_strategist"} and request.get("action") == "delegate_research_task":
        return SCHEMAS["research_delegation"]
    if role in {"meta", "meta_strategist"} and request.get("action") == "preplan_hint":
        return obj({"hint": TEXT})
    if role in {"meta", "meta_strategist"} and request.get("action") == "partial_exploration":
        return obj(
            {
                "decision": {"enum": ["RETRY", "PLAN"]},
                "reason": TEXT,
                "role": {"enum": ["meta", "meta_strategist"]},
                "action": {"const": "partial_exploration", "type": "string"},
                "findings": TEXTS,
                "allowed_tools": {"type": "array", "items": TEXT},
            },
            ["decision", "reason"],
        )
    if role in {"meta", "meta_strategist"}:
        return SCHEMAS["meta_guidance" if request.get("guidance_request") else "meta"]
    if role not in SCHEMAS:
        raise ValueError("unsupported_intern_role")
    schema = SCHEMAS[role]
    if not isinstance(request.get("problem_spec"), dict):
        return schema
    schema = deepcopy(schema)
    if role == "step_verifier":
        from .intern_instructions import step_review_scope
        from .specification import _EVIDENCE_TYPES

        scope = step_review_scope(request)
        roots = scope["root_obligations"] if scope is not None else request["problem_spec"].get("root_obligations", [])
        evidence = [obj({
            "obligation_id": {"enum": [root["obligation_id"]]},
            "evidence_category": {"enum": sorted(_EVIDENCE_TYPES[root["obligation_type"]])},
            "claim_indexes": {"type": "array", "minItems": 1,
                              "items": {"type": "integer", "minimum": 0}},
        }) for root in roots]
        schema["properties"]["obligation_evidence"] = {
            "type": "array",
            **({"items": {"oneOf": evidence}} if evidence else {"maxItems": 0}),
        }
    if role in {"planner", "planner_checkpoint"}:
        planner = deepcopy(SCHEMAS["planner"])
        step = planner["properties"]["steps"]["items"]
        step["properties"].update({"obligation_ids": TEXTS, "auxiliary_goal_ids": TEXTS})
        for field, source, id_field in (
            ("obligation_ids", "root_obligations", "obligation_id"),
            ("auxiliary_goal_ids", "auxiliary_goals", "goal_id"),
        ):
            objectives = request["problem_spec"].get(source, [])
            ids = [item[id_field] for item in objectives if id_field in item]
            if ids:
                step["properties"][field] = {"type": "array", "items": {"type": "string", "enum": ids}}
            elif not objectives:
                step["properties"][field] = {"type": "array", "maxItems": 0, "items": TEXT}
        step["required"].extend(["obligation_ids", "auxiliary_goal_ids"])
        if request.get("progress_policy", {}).get("enabled") is True:
            from .progress import METHOD_IDS

            step["properties"]["method_id"] = {
                "type": "string",
                "enum": sorted(METHOD_IDS),
                "description": "Choose " + ", ".join(sorted(METHOD_IDS))
                + "; unknown denotes an unresolved method and cannot start a serial route.",
            }
            step["required"].append("method_id")
        if request.get("autonomous_routes"):
            planner["properties"]["alternative_plans"] = {
                "type": "array", "maxItems": 3, "items": deepcopy(planner),
            }
            planner["properties"]["execution_selection"] = obj({
                "mode": {"enum": ["serial", "population"]}, "reason": TEXT,
            })
            if request["autonomous_routes"].get("capacity"):
                planner["required"].append("execution_selection")
        if role == "planner":
            schema = planner
            if request.get("population_policy", {}).get("version") == "concurrent-aprs-v1":
                schema["properties"]["alternative_plans"] = {
                    "type": "array", "items": deepcopy(planner),
                }
        else:
            schema["properties"]["plan"]["oneOf"][0] = planner
            for branch in schema["properties"]["checkpoint"]["oneOf"]:
                nested_plan = branch["properties"].get("plan")
                if nested_plan:
                    nested_plan["oneOf"][0] = planner
    return schema
