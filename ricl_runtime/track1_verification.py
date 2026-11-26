"""Evaluate bounded exact assertions and validate coarse dependency graphs."""

import ast
import json
import operator
from dataclasses import dataclass
from fractions import Fraction
from math import comb, gcd

_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
_FUNCTIONS = {"choose": comb, "gcd": gcd}
CHECK_FORMAT = (
    'A check is {"step": 1, "lhs": "choose(10, 2)", "rhs": "45", "at": null}. '
    "Use exact integer arithmetic, fractions, %, ** (exponents -12 to 12), choose(n,k), "
    "and gcd(a,b). For a claimed universal equality, integer samples such as "
    '"at":{"x":3} can disprove it but cannot establish it. '
    "Quote an equality actually asserted in that step, including its erroneous side as written. "
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
            if any(v.denominator != 1 or abs(v) > 256 for v in (a, b)):
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
            expressions.append(_number(tree.body, point or {}))
        if expressions[0] != expressions[1]:
            return "fail"
        return "pass" if point is None else "uncheckable"
    except (KeyError, ValueError, SyntaxError, TypeError, ArithmeticError):
        return "uncheckable"


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


def lemma_graph(text: str, step_count: int) -> tuple[Lemma, ...]:
    """Require topological dependencies and evidence tied to a source step."""
    raw = json_object(text).get("lemmas")
    if not isinstance(raw, list) or not 5 <= len(raw) <= 10:
        return ()
    graph = []
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            return ()
        step, claim, premises = item.get("step"), item.get("claim"), item.get("premises")
        if (
            item.get("id") != f"L{index}" or type(step) is not int or not 1 <= step <= step_count
            or not isinstance(claim, str) or not 0 < len(claim.strip()) <= 400
            or not isinstance(premises, list)
            or any(p not in [node.id for node in graph] for p in premises)
            or len(set(premises)) != len(premises)
        ):
            return ()
        check = item.get("check")
        if isinstance(check, dict) and check.get("step") == step:
            # Only a matching closed equality may confer positive reusable evidence.
            equality = f'{check.get("lhs")} = {check.get("rhs")}'
            status = check_assertion(check)
            if status == "pass" and "".join(claim.split()) != "".join(equality.split()):
                status = "uncheckable"
        else:
            status = "uncheckable"
        graph.append(Lemma(f"L{index}", step, claim, tuple(premises), status,
                           item.get("global_scope") is True))
    return tuple(graph)


def prune_graph(
    graph: tuple[Lemma, ...], first_error: int, reviewed_prefix: int,
) -> tuple[set[str], tuple[Lemma, ...]]:
    """Propagate invalidation down dependency edges and retain global exact lemmas."""
    invalid: set[str] = set()
    retained = []
    checked: set[str] = set()
    for node in graph:
        if first_error == node.step or node.check == "fail" or invalid.intersection(node.premises):
            invalid.add(node.id)
        elif node.check == "pass" and node.global_scope and (
            node.step <= reviewed_prefix or (node.step > first_error > 0 and not node.premises)
        ) and checked.issuperset(node.premises):
            retained.append(node)
            checked.add(node.id)
    return invalid, tuple(retained)
