"""Original project protocols derived from STAR Core v1.2 sections 7 and 11.8.

These are project-authored instructions, not copies of upstream skill texts.
"""

from collections.abc import Mapping
from typing import Any

# Each protocol states its trigger, input/output contract, and authority boundary.
PROTOCOLS = {
    "exploration-protocol": {
        "trigger": "explore role",
        "input": "problem, previous worked/failed findings, remaining budget",
        "output": "assessment, worked, failed, candidates, optional solution_candidate",
        "permissions": ["read_state", "read_ledger"],
        "instructions": "Try small examples and record failed approaches. Return exactly SOLVED, PARTIALLY_SOLVED, NEED_PLAN or UNKNOWN. SOLVED requires a complete candidate; partial progress must identify the remaining gap. Respect the supplied call budget.",
    },
    "verifier-review-protocol": {
        "trigger": "step or whole-solution verifier",
        "input": "objective, report/candidate, accepted evidence",
        "output": "goal_gate, logic_gate, verdict, objection, retained_results",
        "permissions": ["read_state", "read_ledger"],
        "instructions": "Check Goal Gate YES/PARTIAL/NO before Logic Gate PASS/FAIL/UNCERTAIN. Step verdict is ACCEPT, CHALLENGE, TRACE_BACK or PROPOSE_REPLAN; ACCEPT requires YES and PASS. TRACE_BACK supplies a legal step index. State a specific objection and evidence refs for retained results. For step review of an answer-bearing, sharp, optimal, extremal or necessary-and-sufficient claim, declare answer_claim with its zero-based claim_index, both_directions_proved, assumptions and approach. If either direction is missing, set both_directions_proved=false: the controller must run independent noncoding falsification before acceptance. NOT_FOUND cannot promote the missing direction from Conjecture to Lemma. Whole-solution verdict is ACCEPT or REJECT and requires all goals and proof obligations.",
    },
    "verification-tag-protocol": {
        "trigger": "reasoner report or verifier review",
        "input": "nontrivial claims and available evidence refs",
        "output": "one verification label per claim",
        "permissions": ["read_ledger"],
        "instructions": "Use verified only for a claim covered by actual matching tool evidence, easy-verify for a reproducible finite computation, and hard-verify for proof obligations. Numerical examples cannot certify a universal claim. Never invent evidence refs or promote a model assertion to tool evidence.",
    },
    "meta-intervention-protocol": {
        "trigger": "meta role",
        "input": "cross-attempt progress, failures, budget",
        "output": "CONTINUE, TRACE_BACK, APPROVE_REPLAN or ABORT with reason",
        "permissions": ["read_state", "read_ledger"],
        "instructions": "Choose one strategy decision without taking over the proof. Give a legal target for TRACE_BACK. APPROVE_REPLAN states failure causes, forbidden directions and reusable results. ABORT when no justified continuation remains within budget. Never execute code or mutate authoritative state.",
    },
    "math-solving-strategies": {
        "trigger": "meta selects mathematical method",
        "input": "problem structure and failed methods",
        "output": "selected method, applicability, concrete next objective",
        "permissions": ["read_ledger"],
        "instructions": "Compare induction for recursive integer structure, contradiction for impossible assumptions, invariants for transformations, extremal arguments for finite ordered configurations, and construction for existence. Explain why the selected method fits and where its assumptions must be proved; avoid repeating a confirmed failed direction.",
    },
    "construct-counterexamples": {
        "trigger": "explicit suspected false claim",
        "input": "suspected claim, domain and constraints",
        "output": "validated counterexample or bounded unsuccessful search",
        "permissions": ["read_ledger"],
        "instructions": "Check smallest admissible instances, zero/sign/degenerate boundaries and equality cases. Verify every original assumption on a proposed counterexample and show the violated conclusion. A failed finite search is not proof; report the searched bounds.",
    },
    "code-issue-resolution": {
        "trigger": "recorded timeout, execution error or output mismatch",
        "input": "sanitized tool failure and retry budget",
        "output": "failure class, recovery action, bounded retry proposal",
        "permissions": ["read_state"],
        "instructions": "Classify timeout, execution_error or output_mismatch. Reduce work for timeout, isolate the failing operation for execution errors, and inspect input/units/invariants for mismatch. Propose at most one retry within remaining budget, otherwise return blocked. Do not request shell, network or cross-run files.",
    },
}


def select_skills(role: str, request: Mapping[str, Any]) -> list[str]:
    selected = []
    if role == "explore":
        selected.append("exploration-protocol")
    if role in {"step_verifier", "whole_solution_verifier"}:
        selected.append("verifier-review-protocol")
    if role in {"reasoner", "reason_noncoding", "step_verifier", "whole_solution_verifier"}:
        selected.append("verification-tag-protocol")
    if role in {"meta", "meta_strategist"}:
        selected.extend(["meta-intervention-protocol", "math-solving-strategies"])
    if request.get("suspected_false_claim") is True:
        selected.append("construct-counterexamples")
    if request.get("tool_failure") in {"timeout", "execution_error", "output_mismatch"}:
        selected.append("code-issue-resolution")
    return selected
