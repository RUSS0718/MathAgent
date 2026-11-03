"""Explicit Intern bridge; injected adapters remain fully offline-testable."""

import hashlib
import json
import re
import time
from collections.abc import Mapping
from copy import deepcopy

from llm_response import provider_usage

from ..adapters import AdapterError, InternModelAdapter
from ..redaction import redact
from ..stream_preference import profile_set_fingerprint, select_transport
from ..tool_schemas import POLYNOMIAL_CHECK_SCHEMA, PYTHON_MATH_SCHEMA, schema_error
from .intern_schemas import response_schema
from .roles import definition


class InternPortError(RuntimeError):
    """A recorded transmission or strict structured-response failure."""

    def __init__(self, category, *, no_dispatch=False, transport_decision=None):
        self.category = category
        self.no_dispatch = no_dispatch is True
        self.transport_decision = transport_decision
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


def _request_metadata(request, deadlines=None, activity_observer=None):
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
    if callable(activity_observer):
        metadata["activity_observer"] = activity_observer
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
        "input_fingerprint": None,
        "prompt_layers_fingerprint": request.get(
            "prompt_layers_fingerprint", request.get("prompt_fingerprint")
        ),
        "prompt_fingerprint": None,
        "schema_fingerprint": None,
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


def _fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _actual_problem(request, fallback=None):
    return request.get("problem", fallback)


