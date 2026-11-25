"""Run the paired Runtime conditions against two offline arithmetic fixtures."""

import argparse
import hashlib
import json
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from random import Random
from typing import Any, Literal

from .aprs import Candidate
from .counterfactual import CounterfactualCheckpoint, InterventionAudit, RepairOptions
from .population import CandidateRoute, PopulationBudget
from .port import ModelPortFailure, ModelReply, ToolCall, ToolReceipt
from .reasoning_state import SharedReasoningState
from .runtime import Runtime, _canonical_json, _RunScope, _source_revision, _write_run


@dataclass(frozen=True)
class _Condition:
    state: bool = False
    search: bool = False
    aprs: bool = False
    repair: Literal["random", "diagnostic"] | None = None


_CONDITIONS = {
    "baseline": _Condition(),
    "ricl-state": _Condition(state=True),
    "ricl-search": _Condition(state=True, search=True, aprs=True),
    "ricl-full": _Condition(state=True, search=True, aprs=True, repair="diagnostic"),
    "ricl-without-search": _Condition(state=True, repair="diagnostic"),
    "plain-search": _Condition(state=True, search=True),
    "aprs": _Condition(state=True, search=True, aprs=True),
    "random-repair": _Condition(state=True, repair="random"),
    "diagnostic-repair": _Condition(state=True, repair="diagnostic"),
}
_CASES = {
    "ordinary": ("Compute 2 + 2.", "4"),
    "repair": ("Compute 3 + 2.", "5"),
}
_CONTEXT = "Use exact integer arithmetic."
_BUDGET = PopulationBudget(model_requests=5, tokens=320, tools=1, elapsed_ms=30_000, cost_usd=0)
_REPAIR = RepairOptions(
    options=(("regroup", "Try regrouping."), ("recalculate", "Recalculate each sum.")),
    diagnosed_id="recalculate",
    seed=1,
)


class _FixtureBudgetExhausted(ModelPortFailure):
    failure_status = "budget_exhausted"
    request_sent = False


class _FixtureResources:
    """A single offline ModelPort, tool executor and resource ledger for a paired Run."""

    name = "paired-offline-fixture"

    def __init__(self, case_id: str, answer: str, scope: _RunScope, budget: PopulationBudget):
        self.case_id = case_id
        self.answer = answer
        self.scope = scope
        self.budget = budget
        self.started = time.perf_counter()
        self.requests: list[dict[str, Any]] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.tools = 0

    @property
    def elapsed_ms(self) -> float:
        return round((time.perf_counter() - self.started) * 1000, 3)

    def complete(self, prompt: str) -> ModelReply:
        input_tokens, output_tokens = len(prompt.split()), 1
        request_id = f"{self.scope.run_id}_request_{len(self.requests) + 1:03d}"
        if (
            len(self.requests) >= self.budget.model_requests
            or self.input_tokens + self.output_tokens + input_tokens + output_tokens
            > self.budget.tokens
            or self.elapsed_ms >= self.budget.elapsed_ms
        ):
            self.scope.trace.append(
                {
                    "event": "fixture_request_rejected",
                    "request_id": request_id,
                    "status": "budget_exhausted",
                    "context_sha256": _digest(prompt),
                }
            )
            raise _FixtureBudgetExhausted("paired Run resource budget exhausted")

        request = {
            "request_id": request_id,
            "requested_model": self.name,
            "actual_model": "unknown",
            "request_sent": False,
            "status": "started",
            "context_sha256": _digest(prompt),
            "usage": {"input_tokens": "unknown", "output_tokens": "unknown", "source": "unknown"},
        }
        self.requests.append(request)
        try:
            reply = self._generate(prompt, input_tokens)
        except ModelPortFailure as error:
            request["status"] = error.failure_status
            raise
        request.update(
            {
                "actual_model": reply.model,
                "status": "completed",
                "usage": {
                    "input_tokens": reply.input_tokens,
                    "output_tokens": reply.output_tokens,
                    "source": reply.usage_source,
                },
            }
        )
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        return reply

    def _generate(self, prompt: str, input_tokens: int) -> ModelReply:
        diagnostic = "Recalculate each sum." in prompt
        reused = f": {self.answer}" in prompt and "Verified context:" in prompt
        correct = self.case_id == "ordinary" or diagnostic or reused
        tool_calls = ()
        if self.case_id == "ordinary" and len(self.requests) == 1 and self.budget.tools:
            tool_calls = (ToolCall("addition", "2 + 2"),)
        return ModelReply(
            self.answer if correct else "6",
            model=self.name,
            input_tokens=input_tokens,
            output_tokens=1,
            usage_source="fixture",
            tool_calls=tool_calls,
            action="recalculate" if diagnostic or reused else "solve",
        )

    def execute(self, invocation_id: str, call: ToolCall) -> ToolReceipt:
        if self.tools >= self.budget.tools or self.elapsed_ms >= self.budget.elapsed_ms:
            raise _FixtureBudgetExhausted("paired Run tool budget exhausted")
        self.tools += 1
        left, right = call.input.split(" + ")
        return ToolReceipt(
            invocation_id,
            f"{invocation_id}_receipt",
            call.tool_name,
            True,
            str(int(left) + int(right)),
        )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fixture_audit(feedback: str, reply: ModelReply) -> InterventionAudit:
    consumed = feedback == "Recalculate each sum." and reply.action == "recalculate"
    return InterventionAudit("approved" if consumed else "rejected", "offline_fixture", consumed)


