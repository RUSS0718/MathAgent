"""Evaluate bounded exact assertions and validate coarse dependency graphs."""

import ast
import json
import operator
from dataclasses import dataclass
from fractions import Fraction
from math import comb, gcd, lcm

_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
_FUNCTIONS = {"choose": comb, "gcd": gcd, "lcm": lcm}
L1_EVIDENCE = "L1-Executable-Verified"
L2_EVIDENCE = "L2-Reviewed"
CHECK_FORMAT = (
    'A check is {"step": 1, "lhs": "choose(10, 2)", "rhs": "45", "at": null}. '
    "Use exact integer arithmetic, fractions, %, ** (exponents -12 to 12), choose(n,k), "
    "gcd(a,b), and lcm(a,b). For a claimed universal equality, integer samples such as "
    '"at":{"x":3} can disprove it but cannot establish it. '
    'Use "variable":"x" (with at null) to verify a one-variable polynomial identity. '
    "For a value or equation root explicitly claimed in the step, substitute the stated "
    'values into a closed equality (e.g. "2*3+1 = 7" for x=3 in 2*x+1=7). '
    "Keep the original equality, including any erroneous side. "
    "Use null when there is no useful exact check."
)


def _number(node: ast.AST, bindings: dict[str, int]) -> Fraction:
    """Interpret a small arithmetic grammar with bounded intermediate values."""
    match node:
        case ast.Constant(value=value) if type(value) is int and value.bit_length() <= 128:
            result = Fraction(value)
        case ast.Name(id=name) if name in bindings:
            result = Fraction(bindings[name])
        case ast.UnaryOp(op=ast.UAdd() | ast.USub(), operand=operand):
            result = _number(operand, bindings)
            if isinstance(node.op, ast.USub):
                result = -result
        case ast.BinOp(left=left, op=op, right=right):
            a, b = _number(left, bindings), _number(right, bindings)
            if isinstance(op, ast.Pow):
                if b.denominator != 1 or abs(b) > 12:
                    raise ValueError("unsupported exponent")
                result = a ** int(b)
            else:
                result = _OPERATORS[type(op)](a, b)
        case ast.Call(func=ast.Name(id=name), args=[left, right], keywords=[]) if name in _FUNCTIONS:
            a, b = _number(left, bindings), _number(right, bindings)
            if any(v.denominator != 1 for v in (a, b)) or (name == "choose" and max(a, b) > 256):
                raise ValueError("unsupported function argument")
            result = Fraction(_FUNCTIONS[name](int(a), int(b)))
        case _:
            raise ValueError("unsupported expression")
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 512:
        raise ValueError("large intermediate")
    return result


def check_assertion(check: dict) -> str:
    """Check an exact equality or search for a counterexample at a supplied point."""
    try:
        point = check.get("at")
        variable = check.get("variable")
        if variable is not None and (
            point is not None or not isinstance(variable, str)
            or len(variable) > 8 or not variable.isidentifier()
        ):
            return "uncheckable"
        if point is not None and (
            not isinstance(point, dict) or not 1 <= len(point) <= 4
            or any(not k.isidentifier() or type(v) is not int or abs(v) > 256
                   for k, v in point.items())
        ):
            return "uncheckable"
        expressions = []
        for expression in (check["lhs"], check["rhs"]):
            if not isinstance(expression, str) or len(expression) > 240:
                return "uncheckable"
            tree = ast.parse(expression, mode="eval")
            if sum(1 for _ in ast.walk(tree)) > 64:
                return "uncheckable"
            expressions.append(tree.body)
        if variable is not None:
            degree = max(_degree(expr, variable) for expr in expressions)
            if degree > 12:
                return "uncheckable"
            left, right = expressions
            return "pass" if all(
                _number(left, {variable: x}) == _number(right, {variable: x})
                for x in range(degree + 1)
            ) else "fail"
        if _number(expressions[0], point or {}) != _number(expressions[1], point or {}):
            return "fail"
        return "pass" if point is None else "uncheckable"
    except (KeyError, ValueError, SyntaxError, TypeError, ArithmeticError):
        return "uncheckable"


