"""Lazy adapter for the public authenticated Showcase Job API."""

from __future__ import annotations

import re
import time
from typing import Any

_PUBLIC_CALL_ID = re.compile(r"solver_call_[0-9a-f]{32}\Z")


class PublicExperimentJobAdapter:
    """Use only public Job routes; client construction is delayed until Run registration."""

    def __init__(
        self,
        client: Any,
        manifest: dict[str, Any],
        model_config: Any,
        sample_resolver: Any,
        transport_adapter: Any,
    ) -> None:
        self.client = client
        self.manifest = manifest
        self.model_config = model_config
        self.sample_resolver = sample_resolver
        self.transport_adapter = transport_adapter
        self._bindings: dict[str, tuple[str, str]] = {}
        self.client.bootstrap()

    def validate_runtime_contract(self, manifest: dict[str, Any]) -> bool:
        try:
            self.transport_adapter.validate_manifest_transport(manifest["transport"])
            return dict(self.model_config.config()) == manifest["model"]
        except (AttributeError, KeyError, TypeError, ValueError):
            return False

    def create_session(self, _run_id: str) -> str:
        result = self.client.request("POST", "/api/new_chat", payload={})
        session_id = result.get("new_session_id") if isinstance(result, dict) else None
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("experiment_session_creation_unknown")
        return session_id

    def request_digest(
        self,
        sample: dict[str, Any],
        session_id: str,
        *,
        budget_limits: dict[str, Any],
        deadline_at: float,
    ) -> str:
        from .run_budget import RunBudgetLimits
        from .workspace import workspace_job_request_digest

        message = self.sample_resolver.read_text(sample).strip()
        return workspace_job_request_digest(
            session_id=session_id,
            message=message,
            verification_mode=self.manifest["model"]["verification_mode"],
            solver_mode=self.manifest["model"]["solver_mode"],
            budget_limits=RunBudgetLimits(**budget_limits),
            deadline_at=deadline_at,
        )

    def find_by_idempotency_key(self, key: str, request_digest: str) -> list[dict[str, Any]]:
        from .cli import CliError

        try:
            result = self.client.request(
                "GET",
                "/api/agent/jobs/by-idempotency",
                headers={"Idempotency-Key": key, "X-Request-Digest": request_digest},
            )
        except CliError as exc:
            if exc.status == 404 and exc.code == "job_not_found":
                return []
            raise
        if (
            not isinstance(result, dict)
            or result.get("request_digest") != request_digest
            or not isinstance(result.get("job_id"), str)
        ):
            return [{}]
        self._bindings[result["job_id"]] = (key, request_digest)
        return [result]

    def create_job(
        self,
        sample: dict[str, Any],
        session_id: str,
        key: str,
        *,
        budget_limits: dict[str, Any],
        deadline_at: float,
    ) -> dict[str, Any]:
        message = self.sample_resolver.read_text(sample).strip()
        return self.client.request(
            "POST",
            "/api/agent/jobs",
            payload={
                "session_id": session_id,
                "message": message,
                "verification_mode": self.manifest["model"]["verification_mode"],
                "solver_mode": self.manifest["model"]["solver_mode"],
                "web_search_enabled": False,
                "budget_limits": dict(budget_limits),
                "deadline_at": deadline_at,
            },
            headers={"Idempotency-Key": key},
        )

    def wait_for_job(self, job_id: str, deadline_at: float) -> dict[str, Any]:
        binding = self._bindings.get(job_id)
        if binding is None:
            return {"status": "unknown", "ledger_consistent": False}
        key, digest = binding
        while True:
            records = self.find_by_idempotency_key(key, digest)
            if len(records) != 1 or records[0].get("job_id") != job_id:
                return {"status": "unknown", "ledger_consistent": False}
            record = records[0]
            budget = record.get("budget")
            if not isinstance(budget, dict):
                return {"status": "unknown", "ledger_consistent": False}
            if record.get("status") in {"succeeded", "failed", "canceled", "waiting_input"}:
                return self._observation(record, budget, deadline_at)
            if time.time() >= deadline_at:
                return self._observation(record, budget, deadline_at, status="running")
            time.sleep(min(0.25, max(0.01, deadline_at - time.time())))

    def resume_preflight(
        self,
        job_id: str,
        deadline_at: float,
        *,
        intent: dict[str, Any],
    ) -> dict[str, Any]:
        records = self.find_by_idempotency_key(
            intent.get("idempotency_key", ""), intent.get("request_digest", "")
        )
        if len(records) != 1:
            return {"observer_only": True, "safe_to_resume": False}
        record = records[0]
        budget = record.get("budget")
        if not isinstance(budget, dict):
            return {"observer_only": True, "safe_to_resume": False}
        status = record.get("status")
        expected_limits = self.manifest.get("run_limits")
        consistent = (
            record.get("job_id") == job_id
            and record.get("request_digest") == intent.get("request_digest")
            and status in {"queued", "running", "succeeded"}
            and budget.get("limits") == expected_limits
            and budget.get("deadline_at") == deadline_at
            and all(
                budget.get(key) == 0
                for key in ("unknown_attempts", "unresolved_attempts", "unknown_tool_calls")
            )
        )
        return {
            "observer_only": True,
            "safe_to_resume": consistent,
            "job_id": record.get("job_id"),
            "request_digest": record.get("request_digest"),
            "status": status,
            "ledger_consistent": consistent,
            "deadline_at": budget.get("deadline_at"),
            "budget": budget,
        }

    def _observation(
        self,
        record: dict[str, Any],
        budget: dict[str, Any],
        deadline_at: float,
        *,
        status: str | None = None,
    ) -> dict[str, Any]:
        expected_limits = self.manifest["run_limits"]
        ledger_consistent = (
            budget.get("limits") == expected_limits and budget.get("deadline_at") == deadline_at
        )
        transport = record.get("transport_identity")
        transport_known = self._transport_matches_manifest(transport)
        return {
            "status": status or record.get("status"),
            "ledger_consistent": ledger_consistent,
            "transport_known": transport_known,
            "transport": self.manifest.get("transport") if transport_known else None,
            "budget": budget,
            "deadline_at": budget.get("deadline_at"),
        }

    def _transport_matches_manifest(self, observed: Any) -> bool:
        expected = self.manifest.get("transport")
        adapter = self.transport_adapter
        try:
            adapter.validate_manifest_transport(expected)
        except (AttributeError, TypeError, ValueError):
            return False
        if (
            not isinstance(observed, dict)
            or set(observed) != {"policy", "profile_set_fingerprint", "calls"}
            or observed.get("policy") != expected.get("policy")
            or observed.get("profile_set_fingerprint") != expected.get("profile_set_fingerprint")
            or not isinstance(observed.get("calls"), list)
        ):
            return False

        actual_calls = observed["calls"]
        if not actual_calls:
            return False
        expected_calls = {call["call_id"]: call for call in expected["calls"]}
        if len(expected_calls) != len(expected["calls"]):
            return False
        profiles = {}
        if expected["policy"] == "stream_first":
            from .experiment_transport import profile_fingerprint

            profiles = {
                profile_fingerprint(profile): profile
                for profile in getattr(adapter, "profiles", ())
            }
        seen_call_ids = set()
        for call in actual_calls:
            if (
                not isinstance(call, dict)
                or not isinstance(call.get("role"), str)
                or call.get("role") not in expected_calls
                or not isinstance(call.get("call_id"), str)
                or _PUBLIC_CALL_ID.fullmatch(call["call_id"]) is None
                or call["call_id"] in seen_call_ids
            ):
                return False
            role = call["role"]
            expected_call = expected_calls[role]
            if expected["policy"] == "stream_first":
                profile_fingerprint = expected_call["profile_fingerprint"]
                profile = profiles.get(profile_fingerprint)
                if profile is None or call != {
                    "call_id": call["call_id"],
                    "role": role,
                    "policy": "stream_first",
                    "transport": "stream",
                    "evidence_kind": profile.evidence_kind,
                    "profile_fingerprint": profile_fingerprint,
                }:
                    return False
            else:
                if set(call) != {
                    "call_id",
                    "role",
                    "policy",
                    "transport",
                    "evidence_kind",
                    "reason",
                    "capability_limit",
                }:
                    return False
                if (
                    call.get("policy") != "legacy"
                    or call.get("transport") != expected_call["transport"]
                    or call.get("reason") != expected_call["reason"]
                    or call.get("capability_limit")
                    != expected_call["capability_limit"]
                    or call.get("evidence_kind") not in {None, "documented"}
                ):
                    return False
            seen_call_ids.add(call["call_id"])
        return True
