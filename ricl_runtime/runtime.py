"""Single-route Runtime with explicit run accounting and redacted artifacts."""

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .aprs import Candidate, VerifierEvidence, evaluate_fixed_candidates
from .identity import stable_id
from .population import CandidateRoute, PopulationBudget
from .port import ModelPort, ToolExecutor
from .reasoning_state import Evidence, SharedReasoningState
from .verification import verify_integer_addition


class Runtime:
    """Run one offline text problem through a ModelPort and an independent check."""

    def __init__(self, model_port: ModelPort, *, tool_executor: ToolExecutor | None = None) -> None:
        """Bind the model capability and optional controlled tool executor."""

        self._model_port = model_port
        self._tool_executor = tool_executor

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
    ) -> dict[str, Any]:
        """Expand supplied route opportunities serially under one Run budget."""

        route_ids = [route.candidate.candidate_id for route in routes]
        if len(route_ids) != len(set(route_ids)):
            raise ValueError("candidate route IDs must be unique")
        if max_candidates is not None and max_candidates < 1:
            raise ValueError("candidate limit must be positive")

        run_id = f"run_{uuid.uuid4().hex}"
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
        trace: list[dict[str, Any]] = [
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
        ]
        state = SharedReasoningState()
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
            prompt_parts = [problem, f"Candidate route:\n{route.prompt}"]
            if evidence:
                prompt_parts.append(f"Verified context:\n{_render_evidence(evidence)}")
            prompt = "\n\n".join(prompt_parts)
            request_id = f"{run_id}_request_{request_count + 1:03d}"
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
        run_dir.mkdir(parents=True, exist_ok=False)
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
        trace_path.write_text(
            "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
        )
        run_path.write_text(
            json.dumps(result_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result_record



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