"""Single-route Runtime with explicit run accounting and redacted artifacts."""

import hashlib
import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from .port import ModelPort
from .verification import verify_integer_addition


class Runtime:
    """Run one offline text problem through a ModelPort and an independent check."""

    def __init__(self, model_port: ModelPort) -> None:
        """Bind the one model capability available to this Runtime instance."""

        self._model_port = model_port

    def run(
        self,
        problem: str,
        *,
        problem_id: str | None = None,
        condition_id: str = "offline-single-route",
        output_root: Path = Path("artifacts"),
    ) -> dict[str, Any]:
        """Generate one free-text answer, record verification, and persist the Run."""

        run_id = f"run_{uuid.uuid4().hex}"
        request_id = f"{run_id}_request_001"
        problem_sha256 = hashlib.sha256(problem.encode("utf-8")).hexdigest()
        problem_id = problem_id or problem_sha256
        config = {
            "mode": "offline",
            "route": "single",
            "model_port": self._model_port.name,
            "reasoning_config": "none",
            "budget": {
                "scope": "run_shared",
                "model_requests": 1,
                "tokens": "unknown",
                "tools": 0,
                "elapsed_limit_ms": "unknown",
                "cost_usd": "unknown",
            },
            "verifier": "integer_addition_v1",
        }
        config_sha256 = hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest()
        started = time.perf_counter()
        reply = self._model_port.complete(problem)
        verification = verify_integer_addition(problem, reply.text)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        answer_sha256 = hashlib.sha256(reply.text.encode("utf-8")).hexdigest()
        revision = _source_revision()
        run_dir = output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        trace_path = run_dir / "trace.jsonl"
        run_path = run_dir / "run.json"

        result = {
            "schema_version": 1,
            "run_id": run_id,
            "source": {"revision": revision},
            "config": config,
            "config_sha256": config_sha256,
            "problem": {"id": problem_id, "sha256": problem_sha256},
            "condition_id": condition_id,
            "model": {
                "requested": self._model_port.name,
                "actual": reply.model or "unknown",
                "reasoning_config": config["reasoning_config"],
            },
            "budget": {
                "scope": "run_shared",
                "model_requests": {"limit": 1, "used": 1},
                "tokens": {"limit": "unknown", "used": "unknown"},
                "tools": {"limit": 0, "used": 0},
                "elapsed_ms": elapsed_ms,
                "elapsed_limit_ms": "unknown",
                "cost_usd": {"limit": "unknown", "used": "unknown"},
            },
            "usage": {
                "input_tokens": reply.input_tokens,
                "output_tokens": reply.output_tokens,
                "tokens": (
                    reply.input_tokens + reply.output_tokens
                    if isinstance(reply.input_tokens, int)
                    and isinstance(reply.output_tokens, int)
                    else "unknown"
                ),
                "source": reply.usage_source,
            },
            "cost": {"amount_usd": "unknown", "source": "unknown"},
            "result": {"id": f"result_{run_id}", "answer": reply.text},
            "verification": verification,
            "run": {"status": "completed", "stop_reason": "answer_generated"},
            "artifacts": {"run": str(run_path), "trace": str(trace_path)},
        }
        trace = [
            {
                "event": "run_started",
                "run_id": run_id,
                "request_id": request_id,
                "problem_id": problem_id,
                "problem_sha256": problem_sha256,
                "condition_id": condition_id,
                "config_sha256": config_sha256,
            },
            {
                "event": "answer_generated",
                "request_id": request_id,
                "result_id": result["result"]["id"],
                "model": reply.model or "unknown",
                "answer_sha256": answer_sha256,
            },
            {"event": "verification_completed", **verification},
            {
                "event": "run_stopped",
                "status": result["run"]["status"],
                "stop_reason": result["run"]["stop_reason"],
            },
        ]
        trace_path.write_text(
            "".join(f"{_canonical_json(event)}\n" for event in trace), encoding="utf-8"
        )
        run_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result


def _canonical_json(value: Any) -> str:
    """Serialize JSON deterministically for configuration and trace fingerprints."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_revision() -> str:
    """Read the containing Git revision, returning unknown outside a Git checkout."""

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent,
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"