def _audit_fingerprints(request, schema, messages, *, fallback_problem=None):
    original = _actual_problem(request, fallback_problem)
    return {
        "input_fingerprint": _fingerprint(original),
        "prompt_fingerprint": _fingerprint(messages),
        "schema_fingerprint": _fingerprint(schema),
    }


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

    def __init__(self, adapter: InternModelAdapter | None = None, *, original_problem=None,
                 deadlines=None, activity_observer=None, streaming=False,
                 transport_policy="legacy", stream_profiles=None,
                 transport_choice_observer=None):
        self.adapter = adapter
        self.original_problem = original_problem
        self.deadlines = deadlines
        self.activity_observer = activity_observer
        self.streaming = streaming is True
        if transport_policy not in {"legacy", "stream_first"}:
            raise ValueError("star_transport_policy_invalid")
        self.transport_policy = transport_policy
        self.stream_profiles = stream_profiles
        self.transport_choice_observer = transport_choice_observer
        self._run_transport_choices = {}
        self.invocations = []

    def verify(self, request):
        if request.get("role") not in {"step_verifier", "whole_solution_verifier"}:
            raise InternPortError("invalid_verifier_role")
        return self.complete(request)

    def restore_transport_policy(self, run_id, choice):
        """Restore the persisted Run choice before resuming its next call."""
        if isinstance(choice, Mapping):
            self._run_transport_choices[run_id] = dict(choice)

    def complete(self, request):
        if self.adapter is None:
            raise InternPortError("live_not_enabled")
        schema = response_schema(request)
        messages = self._messages(request, schema)
        fingerprints = _audit_fingerprints(
            request, schema, messages, fallback_problem=self.original_problem
        )
        run_id = request.get("run_id")
        locked = self._run_transport_choices.get(run_id)
        activity_observer = request.get("activity_observer")
        if not callable(activity_observer):
            activity_observer = self.activity_observer
        provider_tools = request.get("provider_tools", request.get("tools", ()))
        if not isinstance(provider_tools, (list, tuple)):
            raise InternPortError("invalid_provider_tools")
        decision = None
        if self.transport_policy == "stream_first":
            profile_set_id = profile_set_fingerprint(self.stream_profiles)
            if locked is not None and (
                locked.get("policy") != self.transport_policy
                or locked.get("profile_set_fingerprint") != profile_set_id
            ):
                self._raise_transport_rejection(
                    request,
                    {"transport": "reject",
                     "reason": "transport_policy_run_mismatch",
                     "evidence_kind": "persisted_run_choice", "new_run_required": True,
                     "policy": self.transport_policy,
                     "profile_set_fingerprint": profile_set_id},
                    fingerprints,
                )
            decision = select_transport(
                self.adapter,
                messages,
                policy=self.transport_policy,
                native_tools=bool(provider_tools),
                profiles=self.stream_profiles,
                schema_fingerprint=fingerprints["schema_fingerprint"],
            )
            self._authorize_transport(request, decision, fingerprints)
        else:
            decision = select_transport(
                self.adapter,
                messages,
                policy="legacy",
                native_tools=bool(provider_tools),
                profiles=self.stream_profiles,
                schema_fingerprint=fingerprints["schema_fingerprint"],
            )
            if decision["transport"] == "legacy" and self.streaming:
                reason = (
                    "stream_first_policy_required"
                    if callable(getattr(self.adapter, "stream_complete", None))
                    else "stream_adapter_unavailable"
                )
                decision = {
                    **decision,
                    "transport": "reject",
                    "reason": reason,
                    "evidence_kind": "not_verified",
                    "new_run_required": True,
                }
            elif decision["transport"] == "legacy":
                decision = {
                    **decision,
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "evidence_kind": "documented",
                }
            self._authorize_transport(request, decision, fingerprints)
        streaming = decision["transport"] == "stream" if decision else self.streaming
        if streaming and callable(getattr(self.adapter, "stream_complete", None)):
            if decision is None:
                decision = {"transport": "stream", "reason": "legacy_stream_activity",
                            "evidence_kind": "controlled"}
            return self._complete_stream(
                request, schema, messages, activity_observer, fingerprints, decision
            )
        started = time.monotonic()
        record = _invocation_record(request, self.adapter.model_id)
        record.update(fingerprints)
        if decision is not None:
            record["transport"] = dict(decision)
        try:
            adapter_kwargs = {
                "metadata": _request_metadata(request, self.deadlines, activity_observer),
            }
            if provider_tools:
                adapter_kwargs["tools"] = provider_tools
            response = self.adapter.complete(messages, **adapter_kwargs)
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
            self.invocations.append(redact(record))

    def _complete_stream(
        self, request, schema, messages, activity_observer=None, fingerprints=None, decision=None
    ):
        """Stream fragments through the caller's audit; strict schema gates the result.

        Each ``text_delta`` is yielded as it arrives so ``calls`` persists it before
        the next provider fragment is requested. Only a complete package that passes
        the strict provider schema is normalized into a final result chunk.
        """
        started = time.monotonic()
        record = _invocation_record(request, self.adapter.model_id, stream=True)
        if decision is not None:
            record["transport"] = dict(decision)
        record.update(
            fingerprints
            or _audit_fingerprints(request, schema, messages, fallback_problem=self.original_problem)
        )
        metrics = record["stream"]

        try:
            envelope = None
            for chunk in self.adapter.stream_complete(
                messages,
                metadata=_request_metadata(request, self.deadlines, activity_observer),
            ):
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
            self.invocations.append(redact(record))

    def _messages(self, request, schema):
        original = _actual_problem(request, self.original_problem)
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
        if request.get("checkpoint_protocol"):
            role_label = role.replace("_", " ").title()
            instructions += (
                f" This {role_label} call uses the checkpoint protocol: return only the checkpoint wrapper; "
                "YIELD must retain open gaps, FINAL must have no gaps, and a checkpoint is a partial "
                "handoff rather than completion of the whole Step."
            )
        system = [{"role": "system", "content": instructions}]
        system.extend(
            {"role": "system", "content": json.dumps(layer, ensure_ascii=False)} for layer in layers
        )
        tools = {"polynomial_check": POLYNOMIAL_CHECK_SCHEMA, "python_math": PYTHON_MATH_SCHEMA}
        context = deepcopy(dict(request))
        context.pop("prompt_layers", None)
        context.pop("prompt_layers_fingerprint", None)
        context.pop("input_fingerprint", None)
        context.pop("schema_fingerprint", None)
        context.pop("activity_observer", None)
        context.pop("transport_decision_observer", None)
        context["original_problem"] = original
        context["tool_argument_schemas"] = {
            name: value for name, value in tools.items() if name in request.get("allowed_tools", [])
        }
        return system + [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]

    def _authorize_transport(self, request, decision, fingerprints):
        """Persist and freeze this Run's transport choice before any HTTP call."""
        observer = request.get("transport_decision_observer")
        if not callable(observer):
            observer = self.transport_choice_observer
        accepted = observer(decision, request) if callable(observer) else True
        run_id = request.get("run_id")
        transport = decision["transport"]
        locked = self._run_transport_choices.get(run_id)
        choice = {
            "policy": self.transport_policy,
            "profile_set_fingerprint": decision.get("profile_set_fingerprint"),
        }
        if accepted is False or (locked is not None and locked != choice):
            rejected = {
                **decision,
                "transport": "reject",
                "reason": "transport_policy_run_mismatch",
                "new_run_required": True,
            }
            self._raise_transport_rejection(request, rejected, fingerprints)
        if transport == "reject":
            self._raise_transport_rejection(request, decision, fingerprints)
        if run_id is not None:
            self._run_transport_choices.setdefault(run_id, choice)

    def _raise_transport_rejection(self, request, decision, fingerprints):
        record = _invocation_record(request, self.adapter.model_id)
        record.update(fingerprints, transport=dict(decision), status="policy_rejected",
                      error_category=decision["reason"])
        self.invocations.append(redact(record))
        raise InternPortError(
            decision["reason"], no_dispatch=True, transport_decision=decision
        )
