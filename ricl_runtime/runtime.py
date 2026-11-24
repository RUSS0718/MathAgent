"""Single-route Runtime with explicit run accounting and redacted artifacts."""

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .identity import stable_id
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