def _run_case(
    case_id: str,
    condition_id: str,
    condition: _Condition,
    budget: PopulationBudget,
    output_root: Path,
    revision: str,
) -> dict[str, Any]:
    problem, answer = _CASES[case_id]
    scope = _RunScope()
    fixture = _FixtureResources(case_id, answer, scope, budget)
    runtime = Runtime(fixture, tool_executor=fixture)
    arguments = {
        "problem_id": case_id,
        "condition_id": condition_id,
        "output_root": output_root,
        "_scope": scope,
    }
    main: dict[str, Any] = {}
    repair: dict[str, Any] = {}
    failure: str | None = None
    try:
        if condition.search:
            routes = tuple(
                CandidateRoute(
                    Candidate(candidate_id, novelty=novelty, known_token_cost=48),
                    prompt=prompt,
                    source="paired_fixture",
                    parent_route_id="root",
                    tool_calls_reserved=min(budget.tools, 1) if novelty == 0 else 0,
                    elapsed_ms_reserved=1,
                    cost_usd_reserved=0,
                )
                for candidate_id, novelty, prompt in (
                    ("direct", 0, "Add from left to right."),
                    ("regroup", 1, "Check the arithmetic by grouping."),
                )
            )
            main = runtime.run_population(
                problem,
                routes,
                budget=budget,
                aprs_enabled=condition.aprs,
                visible_context=_CONTEXT,
                **arguments,
            )
        else:
            main_limit = (
                max(1, budget.model_requests - 3) if condition.repair else budget.model_requests
            )
            main = runtime.run(
                problem,
                reasoning_state_enabled=condition.state,
                model_request_limit=main_limit,
                tool_call_limit=budget.tools,
                visible_context=_CONTEXT,
                **arguments,
            )
        if (
            condition.repair
            and main["run"]["status"] == "completed"
            and main["verification"]["status"] == "failed"
        ):
            remaining = budget.model_requests - len(fixture.requests)
            if remaining < 2:
                scope.trace.append(
                    {
                        "event": "counterfactual_trigger_evaluated",
                        "qualified": True,
                        "admitted": False,
                    }
                )
                failure = "budget_exhausted"
            else:
                checkpoint = CounterfactualCheckpoint(
                    visible_prefix=f"{_CONTEXT}\nPrevious answer: {main['result']['answer']}",
                    failure_count=1,
                    current_action="solve",
                    reasoning_state=scope.state,
                )
                repair = runtime.run_counterfactual(
                    problem,
                    checkpoint=checkpoint,
                    repair_options=_REPAIR,
                    intervention_auditor=_fixture_audit,
                    feedback_kind=condition.repair,
                    model_request_limit=remaining,
                    **arguments,
                )
    except ModelPortFailure as error:
        failure = error.failure_status
        scope.trace.append({"event": "phase_interrupted", "status": failure})

    final = repair if repair.get("parent_continuation") else main
    last_phase = repair or main
    run_status = last_phase.get("run", {"status": "failed", "stop_reason": failure})
    if (
        run_status.get("stop_reason") == "budget_exhausted"
        or fixture.elapsed_ms > budget.elapsed_ms
    ):
        failure = "budget_exhausted"
    if failure:
        run_status = {
            "status": "stopped" if failure == "budget_exhausted" else "failed",
            "stop_reason": failure,
        }
    elif repair and repair["run"]["stop_reason"] == "parent_feedback_budget_exhausted":
        run_status = {"status": "stopped", "stop_reason": "parent_feedback_budget_exhausted"}
    config = {
        "mode": "offline_paired_pilot",
        "mechanisms": asdict(condition),
        "budget": asdict(budget),
        "model_port": fixture.name,
        "tool": "addition",
        "verifier": "integer_addition_v1",
        "model_seed": "unavailable",
        "phases": [
            {"config": phase["config"], "sha256": phase["config_sha256"]}
            for phase in (main, repair)
            if phase
        ],
    }
    run_dir = output_root / scope.run_id
    completed_request_ids = {
        entry["request_id"] for entry in fixture.requests if entry["status"] == "completed"
    }
    known_token_use = fixture.input_tokens + fixture.output_tokens
    usage = {
        "input_tokens": fixture.input_tokens,
        "output_tokens": fixture.output_tokens,
        "tokens": known_token_use,
        "source": "fixture",
    }
    if len(completed_request_ids) != len(fixture.requests):
        usage = {
            "input_tokens": "unknown",
            "output_tokens": "unknown",
            "tokens": "unknown",
            "source": "mixed_or_unknown" if completed_request_ids else "unknown",
        }
    result = {
        "schema_version": 1,
        "run_id": scope.run_id,
        "source": {"revision": revision},
        "problem": {"id": case_id, "sha256": _digest(problem)},
        "condition_id": condition_id,
        "config": config,
        "config_sha256": _digest(_canonical_json(config)),
        "model": {
            "requested": fixture.name,
            "actual": fixture.requests[-1]["actual_model"] if fixture.requests else "unknown",
        },
        "provider_requests": fixture.requests,
        "budget": {
            "scope": "run_shared",
            "model_requests": {"limit": budget.model_requests, "used": len(fixture.requests)},
            "tokens": {
                "limit": budget.tokens,
                "used": usage["tokens"],
                "known_used": known_token_use,
            },
            "tools": {"limit": budget.tools, "used": fixture.tools},
            "elapsed_ms": {"limit": budget.elapsed_ms, "used": fixture.elapsed_ms},
            "cost_usd": {"limit": budget.cost_usd, "used": 0},
        },
        "usage": usage,
        "cost": {"amount_usd": 0, "source": "no_provider_request"},
        "state_reused": any(
            event.get("referenced_evidence_ids")
            and event.get("request_id") in completed_request_ids
            for event in scope.trace
        ),
        "evidence": scope.state.public_snapshot(),
        "result": final.get("result"),
        "verification": final.get(
            "verification", {"status": "unknown", "scope": "none", "reason": "no_answer"}
        ),
        "run": run_status,
        "artifacts": {"run": str(run_dir / "run.json"), "trace": str(run_dir / "trace.jsonl")},
    }
    if "population" in main:
        result["population"] = main["population"]
    if repair:
        result.update(
            {
                key: repair[key]
                for key in ("checkpoint", "branches", "intervention", "parent_continuation")
            }
        )

    _write_run(
        result,
        [
            {
                "event": "run_started",
                "run_id": scope.run_id,
                "condition_id": condition_id,
                "problem_id": case_id,
            },
            *scope.trace,
            {"event": "run_stopped", **run_status},
        ],
    )
    return result


