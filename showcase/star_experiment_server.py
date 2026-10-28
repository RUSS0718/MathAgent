"""Two trusted local product instances, authenticated public Job/Run requests."""

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.parse import urlparse

from .adapters import InternModelAdapter, InternStreamAdapter
from .flask_app import create_app
from .request_transport import INTERN_S2_LIVE_ENDPOINT
from .solver_harness.storage import SolverStateStore
from .star_experiment_registration import CONDITIONS
from .star_product_runtime import CONTRACT_PYTHON_IMAGE_ID


class ExperimentServer:
    def __init__(self, path, transport, adapter, policy, evidence_kind,
                 *, refresh_preflight_each_call=False, late_usage_evidence_dir=None,
                 request_timeout_seconds=CONDITIONS["timeout"]):
        self.adapter, self.transport, self.evidence_kind = adapter, transport, evidence_kind
        self.request_timeout_seconds = request_timeout_seconds
        self.refresh_preflight_each_call = refresh_preflight_each_call
        self.preflight_count = 0
        self.contexts = {}
        self._previous_observer = adapter.outbound_observer
        adapter.outbound_observer = self._capture_outbound
        self.check_conditions()
        self.app = create_app({"SHOWCASE_DATA_DIR": str(path), "SHOWCASE_JOB_DELAY_SECONDS": 0,
            "SHOWCASE_STAR_FULL_ENABLED": True, "SHOWCASE_STAR_ADAPTER": adapter,
            "SHOWCASE_STAR_PYTHON_IMAGE_ID": CONTRACT_PYTHON_IMAGE_ID,
            "SHOWCASE_STAR_EXPERIMENT_POLICY": policy, "SHOWCASE_STAR_EVIDENCE_KIND": evidence_kind})
        self.app.extensions["showcase_workspace_service"].budget_ledger.late_usage_evidence_dir = (
            Path(late_usage_evidence_dir)
            if late_usage_evidence_dir is not None
            else Path(path).parent / "supplemental-usage"
        )
        self.client = self.app.test_client()
        self.csrf = self.get("/api/check_auth")["csrf_token"]

    def _capture_outbound(self, messages):
        context = json.loads(messages[-1]["content"])
        if isinstance(context, dict) and context.get("call_id"):
            # Multiple HTTP attempts retain one logical context, never a role-order guess.
            self.contexts[context["call_id"]] = context
        if self._previous_observer is not None:
            self._previous_observer(messages)

    def provenance(self, job_id):
        """Trusted server-side read; raw snapshots/contexts never enter public HTTP."""
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        database = Path(pipeline.database_path)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            snapshot = SolverStateStore(connection).get_run(job_id)
        return snapshot, [c for c in self.contexts.values() if c.get("run_id") == job_id]

    def check_conditions(self):
        adapter, transport, evidence_kind = self.adapter, self.transport, self.evidence_kind
        expected = InternStreamAdapter if transport == "stream" else InternModelAdapter
        if not isinstance(adapter, expected) or (transport == "nonstream" and isinstance(adapter, InternStreamAdapter)):
            raise ValueError("experiment_transport_mismatch")
        client = adapter._get_client()
        if evidence_kind == "live" and (
            client.api_base != INTERN_S2_LIVE_ENDPOINT
            or client.provider_endpoint_only is not True
            or client.loopback_only is not False
        ):
            raise ValueError("experiment_live_provider_mismatch")
        if evidence_kind != "live" and urlparse(client.api_base).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("scripted_provider_must_be_loopback")
        if (adapter.model_id != CONDITIONS["model"] or client.model != CONDITIONS["model"]
                or client.timeout != self.request_timeout_seconds or client.retry != CONDITIONS["retry"]
                or adapter.max_tokens != CONDITIONS["max_tokens"]
                or adapter.temperature != CONDITIONS["temperature"]
                or adapter.thinking_mode is not CONDITIONS["thinking_mode"]):
            raise ValueError("experiment_conditions_mismatch")

    def headers(self):
        return {"X-CSRF-Token": self.csrf, "Idempotency-Key": str(uuid.uuid4())}

    def get(self, path):
        response = self.client.get(path)
        if response.status_code != 200:
            raise ValueError("experiment_public_read_failed")
        return response.get_json()

    def post(self, path, payload, *, idempotency_key=None):
        headers = self.headers()
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        response = self.client.post(path, json=payload, headers=headers)
        if response.status_code not in {200, 202}:
            raise ValueError("experiment_public_admission_failed")
        return response.get_json()

    def preflight(self):
        if self.refresh_preflight_each_call and self.preflight_count:
            pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
            pipeline.full_gaps(probe=True)
        self.preflight_count += 1
        record = next(item for item in self.get("/api/capabilities")["solver_modes"]
                      if item["solver_mode"] == "star_reference")
        # Verify actual immutable receipt and the probe's own S3 ledger, not enabled alone.
        pipeline = self.app.extensions["showcase_workspace_service"].star_pipeline
        artifacts = pipeline.registry.container_python_executor.artifacts
        reference = record.get("last_preflight")
        observed = dict(identity=reference, available=False, receipt=None, budget=None)
        try:
            receipt = json.loads(artifacts.verify(reference["receipt_ref"], run_id=reference["run_id"]))
            ledger = json.loads(artifacts.verify(reference["budget_ref"], run_id=reference["run_id"]))
            observed.update(receipt=receipt, budget=ledger["summary"])
            observed["available"] = bool(record["enabled"] and receipt.get("status") == "success"
                and receipt.get("executed") and receipt.get("cleanup_verified") and receipt.get("exit_code") == 0
                and receipt.get("image") == CONTRACT_PYTHON_IMAGE_ID
                and ledger["summary"]["tool_calls"] == 1 and ledger["summary"]["http_attempts"] == 0)
        except (ValueError, KeyError, TypeError):
            observed["reason"] = "experiment_preflight_evidence_invalid"
        return observed

    def dispatch(self, question, *, idempotency_key=None):
        """Create one public Job, optionally using the caller's retained dispatch key."""
        self.check_conditions()
        session = self.post("/api/new_chat", {})["new_session_id"]
        payload = dict(message=question["prompt"], session_id=session,
                       solver_mode="star_reference", verification_mode="auto")
        if idempotency_key is None:
            return self.post("/api/agent/jobs", payload)["job_id"]
        return self.post("/api/agent/jobs", payload, idempotency_key=idempotency_key)["job_id"]

    def resolve_dispatch(self, idempotency_key):
        """Read a durably accepted Job by its retained key without repeating POST."""
        database = Path(self.app.extensions["showcase_workspace_service"].store.database_path)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            rows = connection.execute(
                "SELECT job_id FROM workspace_jobs WHERE idempotency_key=?", (idempotency_key,)
            ).fetchall()
        # The local dispatch key is a fresh UUID. Ambiguous identity fails closed.
        return rows[0][0] if len(rows) == 1 else None

    def collect(self, job_id, deadline_at, *, canceled=lambda: False):
        while True:
            job = self.get(f"/api/agent/jobs/{job_id}")
            if job["status"] in {"succeeded", "failed", "canceled"}:
                break
            if time.time() >= deadline_at or canceled():
                try:
                    self.post(f"/api/agent/jobs/{job_id}/cancel", {})
                except ValueError:
                    # The worker may commit its terminal state between GET and cancel.
                    if self.get(f"/api/agent/jobs/{job_id}")["status"] not in {
                        "succeeded", "failed", "canceled"
                    }:
                        raise
                # Snapshot preserves unknown reservations even if a worker is still unwinding.
                break
            time.sleep(.01)
        return dict(job=self.get(f"/api/agent/jobs/{job_id}"),
                    report=self.get(f"/api/agent/jobs/{job_id}/report")["report"],
                    evidence=self.get(f"/api/runs/{job_id}/evidence"),
                    run=self.get(f"/api/runs/{job_id}"))

    def close(self):
        self.adapter.outbound_observer = self._previous_observer
        for name in ("showcase_workspace_service", "showcase_run_service", "loopback_store"):
            self.app.extensions[name].close()
