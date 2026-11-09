"""Build the opt-in STAR runtime from trusted local server configuration."""

import os
from pathlib import Path

from .run_budget import RunBudgetLimits
from .star_product_pipeline import StarProductPipeline
from .tools import ToolRegistry

# SP-13 合同固定的数学镜像指纹（初始来自 SP-09）。此常量把合同值锚定在代码内，
# 供不依赖 Docker 的断言测试核对；运行时接线仍是显式 opt-in——操作者必须经
# SHOWCASE_STAR_PYTHON_IMAGE_ID 提供精确镜像 ID，本常量不会自动启用容器执行。
CONTRACT_PYTHON_IMAGE_ID = "sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d"


def create_star_product_pipeline(database_path, *, storage_root, config):
    """Keep container execution disabled unless the operator supplies an exact image ID."""
    full_enabled = config.get("SHOWCASE_STAR_FULL_ENABLED") is True
    population_enabled = config.get("SHOWCASE_STAR_POPULATION_ENABLED") is True
    limited_enabled = config.get("SHOWCASE_STAR_ENABLED") is True
    if not limited_enabled and not full_enabled and not population_enabled:
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

    formal_backend = config.get("SHOWCASE_FORMAL_BACKEND")
    formal_server_policy = config.get("SHOWCASE_FORMAL_VERIFICATION_CONFIG")
    formal_registry = None
    if formal_backend is not None:
        if registry is None:
            registry = ToolRegistry()
        from .formal import BackendRegistry, register_formal, register_formal_backend

        register_formal(registry, formal_backend)
        formal_registry = BackendRegistry()
        register_formal_backend(formal_registry, formal_backend)

    budget = config.get("SHOWCASE_STAR_BUDGET")
    if budget is None:
        budget = RunBudgetLimits(max_model_calls=8 if image_enabled else 3,
            max_http_attempts=8 if image_enabled else 3,
            max_tool_calls=2 if image_enabled else 0)
    population_budget = config.get("SHOWCASE_STAR_POPULATION_BUDGET")
    if population_budget is None:
        population_budget = RunBudgetLimits(
            max_model_calls=24, max_http_attempts=48, max_tool_calls=0,
            max_tokens=2_097_152, max_runtime_seconds=7_200,
        )

    return StarProductPipeline(database_path,
        acceptance_mode=config.get("SHOWCASE_STAR_ACCEPTANCE_MODE", "strict"),
        adapter=config.get("SHOWCASE_STAR_ADAPTER"),
        budget=budget,
        population_budget=population_budget,
        features=features,
        registry=registry,
        full_enabled=full_enabled,
        full_features=config.get("SHOWCASE_STAR_FULL_FEATURES"),
        full_budget=config.get("SHOWCASE_STAR_FULL_BUDGET"),
        experiment_policy=config.get("SHOWCASE_STAR_EXPERIMENT_POLICY"),
        transport_policy=config.get("SHOWCASE_STAR_TRANSPORT_POLICY", "legacy"),
        stream_profiles=config.get("SHOWCASE_STAR_TRANSPORT_PROFILES"),
        context_capacity=config.get("SHOWCASE_STAR_CONTEXT_CAPACITY"),
        population_capacity=config.get("SHOWCASE_STAR_POPULATION_CAPACITY"),
        limited_enabled=limited_enabled,
        population_enabled=population_enabled,
        hint_mode=config.get("SHOWCASE_STAR_HINT_MODE", "none"),
        evidence_kind=config.get("SHOWCASE_STAR_EVIDENCE_KIND", "live"),
        formal_backend=formal_backend,
        formal_registry=formal_registry,
        formal_server_policy=formal_server_policy)
