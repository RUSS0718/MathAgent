"""Estimate prompt-byte and token deltas attributable to advisory memory."""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy

_ESTIMATOR_VERSION = "utf8-byte-ceil-third-v1-estimated"


def measure_population_memory_cost(port, request, *, input_fingerprint):
    """Return a payload-free audit of the incremental serialized prompt cost."""
    advisories = _advisories(request)
    record_ids = list(dict.fromkeys(
        item["record_id"]
        for advisory in advisories
        for item in advisory.get("observations", [])
        if isinstance(item, Mapping) and isinstance(item.get("record_id"), str)
    ))
    base = {
        "record_ids": record_ids,
        "additional_utf8_bytes": None,
        "estimated_tokens": None,
        "estimator_version": _ESTIMATOR_VERSION,
        "input_fingerprint": input_fingerprint,
        "status": "unknown",
    }
    if not advisories:
        return base
    try:
        with_memory = port.serialized_payload_size(request)
        without_memory = port.serialized_payload_size(_without_advisory(request))
        if (type(with_memory) is not int or type(without_memory) is not int
                or with_memory < without_memory):
            return base
        byte_delta = with_memory - without_memory
        return {
            **base,
            "additional_utf8_bytes": byte_delta,
            "estimated_tokens": math.ceil(byte_delta / 3),
            "status": "estimated",
        }
    except Exception:
        return base


def _advisories(request):
    found = []
    direct = request.get("population_memory_advisory")
    if isinstance(direct, Mapping) and direct.get("authority") == "advisory_only":
        found.append(direct)
    context = request.get("role_context")
    state = context.get("state") if isinstance(context, Mapping) else None
    if isinstance(state, Mapping):
        memory = state.get("population_memory_advisory")
        if isinstance(memory, Mapping) and memory.get("authority") == "advisory_only":
            found.append(memory)
    for layer in request.get("prompt_layers", []):
        layer_state = layer.get("state") if isinstance(layer, Mapping) else None
        memory = layer_state.get("population_memory_advisory") if isinstance(layer_state, Mapping) else None
        if isinstance(memory, Mapping) and memory.get("authority") == "advisory_only":
            found.append(memory)
    return found


def _without_advisory(request):
    result = deepcopy(dict(request))
    result.pop("population_memory_advisory", None)
    context = result.get("role_context")
    state = context.get("state") if isinstance(context, dict) else None
    if isinstance(state, dict):
        state.pop("population_memory_advisory", None)
    layers = result.get("prompt_layers")
    if isinstance(layers, list):
        for layer in layers:
            layer_state = layer.get("state") if isinstance(layer, dict) else None
            if isinstance(layer_state, dict):
                layer_state.pop("population_memory_advisory", None)
    return result
