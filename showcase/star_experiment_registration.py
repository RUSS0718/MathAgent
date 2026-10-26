"""Spec #87 preregistration. Solver prompts contain no independent answers."""

import hashlib
import json
from fractions import Fraction

VERSION = "rob87-round-v1"
E1 = dict(max_model_calls=6, max_http_attempts=8, max_tool_calls=1,
          max_tokens=32768, max_runtime_seconds=300)
E2 = dict(max_model_calls=12, max_http_attempts=16, max_tool_calls=3,
          max_tokens=65536, max_runtime_seconds=600)
ROUND = dict(runs=10, logical_calls=96, http_attempts=128, tool_calls=22,
             charged_tokens=524288, wall_time_seconds=4800, preflights=12,
             tools_including_environment=34)
CONDITIONS = dict(model="intern-s2", timeout=180, max_tokens=8192,
                  retry=3, thinking_mode=True, temperature=0.2,
                  solver_mode="star_reference", verification_mode="auto")
REVIEW_RULES = {
    "finite": "Independent deterministic oracle plus a separate review of every registered proof obligation; numerical agreement alone is insufficient.",
    "sharp": "Independent mathematical review: lower bound on the entire simplex; upper bound including boundary and interior; equality at vertices for zero and at (1/3,1/3,1/3) for 7/27. A numerical search is insufficient.",
    "review": "Reviewer must bind the exact question and delivered-answer hashes, decide each obligation, identify themselves, and give reasons. Missing or inconclusive review is undecided; same-model self-review is not independent truth.",
    "e2": "At least one independently accepted complete answer per class; every executed Run must retain truthful state/evidence. Natural fastpath counts for correctness but never for the separate nonfastpath requirement.",
}

# Original public text checked directly on 2026-10-26; task additions are explicit.
QUESTIONS = {
    "multiply": dict(source="user/synthetic", original="计算 17×23 并简要解释",
                     obligations=["correct_result", "explanation"]),
    "fractions": dict(source="user/synthetic", original="计算 3/4+1/6 并简要解释",
                      obligations=["correct_result", "explanation"]),
    "digit_cancel": dict(source="https://projecteuler.net/minimal=33",
        original=("The fraction 49/98 is a curious fraction, as an inexperienced mathematician "
                  "in attempting to simplify it may incorrectly believe that 49/98 = 4/8, "
                  "which is correct, is obtained by cancelling the 9s.\n"
                  "We shall consider fractions like, 30/50 = 3/5, to be trivial examples.\n"
                  "There are exactly four non-trivial examples of this type of fraction, less "
                  "than one in value, and containing two digits in the numerator and denominator.\n"
                  "If the product of these four fractions is given in its lowest common terms, "
                  "find the value of the denominator."),
        addition="Give a complete finite enumeration argument and justify the reduced product.",
        obligations=["correct_result", "nontrivial_digit_rule", "exhaustive_domain", "reduced_product"]),
    "sharp": dict(source="https://www.imo-official.org/assets/documents/problems/1984/1984_eng.pdf",
        original="Prove that 0 ≤ yz + zx + xy − 2xyz ≤ 7/27, where x, y and z are non-negative real numbers for which x + y + z = 1.",
        addition="Justify both bounds and their equality cases.",
        obligations=["lower_bound", "upper_bound", "equality_cases", "entire_domain"]),
    "partitions": dict(source="https://projecteuler.net/minimal=76",
        original=("It is possible to write five as a sum in exactly six different ways:\n"
                  "4 + 1\n3 + 2\n3 + 1 + 1\n2 + 2 + 1\n2 + 1 + 1 + 1\n1 + 1 + 1 + 1 + 1\n"
                  "How many different ways can one hundred be written as a sum of at least two positive integers?"),
        addition="Derive a recurrence, justify unordered counting and completeness, and evaluate it.",
        obligations=["correct_result", "recurrence", "no_order_duplicates", "exclude_single_part", "evaluation"]),
}


def digest(value):
    data = value.encode("utf-8") if isinstance(value, str) else json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def oracle(question):
    """Independent deterministic values; never called while building solver messages."""
    if question == "multiply":
        return str(17 * 23)
    if question == "fractions":
        return str(Fraction(3, 4) + Fraction(1, 6))
    if question == "digit_cancel":
        found = set()
        for n in range(10, 100):
            for d in range(n + 1, 100):
                for i in range(2):
                    for j in range(2):
                        a, b = str(n), str(d)
                        if a[i] == b[j] != "0" and b[1-j] != "0" and Fraction(n, d) == Fraction(int(a[1-i]), int(b[1-j])):
                            found.add(Fraction(n, d))
        product = Fraction(1)
        for value in found:
            product *= value
        return str(product.denominator)
    if question == "partitions":
        # Euler's pentagonal recurrence; independent of a solver's coin-change DP.
        p = [1]
        for n in range(1, 101):
            value, k = 0, 1
            while k * (3*k-1) // 2 <= n:
                for g in (k*(3*k-1)//2, k*(3*k+1)//2):
                    if g <= n:
                        value += (-1)**(k+1) * p[n-g]
                k += 1
            p.append(value)
        return str(p[100] - 1)
    if question == "sharp":
        return None  # Independent mathematical review required, no numerical proof proxy.
    raise ValueError("unknown_registered_question")


def registration():
    questions = {}
    for key, value in QUESTIONS.items():
        prompt = value["original"] + ("\n" + value["addition"] if "addition" in value else "")
        questions[key] = {**value, "prompt": prompt,
                          "original_sha256": digest(value["original"]), "prompt_sha256": digest(prompt)}
    order = [("E1", q, t) for q in ("multiply", "fractions") for t in ("nonstream", "stream")]
    order += [("E2", q, "nonstream") for _ in range(2) for q in ("digit_cancel", "sharp", "partitions")]
    record = dict(version=VERSION, questions=questions, conditions=CONDITIONS,
                  round_limits=ROUND, source_checked="2026-10-26", review_rules=REVIEW_RULES, schedule=[
                      dict(index=i, stage=s, question=q, transport=t, limits=dict(E1 if s == "E1" else E2))
                      for i, (s, q, t) in enumerate(order)])
    return json.loads(json.dumps(record, ensure_ascii=False))
