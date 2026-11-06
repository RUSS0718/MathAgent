"""Synthetic loopback profiles for public STAR streaming tests."""

import hashlib
import json

from showcase.solver_harness.intern_schemas import SCHEMAS, response_schema
from showcase.stream_preference import StreamProfile

ENDPOINT = "http://127.0.0.1:5000/api/v1/chat/completions"
_MESSAGE_SHAPE = (("system", ("content", "role")), ("user", ("content", "role")))
_SCHEMA_REQUESTS = [
    {"role": role}
    for role in SCHEMAS
] + [
    {"role": "meta", "guidance_request": True},
    {"role": "meta", "action": "delegate_research_task"},
    {"role": "meta", "action": "preplan_hint"},
    {"role": "meta", "action": "partial_exploration"},
    {"role": "researcher", "action": "counterexample_check"},
    {"role": "reasoner", "checkpoint_protocol": True},
    {"role": "planner", "checkpoint_protocol": True},
]


def configure_controlled_streaming(adapter):
    """Pin a streaming adapter to mockable loopback and register its known schemas."""
    client = adapter._get_client()
    client.api_base = ENDPOINT
    client.loopback_only = True
    model = getattr(client, "model", None) or adapter.model_id
    thinking_mode = adapter.thinking_mode
    if thinking_mode is None:
        thinking_mode = getattr(client, "thinking_mode", None)
    payload_keys = {"model", "messages", "stream", "temperature", "max_tokens"}
    if thinking_mode is not None:
        payload_keys.add("thinking_mode")

    profiles = {}
    for request in _SCHEMA_REQUESTS:
        schema = response_schema(request)
        encoded = json.dumps(schema, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        profiles[fingerprint] = StreamProfile(
            endpoint=ENDPOINT,
            model=model,
            temperature=adapter.temperature,
            max_tokens=adapter.max_tokens,
            thinking_mode=thinking_mode,
            messages_schema=_MESSAGE_SHAPE,
            evidence_kind="controlled_test",
            status="controlled_test",
            schema_fingerprint=fingerprint,
            payload_keys=frozenset(payload_keys),
        )
    return tuple(profiles.values())
