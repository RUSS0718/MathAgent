"""Evaluate bounded exact assertions and validate coarse dependency graphs."""

import ast
import json
import math
import operator
import re
from dataclasses import dataclass
from fractions import Fraction
from math import comb, factorial, gcd, lcm
from typing import Any

_OPERATORS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.Div: operator.truediv, ast.Mod: operator.mod}
_FUNCTIONS = {"choose": comb, "gcd": gcd, "lcm": lcm}
_MATH_DELIM_RE = re.compile(
    r"\$\$?|\\\[|\\\]|\\\(|\\\)|\\displaystyle|\\left|\\right|\\(?:,|;|!|quad|qquad)|`|\*\*|__"
)
_FRAC_NORM_RE = re.compile(r"\\[dt]?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_MATH_TOKEN_RE = re.compile(r"[a-z0-9]+|[=+\-*/<>^]")
_OP_SPACE_RE = re.compile(r"\s*([=+\-*/<>(),])\s*")
_WS_RE = re.compile(r"\s+")
L1_EVIDENCE = "L1-Executable-Verified"
L2_EVIDENCE = "L2-Reviewed"
CHECK_FORMAT = (
    'A check is {"step": 1, "lhs": "choose(10, 2)", "rhs": "45", "at": null}. '
    "Use exact integer arithmetic, fractions, %, ** (exponents -12 to 12), abs, sqrt, "
    "factorial, pi, sin, cos, choose(n,k), gcd(a,b), and lcm(a,b). For a claimed universal "
    'equality, integer samples such as "at":{"x":3} can disprove it but cannot establish it. '
    'Use "variable":"x" or "variables":["x","y"] (with at null) to verify a symbolic '
    "identity. For a value or equation root explicitly claimed in the step, substitute the "
    'stated values into a closed equality (e.g. "2*3+1 = 7" for x=3 in 2*x+1=7). '
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
        case ast.Call(func=ast.Name(id="abs"), args=[arg], keywords=[]):
            result = abs(_number(arg, bindings))
        case ast.Call(func=ast.Name(id="factorial"), args=[arg], keywords=[]):
            n = _number(arg, bindings)
            if n.denominator != 1 or not 0 <= n <= 64:
                raise ValueError("unsupported factorial argument")
            result = Fraction(factorial(int(n)))
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


def _sympy_expr(node: ast.AST, bindings: dict[str, int], free_vars: set[str], sp: Any) -> Any:
    """Translate a whitelisted AST into SymPy without calling eval/sympify on strings."""
    match node:
        case ast.Constant(value=value) if type(value) is int and value.bit_length() <= 128:
            return sp.Integer(value)
        case ast.Name(id=name):
            if name in bindings:
                return sp.Integer(bindings[name])
            if name == "pi":
                return sp.pi
            if name == "E":
                return sp.E
            if name in free_vars:
                return sp.Symbol(name)
            raise ValueError("unsupported symbol")
        case ast.UnaryOp(op=ast.UAdd() | ast.USub(), operand=operand):
            val = _sympy_expr(operand, bindings, free_vars, sp)
            return -val if isinstance(node.op, ast.USub) else val
        case ast.BinOp(left=left, op=op, right=right):
            a = _sympy_expr(left, bindings, free_vars, sp)
            b = _sympy_expr(right, bindings, free_vars, sp)
            if isinstance(op, ast.Add):
                return a + b
            if isinstance(op, ast.Sub):
                return a - b
            if isinstance(op, ast.Mult):
                return a * b
            if isinstance(op, ast.Div):
                if b == 0:
                    raise ValueError("division by zero")
                return a / b
            if isinstance(op, ast.Mod):
                if a.is_Integer and b.is_Integer and b != 0:
                    return a % b
                raise ValueError("unsupported modulo")
            if isinstance(op, ast.Pow):
                if not b.is_Rational or int(b.q) > 6 or abs(b) > 12:
                    raise ValueError("unsupported symbolic exponent")
                return a ** b
            raise ValueError("unsupported binary operator")
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]):
            vals = [_sympy_expr(arg, bindings, free_vars, sp) for arg in args]
            if len(vals) == 1:
                x = vals[0]
                if name == "sqrt":
                    return sp.sqrt(x)
                if name == "abs":
                    return sp.Abs(x)
                if name == "sin":
                    return sp.sin(x)
                if name == "cos":
                    return sp.cos(x)
                if name == "tan":
                    return sp.tan(x)
                if name == "log":
                    return sp.log(x)
                if name == "exp":
                    return sp.exp(x)
                if name == "factorial":
                    if x.is_Integer and 0 <= int(x) <= 64:
                        return sp.factorial(int(x))
                    raise ValueError("unsupported factorial argument")
            if len(vals) == 2:
                a, b = vals
                if name in ("choose", "binomial"):
                    if a.is_Integer and b.is_Integer and max(abs(int(a)), abs(int(b))) <= 256:
                        return sp.binomial(int(a), int(b))
                    raise ValueError("unsupported binomial argument")
                if name in ("gcd", "lcm"):
                    if a.is_Integer and b.is_Integer:
                        return sp.Integer(_FUNCTIONS[name](int(a), int(b)))
                    raise ValueError("unsupported integer function")
                if name == "Rational":
                    if a.is_Integer and b.is_Integer and b != 0:
                        return sp.Rational(int(a), int(b))
                    raise ValueError("unsupported Rational argument")
                if name == "root":
                    if b.is_Integer and 2 <= int(b) <= 6:
                        return sp.root(a, int(b))
                    raise ValueError("unsupported root index")
            raise ValueError("unsupported call")
        case _:
            raise ValueError("unsupported symbolic expression")


