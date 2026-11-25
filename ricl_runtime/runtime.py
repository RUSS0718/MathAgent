"""Single-route Runtime with explicit run accounting and redacted artifacts."""

import hashlib
import json
import subprocess
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .aprs import Candidate, VerifierEvidence, evaluate_fixed_candidates
from .counterfactual import CounterfactualCheckpoint, InterventionAudit, RepairOptions
from .identity import stable_id
from .population import CandidateRoute, PopulationBudget
from .port import ModelPort, ModelPortFailure, ModelReply, ToolExecutor
from .reasoning_state import Evidence, SharedReasoningState
from .verification import verify_integer_addition


@dataclass
class _RunScope:
    """Correlate Runtime phases that execute within one configured Run."""

    run_id: str = field(default_factory=lambda: f"run_{uuid.uuid4().hex}")
    trace: list[dict[str, Any]] = field(default_factory=list)
    request_offset: int = 0
    state: SharedReasoningState = field(default_factory=SharedReasoningState)

    def request_id(self, index: int) -> str:
        return f"{self.run_id}_request_{self.request_offset + index:03d}"


def _write_run(result: dict[str, Any], trace: list[dict[str, Any]]) -> None:
    run_path = Path(result["artifacts"]["run"])
    trace_path = Path(result["artifacts"]["trace"])
    run_path.parent.mkdir(parents=True, exist_ok=False)
    trace_path.write_text(
        "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
    )
    run_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _phase_trace(events: list[dict[str, Any]], scope: _RunScope | None) -> list[dict[str, Any]]:
    if scope is None:
        return events
    events[0]["event"] = "phase_started"
    scope.trace.extend(events)
    return scope.trace