@dataclass(frozen=True)
class _RollbackFixturePort:
    invalidated_id: str
    surviving_id: str
    name = _FixtureResources.name
    max_output_tokens = 128

    def complete(self, prompt: str) -> ModelReply:
        if "Condition: Baseline" in prompt:
            work = "Replay the suffix, interpret the operands again, and check each calculation."
            evidence_id = self.invalidated_id
        else:
            work = "Recompute with the independently supported operands."
            evidence_id = self.surviving_id
        answer = f"{work}\nEvidence used: {evidence_id}\nFinal answer: 4"
        return ModelReply(
            answer,
            model=self.name,
            input_tokens=len(prompt.split()),
            output_tokens=len(answer.split()),
            usage_source="fixture",
        )


def _run_fixture_rollback(output_root: Path, order_seed: int) -> dict[str, Any]:
    from .rollback_experiment import RollbackCheckpoint, RollbackStep, run_rollback_pair

    state = SharedReasoningState()
    mistaken_reading = state.add_verified_result(
        "The second addend is 3.", scope="rollback-fixture"
    )
    independent_reading = state.add_verified_result(
        "The original prompt contains two 2s.", scope="rollback-fixture"
    )
    known_operands = state.add_verified_result(
        "The addends can be read from the problem.",
        scope="rollback-fixture",
        depends_on_any=(mistaken_reading.evidence_id, independent_reading.evidence_id),
    )
    bad_sum = state.add_verified_result(
        "The sum is 5.",
        scope="rollback-fixture",
        depends_on_all=(mistaken_reading.evidence_id,),
    )
    checkpoint = RollbackCheckpoint(
        problem="Compute 2 + 2.",
        problem_id="rollback-addition",
        original_trace=("Read the addends.", "Record the operand evidence.", "Compute the sum."),
        steps=(
            RollbackStep("misread", mistaken_reading.evidence_id),
            RollbackStep("known-operands", known_operands.evidence_id),
            RollbackStep("sum", bad_sum.evidence_id),
        ),
        failed_step_id="misread",
        diagnosis="The first derivation misread the second addend.",
        reasoning_state=state,
    )
    return run_rollback_pair(
        _RollbackFixturePort(mistaken_reading.evidence_id, known_operands.evidence_id),
        checkpoint,
        output_root=output_root / "rollback",
        model_request_limit=1,
        order_seed=order_seed,
    )


