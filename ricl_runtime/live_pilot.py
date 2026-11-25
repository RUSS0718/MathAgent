"""Execute the fixed, separately approved DeepSeek paired pilot."""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from random import Random

from .experiments import _CONDITIONS, _run_case, _run_fixture_rollback, _write_manifest
from .population import PopulationBudget
from .port import ModelPortFailure
from .providers.chat_completions import (
    ChatCompletionReply,
    ProviderOutcomeUnknownError,
    ProviderPreflightError,
    ProviderProtocolError,
    ProviderTimeoutError,
    validate_base_url,
)
from .providers.deepseek import (
    ALLOWED_HOST,
    INPUT_FRAMING_MARGIN_TOKENS,
    INPUT_PEAK_USD_PER_MILLION,
    MAX_OUTPUT_TOKENS,
    OUTPUT_PEAK_USD_PER_MILLION,
    DeepSeekModelPort,
)
from .runtime import _failure_reply, _model_failure_status, _source_revision

MODEL = "deepseek-v4-flash"
MAX_REQUESTS = 47
MAX_PROMPT_BYTES = 4096
REQUEST_TIMEOUT_SECONDS = 30
COST_LIMIT = Decimal("0.10")
_INPUT_LIMIT = MAX_PROMPT_BYTES + INPUT_FRAMING_MARGIN_TOKENS
_TOKEN_LIMIT = _INPUT_LIMIT + MAX_OUTPUT_TOKENS
_REQUEST_COST = (
    _INPUT_LIMIT * INPUT_PEAK_USD_PER_MILLION + MAX_OUTPUT_TOKENS * OUTPUT_PEAK_USD_PER_MILLION
) / 1_000_000
_RUN_BUDGET = PopulationBudget(
    model_requests=5,
    tokens=5 * _TOKEN_LIMIT,
    tools=0,
    elapsed_ms=160_000,
    cost_usd=float(5 * _REQUEST_COST),
)
_ACCEPTED_MODELS = {MODEL, "deepseek-flash", "DeepSeek-V4.1-Flash-1017"}


def _reply_fields(reply):
    return {
        "text": reply.text,
        "model": reply.model,
        "request_id": getattr(reply, "request_id", "unknown"),
        "finish_reason": getattr(reply, "finish_reason", "unknown"),
        "input_tokens": reply.input_tokens,
        "output_tokens": reply.output_tokens,
        "usage_source": reply.usage_source,
    }


def _selected_provider() -> DeepSeekModelPort:
    provider = DeepSeekModelPort.from_environment(thinking="disabled")
    if provider.model != MODEL or not validate_base_url(provider.base_url, ALLOWED_HOST):
        raise ProviderPreflightError("approved DeepSeek model and host are required")
    return provider


def _complete_worker() -> None:
    """Perform one request in a subprocess that the caller can time out."""
    from dataclasses import replace

    prompt = sys.stdin.buffer.read(MAX_PROMPT_BYTES + 1).decode("utf-8")
    try:
        if not prompt or len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ProviderPreflightError("pilot prompt exceeds its byte bound")
        reply = _selected_provider().complete(prompt)
        if "<think" in reply.text.lower() or "</think" in reply.text.lower():
            raise ProviderProtocolError(
                "disabled thinking response contained inline reasoning",
                reply=replace(reply, text=""),
            )
    except ModelPortFailure as error:
        print(
            json.dumps(
                {
                    "failure_status": _model_failure_status(error),
                    "request_sent": getattr(error, "request_sent", "unknown"),
                    "reply": _reply_fields(replace(_failure_reply(error), text="")),
                    "http_status": getattr(error, "status_code", None),
                }
            )
        )
    else:
        print(
            json.dumps(
                {"reply": _reply_fields(replace(reply, text=reply.text.replace(prompt, "")))}
            )
        )


class _ReportedFailure(ModelPortFailure):
    def __init__(self, record):
        super().__init__(record["failure_status"])
        self.failure_status = record["failure_status"]
        self.request_sent = record["request_sent"]
        self.reply = ChatCompletionReply(**record["reply"])
        self.status_code = record.get("http_status")


def _call_with_deadline(prompt: str) -> ChatCompletionReply:
    try:
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                "from ricl_runtime.live_pilot import _complete_worker; _complete_worker()",
            ],
            input=prompt.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            check=True,
        )
        record = json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        raise ProviderTimeoutError("pilot model request exceeded the wall-clock limit") from None
    except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError):
        raise ProviderOutcomeUnknownError("pilot worker outcome is unknown") from None
    if "failure_status" in record:
        raise _ReportedFailure(record)
    return ChatCompletionReply(**record["reply"])


