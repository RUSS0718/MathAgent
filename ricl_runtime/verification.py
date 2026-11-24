"""A deliberately narrow independent verifier for basic integer addition."""

import re

_PROBLEM = re.compile(r"\s*(?:compute|calculate)\s+(-?\d+)\s*\+\s*(-?\d+)\s*[.!?]?\s*", re.I)
_INTEGER = re.compile(r"-?\d+")


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

    expected = int(match.group(1)) + int(match.group(2))
    answer_numbers = _INTEGER.findall(answer)
    if not answer_numbers:
        return {
            "status": "unknown",
            "applicable": True,
            "scope": "integer arithmetic reference check",
            "reason": "answer_has_no_integer_candidate",
        }

    verified = int(answer_numbers[-1]) == expected
    return {
        "status": "verified" if verified else "failed",
        "applicable": True,
        "scope": "integer arithmetic reference check",
        "reason": "answer_matches_reference" if verified else "answer_differs_from_reference",
    }
