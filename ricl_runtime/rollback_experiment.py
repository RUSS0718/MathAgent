"""Offline paired comparison of Baseline suffix replay and RiCL-State rollback.

Matrix runners can invoke this slice with a shared offline ModelPort and a frozen
checkpoint::

    pair = run_rollback_pair(
        offline_model_port,
        checkpoint,
        problem_id="item-001",
        output_root=Path("artifacts/rollback"),
        model_request_limit=1,
        tool_call_limit=0,
    )

Each condition gets an isolated Runtime Run with the same model/tool capability,
request limit, token ceiling, checkpoint, and diagnosis. The returned pair record
contains redacted hashes, budgets, usage, evidence-citation audits, and rework
output-token counts. The paired comparison uses an offline ModelPort.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

from .port import ModelPort, ToolExecutor
from .reasoning_state import Evidence, SharedReasoningState
from .runtime import Runtime, _canonical_json, _source_revision


@dataclass(frozen=True)
class RollbackStep:
    """A frozen trace step linked to the verified evidence it establishes."""

    step_id: str
    evidence_id: str

    def __post_init__(self) -> None:
        if not self.step_id.strip() or not self.evidence_id.strip():
            raise ValueError("rollback steps require step and evidence IDs")


@dataclass(frozen=True)
class RollbackCheckpoint:
    """Common pre-repair problem, trace, verified state and diagnosis."""

    problem: str
    problem_id: str
    original_trace: tuple[str, ...]
    steps: tuple[RollbackStep, ...]
    failed_step_id: str
    diagnosis: str
    reasoning_state: SharedReasoningState

    def __post_init__(self) -> None:
        if not self.problem.strip() or not self.problem_id.strip():
            raise ValueError("rollback checkpoints require a problem and problem ID")
        if not self.diagnosis.strip():
            raise ValueError("rollback checkpoints require a diagnosis")
        if not isinstance(self.reasoning_state, SharedReasoningState):
            raise TypeError("rollback checkpoints require SharedReasoningState")
        if not self.steps:
            raise ValueError("rollback checkpoints require at least one linked step")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("rollback step IDs must be unique")
        if step_ids.count(self.failed_step_id) != 1:
            raise ValueError("failed step must occur exactly once in the frozen trace")
        evidence_ids = {item.evidence_id for item in self.reasoning_state.valid_evidence()}
        if any(step.evidence_id not in evidence_ids for step in self.steps):
            raise ValueError("every rollback step must reference valid checkpoint evidence")


def run_rollback_pair(
    model_port: ModelPort,
    checkpoint: RollbackCheckpoint,
    **options: Any,
) -> dict[str, Any]:
    """Run the offline rollback comparison through an offline ModelPort."""
    if getattr(model_port, "provider", "offline") != "offline":
        raise ValueError("rollback pair is restricted to offline ModelPort implementations")
    return _run_rollback_pair(model_port, checkpoint, **options)


def _run_rollback_pair(
    model_port: ModelPort,
    checkpoint: RollbackCheckpoint,
    *,
    problem_id: str | None = None,
    output_root: Path = Path("artifacts/rollback"),
    tool_executor: ToolExecutor | None = None,
    model_request_limit: int = 1,
    tool_call_limit: int = 0,
    order_seed: int | None = None,
) -> dict[str, Any]:
    """Run the offline Baseline/RiCL-State rollback pair from one frozen input.

    Pass an offline implementation of ModelPort (for example DeterministicModelPort),
    a RollbackCheckpoint, and matrix metadata/limits as keyword arguments. Example::

        pair = run_rollback_pair(port, checkpoint, problem_id="q-01")

    Baseline replays the full trace suffix from the diagnosed step; RiCL-State
    invalidates that step's evidence in an isolated state fork and recomputes only
    steps whose AND/OR supports are no longer valid. Each arm runs through Runtime
    once with identical model, tool executor, model-request/token/tool budgets and
    the same frozen checkpoint/diagnosis. Provider-backed ports are rejected.

    Evidence-use audit means explicit evidence IDs cited in the generated repair
    record, independently intersected with the dependency invalidation closure; it
    does not claim to observe a model's private reasoning. Missing or unrecognized
    citations remain unknown. Rework tokens are generated output tokens only; the
    Runtime separately records input/output tokens, calls, tool uses and unknowns.
    """

    if model_request_limit < 1:
        raise ValueError("model request limit must be positive")
    if tool_call_limit < 0:
        raise ValueError("tool call limit must be nonnegative")

    initial_state = checkpoint.reasoning_state.fork()
    initial_evidence = initial_state.valid_evidence()
    evidence_by_id = {item.evidence_id: item for item in initial_evidence}
    failed_step_index = next(
        index
        for index, step in enumerate(checkpoint.steps)
        if step.step_id == checkpoint.failed_step_id
    )
    failed_evidence_id = checkpoint.steps[failed_step_index].evidence_id
    treatment_state = initial_state.fork()
    invalidated_evidence_ids = treatment_state.invalidate(failed_evidence_id)
    invalidated_set = set(invalidated_evidence_ids)
    suffix_steps = checkpoint.steps[failed_step_index:]
    treatment_steps = tuple(
        step for step in checkpoint.steps if step.evidence_id in invalidated_set
    )
    diagnosis_sha256 = _sha256(checkpoint.diagnosis)
    checkpoint_record = {
        "problem_sha256": _sha256(checkpoint.problem),
        "problem_id": problem_id or checkpoint.problem_id,
        "trace_sha256": [_sha256(line) for line in checkpoint.original_trace],
        "steps": [
            {"step_id": step.step_id, "evidence_id": step.evidence_id} for step in checkpoint.steps
        ],
        "failed_step_id": checkpoint.failed_step_id,
        "diagnosis_sha256": diagnosis_sha256,
        "evidence": initial_state.public_snapshot(),
    }
    checkpoint_sha256 = _sha256(_canonical_json(checkpoint_record))

    tool_limit = tool_call_limit if tool_executor is not None else 0
    conditions = {
        "baseline": ("offline-baseline-rollback", suffix_steps, "suffix_replay"),
        "ricl_state": ("offline-ricl-state-rollback", treatment_steps, "dependency_invalidation"),
    }
    condition_order = list(conditions)
    if order_seed is not None:
        Random(order_seed).shuffle(condition_order)
    pair_id = f"rollback_pair_{uuid.uuid4().hex}"
    pair_dir = output_root / pair_id
    pair_dir.mkdir(parents=True, exist_ok=False)
    arms: dict[str, dict[str, Any]] = {}
    trace: list[dict[str, Any]] = [
        {
            "event": "rollback_pair_started",
            "pair_id": pair_id,
            "problem_id": checkpoint_record["problem_id"],
            "checkpoint_sha256": checkpoint_sha256,
            "diagnosis_sha256": diagnosis_sha256,
            "conditions": condition_order,
            "order_seed": order_seed,
        }
    ]

    runtime = Runtime(model_port, tool_executor=tool_executor)
    for arm in condition_order:
        condition, steps_to_process, mode = conditions[arm]
        arm_prompt = _render_arm_prompt(
            checkpoint,
            initial_evidence,
            problem_id=checkpoint_record["problem_id"],
            checkpoint_sha256=checkpoint_sha256,
            mode=mode,
            steps_to_process=steps_to_process,
        )
        run = runtime.run(
            checkpoint.problem,
            problem_id=checkpoint_record["problem_id"],
            condition_id=condition,
            output_root=output_root,
            visible_context=arm_prompt,
            model_request_limit=model_request_limit,
            tool_call_limit=tool_limit,
        )
        answer = (run.get("result") or {}).get("answer")
        evidence_use = _audit_evidence_use(
            answer if isinstance(answer, str) else None,
            evidence_by_id=evidence_by_id,
            invalidated_ids=invalidated_set,
            failed_evidence_id=failed_evidence_id,
        )
        usage = run["usage"]
        output_tokens = usage["output_tokens"]
        arms[arm] = {
            "condition_id": condition,
            "runtime_run_id": run["run_id"],
            "checkpoint_sha256": checkpoint_sha256,
            "diagnosis_sha256": diagnosis_sha256,
            "rollback": {
                "mode": mode,
                "processed_step_ids": [step.step_id for step in steps_to_process],
                "invalidated_evidence_ids": list(invalidated_evidence_ids)
                if arm == "ricl_state"
                else [],
            },
            "answer_sha256": _sha256(answer) if isinstance(answer, str) else "unknown",
            "config": run["config"],
            "config_sha256": run["config_sha256"],
            "model": run["model"],
            "provider_requests": run["provider_requests"],
            "verification": run["verification"],
            "status": run["run"]["status"],
            "stop_reason": run["run"]["stop_reason"],
            "budget": {
                "model_requests": run["budget"]["model_requests"],
                "tokens": run["budget"]["tokens"],
                "tools": run["budget"]["tools"],
            },
            "usage": usage,
            "rework_tokens": output_tokens if isinstance(output_tokens, int) else "unknown",
            "rework_tokens_source": (
                usage["source"] if isinstance(output_tokens, int) else "unknown"
            ),
            "evidence_use": evidence_use,
            "artifacts": run["artifacts"],
        }
        trace.append(
            {
                "event": "rollback_arm_completed",
                "arm": arm,
                "condition_id": condition,
                "runtime_run_id": run["run_id"],
                "checkpoint_sha256": checkpoint_sha256,
                "diagnosis_sha256": diagnosis_sha256,
                "mode": mode,
                "processed_step_count": len(steps_to_process),
                "invalidated_evidence_count": len(invalidated_evidence_ids)
                if arm == "ricl_state"
                else 0,
                "status": run["run"]["status"],
                "stop_reason": run["run"]["stop_reason"],
                "usage": usage,
                "rework_tokens": arms[arm]["rework_tokens"],
                "evidence_use": evidence_use,
            }
        )

    pair_record = {
        "schema_version": 1,
        "pair_id": pair_id,
        "source": {"revision": _source_revision(), "working_tree_clean": _working_tree_clean()},
        "problem": {
            "id": checkpoint_record["problem_id"],
            "sha256": checkpoint_record["problem_sha256"],
        },
        "checkpoint_sha256": checkpoint_sha256,
        "diagnosis_sha256": diagnosis_sha256,
        "condition_order": condition_order,
        "order_seed": order_seed,
        "capabilities": {
            "requested_model": model_port.name,
            "provider": getattr(model_port, "provider", "offline"),
            "model_seed": "unavailable",
            "thinking": getattr(model_port, "thinking", "none"),
            "max_output_tokens": getattr(model_port, "max_output_tokens", "unknown"),
            "tool_executor_enabled": tool_executor is not None,
            "tool_call_limit": tool_limit,
            "model_request_limit": model_request_limit,
        },
        "arms": arms,
        "pair_status": (
            "completed"
            if all(arm["status"] == "completed" for arm in arms.values())
            else "incomplete"
        ),
        "artifacts": {
            "run": str(pair_dir / "run.json"),
            "trace": str(pair_dir / "trace.jsonl"),
        },
    }
    trace.append({"event": "rollback_pair_stopped", "status": pair_record["pair_status"]})
    (pair_dir / "trace.jsonl").write_text(
        "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
    )
    (pair_dir / "run.json").write_text(
        json.dumps(pair_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return pair_record


def _render_arm_prompt(
    checkpoint: RollbackCheckpoint,
    evidence: Sequence[Evidence],
    *,
    problem_id: str,
    checkpoint_sha256: str,
    mode: str,
    steps_to_process: Sequence[RollbackStep],
) -> str:
    """Render the shared checkpoint and the condition-specific rollback operation."""

    evidence_lines = [
        "\n".join(
            (
                f"Evidence ID: {item.evidence_id}",
                f"Result ID: {item.result_id or 'none'}",
                f"Scope: {item.scope}",
                f"Source: {item.source}",
                f"Depends on all: {', '.join(item.depends_on_all) or 'none'}",
                f"Depends on any: {', '.join(item.depends_on_any) or 'none'}",
                f"Verified content: {item.content}",
            )
        )
        for item in evidence
    ]
    common = [
        f"Problem ID: {problem_id}",
        f"Checkpoint SHA256: {checkpoint_sha256}",
        "Original trace (frozen):\n" + "\n".join(checkpoint.original_trace),
        "Frozen verified checkpoint evidence:\n" + "\n\n".join(evidence_lines),
        "Failed step ID: " + checkpoint.failed_step_id,
        "Diagnosis: " + checkpoint.diagnosis,
    ]
    if mode == "suffix_replay":
        operation = [
            "Condition: Baseline",
            "Replay the suffix from the diagnosed failed step. Recheck each suffix step "
            "using ordinary context and independent verification; reuse only evidence "
            "that still has valid support.",
            "Replay suffix step IDs: " + ", ".join(step.step_id for step in steps_to_process),
        ]
    else:
        operation = [
            "Condition: RiCL-State",
            "Invalidate the failed derivation and recompute only conclusions whose "
            "AND/OR dependencies have lost all valid support. Preserve a conclusion "
            "with another independent valid OR derivation.",
            "Recompute invalidated step IDs: "
            + ", ".join(step.step_id for step in steps_to_process),
        ]
    step_links = [f"Step {step.step_id}: evidence {step.evidence_id}" for step in checkpoint.steps]
    operation.append("Frozen step-to-evidence links:\n" + "\n".join(step_links))
    operation.append(
        "Return a concise repair record containing exactly one line named Evidence used: "
        "<comma-separated evidence IDs or none> and, if needed, one Repair line. "
        "End with a separate line beginning Final answer: followed by the answer. "
        "Do not include private reasoning."
    )
    return "\n\n".join((*common, *operation))


def _audit_evidence_use(
    answer: str | None,
    *,
    evidence_by_id: dict[str, Evidence],
    invalidated_ids: set[str],
    failed_evidence_id: str,
) -> dict[str, Any]:
    """Cross-check explicit answer citations against independent graph invalidation."""

    prefix = "Evidence used: "
    declarations = [
        line[len(prefix) :].strip()
        for line in (answer or "").splitlines()
        if line.startswith(prefix)
    ]
    if len(declarations) != 1 or not declarations[0]:
        cited: list[str] = []
        citations_known = False
    elif declarations[0].lower() == "none":
        cited = []
        citations_known = True
    else:
        cited = list(dict.fromkeys(item.strip() for item in declarations[0].split(",")))
        citations_known = all(item in evidence_by_id for item in cited)
        if any(not item.strip() for item in declarations[0].split(",")):
            citations_known = False

    invalidated_used = [item for item in cited if item in invalidated_ids]
    unsupported_used = [
        item
        for item in invalidated_used
        if evidence_by_id[item].depends_on_all or evidence_by_id[item].depends_on_any
    ]
    unrecognized = [item for item in cited if item not in evidence_by_id]

    def flag(is_proven: bool, known: bool) -> bool | str:
        return True if is_proven else False if known else "unknown"

    return {
        "status": "verified_by_dependency_audit" if citations_known else "unknown",
        "basis": "explicit cited evidence IDs cross-checked against checkpoint AND/OR invalidation; not a claim about private model reasoning",
        "cited_evidence_ids": [item for item in cited if item in evidence_by_id],
        "invalidated_evidence_ids_used": invalidated_used,
        "unrecognized_evidence_id_sha256": [_sha256(item) for item in unrecognized],
        "continued_using_failed_derivation": flag(failed_evidence_id in cited, citations_known),
        "continued_using_conclusion_without_valid_support": flag(
            bool(unsupported_used), citations_known
        ),
        "continued_using_invalidated_evidence": flag(bool(invalidated_used), citations_known),
    }


def _sha256(value: str | None) -> str:
    """Hash UTF-8 text without persisting its contents."""

    if value is None:
        return "unknown"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _working_tree_clean() -> bool | str:
    """Mark provenance as dirty rather than claiming HEAD alone identifies the run."""

    import subprocess

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", ".", ":(exclude)tests/test.md"],
            cwd=Path(__file__).resolve().parent.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return not result.stdout.strip()
