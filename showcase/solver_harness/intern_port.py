"""Explicit Intern bridge; injected adapters remain fully offline-testable."""

import json
import re
import time
from collections.abc import Mapping
from copy import deepcopy

from llm_response import provider_usage

from ..adapters import AdapterError, InternModelAdapter
from ..redaction import redact
from ..tool_schemas import POLYNOMIAL_CHECK_SCHEMA, PYTHON_MATH_SCHEMA, schema_error
from .intern_schemas import response_schema
from .roles import definition


class InternPortError(RuntimeError):
    """A recorded transmission or strict structured-response failure."""

    def __init__(self, category):
        self.category = category
        super().__init__(category)


# Response failures where the provider reply arrived completely: the finish
# reason and usage are known facts, unlike a network interruption or an
# unfinished stream whose remote outcome stays unknown.
KNOWN_PROTOCOL_FAILURES = frozenset({
    "invalid_json", "invalid_role_schema", "empty_response", "truncated_response",
})

MAX_RESPONSE_EXCERPT_CHARS = 400


def _protocol_failure(category, record, text):
    """Build the known protocol failure with its provider-known evidence."""
    error = InternPortError(category)
    error.usage = record.get("usage")
    error.finish_reason = record.get("finish_reason")
    error.response_excerpt = redact(str(text or ""))[:MAX_RESPONSE_EXCERPT_CHARS]
    return error


def _request_metadata(request, deadlines=None):
    """Pure adapter metadata mapping for one invocation; no metering inside."""
    metadata = {
        "run_id": request.get("run_id"),
        "call_id": request.get("call_id"),
        "role": request["role"],
        "timeout_seconds": request.get("timeout_seconds"),
        "phase_deadline_at": request.get("phase_deadline_at"),
        "batch_deadline_at": request.get("batch_deadline_at"),
        "strict_completion": request.get("strict_completion") is True,
    }
    for name, limit in (deadlines or {}).items():
        if limit is not None:
            metadata[name] = min(metadata[name], limit) if metadata[name] is not None else limit
    return metadata


def _invocation_record(request, model_id, *, stream=False):
    """Assemble the initial audited invocation record; fields only, no dispatch."""
    record = {
        "run_id": request.get("run_id"),
        "call_id": request.get("call_id"),
        "consumed_receipt_ids": [
            item["receipt_id"]
            for item in request.get("report", {}).get("tool_receipts", [])
            if item.get("receipt_id")
        ],
        "role": request["role"],
        "state_revision": request.get("state_revision"),
        "active_skill_ids": request.get("active_skill_ids", []),
        "prompt_fingerprint": request.get("prompt_fingerprint"),
        "requested_model": model_id,
        "returned_model": None,
        "finish_reason": None,
        "request_attempts": [],
        "usage": provider_usage(None),
        "status": "error",
        "error_category": None,
        "response": None,
    }
    if stream:
        record["stream"] = {"fragments": 0, "bytes": 0, "status": "streaming"}
    return record


def _loads_known_escape_rescue(text):
    """Parse strictly; rescue exactly the invalid-escape failure class.

    Live Intern replies embed code whose strings carry single backslashes
    ("\\d", Windows paths): a well-formed JSON object except for escapes JSON
    does not allow. Doubling only the invalid backslashes recovers the model's
    evident intent without loosening anything else. Legal escape pairs are
    consumed atomically, including escaped backslashes; malformed Unicode,
    truncated bodies and structural errors still fail. Schema validation remains
    separate and mandatory; raw response audit content is never rewritten.
    """
    try:
        return json.loads(text)
    except ValueError as strict_error:
        if "Invalid \\escape" not in str(strict_error):
            raise
        # Consume legal escape pairs atomically: the second slash of \\\\
        # must never be reconsidered as the start of an illegal escape.
        rescued = re.sub(r'\\(?:["\\/bfnrtu]|[^"\\/bfnrtu])',
                         lambda match: (match[0] if match[0][1] in '"\\/bfnrtu'
                                        else '\\' + match[0]), text)
        return json.loads(rescued)


