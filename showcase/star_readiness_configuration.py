"""Verify the effective Reference preset independently of dynamic S3 ceilings."""

from copy import deepcopy


def validate_server_configuration(server, expected_configuration):
    """Return an exact static configuration snapshot or reject runtime drift."""
    pipeline = server.app.extensions["showcase_workspace_service"].star_pipeline
    preset = deepcopy(pipeline.preset_config("star_reference"))
    # Each Run's registered ceilings override these three preset defaults in S3.
    for key in ("max_model_calls", "max_tool_calls", "max_total_duration_seconds"):
        preset.pop(key, None)
    observed = {
        "isolation_image_id": pipeline.registry.container_python_executor.image,
        "preset": preset,
        "registered_tools": sorted(tool["name"] for tool in pipeline.registry.describe()),
    }
    if observed != expected_configuration:
        raise ValueError("star_readiness_configuration_mismatch")
    if any(value is not True for value in preset["features"].values()):
        raise ValueError("star_readiness_configuration_mismatch")
    return observed