def _check_sympy(
    left: ast.AST, right: ast.AST, point: dict[str, int] | None, var_names: list[str],
) -> str:
    """Verify closed symbolic identities or disprove via exact/high-precision witness."""
    try:
        import sympy as sp
    except ImportError:
        return "uncheckable"
    bindings = point or {}
    free_vars = set(var_names)
    try:
        diff = _sympy_expr(left, bindings, free_vars, sp) - _sympy_expr(right, bindings, free_vars, sp)
        if diff.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
            return "uncheckable"
        expanded = sp.expand(diff)
        if expanded == 0:
            return "pass" if point is None else "uncheckable"
        simplified = sp.simplify(expanded)
        if simplified == 0 or simplified.is_zero is True:
            return "pass" if point is None else "uncheckable"
        if not simplified.free_symbols:
            if simplified.is_nonzero is True:
                return "fail"
            num = complex(simplified.evalf(30))
            if math.isfinite(num.real) and math.isfinite(num.imag) and abs(num) > 1e-12:
                return "fail"
            return "uncheckable"
        if point is None and var_names:
            for base in (2, 3, -2):
                subs = {sp.Symbol(v): base + i for i, v in enumerate(var_names)}
                sample = simplified.subs(subs)
                if sample.has(sp.zoo, sp.oo, -sp.oo, sp.nan):
                    continue
                if sample.is_nonzero is True:
                    return "fail"
                num = complex(sample.evalf(30))
                if math.isfinite(num.real) and math.isfinite(num.imag) and abs(num) > 1e-12:
                    return "fail"
        return "uncheckable"
    except (ValueError, TypeError, ArithmeticError, RecursionError):
        return "uncheckable"


