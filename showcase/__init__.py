"""Product-side entry points for the explicit ``showcase_mvp`` profile.

The package is intentionally separate from the root ``user_agent`` module.
Importing the official profile therefore never loads this package or its
future product-only dependencies.
"""

from .adapters import (
    AdapterError,
    ContinuationTransport,
    DeepAgentsAdapter,
    InternAgentAdapter,
    InternChatModel,
    InternModelAdapter,
    ModelContinuationTransport,
    ModelResponse,
    ToolRequest,
)
from .evidence import EvidencePackExporter
from .graph import (
    AgentDecision,
    GraphDependencyError,
    LangGraphExecutionLoop,
    LoopBudget,
    ToolExecutionResult,
)
from .polynomial import PolynomialChecker
from .profile import OFFICIAL_PROFILE, SHOWCASE_PROFILE, ProfileBoundaryError
from .replay import ReplayValidationError, load_replay, write_sample_replay
from .run_service import (
    AgentAdapter,
    AgentResult,
    FakeAgentAdapter,
    RunNotFoundError,
    RunRequest,
    RunResumeUnavailable,
    RunService,
    RunValidationError,
)
from .storage import PersistenceError, SQLiteStore
from .tools import PythonMathTool, ToolRegistry, ToolSpec
from .verification import LightweightVerificationHook, VerificationResult
from .vision import ImageAsset, VisionAdapter, VisionInputError, VisionResult


def create_app(*args, **kwargs):
    """Lazily build the Flask Showcase app without loading it for official code."""

    from .flask_app import create_app as _create_app

    return _create_app(*args, **kwargs)

__all__ = [
    "AgentAdapter",
    "AgentDecision",
    "AdapterError",
    "ContinuationTransport",
    "AgentResult",
    "FakeAgentAdapter",
    "GraphDependencyError",
    "DeepAgentsAdapter",
    "InternAgentAdapter",
    "InternChatModel",
    "InternModelAdapter",
    "LangGraphExecutionLoop",
    "LoopBudget",
    "OFFICIAL_PROFILE",
    "ProfileBoundaryError",
    "PersistenceError",
    "RunNotFoundError",
    "RunResumeUnavailable",
    "RunRequest",
    "RunService",
    "RunValidationError",
    "SHOWCASE_PROFILE",
    "SQLiteStore",
    "ToolExecutionResult",
    "ToolRequest",
    "ModelResponse",
    "ModelContinuationTransport",
    "ToolRegistry",
    "ToolSpec",
    "PythonMathTool",
    "PolynomialChecker",
    "ImageAsset",
    "VisionAdapter",
    "VisionInputError",
    "VisionResult",
    "EvidencePackExporter",
    "create_app",
    "LightweightVerificationHook",
    "VerificationResult",
    "ReplayValidationError",
    "load_replay",
    "write_sample_replay",
]
