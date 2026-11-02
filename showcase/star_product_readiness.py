"""Real Registry isolation probe; deployment readiness is not mathematical acceptance."""

import json
import logging
import uuid

from .container_tool import tool_request
from .python_executor import DockerPythonExecutor
from .run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget

logger = logging.getLogger(__name__)

PROBE_CODE = "import sympy, numpy, mpmath\nprint(sympy.factor(sympy.Symbol('x')**2-1))"
PROBE_OUTPUT = "(x - 1)*(x + 1)\n"


def _ledger_audit(ledger, run_id, budget):
    """Serialize the probe's own S3 accounting before the in-memory ledger closes."""
    with ledger.lock:
        row = ledger.connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
        ).fetchone()
    state = json.loads(row[0]) if row else {"actions": []}
    summary = budget.snapshot() if budget is not None else None
    return {"run_id": run_id, "summary": summary, "actions": state.get("actions", [])}


def _persist_ledger_audit(executor, ledger, run_id, budget):
    """Best-effort audit persistence; never flips the readiness verdict."""
    try:
        return executor.artifacts.put(
            run_id, "isolation-probe", "preflight_budget",
            json.dumps(_ledger_audit(ledger, run_id, budget),
                       sort_keys=True, ensure_ascii=False).encode("utf-8"),
            media_type="application/json",
        )
    except Exception as exc:  # noqa: BLE001 - audit write must stay non-fatal
        logger.error("preflight_budget_audit_failed error=%s", type(exc).__name__)
        return None


def isolated_readiness(registry):
    executor = getattr(registry, "container_python_executor", None)
    if not isinstance(executor, DockerPythonExecutor):
        return {"available": False, "reason": "isolated_python_required"}
    tools = {item["name"]: item for item in registry.describe()}
    if "polynomial_check" not in tools or "isolated_mathematical_python" not in tools.get(
        "python_math", {}
    ).get("capabilities", []):
        return {"available": False, "reason": "isolated_registry_required"}
    run_id = "star-preflight-" + uuid.uuid4().hex
    ledger = RunBudgetLedger()
    budget = None
    try:
        budget = ledger.ensure(run_id, RunBudgetLimits(
            max_model_calls=0, max_http_attempts=0, max_tool_calls=1, max_runtime_seconds=45))
        with bind_budget(budget), tool_request({
            "run_id": run_id, "call_id": "isolation-probe",
            "timeout_seconds": 8, "max_output_bytes": 16000,
        }):
            result = registry.invoke("python_math", {"code": PROBE_CODE})
        receipt = result.value if isinstance(result.value, dict) else {}
        available = (
            result.status == "success" and receipt.get("status") == "success"
            and receipt.get("executed") is True and receipt.get("cleanup_verified") is True
            and receipt.get("unknown_outcome") is not True and receipt.get("exit_code") == 0
            and receipt.get("stdout") == PROBE_OUTPUT and receipt.get("image") == executor.image
            and receipt.get("environment", {}).get("image_id") == executor.image
        )
        return {
            "available": available, "reason": None if available else "isolated_python_preflight_failed",
            "run_id": run_id, "image_id": executor.image,
            "receipt_ref": receipt.get("receipt_ref"),
            "budget_ref": _persist_ledger_audit(executor, ledger, run_id, budget),
        }
    except Exception as exc:  # noqa: BLE001 - probe failures stay sanitized categories
        logger.error("isolated_python_preflight_failed error=%s", type(exc).__name__)
        return {"available": False, "reason": "isolated_python_preflight_failed",
                "run_id": run_id, "budget_ref": _persist_ledger_audit(executor, ledger, run_id, budget)}
    finally:
        ledger.close()
