"""Pure constrained specification, safe source rendering, and correspondence records."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from .experiment_manifest import canonical_json
from .solver_harness.specification import normalize_problem_spec

TEMPLATE_VERSION = "rational-polynomial-v1"
MAX_EXPRESSION_BYTES = 4096
MAX_AST_NODES = 256
MAX_AST_DEPTH = 32
MAX_INTEGER_DIGITS = 32
_VARIABLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_']{0,31}$")
_REQUIRED_FIELDS = {"domain", "variables", "quantifiers", "assumptions", "direction", "conclusion"}


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}_invalid")
    return value.strip()


def canonical_identity(value: Any) -> str:
    return _hash(value)


def safe_polynomial_ast(source: str, variable: str) -> ast.AST:
    """Validate a structural polynomial expression without evaluating it."""
    if not isinstance(source, str) or len(source.encode("utf-8")) > MAX_EXPRESSION_BYTES:
        raise ValueError("expression_too_large")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, TypeError, ValueError) as exc:
        raise ValueError("unsafe_expression") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise ValueError("ast_too_large")

    def validate(node: ast.AST, depth: int = 0) -> None:
        if depth > MAX_AST_DEPTH:
            raise ValueError("ast_too_deep")
        if isinstance(node, ast.Expression):
            validate(node.body, depth + 1)
        elif isinstance(node, ast.Constant):
            if (isinstance(node.value, bool) or not isinstance(node.value, int)
                    or len(str(abs(node.value))) > MAX_INTEGER_DIGITS):
                raise ValueError("unsafe_expression")
        elif isinstance(node, ast.Name):
            if node.id != variable:
                raise ValueError("unsupported_variables")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            validate(node.operand, depth + 1)
        elif isinstance(node, ast.BinOp):
            if isinstance(node.op, ast.Pow):
                validate(node.left, depth + 1)
                if not (
                    isinstance(node.right, ast.Constant)
                    and type(node.right.value) is int
                    and 0 <= node.right.value <= 16
                ):
                    raise ValueError("unsafe_expression")
            elif isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                validate(node.left, depth + 1)
                validate(node.right, depth + 1)
                if isinstance(node.op, ast.Div):
                    denominator = node.right
                    if isinstance(denominator, ast.UnaryOp) and isinstance(denominator.op, ast.USub):
                        denominator = denominator.operand
                    if not isinstance(denominator, ast.Constant):
                        raise ValueError("unsafe_expression")
                    if denominator.value == 0:
                        raise ValueError("zero_denominator")
            else:
                raise ValueError("unsafe_expression")
        else:
            raise ValueError("unsafe_expression")

    validate(tree)
    return tree

def _render_expression(node: ast.AST, parent_precedence: int = 0) -> str:
    precedence = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Pow: 3}
    if isinstance(node, ast.Constant):
        return str(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.UnaryOp):
        text = "-" + _render_expression(node.operand, 4)
        return f"({text})" if 4 < parent_precedence else text
    if isinstance(node, ast.BinOp):
        operator = {
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^",
        }[type(node.op)]
        level = precedence[type(node.op)]
        if isinstance(node.op, ast.Pow):
            left = _render_expression(node.left, 0)
            right = _render_expression(node.right, 0)
            text = f"({left}) ^ ({right})"
        else:
            left = _render_expression(node.left, level)
            right = _render_expression(node.right, level + 1)
            text = f"{left} {operator} {right}"
        return f"({text})" if level < parent_precedence else text
    raise ValueError("unsafe_expression")


def normalize_target(target: Any) -> dict[str, Any]:
    """Validate the first-release target shape and keep the original expressions."""
    if not isinstance(target, Mapping):
        raise ValueError("target_invalid")
    if target.get("domain") != "rationals":
        raise ValueError("unsupported_domain")
    variables = target.get("variables")
    if not isinstance(variables, list) or len(variables) != 1:
        raise ValueError("unsupported_variables")
    variable = _nonempty(variables[0], "variable")
    if not _VARIABLE.fullmatch(variable):
        raise ValueError("unsafe_expression")
    quantifiers = target.get("quantifiers")
    if quantifiers != [f"forall {variable}"]:
        raise ValueError("unsupported_quantifiers")
    if target.get("assumptions", []) != []:
        raise ValueError("unsupported_assumptions")
    if target.get("direction") != "equality":
        raise ValueError("unsupported_direction")
    lhs, rhs = _nonempty(target.get("lhs"), "lhs"), _nonempty(target.get("rhs"), "rhs")
    lhs_tree, rhs_tree = safe_polynomial_ast(lhs, variable), safe_polynomial_ast(rhs, variable)
    result = {
        "domain": "rationals",
        "variables": [variable],
        "lhs": lhs,
        "rhs": rhs,
        "quantifiers": [f"forall {variable}"],
        "assumptions": [],
        "direction": "equality",
    }
    result["hash"] = _hash(result)
    result["_lean_lhs"] = _render_expression(lhs_tree.body)
    result["_lean_rhs"] = _render_expression(rhs_tree.body)
    return result


def build_polynomial_identity_source(target: Any) -> str:
    """Render the original safe lhs/rhs directly; Lean ring is the only simplifier."""
    normalized = normalize_target(target)
    variable = normalized["variables"][0]
    lhs = normalized["_lean_lhs"]
    rhs = normalized["_lean_rhs"]
    return (
        "import Mathlib.Tactic.Ring\n\n"
        "set_option pp.all true\n"
        "set_option pp.maxSteps 1000000\n"
        f"theorem polynomial_identity ({variable} : ℚ) :\n"
        f"    {lhs} = {rhs} := by ring\n"
        "#print polynomial_identity\n"
        "#print axioms polynomial_identity\n"
    )

def public_target(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if not key.startswith("_")
    }


def build_specification_records(problem: str, specification: Any, target: Any) -> dict[str, Any]:
    """Build three typed records without asserting any correspondence review."""
    problem = _nonempty(problem, "problem")
    normalized_spec = normalize_problem_spec(specification)
    normalized_target = normalize_target(target)
    domain = str(normalized_spec.get("domain", "")).strip().lower()
    if domain not in {"rationals", "rational", "rational numbers"}:
        raise ValueError("spec_target_mismatch")
    if normalized_spec.get("quantifiers", []) != normalized_target["quantifiers"]:
        raise ValueError("spec_target_mismatch")
    directions = normalized_spec.get("directions", [])
    if not directions or directions[0] != normalized_target["direction"]:
        raise ValueError("spec_target_mismatch")
    public = public_target(normalized_target)
    return {
        "original_to_spec": {
            "original_problem_hash": _hash(problem),
            "problem_spec_version": normalized_spec.get("specification_version"),
            "problem_spec_hash": _hash(normalized_spec),
            "scope": normalized_spec.get("domain"),
            "root_obligations": normalized_spec.get("root_obligations"),
            "review_status": "not_reviewed",
            "review_record_hash": None,
        },
        "spec_to_target": {
            "problem_spec_hash": _hash(normalized_spec),
            "target_hash": public["hash"],
            "domain": public["domain"],
            "variables": public["variables"],
            "quantifiers": public["quantifiers"],
            "assumptions": public["assumptions"],
            "direction": public["direction"],
            "conclusion": f"{public['lhs']} = {public['rhs']}",
            "review_status": "not_reviewed",
            "review_record_hash": None,
        },
        "target_to_environment": {
            "target_hash": public["hash"],
            "template_version": TEMPLATE_VERSION,
            "environment_hash": None,
            "source_hash": None,
            "proof_hash": None,
            "attempt_hash": None,
            "review_status": "not_reviewed",
            "review_record_hash": None,
        },
    }


def normalize_formal_request(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema_version") != 1:
        raise ValueError("formal_request_schema_invalid")
    request = json.loads(json.dumps(value, ensure_ascii=False))
    for name in ("job_id", "run_id", "attempt_id"):
        request[name] = _nonempty(request.get(name), name)
    parent = request.get("parent_attempt_id")
    if parent is not None and (
        not isinstance(parent, str) or not parent or parent == request["attempt_id"]
    ):
        raise ValueError("attempt_lineage_invalid")
    problem = request.get("problem")
    if not isinstance(problem, Mapping):
        raise ValueError("problem_invalid")
    text = _nonempty(problem.get("text"), "problem")
    specification = normalize_problem_spec(request.get("specification"))
    target = normalize_target(request.get("target"))
    records = build_specification_records(text, specification, target)
    request["problem"] = {"text": text, "hash": _hash(text)}
    request["specification"] = specification
    request["specification"]["hash"] = records["original_to_spec"]["problem_spec_hash"]
    supplied_hash = request["target"].get("hash")
    if supplied_hash is not None and supplied_hash != target["hash"]:
        raise ValueError("target_hash_mismatch")
    request["target"] = public_target(target)
    policy = request.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("policy_invalid")
    allowed = policy.get(
        "allowed_axioms", ["propext", "Classical.choice", "Quot.sound"]
    )
    if not isinstance(allowed, list) or any(
        not isinstance(item, str) or not item.strip() for item in allowed
    ):
        raise ValueError("allowed_axioms_invalid")
    request["policy"] = {
        "enabled": policy.get("enabled") is True,
        "backend": policy.get("backend"),
        "timeout_seconds": float(policy.get("timeout_seconds", 30)),
        "max_output_bytes": int(policy.get("max_output_bytes", 16000)),
        "allowed_axioms": sorted(set(allowed)),
        "environment": dict(policy.get("environment") or {}),
        "resource_limits": dict(policy.get("resource_limits") or {}),
    }
    if (not math.isfinite(request["policy"]["timeout_seconds"])
            or request["policy"]["timeout_seconds"] <= 0
            or request["policy"]["max_output_bytes"] <= 0):
        raise ValueError("formal_limits_invalid")
    request["cost"] = dict(request.get("cost") or {})
    request["specifications"] = records
    return request
def required_review_fields() -> set[str]:
    return set(_REQUIRED_FIELDS)


__all__ = [
    "TEMPLATE_VERSION", "build_polynomial_identity_source", "build_specification_records",
    "canonical_identity", "normalize_formal_request", "normalize_target",
    "public_target", "required_review_fields", "safe_polynomial_ast",
]
