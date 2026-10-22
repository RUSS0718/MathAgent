"""Opt-in role / triggered protocol / latest state projection composition."""

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .skills import PROTOCOLS, select_skills

ROLE_DEFINITIONS = {
    "explore": "Explore the problem; distinguish observations from proofs and report structured assessment. Do not alter authoritative state.",
    "reasoner": "Solve only the current objective using accepted results and relevant failures. Return a labeled StepReport; respond to the current objection during Challenge. Do not alter authoritative state.",
    "reason_noncoding": "Prove the current objective by pure reasoning, without executable tools. Return a labeled StepReport. Do not alter authoritative state.",
    "step_verifier": "Independently review the current objective and proof. Return exactly one structured verdict and concrete objections. Do not alter authoritative state or access other runs.",
    "whole_solution_verifier": "Independently review the full candidate against the original problem and proof obligations. Return ACCEPT or REJECT. Do not alter authoritative state or access other runs.",
    "meta": "Select a strategy from progress, failures and budget. Do not take over the proof, execute code or alter authoritative state.",
}


def compose_request(run: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    role = request["role"]
    if role == "reasoner" and run["state"].get("reasoning_mode") == "reason_noncoding":
        role = "reason_noncoding"
        request = {**request, "role": role}
    definition = ROLE_DEFINITIONS.get(
        role,
        ROLE_DEFINITIONS["meta"] if role == "meta_strategist" else ROLE_DEFINITIONS["reasoner"],
    )
    ids = select_skills(role, request)
    state = run["state"]
    projection = {
        key: state[key]
        for key in (
            "phase",
            "plan",
            "current_step",
            "accepted_results",
            "failure_records",
            "verified_results_ledger",
            "confirmed_failures_ledger",
            "budget",
            "counters",
        )
        if key in state
    }
    layers = [
        {"kind": "role", "version": "1", "definition": definition},
        {
            "kind": "protocols",
            "version": "1",
            "protocols": [{"id": key, **PROTOCOLS[key]} for key in ids],
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
    allowed = (
        []
        if role in {"meta", "meta_strategist", "reason_noncoding"}
        else ["read_state", "read_ledger"]
    )
    return {
        **request,
        "state_revision": run["state_revision"],
        "active_skill_ids": ids,
        "prompt_layers": layers,
        "prompt_fingerprint": fingerprint,
        "allowed_tools": allowed,
        "tool_policy": {"allow": allowed},
    }
