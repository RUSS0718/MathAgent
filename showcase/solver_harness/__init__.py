"""Explicit Showcase Solver Harness API."""

from .aprs import decide as decide_aprs
from .aprs import evaluate as evaluate_route
from .aprs import pareto_set, rate_routes
from .explore import ModelPort, ScriptedModelPort
from .harness import (
    SolverEventConflictError,
    SolverHarness,
    SolverHarnessError,
    SolverIdentityError,
    SolverRevisionConflictError,
    SolverRunNotFoundError,
    SolverValidationError,
)
from .meta import MetaPort, ScriptedMetaPort
from .replay import replay_snapshot
from .result import export_result
from .review import ScriptedVerifierPort, VerifierPort
from .routes import frontier_digest, plan_frontier
from .tool_ports import RegistryToolPort, ScriptedToolPort, ToolPort

__all__ = [
    "SolverHarness",
    "export_result",
    "replay_snapshot",
    "ToolPort",
    "ScriptedToolPort",
    "RegistryToolPort",
    "SolverHarnessError",
    "SolverEventConflictError",
    "SolverIdentityError",
    "SolverRevisionConflictError",
    "SolverRunNotFoundError",
    "SolverValidationError",
    "MetaPort",
    "ScriptedMetaPort",
    "ModelPort",
    "ScriptedModelPort",
    "ScriptedVerifierPort",
    "VerifierPort",
    "decide_aprs",
    "evaluate_route",
    "pareto_set",
    "rate_routes",
    "frontier_digest",
    "plan_frontier",
]
