"""Pure structural helpers for versioned problem specifications and work units."""

import json
from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

OBLIGATION_TYPES = frozenset(
    {
        "universal",
        "existence",
        "extremum_bound",
        "extremum_attainment",
        "enumeration",
        "completeness",
        "filtering",
        "format",
    }
)

_EVIDENCE_TYPES = {
    "universal": frozenset({"universal_proof"}),
    "existence": frozenset({"existence_proof", "existence_witness"}),
    "extremum_bound": frozenset(
        {"bound_proof", "upper_bound_proof", "lower_bound_proof"}
    ),
    "extremum_attainment": frozenset({"attainment_witness"}),
    "enumeration": frozenset({"enumeration_result"}),
    "completeness": frozenset({"completeness_proof"}),
    "filtering": frozenset({"filtering_proof"}),
    "format": frozenset({"format_check"}),
}


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list of strings")
    return [_nonempty_string(item, f"{field} item") for item in value]


def _normalized_category(value: Any, field: str, allowed: frozenset[str]) -> str:
    category = "_".join(_nonempty_string(value, field).lower().replace("-", " ").split())
    if category not in allowed:
        raise ValueError(f"{field} has an unsupported category")
    return category


def _stable_obligation_id(obligation_type: str, statement: str, direction: str | None) -> str:
    identity = json.dumps(
        [obligation_type, statement, direction], ensure_ascii=False, separators=(",", ":")
    )
    digest = sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"root:{obligation_type}:{digest}"