def _degree(node: ast.AST, variable: str) -> int:
    """Bound degree for exact identity testing at enough distinct integer points."""
    match node:
        case ast.Constant(value=value) if type(value) is int:
            return 0
        case ast.Name(id=name) if name == variable:
            return 1
        case ast.UnaryOp(op=ast.UAdd() | ast.USub(), operand=operand):
            return _degree(operand, variable)
        case ast.BinOp(left=left, op=ast.Add() | ast.Sub(), right=right):
            return max(_degree(left, variable), _degree(right, variable))
        case ast.BinOp(left=left, op=ast.Mult(), right=right):
            return _degree(left, variable) + _degree(right, variable)
        case ast.BinOp(left=left, op=ast.Div(), right=right):
            if _number(right, {}) != 0:
                return _degree(left, variable)
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            exponent = _number(right, {})
            if exponent.denominator == 1 and 0 <= exponent <= 12:
                return _degree(left, variable) * int(exponent)
    raise ValueError("unsupported polynomial term")


def json_object(text: str) -> dict:
    """Read one object from an isolated review or extraction reply."""
    text = text.strip()
    if text.startswith("```") and text.endswith("```") and "\n" in text:
        text = text.split("\n", 1)[1][:-3].strip()
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


@dataclass(frozen=True)
class Lemma:
    """Keep a checked proposition and its local dependencies for this run only."""

    id: str
    step: int
    claim: str
    premises: tuple[str, ...]
    check: str
    global_scope: bool
    matches_source: bool


@dataclass(frozen=True)
class GraphExtraction:
    """Describe a parsed graph or a redacted validation failure."""

    nodes: tuple[Lemma, ...] = ()
    outcome: str = "not_requested"
    node_count: int | None = None
    rejected_node: int | None = None


def lemma_graph(text: str, steps: tuple[str, ...]) -> GraphExtraction:
    """Require topological dependencies and evidence tied to a source step."""
    raw = json_object(text).get("lemmas")
    if not isinstance(raw, list):
        return GraphExtraction(outcome="missing_lemma_array")
    if not 1 <= len(raw) <= 10:
        return GraphExtraction(outcome="node_count", node_count=len(raw))
    graph = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            return GraphExtraction(outcome="node_shape", node_count=len(raw), rejected_node=index)
        step, claim, premises = item.get("step"), item.get("claim"), item.get("premises")
        if item.get("id") != f"L{index}":
            return GraphExtraction(outcome="node_id", node_count=len(raw), rejected_node=index)
        if type(step) is not int or not 1 <= step <= len(steps):
            return GraphExtraction(outcome="source_step", node_count=len(raw), rejected_node=index)
        if not isinstance(claim, str) or not 0 < len(claim.strip()) <= 400:
            return GraphExtraction(outcome="claim_shape", node_count=len(raw), rejected_node=index)
        if (not isinstance(premises, list)
            or any(p not in [node.id for node in graph] for p in premises)
            or len(set(premises)) != len(premises)):
            return GraphExtraction(outcome="premise_shape", node_count=len(raw), rejected_node=index)
        check = item.get("check")
        status = "uncheckable"
        if isinstance(check, dict) and type(check.get("step")) is int and check["step"] == step:
            equality = f'{check.get("lhs")} = {check.get("rhs")}'
            if "".join(claim.split()) == "".join(equality.split()):
                status = check_assertion(check)
        graph.append(Lemma(
            f"L{index}", step, claim, tuple(premises), status, item.get("global_scope") is True,
            " ".join(claim.split()) in " ".join(steps[step - 1].split()),
        ))
    return GraphExtraction(tuple(graph), "parsed", len(raw))


def prune_graph(
    graph: tuple[Lemma, ...], first_error: int, reviewed_prefix: int,
) -> tuple[set[str], tuple[tuple[Lemma, str], ...]]:
    """Propagate invalidation and admit independent global lemmas with scoped evidence."""
    invalid: set[str] = set()
    retained = []
    checked: set[str] = set()
    for node in graph:
        if first_error == node.step or node.check == "fail" or invalid.intersection(node.premises):
            invalid.add(node.id)
            continue
        if not node.global_scope or not checked.issuperset(node.premises):
            continue
        if node.check == "pass" and (
            node.step <= reviewed_prefix or node.step > first_error > 0 and not node.premises
        ):
            evidence = L1_EVIDENCE
        elif node.matches_source and node.step <= reviewed_prefix and node.step < first_error:
            evidence = L2_EVIDENCE
        else:
            continue
        retained.append((node, evidence))
        checked.add(node.id)
    return invalid, tuple(retained)