class InternModelPort:
    """Reasoner/Verifier/Meta bridge, with no implicit live adapter creation."""

    def __init__(self, adapter: InternModelAdapter | None = None, *, original_problem=None, deadlines=None,
                 restricted_reply_dir=None):
        self.adapter = adapter
        self.original_problem = original_problem
        self.deadlines = deadlines
        self.invocations = []
        from .restricted_replies import RestrictedReplies

        self.restricted_replies = (RestrictedReplies(restricted_reply_dir)
                                   if restricted_reply_dir is not None else None)

    def verify(self, request):
        if request.get("role") not in {"step_verifier", "whole_solution_verifier"}:
            raise InternPortError("invalid_verifier_role")
        return self.complete(request)

    def complete(self, request):
        if self.adapter is None:
            raise InternPortError("live_not_enabled")
        schema = response_schema(request)
        messages = self._messages(request, schema)
        if callable(getattr(self.adapter, "stream_complete", None)):
            return self._complete_stream(request, schema, messages)
        started = time.monotonic()
        record = _invocation_record(request, self.adapter.model_id)
        try:
            response = self.adapter.complete(messages, metadata=_request_metadata(request, self.deadlines))
            record.update(
                effective_model=response.model_id,
                returned_model=response.returned_model,
                finish_reason=response.finish_reason,
                usage=provider_usage(response.usage),
                request_attempts=list(response.request_attempts),
                response=redact(response.text),
            )
            if response.finish_reason == "length":
                raise _protocol_failure("truncated_response", record, response.text)
            if response.error_category:
                raise InternPortError(response.error_category)
            if not response.text.strip():
                raise _protocol_failure("empty_response", record, response.text)
            if request.get("serialization_repair") is True:
                from .serialization_port import parse_reply

                parsed = parse_reply(self, request, record, response.text, schema)
                record["status"] = "success"
                return parsed
            try:
                parsed = _loads_known_escape_rescue(response.text)
            except (TypeError, ValueError) as exc:
                raise _protocol_failure("invalid_json", record, response.text) from exc
            if not isinstance(parsed, Mapping) or schema_error(parsed, schema):
                raise _protocol_failure("invalid_role_schema", record, response.text)
            record["status"] = "success"
            return dict(parsed)
        except AdapterError as exc:
            record.update(
                error_category=exc.category,
                request_attempts=list(getattr(exc, "request_attempts", ())),
            )
            error = InternPortError(exc.category)
            error.request_attempts = record["request_attempts"]
            raise error from exc
        except InternPortError as exc:
            record["error_category"] = exc.category
            raise
        finally:
            record["duration_seconds"] = time.monotonic() - started
            from .serialization_port import public_invocation

            self.invocations.append(redact(public_invocation(record, request.get("serialization_repair"))))

    def _complete_stream(self, request, schema, messages):
        """Stream fragments through the caller's audit; strict schema gates the result.

        Each ``text_delta`` is yielded as it arrives so ``calls`` persists it before
        the next provider fragment is requested. Only a complete package that passes
        the strict provider schema is normalized into a final result chunk.
        """
        started = time.monotonic()
        record = _invocation_record(request, self.adapter.model_id, stream=True)
        metrics = record["stream"]

        try:
            envelope = None
            for chunk in self.adapter.stream_complete(messages, metadata=_request_metadata(request, self.deadlines)):
                if chunk.get("type") == "text_delta" and isinstance(chunk.get("text"), str):
                    metrics["fragments"] += 1
                    metrics["bytes"] += len(chunk["text"].encode("utf-8"))
                    yield {"type": "text_delta", "text": chunk["text"]}
                elif isinstance(chunk, Mapping) and chunk.get("type") == "result":
                    envelope = chunk
            if not isinstance(envelope, Mapping):
                raise InternPortError("stream_ended_without_result")
            record.update(
                returned_model=envelope.get("model"),
                finish_reason=envelope.get("finish_reason"),
                usage=provider_usage(envelope.get("usage")),
                request_attempts=list(envelope.get("attempts") or ()),
            )
            if envelope.get("finish_reason") == "length":
                raise _protocol_failure("truncated_response", record, envelope.get("text"))
            text = envelope.get("text")
            if not isinstance(text, str) or not text.strip():
                raise _protocol_failure("empty_response", record, text)
            if request.get("serialization_repair") is True:
                from .serialization_port import parse_reply

                parsed = parse_reply(self, request, record, text, schema)
                record["status"] = "success"
                metrics["status"] = "completed"
                yield {"result": parsed, "usage": dict(envelope.get("usage") or {})}
                return
            try:
                parsed = _loads_known_escape_rescue(text)
            except (TypeError, ValueError) as exc:
                raise _protocol_failure("invalid_json", record, text) from exc
            if not isinstance(parsed, Mapping) or schema_error(parsed, schema):
                raise _protocol_failure("invalid_role_schema", record, text)
            record["status"] = "success"
            metrics["status"] = "completed"
            yield {"result": dict(parsed), "usage": dict(envelope.get("usage") or {})}
        except AdapterError as exc:
            record.update(
                error_category=exc.category,
                request_attempts=list(getattr(exc, "request_attempts", ())),
            )
            metrics["status"] = exc.category
            error = InternPortError(exc.category)
            error.request_attempts = record["request_attempts"]
            raise error from exc
        except InternPortError as exc:
            record["error_category"] = exc.category
            metrics["status"] = exc.category
            raise
        finally:
            record["duration_seconds"] = time.monotonic() - started
            from .serialization_port import public_invocation

            self.invocations.append(redact(public_invocation(record, request.get("serialization_repair"))))

    def _messages(self, request, schema):
        if request.get("serialization_source"):
            from .serialization_port import repair_messages

            return repair_messages(self, request, schema)
        original = request.get("problem", self.original_problem)
        if not isinstance(original, str) or not original.strip():
            raise InternPortError("missing_original_problem")
        if self.original_problem is not None and original != self.original_problem:
            raise InternPortError("problem_identity_mismatch")
        role = request["role"]
        layers = request.get("prompt_layers", [])
        role_definition = definition(role)
        instructions = (
            f"You are the {role}. {role_definition} Return one JSON object only, no Markdown or commentary. "
            "Obey this exact response schema: "
            + json.dumps(schema, ensure_ascii=False)
            + " Answer with a filled instance of this schema containing your actual values — "
            "never echo the schema definition itself (a reply like "
            '{"type": "object", "properties": ...} is a protocol failure). '
            "Enum fields must take one of their listed values only; while a tool_request is "
            "pending, still state your provisional enum verdict — the runtime withholds any "
            "acceptance until the real receipt exists. "
            "Use only runtime allowed_tools. A tool_request is a proposed local computation, not evidence. "
            "Never fabricate tool receipts. Every pending tool_request MUST use label easy-verify, never verified. "
            "Group candidate substitutions into one request when possible. Omit expected_output unless the exact registered output is known; a guessed shape will not match. "
            "A successful polynomial candidate check proves substitution only, not completeness. "
            "If a report already contains tool_receipts, review those actual inputs/outputs and continue the review; the runtime executed them, not you. "
            "A reviewer may propose at most one tool_request per reply while its verdict is still pending; judge only from recorded receipts, never from assumed outputs."
        )
        system = [{"role": "system", "content": instructions}]
        system.extend(
            {"role": "system", "content": json.dumps(layer, ensure_ascii=False)} for layer in layers
        )
        tools = {"polynomial_check": POLYNOMIAL_CHECK_SCHEMA, "python_math": PYTHON_MATH_SCHEMA}
        context = deepcopy(dict(request))
        context.pop("prompt_layers", None)
        context["original_problem"] = original
        context["tool_argument_schemas"] = {
            name: value for name, value in tools.items() if name in request.get("allowed_tools", [])
        }
        return system + [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
