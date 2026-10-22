"""Pure deterministic replay of persisted candidate selection and evidence grades."""

import hashlib
import json
from collections.abc import Mapping

from .best_effort import RULE_VERSION, select_best_effort


def replay_snapshot(snapshot, events=None):
    """Replay a run envelope, or a state with its explicit event list.

    The input remains unchanged. No Harness, database, model or tool is used.
    ``audit.snapshot_hash`` covers the canonical state and events together.
    """
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be a run envelope or state mapping")
    state = snapshot.get("state", snapshot)
    history = snapshot.get("events", []) if events is None else events
    if not isinstance(state, Mapping) or not isinstance(history, list):
        raise ValueError("replay requires a state mapping and an event list")
    try:
        serialized = json.dumps(
            {"state": state, "events": history},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        detached = json.loads(serialized)
    except (TypeError, ValueError) as exc:
        raise ValueError("replay snapshot must be JSON serializable") from exc
    state, history = detached["state"], detached["events"]
    if any(
        not isinstance(event, dict) or event.get("run_id") != state.get("run_id")
        for event in history
    ):
        raise ValueError("replay event identity must match the snapshot run")
    state["_events"] = history
    decision = select_best_effort(state)
    saved = state.get("best_effort_decision")
    return {
        "decision": decision,
        "audit": {
            "snapshot_hash": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
            "snapshot_hash_algorithm": "sha256-canonical-json-v1",
            "selection_rule_version": RULE_VERSION,
            "recorded_selection_rule_version": saved.get("selection_rule_version")
            if saved
            else None,
            "matches_persisted_decision": decision == saved if saved is not None else None,
        },
    }