def _finish_phase(
    result: dict[str, Any],
    trace: list[dict[str, Any]],
    scope: _RunScope | None,
    state: SharedReasoningState,
) -> dict[str, Any]:
    if scope is None:
        _write_run(result, trace)
    else:
        scope.state = state
        scope.request_offset += result["budget"]["model_requests"]["used"]
        trace[-1]["event"] = "phase_stopped"
        trace[-1]["phase"] = "counterfactual" if "intervention" in result else result["config"]["route"]
    return result


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
        intervention_feedback: str | None = None,
        repair_options: RepairOptions | None = None,
        intervention_auditor: Callable[[str, ModelReply], InterventionAudit] | None = None,
        feedback_kind: Literal["random", "diagnostic"] = "diagnostic",
        enabled: bool = True,
        problem_id: str | None = None,
        condition_id: str = "offline-counterfactual",
        output_root: Path = Path("artifacts"),
        model_request_limit: int = 3,
        _scope: _RunScope | None = None,
    ) -> dict[str, Any]:
        """Run isolated branches and, when budget permits, a parent continuation."""

        eligible = checkpoint.failure_count > 0 and checkpoint.trigger_count < checkpoint.max_trigger_count
        if not enabled or not eligible:
            return self.run(
                problem, problem_id=problem_id, condition_id=condition_id,
                output_root=output_root, _scope=_scope,
            )
        if model_request_limit < 2:
            raise ValueError("counterfactual branches require two shared model requests")
        if feedback_kind not in ("random", "diagnostic"):
            raise ValueError("feedback kind must be random or diagnostic")
        if repair_options is not None and intervention_feedback is not None:
            raise ValueError("provide repair options or direct diagnostic feedback")
        if feedback_kind == "random" and repair_options is None:
            raise ValueError("random repair requires a shared option pool and seed")
        selected_repair_id: str | None = None
        if repair_options is not None:
            selected_repair_id, intervention_feedback = repair_options.select(feedback_kind)
        if not intervention_feedback or not intervention_feedback.strip():
            raise ValueError("intervention feedback must be nonempty")

        checkpoint_trigger_count = checkpoint.trigger_count
        checkpoint.trigger_count += 1
        execution = _scope or _RunScope()
        run_id = execution.run_id
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
        trace = _phase_trace([
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
        ], _scope)
        started = time.perf_counter()
        for index, arm in enumerate(("control", "treatment"), start=1):
            prompt = common_prompt
            if arm == "treatment":
                prompt += f"\n\nIntervention feedback:\n{intervention_feedback}"
            request_id = execution.request_id(index)
            trace.append(
                {
                    "event": "model_request_sent",
                    "request_id": request_id,
                    "arm": arm,
                    "checkpoint_sha256": checkpoint_sha256,
                    **({"selected_repair_id": selected_repair_id} if arm == "treatment" else {}),
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
                "result_id": branch_result_id,
                "answer": reply.text,
                "action": reply.action,
                "route": reply.route,
                "verification": verification,
                "evidence": branch_states[arm].public_snapshot(),
            }

        control = branches["control"]
        treatment = branches["treatment"]
        action_changed = treatment["action"] is not None and treatment["action"] != control["action"]
        route_changed = treatment["route"] is not None and treatment["route"] != control["route"]
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
            parent_request_id = execution.request_id(len(replies) + 1)
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
                "result_id": parent_result_id,
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
                    "action_changed_from_checkpoint": (
                        parent_reply.action != checkpoint.current_action
                        if parent_reply.action is not None and checkpoint.current_action is not None
                        else "unknown"
                    ),
                    "route_changed_from_checkpoint": (
                        parent_reply.route != checkpoint.current_route
                        if parent_reply.route is not None and checkpoint.current_route is not None
                        else "unknown"
                    ),
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
            "feedback_sha256": hashlib.sha256(intervention_feedback.encode()).hexdigest(),
            **(
                {
                    "repair_option_ids": [option_id for option_id, _ in repair_options.options],
                    "repair_options_sha256": hashlib.sha256(
                        _canonical_json(repair_options.options).encode()
                    ).hexdigest(),
                    "repair_seed": repair_options.seed,
                }
                if repair_options is not None else {}
            ),
            "budget": {"scope": "run_shared", "model_requests": model_request_limit},
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        run_dir = output_root / run_id
        trace_path = run_dir / "trace.jsonl"
        run_path = run_dir / "run.json"
        trace.append({"event": "run_stopped", "status": "completed", "stop_reason": stop_reason})
        final = parent_continuation or control
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
            "cost": {"amount_usd": "unknown", "source": "unknown"},
            "result": {"id": final["result_id"], "answer": final["answer"]},
            "verification": final["verification"],
            "checkpoint": checkpoint_record,
            "branches": branches,
            "intervention": {
                "qualified": True,
                "feedback_kind": feedback_kind,
                "selected_repair_id": selected_repair_id,
                "audit_status": audit.status if audit else "unknown",
                "audit_source": audit.source if audit else "",
                "feedback_consumed": bool(parent_request_id),
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
        return _finish_phase(result_record, trace, _scope, parent_state)

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
        visible_context: str = "",
        _scope: _RunScope | None = None,
    ) -> dict[str, Any]:
        """Generate, verify, and optionally reuse results within one shared Run budget."""

        if model_request_limit < 1 or tool_call_limit < 0:
            raise ValueError("model request limit must be positive and tool limit nonnegative")

        execution = _scope or _RunScope()
        run_id = execution.run_id
        problem_sha256 = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        problem_id = problem_id or problem_sha256
        request_limit = model_request_limit
        tool_limit = tool_call_limit
        state = execution.state
        request_count = 0
        tool_count = 0
        diagnosis_used = False
        request_kind = "solve"
        stop_reason: str | None = None
        trace = _phase_trace([
            {
                "event": "run_started",
                "run_id": run_id,
                "problem_id": problem_id,
                "problem_sha256": problem_sha256,
                "condition_id": condition_id,
            }
        ], _scope)
        replies = []
        provider_requests: list[dict[str, Any]] = []
        ordinary_tool_results: list[str] = []
        result: dict[str, Any] | None = None
        verification: dict[str, object] = {}
        failure_status: str | None = None
        started = time.perf_counter()

        while request_count < request_limit:
            evidence = state.valid_evidence() if reasoning_state_enabled else ()
            context = _render_evidence(evidence)
            parts = [problem]
            if visible_context:
                parts.append(f"Problem context:\n{visible_context}")
            if context:
                parts.append(f"Verified context:\n{context}")
            if ordinary_tool_results:
                parts.append("Tool results:\n" + "\n".join(ordinary_tool_results))
            if request_kind == "diagnosis":
                parts.append("One bounded diagnosis: make a substantive correction or stop.")
                if not reasoning_state_enabled and result is not None:
                    parts.append(f"Previous answer failed the reference check:\n{result['answer']}")
            prompt = "\n\n".join(parts)
            referenced_ids = [item.evidence_id for item in evidence]
            request_id = execution.request_id(request_count + 1)
            if reasoning_state_enabled or request_kind != "solve":
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
            request_count += 1
            request_started = time.perf_counter()
            try:
                reply = self._model_port.complete(prompt)
            except ModelPortFailure as error:
                request_elapsed_ms = round((time.perf_counter() - request_started) * 1000, 3)
                failure_status = error.failure_status
                if failure_status not in {
                    "protocol_failed",
                    "unknown_outcome",
                    "timeout",
                    "budget_exhausted",
                    "invalid_output",
                    "preflight_rejected",
                }:
                    failure_status = "unknown_outcome"
                verification = {
                    "status": "unknown",
                    "applicable": False,
                    "scope": "none",
                    "reason": failure_status,
                }
                request_sent = getattr(error, "request_sent", "unknown")
                metadata = getattr(error, "reply", None)
                if not isinstance(metadata, ModelReply):
                    metadata = ModelReply("")
                if request_sent is not False:
                    replies.append(metadata)
                request_record = {
                    "request_id": request_id,
                    "requested_model": self._model_port.name,
                    "actual_model": metadata.model,
                    "provider_request_id": getattr(metadata, "request_id", "unknown"),
                    "finish_reason": getattr(metadata, "finish_reason", "unknown"),
                    "request_sent": request_sent,
                    "status": failure_status,
                    "failure_status": failure_status,
                    "elapsed_ms": request_elapsed_ms,
                    "usage": {
                        "input_tokens": metadata.input_tokens,
                        "output_tokens": metadata.output_tokens,
                        "source": metadata.usage_source,
                    },
                }
                if isinstance(getattr(error, "status_code", None), int):
                    request_record["http_status"] = error.status_code
                provider_requests.append(request_record)
                trace.append(
                    {
                        "event": (
                            "model_request_rejected_before_send"
                            if request_sent is False
                            else "model_request_failed"
                        ),
                        "request_id": request_id,
                        "provider_request_id": request_record["provider_request_id"],
                        "actual_model": request_record["actual_model"],
                        "finish_reason": request_record["finish_reason"],
                        "usage_source": metadata.usage_source,
                        "request_sent": request_sent,
                        "status": failure_status,
                        "failure_status": failure_status,
                        "elapsed_ms": request_elapsed_ms,
                        **(
                            {"http_status": error.status_code}
                            if "http_status" in request_record
                            else {}
                        ),
                    }
                )
                break

            request_elapsed_ms = round((time.perf_counter() - request_started) * 1000, 3)
            replies.append(reply)
            provider_request_id = getattr(reply, "request_id", "unknown") or "unknown"
            actual_model = reply.model or "unknown"
            finish_reason = getattr(reply, "finish_reason", "unknown") or "unknown"
            if finish_reason == "length":
                failure_status = "budget_exhausted"
            elif not reply.text.strip():
                failure_status = "invalid_output"
            if failure_status is not None:
                verification = {
                    "status": "unknown",
                    "applicable": False,
                    "scope": "none",
                    "reason": failure_status,
                }
                provider_requests.append(
                    {
                        "request_id": request_id,
                        "requested_model": self._model_port.name,
                        "actual_model": actual_model,
                        "provider_request_id": provider_request_id,
                        "finish_reason": finish_reason,
                        "request_sent": getattr(self._model_port, "provider", "offline") != "offline",
                        "status": failure_status,
                        "failure_status": failure_status,
                        "elapsed_ms": request_elapsed_ms,
                        "usage": {
                            "input_tokens": reply.input_tokens,
                            "output_tokens": reply.output_tokens,
                            "source": reply.usage_source,
                        },
                    }
                )
                trace.append(
                    {
                        "event": "model_request_failed",
                        "request_id": request_id,
                        "provider_request_id": provider_request_id,
                        "finish_reason": finish_reason,
                        "status": failure_status,
                        "failure_status": failure_status,
                        "elapsed_ms": request_elapsed_ms,
                        "actual_model": actual_model,
                        "usage_source": reply.usage_source,
                    }
                )
                break

            provider_requests.append(
                {
                    "request_id": request_id,
                    "requested_model": self._model_port.name,
                    "actual_model": actual_model,
                    "provider_request_id": provider_request_id,
                    "finish_reason": finish_reason,
                    "request_sent": getattr(self._model_port, "provider", "offline") != "offline",
                    "status": "completed",
                    "elapsed_ms": request_elapsed_ms,
                    "usage": {
                        "input_tokens": reply.input_tokens,
                        "output_tokens": reply.output_tokens,
                        "source": reply.usage_source,
                    },
                }
            )
            verification_started = time.perf_counter()
            verification = verify_integer_addition(problem, reply.text)
            verification_elapsed_ms = round((time.perf_counter() - verification_started) * 1000, 3)
            result_scope = f"{problem_sha256}:{verification['scope']}"
            result_id = stable_id("result", {"content": reply.text, "scope": result_scope})
            result = {"id": result_id, "answer": reply.text}
            trace.append(
                {
                    "event": "answer_generated",
                    "request_id": request_id,
                    "result_id": result_id,
                    "model": reply.model or "unknown",
                    "elapsed_ms": request_elapsed_ms,
                    "answer_sha256": hashlib.sha256(reply.text.encode("utf-8")).hexdigest(),
                }
            )
            trace.append(
                {
                    "event": "verification_completed",
                    "result_id": result_id,
                    "elapsed_ms": verification_elapsed_ms,
                    **verification,
                }
            )

            if reasoning_state_enabled and verification["status"] == "verified":
                item = state.add_verified_result(reply.text, scope=result_scope)
                trace.append(_evidence_event("verified_result_added", item))

            previous_tool_results = len(ordinary_tool_results)
            for call in reply.tool_calls:
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
                        ordinary_result = f"{receipt.tool_name}: {receipt.output}"
                        if ordinary_result not in ordinary_tool_results:
                            ordinary_tool_results.append(ordinary_result)

            if not reasoning_state_enabled:
                if request_count < request_limit:
                    if len(ordinary_tool_results) > previous_tool_results:
                        request_kind = "tool_continuation"
                        continue
                    if verification["status"] == "failed" and not diagnosis_used:
                        diagnosis_used = True
                        request_kind = "diagnosis"
                        continue
                if diagnosis_used and (verification["status"], result_id) == previous_state[:2]:
                    stop_reason = "no_progress"
                    break
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

        if result is None and failure_status is None:
            raise RuntimeError("Runtime ended without a model response")
        if stop_reason is None:
            stop_reason = "model_request_budget_exhausted"

        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        provider_config = {
            "provider": getattr(self._model_port, "provider", "offline"),
            "thinking": {"type": self._model_port.thinking}
            if hasattr(self._model_port, "thinking")
            else "none",
            "max_tokens": getattr(self._model_port, "max_output_tokens", "unknown"),
            "tools_enabled": self._tool_executor is not None and tool_limit > 0,
        }
        provider_config.update(getattr(self._model_port, "preflight_config", {}))
        config = {
            "mode": "provider" if provider_config["provider"] != "offline" else "offline",
            "route": "single",
            "model_port": self._model_port.name,
            "provider_config": provider_config,
            "reasoning_config": provider_config["thinking"],
            **(
                {"visible_context_sha256": hashlib.sha256(visible_context.encode()).hexdigest()}
                if visible_context else {}
            ),
            "mechanisms": {"shared_reasoning_state": reasoning_state_enabled},
            "budget": {
                "scope": "run_shared",
                "model_requests": request_limit,
                "tokens": provider_config["max_tokens"],
                "tools": tool_limit,
                "elapsed_limit_ms": "unknown",
                "cost_usd": "unknown",
            },
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        revision = _source_revision()
        run_dir = output_root / run_id
        trace_path = run_dir / "trace.jsonl"
        run_path = run_dir / "run.json"
        input_tokens = _sum_usage(replies, "input_tokens")
        output_tokens = _sum_usage(replies, "output_tokens")
        trace.append(
            {
                "event": "run_stopped",
                "status": "failed" if failure_status else "completed",
                "stop_reason": failure_status or stop_reason,
            }
        )
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
                "actual": replies[-1].model or "unknown" if replies else "unknown",
                "provider_request_id": getattr(replies[-1], "request_id", "unknown")
                if replies
                else "unknown",
                "reasoning_config": config["reasoning_config"],
            },
            "provider_requests": provider_requests,
            "budget": {
                "scope": "run_shared",
                "model_requests": {"limit": request_limit, "used": request_count},
                "tokens": {
                    "limit": provider_config["max_tokens"],
                    "used": _sum_usage(replies, "tokens"),
                },
                "tools": {"limit": tool_limit, "used": tool_count},
                "elapsed_ms": elapsed_ms,
                "elapsed_limit_ms": "unknown",
                "cost_usd": {
                    "limit": provider_config.get("cost_limit_usd", "unknown"),
                    "preflight_upper_bound": provider_config.get(
                        "preflight_cost_upper_bound_usd", "unknown"
                    ),
                    "used": "unknown",
                },
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
            "run": {
                "status": "failed" if failure_status else "completed",
                "stop_reason": failure_status or stop_reason,
                **({"failure_status": failure_status} if failure_status else {}),
            },
            "artifacts": {"run": str(run_path), "trace": str(trace_path)},
        }
        return _finish_phase(result_record, trace, _scope, state)


    def run_population(
        self,
        problem: str,
        routes: tuple[CandidateRoute, ...],
        *,
        budget: PopulationBudget,
        problem_id: str | None = None,
        condition_id: str = "offline-serial-population",
        output_root: Path = Path("artifacts"),
        aprs_enabled: bool = True,
        max_candidates: int | None = None,
        visible_context: str = "",
        _scope: _RunScope | None = None,
    ) -> dict[str, Any]:
        """Expand supplied route opportunities serially under one Run budget."""

        route_ids = [route.candidate.candidate_id for route in routes]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("candidate route IDs must be unique")
        if max_candidates is not None and max_candidates < 1:
            raise ValueError("candidate limit must be positive")

        execution = _scope or _RunScope()
        run_id = execution.run_id
        problem_sha256 = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        problem_id = problem_id or problem_sha256
        candidate_set_sha256 = hashlib.sha256(
            _canonical_json(
                [
                    {
                        "candidate_id": route.candidate.candidate_id,
                        "source": route.source,
                        "parent_route_id": route.parent_route_id,
                        "prompt_sha256": hashlib.sha256(route.prompt.encode("utf-8")).hexdigest(),
                    }
                    for route in routes
                ]
            ).encode("utf-8")
        ).hexdigest()
        trace = _phase_trace([
            {
                "event": "run_started",
                "run_id": run_id,
                "problem_id": problem_id,
                "problem_sha256": problem_sha256,
                "condition_id": condition_id,
                "route": "serial_population",
                "ranking_mode": "aprs" if aprs_enabled else "plain_search",
                "candidate_ids": route_ids,
                "candidate_set_sha256": candidate_set_sha256,
            }
        ], _scope)
        state = execution.state
        expanded: list[CandidateRoute] = []
        scored_candidates: list[Candidate] = []
        replies: list[Any] = []
        verifier_evidence: list[VerifierEvidence] = []
        outcomes: dict[str, dict[str, Any]] = {}
        request_count = 0
        tool_count = 0
        reserved_tokens = 0
        committed_tokens = 0
        reserved_elapsed = 0
        reserved_cost = 0.0
        budget_blocked = False
        candidate_limit_reached = False
        processed: set[str] = set()
        route_records = {
            route.candidate.candidate_id: _route_record(route, "pending", None)
            for route in routes
        }
        started = time.perf_counter()

        for route in routes:
            candidate_id = route.candidate.candidate_id
            if max_candidates is not None and len(expanded) >= max_candidates:
                candidate_limit_reached = True
                trace.append(_route_event(route, "candidate_discarded", "candidate_limit_reached"))
                route_records[candidate_id]["status"] = "discarded"
                route_records[candidate_id]["stop_reason"] = "candidate_limit_reached"
                processed.add(candidate_id)
                continue

            gaps = _population_budget_gaps(
                route,
                budget,
                requests=request_count,
                tokens=committed_tokens,
                tools=tool_count,
                elapsed_ms=max(reserved_elapsed, (time.perf_counter() - started) * 1000),
                cost_usd=reserved_cost,
            )
            if gaps:
                budget_blocked = True
                trace.append(
                    _route_event(
                        route,
                        "candidate_discarded",
                        "budget_insufficient",
                        insufficient_dimensions=gaps,
                    )
                )
                route_records[candidate_id]["status"] = "discarded"
                route_records[candidate_id]["stop_reason"] = "budget_insufficient"
                route_records[candidate_id]["insufficient_dimensions"] = gaps
                processed.add(candidate_id)
                break

            evidence = state.valid_evidence()
            prompt_parts = [problem]
            if visible_context:
                prompt_parts.append(f"Problem context:\n{visible_context}")
            prompt_parts.append(f"Candidate route:\n{route.prompt}")
            if evidence:
                prompt_parts.append(f"Verified context:\n{_render_evidence(evidence)}")
            prompt = "\n\n".join(prompt_parts)
            request_id = execution.request_id(request_count + 1)
            trace.append(
                {
                    **_route_event(route, "candidate_expansion_started"),
                    "request_id": request_id,
                    "referenced_evidence_ids": [item.evidence_id for item in evidence],
                    "context_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "reservation": {
                        "tokens": route.candidate.known_token_cost,
                        "tools": route.tool_calls_reserved,
                        "elapsed_ms": route.elapsed_ms_reserved,
                        "cost_usd": route.cost_usd_reserved,
                    },
                }
            )
            reply = self._model_port.complete(prompt)
            request_count += 1
            replies.append(reply)
            token_reservation = route.candidate.known_token_cost or 0
            reserved_tokens += token_reservation
            actual_tokens = (
                reply.input_tokens + reply.output_tokens
                if isinstance(reply.input_tokens, int) and isinstance(reply.output_tokens, int)
                else 0
            )
            committed_tokens += max(token_reservation, actual_tokens)
            reserved_elapsed += route.elapsed_ms_reserved or 0
            reserved_cost += route.cost_usd_reserved or 0.0
            expanded.append(route)
            scored_candidates.append(route.candidate)
            route_records[candidate_id]["status"] = "expanded"
            processed.add(candidate_id)

            verification = verify_integer_addition(problem, reply.text)
            scope = f"{problem_sha256}:{verification['scope']}"
            result_id = stable_id("result", {"content": reply.text, "scope": scope})
            answer_sha256 = hashlib.sha256(reply.text.encode("utf-8")).hexdigest()
            if verification["status"] == "verified":
                item = state.add_verified_result(reply.text, scope=scope)
                evidence_id, obligation_id, evidence_kind, valid = item.evidence_id, scope, "goal", True
                trace.append(_evidence_event("verified_result_added", item))
            else:
                evidence_id = stable_id(
                    "answer-check",
                    {"candidate_id": candidate_id, "result_id": result_id, "verification": verification},
                )
                obligation_id, evidence_kind, valid = None, "answer_check", False
            verifier_evidence.append(
                VerifierEvidence(
                    candidate_id,
                    evidence_id,
                    obligation_id,
                    "accepted" if valid else str(verification["status"]),
                    valid,
                    evidence_kind,
                )
            )
            outcomes[candidate_id] = {
                "result_id": result_id,
                "answer": reply.text,
                "answer_sha256": answer_sha256,
                "verification": verification,
                "evidence_id": evidence_id,
                "model": reply.model or "unknown",
            }
            trace.append(
                {
                    **_route_event(route, "candidate_expanded"),
                    "request_id": request_id,
                    "result_id": result_id,
                    "answer_sha256": answer_sha256,
                    "verification_status": verification["status"],
                    "evidence_ids": [evidence_id],
                    "model": reply.model or "unknown",
                }
            )

            route_tool_count = 0
            for call in reply.tool_calls:
                if self._tool_executor is None:
                    trace.append({"event": "tool_call_not_executed", "request_id": request_id, "reason": "no_executor"})
                    continue
                if route_tool_count >= route.tool_calls_reserved:
                    trace.append({"event": "tool_call_not_executed", "request_id": request_id, "reason": "tool_reservation_exhausted"})
                    continue
                invocation_id = f"{run_id}_tool_{tool_count + 1:03d}"
                route_tool_count += 1
                tool_count += 1
                receipt = self._tool_executor.execute(invocation_id, call)
                try:
                    item = state.add_tool_receipt(receipt, invocation_id=invocation_id, call=call)
                except ValueError:
                    trace.append({"event": "tool_receipt_rejected", "invocation_id": invocation_id})
                else:
                    trace.append(
                        {
                            **_evidence_event("tool_receipt_accepted", item),
                            "request_id": request_id,
                            "invocation_id": invocation_id,
                            "receipt_id": receipt.receipt_id,
                        }
                    )

            elapsed = (time.perf_counter() - started) * 1000
            exceeded = []
            if committed_tokens > budget.tokens:
                exceeded.append(("tokens", committed_tokens, budget.tokens))
            if elapsed > budget.elapsed_ms:
                exceeded.append(("elapsed_ms", round(elapsed, 3), budget.elapsed_ms))
            if exceeded:
                budget_blocked = True
                for dimension, used, limit in exceeded:
                    trace.append(
                        {
                            "event": "population_budget_exceeded",
                            "candidate_id": candidate_id,
                            "dimension": dimension,
                            "used": used,
                            "limit": limit,
                        }
                    )
                break

        if budget_blocked or candidate_limit_reached:
            reason = "budget_insufficient" if budget_blocked else "candidate_limit_reached"
            for route in routes:
                candidate_id = route.candidate.candidate_id
                if candidate_id not in processed:
                    trace.append(_route_event(route, "candidate_discarded", reason))
                    route_records[candidate_id]["status"] = "discarded"
                    route_records[candidate_id]["stop_reason"] = reason
                    processed.add(candidate_id)

        ranking = evaluate_fixed_candidates(
            tuple(scored_candidates),
            tuple(verifier_evidence),
            budget_snapshot={
                "model_requests": {"limit": budget.model_requests, "used": request_count},
                "tokens": {
                    "limit": budget.tokens,
                    "used": _sum_usage(replies, "tokens"),
                    "reserved": reserved_tokens,
                    "committed": committed_tokens,
                },
                "tools": {"limit": budget.tools, "used": tool_count},
                "elapsed_ms": {
                    "limit": budget.elapsed_ms,
                    "used": round((time.perf_counter() - started) * 1000, 3),
                    "reserved": reserved_elapsed,
                },
                "cost_usd": {
                    "limit": budget.cost_usd,
                    "used": "unknown",
                    "reserved": round(reserved_cost, 6),
                },
            },
            tool_capabilities=("controlled_executor",) if self._tool_executor else (),
            verifier_capability="integer_addition_v1",
            aprs_enabled=aprs_enabled,
        )
        for evaluation in ranking["candidate_evaluations"]:
            trace.append(
                {
                    "event": "candidate_scored",
                    "ranking_mode": ranking["ranking_mode"],
                    "candidate_id": evaluation["candidate_id"],
                    "evidence_ids": evaluation["evidence_ids"],
                    "verifier_evidence": evaluation["verifier_evidence"],
                    "aprs_score": evaluation["aprs_score"],
                    "priority": evaluation["priority"],
                }
            )

        selected_id = ranking["priority_order"][0] if ranking["priority_order"] else None
        selected = outcomes.get(selected_id) if selected_id is not None else None
        if selected is not None:
            score = next(
                item["aprs_score"]
                for item in ranking["candidate_evaluations"]
                if item["candidate_id"] == selected_id
            )
            trace.append(
                {
                    "event": "candidate_selected",
                    "candidate_id": selected_id,
                    "ranking_mode": ranking["ranking_mode"],
                    "evidence_ids": [selected["evidence_id"]],
                    "aprs_score": score,
                }
            )
            route_records[selected_id]["status"] = "selected"
            route_records[selected_id]["stop_reason"] = "selected"
        for route in expanded:
            candidate_id = route.candidate.candidate_id
            if candidate_id != selected_id:
                trace.append(
                    {
                        **_route_event(route, "candidate_discarded", "not_selected"),
                        "phase": "selection",
                        "evidence_ids": [outcomes[candidate_id]["evidence_id"]],
                    }
                )
                route_records[candidate_id]["status"] = "discarded"
                route_records[candidate_id]["stop_reason"] = "not_selected"

        stop_reason = (
            "budget_insufficient"
            if budget_blocked
            else "candidate_limit_reached"
            if candidate_limit_reached
            else "candidate_set_exhausted"
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        config = {
            "mode": "offline",
            "route": "serial_population",
            "model_port": self._model_port.name,
            "reasoning_config": "none",
            **(
                {"visible_context_sha256": hashlib.sha256(visible_context.encode()).hexdigest()}
                if visible_context else {}
            ),
            "mechanisms": {"population": True, "aprs": aprs_enabled},
            "ranking_mode": ranking["ranking_mode"],
            "candidate_set_sha256": candidate_set_sha256,
            "max_candidates": max_candidates,
            "budget": {
                "scope": "run_shared",
                "model_requests": budget.model_requests,
                "tokens": budget.tokens,
                "tools": budget.tools,
                "elapsed_limit_ms": budget.elapsed_ms,
                "cost_usd": budget.cost_usd,
            },
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        run_dir = output_root / run_id
        trace_path, run_path = run_dir / "trace.jsonl", run_dir / "run.json"
        status = "completed" if selected is not None and not budget_blocked else "stopped"
        verification = selected["verification"] if selected else {
            "status": "unknown", "scope": "none", "reason": "no_candidate_expanded"
        }
        result_record = {
            "schema_version": 1,
            "run_id": run_id,
            "source": {"revision": _source_revision()},
            "config": config,
            "config_sha256": config_sha256,
            "problem": {"id": problem_id, "sha256": problem_sha256},
            "condition_id": condition_id,
            "model": {
                "requested": self._model_port.name,
                "actual": selected["model"] if selected else "unknown",
                "reasoning_config": "none",
            },
            "budget": ranking["budget_snapshot"],
            "usage": {
                "input_tokens": _sum_usage(replies, "input_tokens"),
                "output_tokens": _sum_usage(replies, "output_tokens"),
                "tokens": _sum_usage(replies, "tokens"),
                "source": _usage_source(replies) if replies else "unknown",
            },
            "cost": {"amount_usd": "unknown", "source": "unknown"},
            "result": {"id": selected["result_id"], "answer": selected["answer"]} if selected else None,
            "verification": verification,
            "evidence": state.public_snapshot(),
            "population": {
                "ranking_mode": ranking["ranking_mode"],
                "candidate_ids": route_ids,
                "expanded_candidate_ids": [route.candidate.candidate_id for route in expanded],
                "selected_candidate_id": selected_id,
                "candidate_evaluations": ranking["candidate_evaluations"],
                "routes": [route_records[route.candidate.candidate_id] for route in routes],
                "stop_reason": stop_reason,
            },
            "run": {"status": status, "stop_reason": stop_reason, "elapsed_ms": elapsed_ms},
            "artifacts": {"run": str(run_path), "trace": str(trace_path)},
        }
        trace.append({"event": "run_stopped", "status": status, "stop_reason": stop_reason})
        return _finish_phase(result_record, trace, _scope, state)



def _route_event(route: CandidateRoute, event: str, reason: str | None = None, **fields: Any) -> dict[str, Any]:
    """Keep route provenance on expansion and discard events without storing prompt text."""

    return {
        "event": event,
        "candidate_id": route.candidate.candidate_id,
        "source": route.source,
        "parent_route_id": route.parent_route_id,
        "reason": reason,
        **fields,
    }


def _route_record(
    route: CandidateRoute,
    status: str,
    stop_reason: str | None,
    **fields: Any,
) -> dict[str, Any]:
    """Project route identity and provenance into a saved Run record."""

    return {
        "candidate_id": route.candidate.candidate_id,
        "source": route.source,
        "parent_route_id": route.parent_route_id,
        "prompt_sha256": hashlib.sha256(route.prompt.encode("utf-8")).hexdigest(),
        "status": status,
        "stop_reason": stop_reason,
        **fields,
    }


def _population_budget_gaps(
    route: CandidateRoute,
    budget: PopulationBudget,
    *,
    requests: int,
    tokens: int,
    tools: int,
    elapsed_ms: float,
    cost_usd: float,
) -> list[str]:
    """Return hard admission failures; an unknown reservation is never free."""

    gaps: list[str] = []
    if requests + 1 > budget.model_requests:
        gaps.append("model_requests")
    token_cost = route.candidate.known_token_cost
    if token_cost is None:
        gaps.append("tokens_unknown")
    elif tokens + token_cost > budget.tokens:
        gaps.append("tokens")
    if tools + route.tool_calls_reserved > budget.tools:
        gaps.append("tools")
    if route.elapsed_ms_reserved is None:
        gaps.append("elapsed_ms_unknown")
    elif elapsed_ms + route.elapsed_ms_reserved > budget.elapsed_ms:
        gaps.append("elapsed_ms")
    if route.cost_usd_reserved is None:
        gaps.append("cost_usd_unknown")
    elif cost_usd + route.cost_usd_reserved > budget.cost_usd:
        gaps.append("cost_usd")
    return gaps

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

    if not replies:
        return "unknown"
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

    if not replies:
        return "unknown"
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
