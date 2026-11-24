"""Single-route Runtime with explicit run accounting and redacted artifacts."""

import hashlib
import json
import subprocess
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .counterfactual import CounterfactualCheckpoint, InterventionAudit
from .identity import stable_id
from .port import ModelPort, ModelReply, ToolExecutor
from .reasoning_state import Evidence, SharedReasoningState
from .verification import verify_integer_addition


class Runtime:
    """Run one offline text problem through a ModelPort and an independent check."""

    def __init__(self, model_port: ModelPort, *, tool_executor: ToolExecutor | None = None) -> None:
        """Bind the model capability and optional controlled tool executor."""

        self._model_port = model_port
        self._tool_executor = tool_executor

    def run_counterfactual(
        self,
        problem: str,
        *,
        checkpoint: CounterfactualCheckpoint,
        intervention_feedback: str,
        intervention_auditor: Callable[[str, ModelReply], InterventionAudit] | None = None,
        feedback_kind: Literal["random", "diagnostic"] = "diagnostic",
        enabled: bool = True,
        problem_id: str | None = None,
        condition_id: str = "offline-counterfactual",
        output_root: Path = Path("artifacts"),
        model_request_limit: int = 3,
    ) -> dict[str, Any]:
        """Run isolated branches and, when budget permits, a parent continuation."""

        eligible = checkpoint.failure_count > 0 and checkpoint.trigger_count < checkpoint.max_trigger_count
        if not enabled or not eligible:
            return self.run(problem, problem_id=problem_id, condition_id=condition_id, output_root=output_root)
        if model_request_limit < 2:
            raise ValueError("counterfactual branches require two shared model requests")
        if feedback_kind not in ("random", "diagnostic"):
            raise ValueError("feedback kind must be random or diagnostic")
        if not intervention_feedback.strip():
            raise ValueError("intervention feedback must be nonempty")

        checkpoint_trigger_count = checkpoint.trigger_count
        checkpoint.trigger_count += 1
        run_id = f"run_{uuid.uuid4().hex}"
        problem_sha256 = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        problem_id = problem_id or problem_sha256
        parent_state = checkpoint.reasoning_state.fork()
        evidence = parent_state.valid_evidence()
        checkpoint_record = {
            "visible_prefix_sha256": hashlib.sha256(
                checkpoint.visible_prefix.encode("utf-8")
            ).hexdigest(),
            "failure_count": checkpoint.failure_count,
            "trigger_count": checkpoint_trigger_count,
            "current_action": checkpoint.current_action,
            "current_route": checkpoint.current_route,
            "evidence": parent_state.public_snapshot(),
        }
        checkpoint_sha256 = hashlib.sha256(_canonical_json(checkpoint_record).encode()).hexdigest()
        common_parts = [problem, checkpoint.visible_prefix]
        context = _render_evidence(evidence)
        if context:
            common_parts.append(f"Verified context:\n{context}")
        common_prompt = "\n\n".join(common_parts)
        branch_states = {"control": parent_state.fork(), "treatment": parent_state.fork()}
        replies: list[ModelReply] = []
        branches: dict[str, dict[str, Any]] = {}
        trace: list[dict[str, Any]] = [
            {
                "event": "run_started",
                "run_id": run_id,
                "problem_id": problem_id,
                "problem_sha256": problem_sha256,
                "condition_id": condition_id,
                "mode": "counterfactual_pair",
            },
            {
                "event": "counterfactual_trigger_evaluated",
                "qualified": True,
                "failure_count": checkpoint.failure_count,
                "trigger_count": checkpoint_trigger_count,
                "maximum_trigger_count": checkpoint.max_trigger_count,
                "checkpoint_sha256": checkpoint_sha256,
            },
        ]
        started = time.perf_counter()
        for index, arm in enumerate(("control", "treatment"), start=1):
            prompt = common_prompt
            if arm == "treatment":
                prompt += f"\n\nIntervention feedback:\n{intervention_feedback}"
            request_id = f"{run_id}_request_{index:03d}"
            trace.append(
                {
                    "event": "model_request_sent",
                    "request_id": request_id,
                    "arm": arm,
                    "checkpoint_sha256": checkpoint_sha256,
                    "context_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                }
            )
            reply = self._model_port.complete(prompt)
            replies.append(reply)
            verification = verify_integer_addition(problem, reply.text)
            scope = f"{problem_sha256}:{verification['scope']}"
            branch_result_id = stable_id("result", {"content": reply.text, "scope": scope})
            trace.append(
                {
                    "event": "branch_outcome_recorded",
                    "request_id": request_id,
                    "arm": arm,
                    "result_id": branch_result_id,
                    "answer_sha256": hashlib.sha256(reply.text.encode("utf-8")).hexdigest(),
                    "verification_status": verification["status"],
                }
            )
            if verification["status"] == "verified":
                branch_states[arm].add_verified_result(reply.text, scope=scope)
            branches[arm] = {
                "request_count": 1,
                "checkpoint_sha256": checkpoint_sha256,
                "answer": reply.text,
                "action": reply.action,
                "route": reply.route,
                "verification": verification,
                "evidence": branch_states[arm].public_snapshot(),
            }

        control = branches["control"]
        treatment = branches["treatment"]
        action_changed = treatment["action"] != control["action"]
        route_changed = treatment["route"] != control["route"]
        audit: InterventionAudit | None = None
        if intervention_auditor is not None:
            proposed_audit = intervention_auditor(intervention_feedback, replies[1])
            if isinstance(proposed_audit, InterventionAudit):
                audit = proposed_audit
        audit_approved = bool(
            audit is not None
            and audit.status == "approved"
            and audit.source.strip()
            and audit.feedback_consumed is True
        )
        effective = action_changed or route_changed
        feedback_available = bool(
            audit_approved and effective and treatment["verification"]["status"] == "verified"
        )
        parent_request_id: str | None = None
        parent_referenced_ids: list[str] = []
        parent_continuation: dict[str, Any] | None = None
        parent_budget_available = feedback_available and len(replies) < model_request_limit
        stop_reason = (
            "parent_feedback_budget_exhausted"
            if feedback_available and not parent_budget_available
            else "counterfactual_pair_completed"
        )
        if parent_budget_available:
            intervention_evidence = parent_state.add_verified_result(
                treatment["answer"],
                scope=f"{problem_sha256}:{treatment['verification']['scope']}",
            )
            parent_request_id = f"{run_id}_request_{len(replies) + 1:03d}"
            parent_referenced_ids = [
                item.evidence_id for item in parent_state.valid_evidence()
            ]
            parent_prompt_parts = [problem, checkpoint.visible_prefix]
            parent_context = _render_evidence(parent_state.valid_evidence())
            if parent_context:
                parent_prompt_parts.append(f"Verified context:\n{parent_context}")
            parent_prompt = "\n\n".join(parent_prompt_parts)
            trace.append(
                {
                    "event": "model_request_sent",
                    "request_id": parent_request_id,
                    "arm": "parent",
                    "checkpoint_sha256": checkpoint_sha256,
                    "referenced_evidence_ids": parent_referenced_ids,
                    "context_sha256": hashlib.sha256(parent_prompt.encode("utf-8")).hexdigest(),
                }
            )
            parent_reply = self._model_port.complete(parent_prompt)
            replies.append(parent_reply)
            parent_verification = verify_integer_addition(problem, parent_reply.text)
            parent_scope = f"{problem_sha256}:{parent_verification['scope']}"
            parent_result_id = stable_id(
                "result", {"content": parent_reply.text, "scope": parent_scope}
            )
            parent_continuation = {
                "request_id": parent_request_id,
                "answer": parent_reply.text,
                "action": parent_reply.action,
                "route": parent_reply.route,
                "verification": parent_verification,
            }
            if parent_verification["status"] == "verified":
                parent_state.add_verified_result(parent_reply.text, scope=parent_scope)
            trace.append(
                {
                    "event": "parent_continuation_recorded",
                    "request_id": parent_request_id,
                    "result_id": parent_result_id,
                    "answer_sha256": hashlib.sha256(parent_reply.text.encode("utf-8")).hexdigest(),
                    "verification_status": parent_verification["status"],
                }
            )
        trace.extend(
            [
                {
                    "event": "intervention_feedback_consumed",
                    "feedback_consumed": bool(
                        intervention_evidence.evidence_id in parent_referenced_ids
                    ) if parent_budget_available else False,
                    "consumption_basis": "present_in_parent_request" if parent_budget_available else (
                        "budget_exhausted" if feedback_available else "not_qualified"
                    ),
                    "parent_request_id": parent_request_id,
                    "referenced_evidence_ids": parent_referenced_ids,
                    "treatment_reported_feedback_consumed": bool(
                        audit and audit.feedback_consumed is True
                    ),
                    "audit_status": audit.status if audit else "unknown",
                    "audit_source": audit.source if audit else "",
                },
                {"event": "intervention_action_change_observed", "changed": action_changed},
                {"event": "intervention_route_change_observed", "changed": route_changed},
                {
                    "event": "intervention_adjudicated",
                    "effective": effective,
                    "treatment_verified": treatment["verification"]["status"] == "verified",
                    "feedback_available_to_parent": parent_budget_available,
                    "feedback_eligible": feedback_available,
                    "feedback_consumed_by_parent": bool(parent_request_id),
                },
            ]
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        config = {
            "mode": "offline",
            "route": "single",
            "model_port": self._model_port.name,
            "mechanisms": {"counterfactual_intervention": True},
            "feedback_kind": feedback_kind,
            "budget": {"scope": "run_shared", "model_requests": model_request_limit},
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        trace_path = run_dir / "trace.jsonl"
        run_path = run_dir / "run.json"
        trace.append({"event": "run_stopped", "status": "completed", "stop_reason": stop_reason})
        result_record = {
            "schema_version": 1,
            "run_id": run_id,
            "source": {"revision": _source_revision()},
            "config": config,
            "config_sha256": config_sha256,
            "problem": {"id": problem_id, "sha256": problem_sha256},
            "condition_id": condition_id,
            "model": {"requested": self._model_port.name, "actual": replies[-1].model or "unknown"},
            "budget": {
                "scope": "run_shared",
                "model_requests": {"limit": model_request_limit, "used": len(replies)},
                "tokens": {"limit": "unknown", "used": _sum_usage(replies, "tokens")},
                "tools": {"limit": 0, "used": 0},
                "elapsed_ms": elapsed_ms,
            },
            "usage": {
                "input_tokens": _sum_usage(replies, "input_tokens"),
                "output_tokens": _sum_usage(replies, "output_tokens"),
                "source": _usage_source(replies),
            },
            "checkpoint": checkpoint_record,
            "branches": branches,
            "intervention": {
                "qualified": True,
                "feedback_kind": feedback_kind,
                "audit_status": audit.status if audit else "unknown",
                "audit_source": audit.source if audit else "",
                "feedback_consumed": feedback_available,
                "feedback_consumed_by_parent": bool(parent_request_id),
                "treatment_reported_feedback_consumed": bool(
                    audit and audit.feedback_consumed is True
                ),
                "action_changed": action_changed,
                "route_changed": route_changed,
                "effective": effective,
                "feedback_available_to_parent": parent_budget_available,
                "feedback_eligible": feedback_available,
                "parent_feedback": treatment["answer"] if parent_request_id else None,
                "parent_request_id": parent_request_id,
                "trigger_count_after": checkpoint.trigger_count,
            },
            "parent_continuation": parent_continuation,
            "parent_evidence": parent_state.public_snapshot(),
            "run": {"status": "completed", "stop_reason": stop_reason},
            "artifacts": {"run": str(run_path), "trace": str(trace_path)},
        }
        trace_path.write_text(
            "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
        )
        run_path.write_text(json.dumps(result_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result_record

    def run(
        self,
        problem: str,
        *,
        problem_id: str | None = None,
        condition_id: str = "offline-single-route",
        output_root: Path = Path("artifacts"),
        reasoning_state_enabled: bool = False,
        model_request_limit: int = 1,
        tool_call_limit: int = 0,
    ) -> dict[str, Any]:
        """Generate, verify, and optionally reuse results within one shared Run budget."""

        if model_request_limit < 1 or tool_call_limit < 0:
            raise ValueError("model request limit must be positive and tool limit nonnegative")

        run_id = f"run_{uuid.uuid4().hex}"
        problem_sha256 = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        problem_id = problem_id or problem_sha256
        request_limit = model_request_limit if reasoning_state_enabled else 1
        tool_limit = tool_call_limit if reasoning_state_enabled else 0
        state = SharedReasoningState()
        request_count = 0
        tool_count = 0
        diagnosis_used = False
        request_kind = "solve"
        stop_reason: str | None = None
        trace: list[dict[str, Any]] = [
            {
                "event": "run_started",
                "run_id": run_id,
                "problem_id": problem_id,
                "problem_sha256": problem_sha256,
                "condition_id": condition_id,
            }
        ]
        replies = []
        result: dict[str, Any] | None = None
        verification: dict[str, object] = {}
        started = time.perf_counter()

        while request_count < request_limit:
            evidence = state.valid_evidence() if reasoning_state_enabled else ()
            context = _render_evidence(evidence)
            parts = [problem]
            if context:
                parts.append(f"Verified context:\n{context}")
            if request_kind == "diagnosis":
                parts.append("One bounded diagnosis: make a substantive correction or stop.")
            prompt = "\n\n".join(parts)
            referenced_ids = [item.evidence_id for item in evidence]
            request_id = f"{run_id}_request_{request_count + 1:03d}"
            if reasoning_state_enabled:
                trace.append(
                    {
                        "event": "model_request_sent",
                        "request_id": request_id,
                        "request_kind": request_kind,
                        "referenced_evidence_ids": referenced_ids,
                        "context_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    }
                )
            previous_state = (
                verification.get("status"),
                result["id"] if result else None,
                _state_fingerprint(state),
            )
            reply = self._model_port.complete(prompt)
            request_count += 1
            replies.append(reply)

            verification = verify_integer_addition(problem, reply.text)
            result_scope = f"{problem_sha256}:{verification['scope']}"
            result_id = stable_id("result", {"content": reply.text, "scope": result_scope})
            result = {"id": result_id, "answer": reply.text}
            trace.append(
                {
                    "event": "answer_generated",
                    "request_id": request_id,
                    "result_id": result_id,
                    "model": reply.model or "unknown",
                    "answer_sha256": hashlib.sha256(reply.text.encode("utf-8")).hexdigest(),
                }
            )
            trace.append({"event": "verification_completed", "result_id": result_id, **verification})

            if reasoning_state_enabled and verification["status"] == "verified":
                item = state.add_verified_result(reply.text, scope=result_scope)
                trace.append(_evidence_event("verified_result_added", item))

            for call in reply.tool_calls if reasoning_state_enabled else ():
                if self._tool_executor is None:
                    trace.append(
                        {"event": "tool_call_not_executed", "request_id": request_id, "reason": "no_executor"}
                    )
                    continue
                if tool_count >= tool_limit:
                    trace.append(
                        {
                            "event": "tool_call_not_executed",
                            "request_id": request_id,
                            "reason": "tool_budget_exhausted",
                        }
                    )
                    break

                invocation_id = f"{run_id}_tool_{tool_count + 1:03d}"
                tool_count += 1
                receipt = self._tool_executor.execute(invocation_id, call)
                try:
                    item = state.add_tool_receipt(
                        receipt, invocation_id=invocation_id, call=call
                    )
                except ValueError:
                    trace.append({"event": "tool_receipt_rejected", "invocation_id": invocation_id})
                else:
                    trace.append(
                        {
                            **_evidence_event("tool_receipt_accepted", item),
                            "invocation_id": invocation_id,
                            "receipt_id": receipt.receipt_id,
                            "output_sha256": hashlib.sha256(
                                receipt.output.encode("utf-8")
                            ).hexdigest(),
                        }
                    )

            if not reasoning_state_enabled:
                stop_reason = "answer_generated"
                break

            current_state = (verification["status"], result_id, _state_fingerprint(state))
            substantive_change = current_state != previous_state
            trace.append(
                {
                    "event": "progress_checked",
                    "substantive_change": substantive_change,
                    "evidence_ids": list(_state_fingerprint(state)),
                }
            )
            if substantive_change:
                if request_count < request_limit:
                    request_kind = "continuation"
                    continue
                stop_reason = "answer_generated"
                break

            if request_kind == "diagnosis" or diagnosis_used:
                stop_reason = "no_progress"
                break
            if request_count < request_limit:
                diagnosis_used = True
                request_kind = "diagnosis"
                continue
            stop_reason = "model_request_budget_exhausted"
            break

        if result is None:
            raise RuntimeError("Runtime ended without a model response")
        if stop_reason is None:
            stop_reason = "model_request_budget_exhausted"

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        config = {
            "mode": "offline",
            "route": "single",
            "model_port": self._model_port.name,
            "reasoning_config": "none",
            "mechanisms": {"shared_reasoning_state": reasoning_state_enabled},
            "budget": {
                "scope": "run_shared",
                "model_requests": request_limit,
                "tokens": "unknown",
                "tools": tool_limit,
                "elapsed_limit_ms": "unknown",
                "cost_usd": "unknown",
            },
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        revision = _source_revision()
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        trace_path = run_dir / "trace.jsonl"
        run_path = run_dir / "run.json"
        input_tokens = _sum_usage(replies, "input_tokens")
        output_tokens = _sum_usage(replies, "output_tokens")
        trace.append({"event": "run_stopped", "status": "completed", "stop_reason": stop_reason})
        result_record = {
            "schema_version": 1,
            "run_id": run_id,
            "source": {"revision": revision},
            "config": config,
            "config_sha256": config_sha256,
            "problem": {"id": problem_id, "sha256": problem_sha256},
            "condition_id": condition_id,
            "model": {
                "requested": self._model_port.name,
                "actual": replies[-1].model or "unknown",
                "reasoning_config": config["reasoning_config"],
            },
            "budget": {
                "scope": "run_shared",
                "model_requests": {"limit": request_limit, "used": request_count},
                "tokens": {"limit": "unknown", "used": _sum_usage(replies, "tokens")},
                "tools": {"limit": tool_limit, "used": tool_count},
                "elapsed_ms": elapsed_ms,
                "elapsed_limit_ms": "unknown",
                "cost_usd": {"limit": "unknown", "used": "unknown"},
            },
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tokens": (
                    input_tokens + output_tokens
                    if isinstance(input_tokens, int) and isinstance(output_tokens, int)
                    else "unknown"
                ),
                "source": _usage_source(replies),
            },
            "cost": {"amount_usd": "unknown", "source": "unknown"},
            "result": result,
            "verification": verification,
            "evidence": state.public_snapshot(),
            "run": {"status": "completed", "stop_reason": stop_reason},
            "artifacts": {"run": str(run_path), "trace": str(trace_path)},
        }
        trace_path.write_text(
            "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
        )
        run_path.write_text(
            json.dumps(result_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result_record


def _render_evidence(evidence: tuple[Evidence, ...]) -> str:
    """Render only valid verified results and controlled successful tool receipts."""

    return "\n".join(
        f"[{item.evidence_id}; {item.result_id or 'tool receipt'}] {item.scope}: {item.content}"
        for item in evidence
    )


def _state_fingerprint(state: SharedReasoningState) -> tuple[str, ...]:
    """Use substantive evidence identity, never revision or request counters, as progress."""

    return tuple(item.evidence_id for item in state.valid_evidence())


def _evidence_event(event: str, evidence: Evidence) -> dict[str, Any]:
    """Describe evidence provenance without persisting its underlying text."""

    return {
        "event": event,
        "evidence_id": evidence.evidence_id,
        "result_id": evidence.result_id,
        "source": evidence.source,
        "content_sha256": hashlib.sha256(evidence.content.encode("utf-8")).hexdigest(),
    }


def _sum_usage(replies: list[Any], key: str) -> int | str:
    """Sum a usage field only when every request reports an integer measurement."""

    if key == "tokens":
        values = [
            reply.input_tokens + reply.output_tokens
            if isinstance(reply.input_tokens, int) and isinstance(reply.output_tokens, int)
            else "unknown"
            for reply in replies
        ]
    else:
        values = [getattr(reply, key) for reply in replies]
    return sum(values) if all(isinstance(value, int) for value in values) else "unknown"


def _usage_source(replies: list[Any]) -> str:
    """Keep the measurement source only when all requests share the same known source."""

    sources = {reply.usage_source for reply in replies}
    return sources.pop() if len(sources) == 1 else "mixed_or_unknown"


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for configuration and trace fingerprints."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_revision() -> str:
    """Read the containing Git revision, returning unknown outside a Git checkout."""

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"