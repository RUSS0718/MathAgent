"""Explicit Showcase Solver Harness API."""

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
]