class _PilotPort:
    """Enforce one aggregate budget across all matrix and rollback conditions."""

    name = MODEL
    provider = "deepseek"
    thinking = "disabled"
    max_output_tokens = MAX_OUTPUT_TOKENS
    cost_limit_usd = float(COST_LIMIT)

    def __init__(self, output: Path, provider: DeepSeekModelPort):
        self.events = output / "requests.jsonl"
        self.preflight_config = {
            **provider.preflight_config,
            "max_prompt_bytes": MAX_PROMPT_BYTES,
            "max_input_tokens_upper_bound": _INPUT_LIMIT,
            "preflight_cost_upper_bound_usd": str(_REQUEST_COST),
            "cost_limit_usd": float(COST_LIMIT),
            "wall_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        }
        self.attempts = 0
        self.halted = None
        self.condition = ""

    def _record(self, event) -> None:
        with self.events.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event) + "\n")

    def complete(self, prompt: str) -> ChatCompletionReply:
        if self.halted:
            raise ProviderPreflightError("pilot halted after an earlier request failure")
        if len(prompt.encode("utf-8")) > MAX_PROMPT_BYTES:
            raise ProviderPreflightError("pilot prompt exceeds its byte bound")
        if self.attempts >= MAX_REQUESTS or (self.attempts + 1) * _REQUEST_COST > COST_LIMIT:
            raise ProviderPreflightError("pilot aggregate request or cost limit exhausted")
        self.attempts += 1
        entry = {"attempt": self.attempts, "condition": self.condition}
        self._record(
            {
                **entry,
                "event": "request_reserved",
                "sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "cost_reserved_usd": str(_REQUEST_COST),
            }
        )
        started = time.monotonic()
        try:
            reply = _call_with_deadline(prompt)
            if (
                reply.model not in _ACCEPTED_MODELS | {"unknown"}
                or isinstance(reply.output_tokens, int)
                and reply.output_tokens > MAX_OUTPUT_TOKENS
                or isinstance(reply.input_tokens, int)
                and reply.input_tokens > _INPUT_LIMIT
                or reply.finish_reason == "length"
                or not reply.text.strip()
            ):
                raise _ReportedFailure(
                    {
                        "failure_status": (
                            "budget_exhausted"
                            if reply.finish_reason == "length"
                            else "invalid_output"
                        ),
                        "request_sent": True,
                        "reply": {**_reply_fields(reply), "text": ""},
                    }
                )
        except ModelPortFailure as error:
            self.halted = error.failure_status
            self._record(
                {
                    **entry,
                    "event": "request_failed",
                    "status": self.halted,
                    "request_sent": getattr(error, "request_sent", "unknown"),
                    "http_status": getattr(error, "status_code", None),
                }
            )
            raise
        self._record(
            {
                **entry,
                "event": "request_completed",
                "provider_request_id": reply.request_id,
                "model": reply.model,
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "usage_source": reply.usage_source,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
        )
        return reply


def run_live_pilot(output: Path, *, order_seed: int = 17) -> dict:
    """Run the one public arithmetic problem and its frozen rollback pair."""
    provider = _selected_provider()
    if MAX_REQUESTS * _REQUEST_COST > COST_LIMIT or MAX_OUTPUT_TOKENS != 256:
        raise ProviderPreflightError("pilot configuration exceeds the approved bound")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    revision = _source_revision()
    port = _PilotPort(output, provider)
    conditions = list(_CONDITIONS)
    Random(order_seed).shuffle(conditions)
    run_plan = {
        "model": MODEL,
        "condition_order": conditions,
        "source_revision": revision,
        "order_seed": order_seed,
        "tool_calls": 0,
        "request_limit": MAX_REQUESTS,
        "output_tokens_per_request": MAX_OUTPUT_TOKENS,
        "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "cost_limit_usd": str(COST_LIMIT),
        "preflight_cost_upper_bound_usd": str(MAX_REQUESTS * _REQUEST_COST),
    }
    (output / "plan.json").write_text(json.dumps(run_plan, indent=2) + "\n", encoding="utf-8")
    records = []
    for condition in conditions:
        port.condition = condition
        records.append(
            _run_case(
                "ordinary",
                condition,
                _CONDITIONS[condition],
                _RUN_BUDGET,
                output,
                revision,
                port,
            )
        )
    port.condition = "rollback"
    rollback = _run_fixture_rollback(output, order_seed, port)
    return _write_manifest(
        output,
        revision,
        order_seed,
        {"ordinary": conditions},
        _RUN_BUDGET,
        records,
        rollback,
        authorization_bounds=run_plan,
        provider_attempts=port.attempts,
        provider_stop_reason=port.halted,
        provider_events=str(port.events),
        reserved_cost_usd=str(port.attempts * _REQUEST_COST),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    result = run_live_pilot(args.output_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
