"""Bounded public-problem evidence run for the explicit Solver Intern port."""

import hashlib
import json
import uuid
from pathlib import Path

from ..adapters import InternModelAdapter
from ..redaction import redact
from ..run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget
from ..tools import ToolRegistry
from .harness import SolverHarness
from .intern_port import InternModelPort
from .tool_ports import RegistryToolPort

PROBLEM = (
    "Solve x^2 - 1 = 0 over the real numbers. Derive candidates and request the registered "
    "polynomial_check tool to check their substitution. Use the returned receipt and a separate "
    "algebraic argument to justify completeness; do not treat finite substitution as a completeness proof."
)
CONFIG = {
    "features": {
        "stream_recovery": True,
        "skills": True,
        "persistent_sessions": True,
        "local_code_tool": True,
        "final_generation": True,
        "final_solution_review": True,
    },
    "allowed_tools": ["polynomial_check"],
    "max_model_calls": 6,
    "max_tool_calls": 2,
    "max_tool_retries": 0,
    "max_challenge_rounds": 1,
    "max_final_solution_retries": 0,
    "max_total_duration_seconds": 180,
    "tool_timeout_seconds": 3,
    "max_tool_output_bytes": 16000,
}
PLAN = {
    "version": 1,
    "steps": [
        {
            "step_id": "roots",
            "title": "Derive and check roots",
            "objective": "Derive all real roots, propose polynomial_check for candidate substitution, and prove completeness algebraically.",
        }
    ],
}


class BudgetRegistryPort(RegistryToolPort):
    """Carry the run budget into the tool executor thread before dispatch."""

    def __init__(self, registry, budget):
        super().__init__(registry)
        self.budget = budget

    def execute(self, request):
        with bind_budget(self.budget):
            return super().execute(request)


def run_evidence(
    adapter: InternModelAdapter, artifact_root: Path, *, execution_source, followup=False
):
    config = {**CONFIG}
    if followup:
        config.update(max_model_calls=4, max_tool_calls=1, max_total_duration_seconds=120)
    run_id = f"solver-intern-{uuid.uuid4().hex}"
    folder = artifact_root / run_id
    folder.mkdir(parents=True, exist_ok=False)
    ledger = RunBudgetLedger(database_path=folder / "budget.sqlite3")
    budget = ledger.ensure(
        run_id,
        RunBudgetLimits(
            max_model_calls=config["max_model_calls"],
            max_http_attempts=config["max_model_calls"],
            max_tool_calls=config["max_tool_calls"],
            max_tokens=65536,
            max_runtime_seconds=config["max_total_duration_seconds"],
        ),
    )
    port = InternModelPort(adapter, original_problem=PROBLEM)
    registry = ToolRegistry(max_calls=config["max_tool_calls"])
    registry.register_polynomial_check(timeout_seconds=3)
    tool_port = BudgetRegistryPort(registry, budget)
    result = None
    failure = None
    try:
        with SolverHarness(
            database_path=folder / "solver.sqlite3",
            config=config,
            model_port=port,
            verifier_port=port,
            meta_port=port,
            tool_port=tool_port,
        ) as harness:
            try:
                with bind_budget(budget):
                    result = harness.solve(PROBLEM, {"run_id": run_id, "plan": PLAN})
            except Exception as exc:
                failure = getattr(exc, "category", type(exc).__name__)
                result = harness.get_run(run_id)
            latest = harness.get_run(run_id)
            if latest["state"].get("status") == "running":
                failed = any(item["status"] == "error" for item in port.invocations)
                latest = harness.commit_event(
                    run_id,
                    expected_revision=latest["state_revision"],
                    event={
                        "event_id": "probe_stopped",
                        "type": "probe_stopped",
                        "reason": "probe_ended_without_verified_completion",
                    },
                    state_updates={
                        "probe_exit_phase": latest["state"]["phase"],
                        "phase": "TERMINAL",
                        "status": "failed_runtime" if failed else "partial_aborted",
                        "final_response": "The bounded live probe ended without a verified final answer.",
                    },
                )
            result = harness.commit_event(
                run_id,
                expected_revision=latest["state_revision"],
                event={
                    "event_id": "intern_evidence_recorded",
                    "type": "intern_evidence_recorded",
                    "invocations": port.invocations,
                    "evidence_ref": f"artifacts/{run_id}/evidence.json",
                    "invocations_sha256": hashlib.sha256(
                        json.dumps(port.invocations, sort_keys=True, ensure_ascii=False).encode()
                    ).hexdigest(),
                    "transport_budget": budget.snapshot(),
                },
            )
    finally:
        metering = budget.snapshot()
        attempts = ledger.attempts(run_id)
        ledger.close()
    receipts = result["state"].get("tool_receipts", []) if result else []
    executed = [
        item
        for item in receipts
        if item.get("executed")
        and item.get("status") == "success"
        and item.get("source") == "local_precheck"
    ]
    executed_ids = {item["receipt_id"] for item in executed}
    continuation = any(
        record["role"] == "step_verifier"
        and record["status"] == "success"
        and bool(executed_ids & set(record["consumed_receipt_ids"]))
        for record in port.invocations
    )
    status = (
        "pass"
        if executed and continuation and result["state"].get("status") == "completed_llm_reviewed"
        else "needs_review"
    )
    report = redact(
        {
            "run_id": run_id,
            "execution_source": execution_source,
            "status": status,
            "problem": PROBLEM,
            "config": config,
            "transport": {
                "max_output_tokens": adapter.max_tokens,
                "http_timeout_seconds": adapter.client_timeout,
                "physical_attempts_per_call": adapter.client_retry,
                "retries": 0,
                "thinking_mode": adapter.thinking_mode,
            },
            "failure": failure,
            "invocations": port.invocations,
            "request_attempts": attempts,
            "budget": metering,
            "tool_receipts": receipts,
            "final_status": result["state"].get("status") if result else None,
            "limitation": "One public-problem engineering trace; candidate substitution is not completeness proof or capability uplift.",
        }
    )
    (folder / "evidence.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if result:
        (folder / "run.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return folder, report