def run_offline_pilot(
    *,
    output_root: Path = Path("artifacts/paired-pilot"),
    order_seed: int = 17,
    budget: PopulationBudget = _BUDGET,
) -> dict[str, Any]:
    """Run the shuffled matrix and a separate matched rollback fixture."""
    root = output_root.resolve() / f"pilot_{uuid.uuid4().hex}"
    revision = _source_revision()
    rng = Random(order_seed)
    order = {}
    for case_id in _CASES:
        conditions = list(_CONDITIONS)
        rng.shuffle(conditions)
        order[case_id] = conditions
    records = [
        _run_case(case_id, condition_id, _CONDITIONS[condition_id], budget, root, revision)
        for case_id, conditions in order.items()
        for condition_id in conditions
    ]
    rollback = _run_fixture_rollback(root, order_seed)
    manifest = {
        "source_revision": revision,
        "order_seed": order_seed,
        "model_seed": "unavailable",
        "condition_order": order,
        "budget": asdict(budget),
        "rollback_pair": {"status": rollback["pair_status"], **rollback["artifacts"]},
        "runs": [
            {
                "problem_id": run["problem"]["id"],
                "condition_id": run["condition_id"],
                "verification": run["verification"]["status"],
                "status": run["run"]["status"],
                "stop_reason": run["run"]["stop_reason"],
                **run["artifacts"],
            }
            for run in records
        ],
        "counts": {
            "planned": len(_CASES) * len(_CONDITIONS),
            "status": dict(Counter(run["run"]["status"] for run in records)),
            "stop_reason": dict(Counter(run["run"]["stop_reason"] for run in records)),
            "verification": dict(Counter(run["verification"]["status"] for run in records)),
            "search_executed": sum(
                bool(run.get("population", {}).get("expanded_candidate_ids")) for run in records
            ),
            "state_reused": sum(run["state_reused"] for run in records),
            "intervention_consumed": sum(
                bool(run.get("intervention", {}).get("feedback_consumed_by_parent"))
                for run in records
            ),
        },
        "manifest": str(root / "pilot.json"),
    }
    Path(manifest["manifest"]).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paired offline RiCL Runtime fixtures.")
    parser.add_argument("--output-root", type=Path, default=Path("artifacts/paired-pilot"))
    parser.add_argument("--order-seed", type=int, default=17)
    args = parser.parse_args()
    result = run_offline_pilot(output_root=args.output_root, order_seed=args.order_seed)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