def _normalize_root_obligations(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("root_obligations must contain at least one obligation")

    roots = []
    identifiers = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("each root obligation must be a mapping")
        obligation_type = _normalized_category(
            item.get("obligation_type"), "obligation_type", OBLIGATION_TYPES
        )
        statement = _nonempty_string(item.get("statement"), "obligation statement")
        raw_direction = item.get("direction")
        direction = (
            _nonempty_string(raw_direction, "obligation direction")
            if raw_direction is not None
            else None
        )
        raw_id = item.get("obligation_id")
        obligation_id = (
            _nonempty_string(raw_id, "obligation_id").strip()
            if raw_id is not None
            else _stable_obligation_id(obligation_type, statement, direction)
        )
        if obligation_id in identifiers:
            raise ValueError("root obligation IDs must be unique")
        identifiers.add(obligation_id)
        root = {
            "obligation_id": obligation_id,
            "obligation_type": obligation_type,
            "statement": statement,
        }
        if direction is not None:
            root["direction"] = direction
        prerequisite_ids = item.get("prerequisite_ids", [])
        if not isinstance(prerequisite_ids, list):
            raise ValueError("obligation prerequisite_ids must be a list")
        prerequisites = [
            _nonempty_string(value, "obligation prerequisite_id").strip()
            for value in prerequisite_ids
        ]
        if len(set(prerequisites)) != len(prerequisites) or obligation_id in prerequisites:
            raise ValueError("obligation prerequisite IDs must be unique and non-self-referential")
        if prerequisites:
            root["prerequisite_ids"] = prerequisites
        roots.append(root)
    return roots


def _normalize_auxiliary_goals(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("auxiliary_goals must be a list")
    goals = []
    identifiers = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("each auxiliary goal must be a mapping")
        goal = dict(item)
        goal_id = _nonempty_string(goal.get("goal_id"), "auxiliary goal_id").strip()
        if goal_id in identifiers:
            raise ValueError("auxiliary goal IDs must be unique")
        identifiers.add(goal_id)
        goal["goal_id"] = goal_id
        dependencies = goal.get("dependencies", [])
        if not isinstance(dependencies, list):
            raise ValueError("auxiliary goal dependencies must be a list")
        goal["dependencies"] = [
            _nonempty_string(dependency, "auxiliary goal dependency").strip()
            for dependency in dependencies
        ]
        if len(set(goal["dependencies"])) != len(goal["dependencies"]):
            raise ValueError("auxiliary goal dependencies must be unique")
        if goal_id in goal["dependencies"]:
            raise ValueError("auxiliary goal cannot depend on itself")
        goals.append(goal)
    return goals


def normalize_problem_spec(value: Any) -> dict[str, Any]:
    """Validate and normalize a ProblemSpec without altering its original text."""
    if not isinstance(value, Mapping):
        raise ValueError("problem specification must be a mapping")
    version = value.get("specification_version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("specification_version must be a positive integer")

    roots = _normalize_root_obligations(value.get("root_obligations"))
    goals = _normalize_auxiliary_goals(value.get("auxiliary_goals", []))
    valid_dependencies = {
        *(item["obligation_id"] for item in roots),
        *(item["goal_id"] for item in goals),
    }
    for item in [*roots, *goals]:
        dependencies = item.get("prerequisite_ids", item.get("dependencies", []))
        if any(dependency not in valid_dependencies for dependency in dependencies):
            raise ValueError("specification dependency references an unknown objective")
    _validate_dependency_cycles([*roots, *goals])

    return {
        "specification_version": version,
        "original_problem": _nonempty_string(value.get("original_problem"), "original_problem"),
        "domain": _nonempty_string(value.get("domain"), "domain"),
        "quantifiers": _string_list(value.get("quantifiers"), "quantifiers"),
        "assumptions": _string_list(value.get("assumptions"), "assumptions"),
        "directions": _string_list(value.get("directions"), "directions"),
        "output_requirements": _string_list(
            value.get("output_requirements"), "output_requirements"
        ),
        "root_obligations": roots,
        "auxiliary_goals": goals,
    }


def _validate_dependency_cycles(objectives: Sequence[Mapping[str, Any]]) -> None:
    graph = {
        item.get("obligation_id", item.get("goal_id")): set(
            item.get("prerequisite_ids", item.get("dependencies", []))
        )
        for item in objectives
    }
    visiting, visited = set(), set()

    def visit(objective_id):
        if objective_id in visiting:
            raise ValueError("specification dependencies must be acyclic")
        if objective_id in visited:
            return
        visiting.add(objective_id)
        for dependency in graph[objective_id]:
            visit(dependency)
        visiting.remove(objective_id)
        visited.add(objective_id)

    for objective_id in graph:
        visit(objective_id)


def root_obligation_count(specification: Any) -> int:
    """Return the progress denominator; auxiliary goals are intentionally excluded."""
    return len(normalize_problem_spec(specification)["root_obligations"])


def normalize_work_units(
    value: Any,
    root_obligations: Sequence[Mapping[str, Any]],
    auxiliary_goals: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Validate WorkUnit-to-root mappings and earlier-only AND prerequisites."""
    if not isinstance(value, list) or not value:
        raise ValueError("work_units must contain at least one WorkUnit")
    if not isinstance(root_obligations, Sequence) or isinstance(root_obligations, (str, bytes)):
        raise ValueError("root_obligations must be a sequence")
    root_ids = set()
    for root in root_obligations:
        if not isinstance(root, Mapping):
            raise ValueError("each root obligation must be a mapping")
        root_ids.add(_nonempty_string(root.get("obligation_id"), "obligation_id"))
    if len(root_ids) != len(root_obligations):
        raise ValueError("root obligation IDs must be unique")
    if not root_ids:
        raise ValueError("root_obligations must not be empty")
    auxiliary_ids = {
        _nonempty_string(goal.get("goal_id"), "auxiliary goal_id")
        for goal in auxiliary_goals
        if isinstance(goal, Mapping)
    }

    units = []
    seen = set()
    covered = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError("each WorkUnit must be a mapping")
        unit_id = _nonempty_string(item.get("work_unit_id"), "work_unit_id").strip()
        if unit_id in seen:
            raise ValueError("WorkUnit IDs must be unique")
        raw_obligation_ids = item.get("obligation_ids")
        if not isinstance(raw_obligation_ids, list):
            raise ValueError("WorkUnit obligation_ids must be a list")
        obligation_ids = [
            _nonempty_string(obligation_id, "obligation_id").strip()
            for obligation_id in raw_obligation_ids
        ]
        if len(set(obligation_ids)) != len(obligation_ids):
            raise ValueError("WorkUnit obligation IDs must be unique")
        if any(obligation_id not in root_ids for obligation_id in obligation_ids):
            raise ValueError("WorkUnit references an unknown root obligation")

        raw_auxiliary_ids = item.get("auxiliary_goal_ids", [])
        if not isinstance(raw_auxiliary_ids, list):
            raise ValueError("WorkUnit auxiliary_goal_ids must be a list")
        auxiliary_goal_ids = [
            _nonempty_string(goal_id, "auxiliary_goal_id").strip()
            for goal_id in raw_auxiliary_ids
        ]
        if len(set(auxiliary_goal_ids)) != len(auxiliary_goal_ids):
            raise ValueError("WorkUnit auxiliary goal IDs must be unique")
        if auxiliary_ids and any(goal_id not in auxiliary_ids for goal_id in auxiliary_goal_ids):
            raise ValueError("WorkUnit references an unknown auxiliary goal")
        if not obligation_ids and not auxiliary_goal_ids:
            raise ValueError("WorkUnit must map to a root obligation or auxiliary goal")

        raw_prerequisites = item.get("prerequisites", [])
        if not isinstance(raw_prerequisites, list):
            raise ValueError("WorkUnit prerequisites must be a list")
        prerequisites = [
            _nonempty_string(prerequisite, "WorkUnit prerequisite").strip()
            for prerequisite in raw_prerequisites
        ]
        if len(set(prerequisites)) != len(prerequisites):
            raise ValueError("WorkUnit prerequisites must be unique")
        if any(prerequisite not in seen for prerequisite in prerequisites):
            raise ValueError("WorkUnit prerequisites must reference earlier WorkUnits")
        raw_required_obligations = item.get("required_obligation_ids", [])
        if not isinstance(raw_required_obligations, list):
            raise ValueError("WorkUnit required_obligation_ids must be a list")
        required_obligation_ids = [
            _nonempty_string(value, "required obligation_id").strip()
            for value in raw_required_obligations
        ]
        if (len(set(required_obligation_ids)) != len(required_obligation_ids)
                or any(value not in root_ids for value in required_obligation_ids)):
            raise ValueError("WorkUnit required obligations must reference unique root obligations")

        units.append(
            {
                "work_unit_id": unit_id,
                "obligation_ids": obligation_ids,
                "auxiliary_goal_ids": auxiliary_goal_ids,
                "prerequisites": prerequisites,
                "required_obligation_ids": required_obligation_ids,
            }
        )
        if "method_id" in item:
            from .progress import normalize_method

            units[-1]["method_id"] = normalize_method(item["method_id"])
        seen.add(unit_id)
        covered.update(obligation_ids)

    if covered != root_ids:
        raise ValueError("WorkUnits must cover every root obligation")
    return units


def normalize_plan_work_units(plan: Mapping[str, Any], specification: Any) -> list[dict[str, Any]]:
    """Bind executable Plan steps to versioned root/auxiliary objectives."""
    spec = normalize_problem_spec(specification)
    steps = plan.get("steps")
    if not isinstance(steps, list):
        raise ValueError("plan steps must be a list")
    root_map = {item["obligation_id"]: item for item in spec["root_obligations"]}
    goal_map = {item["goal_id"]: item for item in spec["auxiliary_goals"]}
    units = []
    for step in steps:
        if not isinstance(step, Mapping):
            raise ValueError("plan step must be a mapping")
        units.append({
            **({"method_id": step["method_id"]} if "method_id" in step else {}),
            "work_unit_id": step.get("step_id"),
            "obligation_ids": step.get("obligation_ids", []),
            "auxiliary_goal_ids": step.get("auxiliary_goal_ids", []),
            "prerequisites": step.get("depends_on", []),
        })
    owners: dict[str, list[str]] = {}
    for unit in units:
        for objective_id in [*unit["obligation_ids"], *unit["auxiliary_goal_ids"]]:
            owners.setdefault(objective_id, []).append(unit["work_unit_id"])
    for unit in units:
        dependencies = set(unit["prerequisites"])
        required_obligations = set()
        objective_ids = [*unit["obligation_ids"], *unit["auxiliary_goal_ids"]]
        for objective_id in objective_ids:
            objective = root_map.get(objective_id) or goal_map.get(objective_id, {})
            refs = objective.get("prerequisite_ids", objective.get("dependencies", []))
            for ref in refs:
                owners_for_ref = owners.get(ref, [])
                if not owners_for_ref:
                    raise ValueError("specification prerequisite has no WorkUnit mapping")
                dependencies.update(owners_for_ref)
                if ref in root_map:
                    required_obligations.add(ref)
        unit["prerequisites"] = sorted(dependencies)
        unit["required_obligation_ids"] = sorted(required_obligations)
    normalized = normalize_work_units(
        units, spec["root_obligations"], spec["auxiliary_goals"]
    )
    for unit in normalized:
        if not unit["required_obligation_ids"]:
            unit.pop("required_obligation_ids")
    return [
        {**unit, "step_id": unit["work_unit_id"]}
        for unit in normalized
    ]


def bind_plan_work_units(
    plan: Mapping[str, Any], specification: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return a copied Plan whose steps carry the validated WorkUnit mapping."""
    units = normalize_plan_work_units(plan, specification)
    bound = dict(plan)
    bound["steps"] = [
        {
            **step,
            **({"method_id": unit["method_id"]} if "method_id" in unit else {}),
            "obligation_ids": unit["obligation_ids"],
            "auxiliary_goal_ids": unit["auxiliary_goal_ids"],
        }
        for step, unit in zip(plan["steps"], units)
    ]
    return bound, units


def prerequisites_satisfied(
    work_unit: Mapping[str, Any],
    completed_work_unit_ids: Sequence[str] | set[str],
    completed_obligation_ids: Sequence[str] | set[str] | None = None,
) -> bool:
    """Return whether every prerequisite of a WorkUnit is complete (logical AND)."""
    if not isinstance(work_unit, Mapping):
        raise ValueError("work_unit must be a mapping")
    prerequisites = work_unit.get("prerequisites", [])
    if not isinstance(prerequisites, list) or any(
        not isinstance(item, str) for item in prerequisites
    ):
        raise ValueError("WorkUnit prerequisites must be a list of IDs")
    if isinstance(completed_work_unit_ids, (str, bytes)) or not isinstance(
        completed_work_unit_ids, Sequence | set
    ):
        raise ValueError("completed_work_unit_ids must be a sequence or set")
    if not all(item in completed_work_unit_ids for item in prerequisites):
        return False
    required = work_unit.get("required_obligation_ids", [])
    if required and (
        completed_obligation_ids is None
        or not all(item in completed_obligation_ids for item in required)
    ):
        return False
    return True


def validate_evidence_category(
    specification: Any, obligation_id: str, evidence_category: str
) -> None:
    """Reject structurally incompatible evidence labels; this does not prove claims."""
    spec = normalize_problem_spec(specification)
    root = next(
        (item for item in spec["root_obligations"] if item["obligation_id"] == obligation_id),
        None,
    )
    if root is None:
        raise ValueError("evidence must reference a root obligation")
    accepted = _EVIDENCE_TYPES[root["obligation_type"]]
    category = _normalized_category(evidence_category, "evidence_category", accepted)
    if category not in accepted:
        raise ValueError("evidence category does not match obligation type")
