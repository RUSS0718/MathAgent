"""Commit frozen finalization independently of late physical accounting writes."""

from .storage import SolverRevisionConflictError


def commit_finalization(harness, run, event, updates):
    """Refresh only bookkeeping revisions; changed mathematics remains a CAS conflict."""
    while True:
        current = harness.get_run(run["run_id"])
        before, after = run["state"], current["state"]
        protected = (
            "problem_hash", "config_hash", "problem_spec", "specification_version",
            "plan", "steps", "proof_graph", "final_response",
            "accepted_results", "verified_results_ledger", "obligation_ledger",
            "obligation_evidence_ledger", "final_solution_attempts", "whole_solution_reviews",
            "phase", "status",
        )
        if (any(before.get(key) != after.get(key) for key in protected)
                or before["population"].get("freeze") != after["population"].get("freeze")
                or before["population"].get("owner") != after["population"].get("owner")):
            raise SolverRevisionConflictError(run["run_id"], run["state_revision"],
                                             current["state_revision"])
        try:
            return harness.commit_event(
                run["run_id"], expected_revision=current["state_revision"],
                event=event, state_updates=updates,
            )
        except SolverRevisionConflictError:
            from ..run_control import check_control

            check_control()
