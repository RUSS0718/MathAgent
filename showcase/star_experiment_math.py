"""Conservative rational conclusion parsing, without evaluating expressions."""
import re
from fractions import Fraction


def rational(text):
    text = text.strip().rstrip(".。")
    wrappers = [("$$", "$$"), ("$", "$"), (r"\(", r"\)"), (r"\[", r"\]"),
                ("**", "**"), ("__", "__"), ("`", "`"), (r"\boxed{", "}")]
    while True:
        pair = next(((left, right) for left, right in wrappers
                     if text.startswith(left) and text.endswith(right)
                     and len(text) >= len(left) + len(right)), None)
        if pair is None:
            break
        left, right = pair
        text = text[len(left):-len(right)].strip()
    match = re.fullmatch(r"\\(?:d?frac)\s*\{\s*([+-]?\d+)\s*\}\s*\{\s*([+-]?\d+)\s*\}", text)
    if match:
        numerator, denominator = match.groups()
    else:
        match = re.fullmatch(r"([+-]?\d+)(?:\s*/\s*([+-]?\d+))?", text)
        if not match:
            return None
        numerator, denominator = match.groups()
    try:
        return Fraction(int(numerator), int(denominator or 1))
    except (ValueError, ZeroDivisionError):
        return None


def compare_conclusion(answer, expected, span=None):
    """Unsupported/ambiguous prose remains undecided; never scan intermediate values."""
    # Explicit final markers take precedence over any earlier calculation.
    markers = list(re.finditer(r"(?:final\s+answer|answer|最终答案|最终结果|答案)\s*[:：=]\s*", answer, re.I))
    conclusion = answer[markers[-1].end():].strip() if markers else answer.strip()
    value = rational(conclusion)
    # An explicit parseable final conclusion cannot be replaced by an earlier value.
    if value is None and span is not None:
        if (not isinstance(span, dict) or set(span) != {"start", "end"}
                or type(span["start"]) is not int or type(span["end"]) is not int
                or not 0 <= span["start"] < span["end"] <= len(answer)):
            return "undecided"
        value = rational(answer[span["start"]:span["end"]])
    target = rational(expected)
    if value is None or target is None:
        return "undecided"
    return "pass" if value == target else "reject"
