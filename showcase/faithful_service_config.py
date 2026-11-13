"""Assemble existing Faithful mechanisms from explicit, trusted local settings."""

import json
import re
from pathlib import Path

from .adapters import InternStreamAdapter
from .run_budget import RunBudgetLimits
from .solver_harness.context_pack import frozen_policy
from .star_product_config import CORE_FEATURES, population_config


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("faithful_config_duplicate_key")
        value[key] = item
    return value


def _object(value, required, optional=()):
    if (not isinstance(value, dict) or set(required) - value.keys()
            or value.keys() - set(required) - set(optional)):
        raise ValueError("faithful_config_fields_invalid")
    return value


def _budget(value):
    _object(value, {"max_model_calls", "max_http_attempts", "max_tool_calls",
                    "max_tokens", "max_runtime_seconds"})
    return RunBudgetLimits(**value)


def load_faithful_config(path):
    """Load wiring only; real model, tool and capacity admission remains mandatory."""
    path = Path(path)
    value = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_object)
    _object(value, {"version", "python_image_id", "context_capacity", "budget"},
            {"population", "formal", "population_memory"})
    if value["version"] != "faithful-service-v1":
        raise ValueError("faithful_config_version_invalid")
    image = value["python_image_id"]
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("faithful_python_image_id_invalid")
    features = dict.fromkeys(CORE_FEATURES | {
        "stream_activity", "context_pack", "problem_spec", "progress_scheduling",
        "proof_graph", "serial_routes", "planner_checkpoints", "reasoner_checkpoints",
        "auto_problem_spec",
    }, True)
    frozen_policy({"features": features, "context_capacity": value["context_capacity"]})
    memory = value.get("population_memory", False)
    if type(memory) is not bool:
        raise ValueError("faithful_population_memory_invalid")
    config = {
        "SHOWCASE_FAITHFUL_AUTONOMOUS": True,
        "SHOWCASE_STAR_FULL_ENABLED": True,
        "SHOWCASE_STAR_PYTHON_IMAGE_ID": image,
        "SHOWCASE_STAR_FULL_FEATURES": features,
        "SHOWCASE_STAR_FULL_BUDGET": _budget(value["budget"]),
        "SHOWCASE_STAR_CONTEXT_CAPACITY": value["context_capacity"],
        "SHOWCASE_STAR_TRANSPORT_POLICY": "stream_first",
        "SHOWCASE_STAR_ADAPTER": InternStreamAdapter(max_tokens=32768, thinking_mode=False,
                                                    client_timeout=180, client_retry=3),
        "SHOWCASE_PRESENTATION_ENABLED": True,
        "SHOWCASE_FAITHFUL_MEMORY_ENABLED": True,
        "SHOWCASE_POPULATION_MEMORY_ENABLED": memory,
        "SHOWCASE_FAITHFUL_INTERVENTION_ENABLED": True,
        "SHOWCASE_F7_SYSTEM_VIEW_ENABLED": True,
    }
    if "population" in value:
        population = _object(value["population"], {"capacity", "budget"},
                             {"request_timeout_seconds"})
        budget = _budget(population["budget"])
        # Validate with the current production adapter's default timeout; the
        # runtime repeats admission against the actual configured adapter.
        timeout = population.get("request_timeout_seconds", 180)
        if type(timeout) not in {int, float} or not 0 < timeout <= 180:
            raise ValueError("population_request_timeout_invalid")
        population_config(budget, population["capacity"], evidence_kind="live",
                          request_timeout_seconds=timeout)
        config.update(SHOWCASE_STAR_POPULATION_ENABLED=True,
                      SHOWCASE_STAR_POPULATION_CAPACITY=population["capacity"],
                      SHOWCASE_STAR_POPULATION_BUDGET=budget,
                      SHOWCASE_STAR_POPULATION_REQUEST_TIMEOUT_SECONDS=timeout)
    if "formal" in value:
        from .formal import LeanTacticProver
        from .formal_docker import LeanDockerExecutor

        formal = _object(value["formal"], {"manifest", "policy"})
        policy = formal["policy"]
        if not isinstance(policy, dict) or policy.get("enabled") is not True:
            raise ValueError("faithful_formal_policy_invalid")
        manifest_path = path.parent / formal["manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"),
                              object_pairs_hook=_unique_object)
        executor = LeanDockerExecutor(manifest=manifest,
                                      timeout_seconds=policy["timeout_seconds"],
                                      max_output_bytes=policy["max_output_bytes"])
        config.update(SHOWCASE_FORMAL_BACKEND=LeanTacticProver(
            executor, timeout_seconds=policy["timeout_seconds"]),
            SHOWCASE_FORMAL_VERIFICATION_CONFIG=policy)
    return config
