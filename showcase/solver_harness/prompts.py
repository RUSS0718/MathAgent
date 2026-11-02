"""Opt-in role / triggered protocol / latest state projection composition."""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .context_injection import prepare_role_context
from .roles import definition as role_definition
from .skills import PROTOCOLS, select_skills


def compose_request(run: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    request = deepcopy(dict(request))
    role = request["role"]
    if role == "reasoner" and run["state"].get("reasoning_mode") == "reason_noncoding":
        role = "reason_noncoding"
        request = {**request, "role": role}
    definition = role_definition(role)
    ids = select_skills(role, request)
    projection = prepare_role_context(run, request, include_exploration=True)["state"]
    layers = [
        {"kind": "role", "version": "1", "definition": definition},
        {
            "kind": "protocols",
            "version": "1",
            "protocols": [{"id": key, "version": "1", **deepcopy(PROTOCOLS[key])} for key in ids],
        },
        {
            "kind": "projection",
            "version": "1",
            "state_revision": run["state_revision"],
            "state": projection,
        },
    ]
    fingerprint = hashlib.sha256(
        json.dumps(layers, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    allowed = [] if role in {
        "meta", "meta_strategist", "reason_noncoding", "researcher"
    } else ["read_state", "read_ledger"]
    return {
        **request,
        "state_revision": run["state_revision"],
        "active_skill_ids": ids,
        "prompt_layers": layers,
        "prompt_fingerprint": fingerprint,
        "allowed_tools": allowed,
        "tool_policy": {"allow": allowed},
    }
