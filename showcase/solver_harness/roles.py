"""Role definitions, aliases and invocation ports used by dispatch and replay."""

ROLE_DEFINITIONS = {
    "explore": "Explore the problem; distinguish observations from proofs and report structured assessment. Do not alter authoritative state.",
    "reasoner": "Solve only the current objective using accepted results and relevant failures. Return a labeled StepReport; respond to the current objection during Challenge. Do not alter authoritative state.",
    "reason_noncoding": "Prove the current objective by pure reasoning, without executable tools. Return a labeled StepReport. Do not alter authoritative state.",
    "step_verifier": "Independently review the current objective and proof. Return exactly one structured verdict and concrete objections. Do not alter authoritative state or access other runs.",
    "whole_solution_verifier": "Independently review the full candidate against the original problem and proof obligations. Return ACCEPT or REJECT. Do not alter authoritative state or access other runs.",
    "meta": "Select a strategy from progress, failures and budget. Do not take over the proof, execute code or alter authoritative state.",
}

ROLE_DEFINITIONS.update(
    {
        "explore_polish": "Polish the current Explore candidate in its existing session; do not invent unsupported facts.",
        "planner": "Return a numbered executable Plan with explicit goals and earlier-step dependencies.",
        "researcher": "Perform only the bounded noncoding research task; report unverified findings and limitations.",
        "final_generator": "Synthesize a complete final answer using only accepted facts and their evidence scope.",
    }
)
ALIASES = {"meta_strategist": "meta"}


def canonical_role(role):
    return ALIASES.get(role, role)


def session_role(role):
    return {"reason_noncoding": "reasoner", "explore_polish": "explore"}.get(
        canonical_role(role), canonical_role(role)
    )


def definition(role):
    return ROLE_DEFINITIONS[canonical_role(role)]


def role_operation(harness, role):
    role = canonical_role(role)
    if role == "meta":
        port, method = harness._meta_port, "complete"
    elif role in {"step_verifier", "whole_solution_verifier"}:
        port, method = harness._verifier_port, "verify"
    else:
        port, method = harness._model_port, "complete"
    return getattr(port, method) if port is not None else None
