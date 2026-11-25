"""A deliberately narrow independent verifier for basic integer addition."""

import re

_PROBLEM = re.compile(r"\s*(?:compute|calculate)\s+(-?\d+)\s*\+\s*(-?\d+)\s*[.!?]?\s*", re.I)
_ANSWER = re.compile(
    r"(?:(?:final )?answer:\s*|the (?:answer|sum|result) is\s+|adding the two numbers gives\s+)?"
    r"(-?\d+)[.!]?",
    re.I,
)
_EQUATION = re.compile(r"(-?\d+)\s*\+\s*(-?\d+)\s*=\s*(-?\d+)[.!]?")


def verify_integer_addition(problem: str, answer: str) -> dict[str, object]:
    """Check a supported addition prompt against integer arithmetic, else return unknown."""

    match = _PROBLEM.fullmatch(problem)
    if match is None:
        return {
            "status": "unknown",
            "applicable": False,
            "scope": "none",
            "reason": "no_applicable_criterion",
        }

    left, right = map(int, match.groups())
    answer_line = answer.strip().rpartition("\n")[2].strip()
    standalone = _ANSWER.fullmatch(answer_line)
    equation = _EQUATION.fullmatch(answer_line)
    value = standalone.group(1) if standalone else None
    if equation and sorted(map(int, equation.groups()[:2])) == sorted((left, right)):
        value = equation.group(3)
    if value is None:
        return {
            "status": "unknown",
            "applicable": True,
            "scope": "integer arithmetic reference check",
            "reason": "answer_has_no_unambiguous_integer_candidate",
        }

    verified = int(value) == left + right
    return {
        "status": "verified" if verified else "failed",
        "applicable": True,
        "scope": "integer arithmetic reference check",
        "reason": "answer_matches_reference" if verified else "answer_differs_from_reference",
    }
