"""Initial persisted Solver Run shape."""

import uuid
from datetime import UTC, datetime
from typing import Any


def initial_state(run_id: str, problem_hash: str, config_hash: str) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "schema_version": "1.1",
        "run_id": run_id,
        "problem_hash": problem_hash,
        "config_hash": config_hash,
        "phase": "SETUP",
        "status": "running",
        "plan_version": 0,
        "attempt_index": 0,
        "current_step": None,
        "steps": {},
        "exploration_findings": [],
        "accepted_results": [],
        "failure_records": [],
        "verified_results_ledger": [],
        "confirmed_failures_ledger": [],
        "meta_interventions": [],
        "reexploration_tasks": [],
        "session_registry": {},
        "run_salt": uuid.uuid4().hex,
        "state_revision": 0,
        "tool_policy": {"allow": []},
        "partial_transcript_refs": [],
        "session_refs": {},
        "counters": {"model_calls": 0, "tool_calls": 0},
        "budget": {},
        "usage": {},
        "artifact_refs": {},
        "created_at": now,
        "updated_at": now,
        "candidate_registry": None,
        "best_effort_decision": None,
        "finalization_reason": None,
    }
