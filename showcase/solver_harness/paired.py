"""Persistent offline-first pairs over the existing Solver Harness Run seam."""

import hashlib
import json
import time
import uuid
from contextlib import nullcontext
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from llm_response import USAGE_FIELDS

from ..redaction import redact
from ..run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from ..storage import SQLiteStore
from .harness import SolverHarness
from .harness_config import _hash_json
from .paired_conditions import validate_conditions
from .storage import SolverStateStore


def _safe(value):
    """Keep results and failures while excluding composed prompts and role inputs."""
    if isinstance(value, dict):
        return {
            key: _safe(item)
            for key, item in value.items()
            if key
            not in {
                "prompt_layers",
                "problem",
                "original_problem",
                "role_context",
                "session_history",
                "request",
                "response",
                "partial_text",
            }
        }
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


class PairedRunner:
    """Run two isolated arms once; restore archived reports without redispatch."""

    def __init__(self, *, database_path: str | Path):
        self.store = SQLiteStore(database_path)
        self.connection = self.store._connection
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS solver_pairs (pair_id TEXT PRIMARY KEY, identity_hash TEXT NOT NULL, report_json TEXT NOT NULL)"
        )
        self.connection.commit()

    def run_pair(
        self,
        problem,
        *,
        control_config,
        variant_config,
        conditions,
        control_ports,
        variant_ports,
        strategy_feature="skills",
        pair_id=None,
        metadata=None,
    ):
        if not isinstance(problem, str) or not problem.strip():
            raise ValueError("problem_required")
        validation = validate_conditions(
            control_config,
            variant_config,
            conditions,
            (control_ports, variant_ports),
            strategy_feature,
        )
        pair_id = pair_id or f"pair-{uuid.uuid4().hex}"
        if not isinstance(pair_id, str) or not pair_id.strip():
            raise ValueError("pair_id_required")
        if metadata is not None and "run_id" in metadata:
            raise ValueError("pair_controls_run_identity")
        manifest = {
            "problem_hash": hashlib.sha256(problem.encode()).hexdigest(),
            "conditions": conditions,
            "configs": {"control": control_config, "variant": variant_config},
            "strategy_feature": strategy_feature,
            "metadata": metadata or {},
            "execution_source": control_ports["source"],
        }
        identity_hash = _hash_json(manifest)
        existing = self.connection.execute(
            "SELECT identity_hash FROM solver_pairs WHERE pair_id=?", (pair_id,)
        ).fetchone()
        if existing is not None:
            if existing[0] != identity_hash:
                raise ValueError("pair_identity_conflict")
            return self.get_report(pair_id)
        report = {
            "pair_id": pair_id,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "running",
            "live_gate": "needs_review",
            "live_gate_reason": "SH21_live_tool_loop_unavailable; paired_live_not_run",
            "manifest": redact(manifest),
            "condition_validation": validation,
            "comparison_scope": "engineering_only; no mathematical improvement conclusion",
            "arms": {
                name: {"run_id": f"{pair_id}:{name}", "status": "not_dispatched"}
                for name in ("control", "variant")
            },
        }
        try:
            self.connection.execute(
                "INSERT INTO solver_pairs VALUES (?,?,?)",
                (pair_id, identity_hash, json.dumps(report)),
            )
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        for name, config, arm_ports in (
            ("control", control_config, control_ports),
            ("variant", variant_config, variant_ports),
        ):
            report["arms"][name]["status"] = "dispatching"
            self._save(report)
            report["arms"][name] = self._run_arm(
                problem, report["arms"][name]["run_id"], config, arm_ports, conditions, metadata
            )
            self._save(report)
        report["status"] = "completed"
        report["completed_at"] = datetime.now(UTC).isoformat()
        self._save(report)
        return self.get_report(pair_id)

    def _run_arm(self, problem, run_id, config, ports, conditions, metadata):
        started = time.monotonic()
        observed = datetime.now(UTC).isoformat()
        result, failure = None, None
        model_ports = {
            id(port): port
            for key, port in ports.items()
            if key.endswith("_port") and key != "tool_port" and port is not None
        }
        invocation_offsets = {
            id(port): len(getattr(port, "invocations", [])) for port in model_ports.values()
        }
        actual_transport = any(
            getattr(port, "adapter", None) is not None for port in model_ports.values()
        )
        ledger, budget = None, None
        if actual_transport:
            ledger = RunBudgetLedger(connection=self.connection)
            budget = ledger.ensure(
                run_id,
                RunBudgetLimits(
                    max_model_calls=config["max_model_calls"],
                    max_http_attempts=config.get(
                        "max_http_attempts",
                        config["max_model_calls"]
                        * conditions["transport"]["physical_attempts_per_call"],
                    ),
                    max_tool_calls=config["max_tool_calls"],
                    max_tokens=config.get("max_total_tokens", 65536),
                    max_runtime_seconds=config["max_total_duration_seconds"],
                ),
            )
        with SolverHarness(
            store=self.store,
            config=config,
            **{key: value for key, value in ports.items() if key.endswith("_port")},
        ) as harness:
            try:
                with bind_budget(budget) if budget is not None else nullcontext():
                    result = harness.solve(problem, {**(metadata or {}), "run_id": run_id})
            except Exception as exc:
                failure = {
                    "category": str(getattr(exc, "category", type(exc).__name__)),
                    "message": "arm_failed; provider details excluded",
                }
            try:
                result = harness.get_run(run_id)
            except Exception:
                pass
        invocations = [
            deepcopy(record)
            for port in model_ports.values()
            for record in getattr(port, "invocations", [])[invocation_offsets[id(port)] :]
        ]
        attempts = [
            attempt for record in invocations for attempt in record.get("request_attempts", [])
        ]
        usage = {
            key: sum(record["usage"][key] for record in invocations)
            if invocations
            and all(type(record.get("usage", {}).get(key)) is int for record in invocations)
            else None
            for key in USAGE_FIELDS
        }
        for record in invocations:
            response = record.pop("response", None)
            record["response_sha256"] = (
                hashlib.sha256(response.encode()).hexdigest() if isinstance(response, str) else None
            )
        state = result["state"] if result else {}
        counter = state.get("counters", {}).get("model_calls")
        result_status = state.get("status")
        arm_status = (
            "failed"
            if failure or result_status in {"failed_runtime", "partial_aborted"}
            else "unknown_outcome"
            if result_status == "interrupted"
            else "incomplete"
            if result_status == "running"
            else "retained"
        )
        if result_status in {"failed_runtime", "partial_aborted"} and failure is None:
            failure = {"category": result_status, "message": "solver_returned_failure"}
        return redact(
            _safe(
                {
                    "run_id": run_id,
                    "status": arm_status,
                    "failure": failure,
                    "result": result,
                    "execution_source": ports["source"],
                    "started_at": observed,
                    "duration_seconds": time.monotonic() - started,
                    "duration_source": "monotonic_wall_clock",
                    "usage": usage,
                    "cost": None,
                    "invocations": invocations,
                    "provider_attempts": attempts,
                    "logical_calls": counter,
                    "physical_attempt_count": len(attempts)
                    if attempts or ports["source"] == "scripted"
                    else None,
                    "unknown_calls": [
                        record.get("call_id")
                        for record in state.get("calls", {}).values()
                        if record.get("status") not in {"completed", "ignored_late_response"}
                    ],
                    "transport_budget": budget.snapshot() if budget is not None else None,
                    "feature_skips": {
                        key: "disabled_by_profile"
                        for key in (
                            "skills",
                            "persistent_sessions",
                            "local_code_tool",
                            "stream_recovery",
                            "final_generation",
                            "final_solution_review",
                            "candidate_registry",
                            "best_effort",
                            "reexplore_after_replan",
                        )
                        if config.get("features", {}).get(key) is not True
                    },
                    "terminal": state.get("phase") == "TERMINAL",
                }
            )
        )

    def _save(self, report):
        self.connection.execute(
            "UPDATE solver_pairs SET report_json=? WHERE pair_id=?",
            (json.dumps(report, ensure_ascii=False), report["pair_id"]),
        )
        self.connection.commit()

    def get_report(self, pair_id):
        row = self.connection.execute(
            "SELECT report_json FROM solver_pairs WHERE pair_id=?", (pair_id,)
        ).fetchone()
        if row is None:
            raise KeyError("pair_not_found")
        report = json.loads(row[0])
        if report["status"] == "running":
            report.update(
                status="incomplete",
                recovery_reason="execution_not_completed; no automatic redispatch",
            )
            for arm in report["arms"].values():
                if arm["status"] == "dispatching":
                    result = SolverStateStore(self.connection).get_run(arm["run_id"])
                    arm.update(
                        status="unknown_outcome",
                        result=_safe(result),
                        duration_seconds=None,
                        duration_source="unavailable_after_interruption",
                        cost=None,
                        usage={key: None for key in USAGE_FIELDS},
                    )
        return report

    def close(self):
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
