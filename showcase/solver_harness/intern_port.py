"""Explicit Intern bridge; injected adapters remain fully offline-testable."""

import json
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


class InternModelPort:
    """Reasoner/Verifier/Meta bridge, with no implicit live adapter creation."""

    def __init__(self, adapter: InternModelAdapter | None = None, *, original_problem=None):
        self.adapter = adapter
        self.original_problem = original_problem
        self.invocations = []

    def verify(self, request):
        if request.get("role") not in {"step_verifier", "whole_solution_verifier"}:
            raise InternPortError("invalid_verifier_role")
        return self.complete(request)

    def complete(self, request):
        if self.adapter is None:
            raise InternPortError("live_not_enabled")
        schema = response_schema(request)
        messages = self._messages(request, schema)
        started = time.monotonic()
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
            "requested_model": self.adapter.model_id,
            "returned_model": None,
            "finish_reason": None,
            "request_attempts": [],
            "usage": provider_usage(None),
            "status": "error",
            "error_category": None,
            "response": None,
        }
        try:
            response = self.adapter.complete(
                messages,
                metadata={
                    "run_id": request.get("run_id"),
                    "role": request["role"],
                    "timeout_seconds": request.get("timeout_seconds"),
                },
            )
            record.update(
                effective_model=response.model_id,
                returned_model=response.returned_model,
                finish_reason=response.finish_reason,
                usage=provider_usage(response.usage),
                request_attempts=list(response.request_attempts),
                response=redact(response.text),
            )
            if response.finish_reason == "length":
                raise InternPortError("truncated_response")
            if response.error_category:
                raise InternPortError(response.error_category)
            if not response.text.strip():
                raise InternPortError("empty_response")
            try:
                parsed = json.loads(response.text)
            except (TypeError, ValueError) as exc:
                raise InternPortError("invalid_json") from exc
            if not isinstance(parsed, Mapping) or schema_error(parsed, schema):
                raise InternPortError("invalid_role_schema")
            record["status"] = "success"
            return dict(parsed)
        except AdapterError as exc:
            record.update(
                error_category=exc.category,
                request_attempts=list(getattr(exc, "request_attempts", ())),
            )
            raise InternPortError(exc.category) from exc
        except InternPortError as exc:
            record["error_category"] = exc.category
            raise
        finally:
            record["duration_seconds"] = time.monotonic() - started
            self.invocations.append(redact(record))

    def _messages(self, request, schema):
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
            + " Use only runtime allowed_tools. A tool_request is a proposed local computation, not evidence. "
            "Never fabricate tool receipts. Every pending tool_request MUST use label easy-verify, never verified. "
            "Group candidate substitutions into one request when possible. Omit expected_output unless the exact registered output is known; a guessed shape will not match. "
            "A successful polynomial candidate check proves substitution only, not completeness. "
            "If a report already contains tool_receipts, review those actual inputs/outputs and continue the proof; do not claim you executed them yourself."
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
