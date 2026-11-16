"""Frozen, opt-in capacity for the first semantic exploration only."""

from .harness_config import SolverValidationError

VERSION = "initial-explore-v1-2048"
POLICY = {"version": VERSION}
OUTPUT_CAP = 2048


def validate_config(config):
    if "initial_explore_policy_version" not in config:
        return
    from .dependency_routing import VERSION as ROUTING_VERSION

    if config["initial_explore_policy_version"] != VERSION:
        raise SolverValidationError("initial_explore_policy_version_invalid")
    if config.get("routing_policy_version") != ROUTING_VERSION:
        raise SolverValidationError("initial_explore_requires_dependency_routing")


def is_initial(state):
    """Corrections retain the Run's original capacity and transport."""
    return (state.get("initial_explore_policy") == POLICY
            and not state.get("exploration_findings")
            and state.get("adaptive_solving", {}).get("corrections", 0) == 0)