def check_assertion(check: dict) -> str:
    """Check an exact equality or search for a counterexample at a supplied point."""
    try:
        point = check.get("at")
        variable = check.get("variable")
        variables = check.get("variables")
        if variable is not None and variables is not None:
            return "uncheckable"
        var_names: list[str] = []
        if variable is not None:
            if (
                point is not None or not isinstance(variable, str)
                or len(variable) > 8 or not variable.isidentifier()
                or variable in ("pi", "E")
            ):
                return "uncheckable"
            var_names = [variable]
        elif variables is not None:
            if (
                point is not None or not isinstance(variables, list)
                or not 1 <= len(variables) <= 3
                or any(
                    not isinstance(v, str) or len(v) > 8 or not v.isidentifier() or v in ("pi", "E")
                    for v in variables
                )
            ):
                return "uncheckable"
            var_names = list(dict.fromkeys(variables))
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
        left, right = expressions
        if len(var_names) <= 1:
            try:
                if var_names:
                    var = var_names[0]
                    degree = max(_degree(expr, var) for expr in expressions)
                    if degree > 12:
                        return "uncheckable"
                    return "pass" if all(
                        _number(left, {var: x}) == _number(right, {var: x})
                        for x in range(degree + 1)
                    ) else "fail"
                if _number(left, point or {}) != _number(right, point or {}):
                    return "fail"
                return "pass" if point is None else "uncheckable"
            except (ValueError, ArithmeticError):
                return _check_sympy(left, right, point, var_names)
        return _check_sympy(left, right, point, var_names)
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
        if isinstance(value, dict):
            return value
    except (ValueError, RecursionError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                return value
        except (ValueError, RecursionError):
            return {}
    return {}


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


def _normalize_math_text(text: str) -> str:
    """Normalize lightweight markdown and LaTeX spacing for source-quote verification."""
    cleaned = text.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    cleaned = cleaned.replace("\\cdot", "*").replace("\\times", "*")
    cleaned = _MATH_DELIM_RE.sub(" ", cleaned).casefold()
    cleaned = _OP_SPACE_RE.sub(r"\1", cleaned)
    return _WS_RE.sub(" ", cleaned).strip(" .,:;")


def _matches_source(candidate: str, source: str) -> bool:
    """Verify whether a candidate proposition aligns verbatim or after light math normalization."""
    norm_cand = _normalize_math_text(candidate)
    norm_src = _normalize_math_text(source)
    if len(norm_cand) >= 3 and norm_cand in norm_src:
        return True
    if len(norm_cand) < 12:
        return False
    cand_tokens = _MATH_TOKEN_RE.findall(norm_cand)
    src_token_set = set(_MATH_TOKEN_RE.findall(norm_src))
    if len(cand_tokens) < 5:
        return False
    src_digits = set(re.findall(r"\d+", norm_src))
    if not set(re.findall(r"\d+", norm_cand)).issubset(src_digits):
        return False
    overlap = sum(1 for tok in cand_tokens if tok in src_token_set)
    return overlap / len(cand_tokens) >= 0.85


def _norm_eq_expr(text: str) -> str:
    """Canonicalize simple LaTeX and Python equations for claim-to-check grounding."""
    out = text.replace("**", "^").replace("\\cdot", "*").replace("\\times", "*")
    out = _MATH_DELIM_RE.sub("", out)
    for _ in range(2):
        out, n = _FRAC_NORM_RE.subn(r"(\1)/(\2)", out)
        if n == 0:
            break
    out = out.replace("$", "").replace("*", "")
    out = re.sub(r"\s+", "", out).casefold()
    return re.sub(r"\(([a-z0-9]+)\)", r"\1", out)


def _check_matches_claim(claim: str, lhs: str, rhs: str) -> bool:
    """Verify that an executable check matches the lemma claim without allowing spoofed checks."""
    equality = f"{lhs} = {rhs}"
    if "".join(claim.split()) == "".join(equality.split()):
        return True
    norm_claim = _norm_eq_expr(claim)
    norm_eq = _norm_eq_expr(equality)
    return bool(norm_eq) and (norm_eq == norm_claim or (len(norm_eq) >= 5 and norm_eq in norm_claim))


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
        if isinstance(check, dict):
            check_step = check.get("step", step)
            lhs, rhs = check.get("lhs"), check.get("rhs")
            if (
                type(check_step) is int
                and check_step == step
                and isinstance(lhs, str)
                and isinstance(rhs, str)
                and _check_matches_claim(claim, lhs, rhs)
            ):
                status = check_assertion(check)
        source = steps[step - 1]
        quote = item.get("source_quote")
        if status == "uncheckable" and isinstance(quote, str) and 0 < len(quote.strip()) <= 400:
            if _matches_source(quote, source):
                claim = quote.strip()
        graph.append(Lemma(
            f"L{index}", step, claim, tuple(premises), status, item.get("global_scope") is True,
            _matches_source(claim, source),
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
            node.step <= reviewed_prefix or not node.premises or (first_error > 0 and node.step > first_error)
        ):
            evidence = L1_EVIDENCE
        elif node.matches_source and node.step <= reviewed_prefix and (first_error == 0 or node.step < first_error):
            evidence = L2_EVIDENCE
        else:
            continue
        retained.append((node, evidence))
        checked.add(node.id)
    return invalid, tuple(retained)
