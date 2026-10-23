"""Build the opt-in STAR runtime from trusted local server configuration."""

import os
from pathlib import Path

from .run_budget import RunBudgetLimits
from .star_product_pipeline import StarProductPipeline
from .tools import ToolRegistry


def create_star_product_pipeline(database_path, *, storage_root, config):
    """Keep container execution disabled unless the operator supplies an exact image ID."""
    if config.get("SHOWCASE_STAR_ENABLED") is not True:
        return None

    registry = config.get("SHOWCASE_STAR_REGISTRY")
    features = config.get("SHOWCASE_STAR_FEATURES")
    image = config.get("SHOWCASE_STAR_PYTHON_IMAGE_ID") or os.getenv(
        "SHOWCASE_STAR_PYTHON_IMAGE_ID", "")
    image_enabled = registry is None and bool(image)
    if registry is None and image:
        from .python_executor import DockerPythonExecutor

        executor = DockerPythonExecutor(
            image=image, artifact_root=Path(storage_root) / "tool_artifacts")
        registry = ToolRegistry()
        registry.register_polynomial_check()
        registry.register_container_python(executor)
        if features is None:
            features = {"final_generation": True, "final_solution_review": True,
                "local_code_tool": True}

    budget = config.get("SHOWCASE_STAR_BUDGET")
    if budget is None:
        budget = RunBudgetLimits(max_model_calls=8 if image_enabled else 3,
            max_http_attempts=8 if image_enabled else 3,
            max_tool_calls=2 if image_enabled else 0)

    return StarProductPipeline(database_path,
        adapter=config.get("SHOWCASE_STAR_ADAPTER"),
        budget=budget,
        features=features,
        registry=registry,
        hint_mode=config.get("SHOWCASE_STAR_HINT_MODE", "none"),
        evidence_kind=config.get("SHOWCASE_STAR_EVIDENCE_KIND", "live"))
