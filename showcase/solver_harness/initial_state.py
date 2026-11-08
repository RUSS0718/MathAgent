"""Initial persisted Solver Run shape."""

import uuid
from datetime import UTC, datetime
from typing import Any


def initial_state(run_id: str, problem_hash: str, config_hash: str, *,
                  context_policy: dict[str, Any] | None = None,
                  problem_spec: dict[str, Any] | None = None,
                  work_units: list[dict[str, Any]] | None = None,
                  proof_graph: bool = False) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    state = {
        "schema_version": "1.1",
        "run_id": run_id,
        "problem_hash": problem_hash,
        "config_hash": config_hash,
        "context_policy": context_policy or {"enabled": False, "version": "context-pack-v1"},
        "context_packs": [],
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
        "meta_guidance_decision": None,
        "pending_guidance_task": None,
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
    if problem_spec is not None:
        state.update({
            "problem_spec_policy": {"enabled": True, "version": "problem-spec-v1"},
            "problem_spec": problem_spec,
            "specification_version": problem_spec["specification_version"],
            "specification_history": [problem_spec],
            "work_units": work_units or [],
            "obligation_ledger": [
                {
                    "obligation_id": item["obligation_id"],
                    "status": "open",
                    "evidence_refs": [],
                    "specification_version": problem_spec["specification_version"],
                }
                for item in problem_spec["root_obligations"]
            ],
            "obligation_evidence_ledger": [],
            "skipped_work_units": [],
        })
    if proof_graph:
        from .proof_graph import initial_proof_graph

        state["proof_graph_policy"] = {
            "enabled": True, "version": "proof-graph-v1",
            "schema_version": "proof-graph-v1",
        }
        state["proof_graph"] = initial_proof_graph()
    return state
