"""Strict, exact checker for the v0.2 one-variable polynomial contract."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from fractions import Fraction
from typing import Any

_RATIONAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:/(?:[1-9][0-9]*))?\Z")
_VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class PolynomialChecker:
    """Validate and evaluate only the explicitly structured polynomial schema."""

    def check(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        evidence_id = _evidence_id(payload)
        result: dict[str, Any] = {
            "checker": "polynomial_check",
            "evidence_id": evidence_id,
            "input_summary": _input_summary(payload),
            "candidates": [],
            "duplicates": [],
            "candidate_status": "unknown",
            "coverage_status": "unknown",
            "limitations": ["仅检查候选代回、重复项和定义域；不证明完整解集。"],
        }
        try:
            coefficients = _parse_coefficients(payload)
            domain = _parse_domain(payload)
            candidates = _parse_candidates(payload)
        except (TypeError, ValueError) as exc:
            result["limitations"].append(str(exc))
            return result

        seen: set[Fraction] = set()
        duplicate_text: list[str] = []
        checks: list[dict[str, Any]] = []
        for candidate_text, candidate in candidates:
            duplicate = candidate in seen
            if duplicate and candidate_text not in duplicate_text:
                duplicate_text.append(candidate_text)
            seen.add(candidate)
            residual = sum(
                coefficient * candidate**power
                for power, coefficient in enumerate(reversed(coefficients))
            )
            in_domain = _in_domain(candidate, domain)
            item_status = "conflict" if residual != 0 or duplicate else ("unknown" if not in_domain else "pass")
            checks.append({
                "candidate": candidate_text,
                "residual": _fraction_text(residual),
                "in_domain": in_domain,
                "duplicate": duplicate,
                "status": item_status,
            })
        result["candidates"] = checks
        result["duplicates"] = duplicate_text
        if any(item["status"] == "conflict" for item in checks):
            result["candidate_status"] = "conflict"
            result["coverage_status"] = "conflict"
        elif any(item["status"] == "unknown" for item in checks):
            result["candidate_status"] = "unknown"
        else:
            result["candidate_status"] = "pass"
        return result


def _parse_coefficients(payload: Mapping[str, Any]) -> list[Fraction]:
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1:
        raise ValueError("schema_version_unsupported")
    if set(payload) - {"schema_version", "variable", "coefficients", "domain", "candidates"}:
        raise ValueError("schema_fields_invalid")
    variable = payload.get("variable")
    if not isinstance(variable, str) or not _VARIABLE.fullmatch(variable):
        raise ValueError("variable_invalid")
    raw = payload.get("coefficients")
    if not isinstance(raw, list) or not 2 <= len(raw) <= 5:
        raise ValueError("degree_out_of_range")
    if raw[0] == "0":
        raise ValueError("leading_zero_coefficient")
    return [_parse_rational(value, "coefficient") for value in raw]


def _parse_candidates(payload: Mapping[str, Any]) -> list[tuple[str, Fraction]]:
    raw = payload.get("candidates")
    if not isinstance(raw, list) or not raw:
        raise ValueError("candidates_invalid")
    parsed: list[tuple[str, Fraction]] = []
    for value in raw:
        if not isinstance(value, str):
            raise ValueError("candidate_invalid")
        parsed.append((value, _parse_rational(value, "candidate")))
    return parsed


def _parse_domain(payload: Mapping[str, Any]) -> tuple[str, Fraction | None, Fraction | None, bool, bool]:
    domain = payload.get("domain")
    if not isinstance(domain, Mapping):
        raise ValueError("domain_invalid")
    kind = domain.get("kind")
    if kind == "real":
        return ("real", None, None, True, True)
    if kind != "interval":
        raise ValueError("domain_unsupported")
    left = _parse_rational(domain.get("left"), "domain_endpoint")
    right = _parse_rational(domain.get("right"), "domain_endpoint")
    left_closed = domain.get("left_closed", True)
    right_closed = domain.get("right_closed", True)
    if not isinstance(left_closed, bool) or not isinstance(right_closed, bool) or left > right:
        raise ValueError("domain_interval_invalid")
    return ("interval", left, right, left_closed, right_closed)


def _parse_rational(value: Any, label: str) -> Fraction:
    if not isinstance(value, str) or not _RATIONAL.fullmatch(value):
        raise ValueError(f"{label}_not_rational")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{label}_not_rational") from exc


def _in_domain(value: Fraction, domain: tuple[str, Fraction | None, Fraction | None, bool, bool]) -> bool:
    kind, left, right, left_closed, right_closed = domain
    if kind == "real":
        return True
    assert left is not None and right is not None
    return (value > left or (left_closed and value == left)) and (
        value < right or (right_closed and value == right)
    )


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _input_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"kind": "invalid"}
    return {
        "schema_version": payload.get("schema_version"),
        "variable": payload.get("variable") if isinstance(payload.get("variable"), str) else None,
        "coefficient_count": len(payload.get("coefficients", [])) if isinstance(payload.get("coefficients"), list) else None,
        "domain_kind": payload.get("domain", {}).get("kind") if isinstance(payload.get("domain"), Mapping) else None,
        "candidate_count": len(payload.get("candidates", [])) if isinstance(payload.get("candidates"), list) else None,
    }


def _evidence_id(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "ev_poly_" + hashlib.sha256(encoded).hexdigest()[:16]


__all__ = ["PolynomialChecker"]
