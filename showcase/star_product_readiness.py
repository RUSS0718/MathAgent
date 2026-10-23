"""Real Registry isolation probe; deployment readiness is not mathematical acceptance."""

import uuid

from .container_tool import tool_request
from .python_executor import DockerPythonExecutor
from .run_budget import RunBudgetLedger, RunBudgetLimits, bind_budget

PROBE_CODE = "import sympy, numpy, mpmath\nprint(sympy.factor(sympy.Symbol('x')**2-1))"
PROBE_OUTPUT = "(x - 1)*(x + 1)\n"


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
        }
    except Exception:
        return {"available": False, "reason": "isolated_python_preflight_failed"}
    finally:
        ledger.close()
