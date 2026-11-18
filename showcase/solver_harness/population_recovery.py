"""Recover unfinished Population routes after a rejected final candidate."""

import hashlib
import json
from collections.abc import Mapping


def evidence_fingerprint(state):
    """Identify the accepted evidence supplied to final synthesis."""
    evidence = {
        "specification_version": state.get("specification_version"),
        "obligation_ledger": state.get("obligation_ledger", []),
        "obligation_evidence_ledger": state.get("obligation_evidence_ledger", []),
        "verified_results_ledger": state.get("verified_results_ledger", []),
        "accepted_results": state.get("accepted_results", []),
    }
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def review_rejected(harness, run):
    """Atomically reopen legal routes, or leave finalization to its retry limit."""
    from .population_store import PopulationConflict, command

    attempts = run["state"].get("final_solution_attempts", [])
    attempt = attempts[-1] if attempts else None
    review = attempt.get("review") if isinstance(attempt, Mapping) else None
    if (not isinstance(attempt, Mapping)
            or not isinstance(review, Mapping)
            or review.get("verdict") != "REJECT"
            or not isinstance(attempt.get("session_key"), str)):
        return run
    original = run
    while True:
        try:
            return command(
                harness, run["run_id"], "review_rejected",
                expected_revision=run["state_revision"],
                candidate_key=attempt["session_key"],
                evidence_hash=evidence_fingerprint(run["state"]),
            )
        except PopulationConflict as exc:
            if str(exc) != "population_review_revision_conflict":
                raise
            latest = harness.get_run(run["run_id"])
            if (evidence_fingerprint(latest["state"]) != evidence_fingerprint(original["state"])
                    or latest["state"].get("final_solution_attempts") != attempts
                    or latest["state"]["population"].get("freeze") != original["state"]["population"].get("freeze")
                    or latest["state"]["population"].get("owner") != original["state"]["population"].get("owner")):
                raise
            from ..run_control import check_control

            check_control()
            run = latest
