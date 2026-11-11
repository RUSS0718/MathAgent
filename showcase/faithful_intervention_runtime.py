"""Build server-owned native F4 execution and reservation seams from STAR config."""

from __future__ import annotations

import json

from .run_budget import RunBudgetLedger
from .solver_harness.faithful_intervention import FaithfulInterventionEngine
from .solver_harness.faithful_intervention_native import NativeCheckpointExecutor
from .solver_harness.intern_port import InternModelPort
from .solver_harness.tool_ports import RegistryToolPort


def runtime_hooks(pipeline, database_path):
    """Return trusted reservation and executor factories for one configured STAR pipeline."""
    from .faithful_intervention_api import _SCHEMA_LOCK

    connection_lock = _SCHEMA_LOCK
    if pipeline is None:
        return None, None

    def frozen_config(connection, job_id):
        row = connection.execute(
            "SELECT config_json FROM faithful_intervention_control WHERE job_id=? AND status='paused'",
            (job_id,),
        ).fetchone()
        config = json.loads(row[0]) if row and row[0] else None
        if not isinstance(config, dict):
            raise ValueError("intervention_frozen_config_unavailable")
        return config

    def make_ports(connection, job_id, config):
        row = connection.execute(
            "SELECT problem FROM workspace_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise ValueError("intervention_parent_job_unavailable")
        problem = row[0]
        model_port = InternModelPort(
            pipeline.adapter,
            original_problem=problem,
            streaming=config.get("features", {}).get("stream_activity") is True,
            transport_policy=pipeline.transport_policy,
            stream_profiles=pipeline.stream_profiles,
        )
        return problem, model_port

    def reservation_estimator(connection, checkpoint, hypothesis, actions):
        job_id = checkpoint["state"].get("run_id")
        config = frozen_config(connection, job_id)
        from .faithful_intervention_control import assert_applied_config

        assert_applied_config(connection, job_id, pipeline.adapter.applied_config())
        problem, model_port = make_ports(connection, job_id, config)
        row = connection.execute(
            "SELECT status FROM faithful_intervention_control WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None or row[0] != "paused":
            raise ValueError("intervention_parent_not_paused")
        with __harness(database_path, config, problem, model_port, pipeline.registry) as harness:
            run = harness.get_run(job_id, problem=problem)
            state = run["state"]
            step_id = state.get("current_step")
            step = next(item for item in state["plan"]["steps"] if item["step_id"] == step_id)
            from .solver_harness.finalize import _serialized_request_size

            reasoner_sizes = []
            for action in actions:
                proposed_step = {**step, "method_id": action.parameters["method_id"]}
                request = {
                    "run_id": job_id,
                    "call_id": f"{job_id}:reasoner:{state['plan_version']}:{step_id}:reservation",
                    "session_key": f"reasoner:{job_id}:plan{state['plan_version']}:attempt{state['attempt_index']}",
                    "failure_records": state.get("failure_records", []),
                    "rescued_results": state.get("rescued_results", []),
                    "role": "reasoner",
                    "problem": problem,
                    "step": proposed_step,
                    "state_revision": run["state_revision"],
                    "tool_policy": {"allow": []},
                }
                reasoner_sizes.append(_serialized_request_size(
                    harness, model_port, run, request
                ))
            verifier_request = {
                "run_id": job_id,
                "call_id": f"{job_id}:step-verifier:{state['plan_version']}:{step_id}:reservation",
                "session_key": f"verify:{job_id}:plan{state['plan_version']}:step{step_id}",
                "role": "step_verifier",
                "problem": problem,
                "step": step,
                "report": {"argument": "x" * (pipeline.adapter.max_tokens * 4),
                           "claims": [], "blocked": False},
                "current_step_index": 1,
                "state_revision": run["state_revision"],
            }
            verifier_size = _serialized_request_size(
                harness, model_port, run, verifier_request
            )
        applied = pipeline.adapter.applied_config()
        try:
            client = pipeline.adapter._get_client()
        except Exception as error:
            raise ValueError("intervention_retry_policy_unavailable") from error
        retries = min(max(1, int(getattr(client, "retry", 1))), 3)
        timeout = applied.get("request_timeout_seconds") or 30
        if type(timeout) not in {int, float} or timeout <= 0:
            raise ValueError("intervention_timeout_unavailable")
        budget = RunBudgetLedger(connection=connection, connection_lock=connection_lock)
        summary = budget.snapshot(job_id)
        state = checkpoint["state"]
        closing = state.get("route_budget", {}).get("closing_reserve", {})
        frozen_floor = connection.execute(
            "SELECT closing_reserve_json FROM faithful_intervention_control WHERE job_id=?",
            (job_id,),
        ).fetchone()
        if frozen_floor is not None and frozen_floor[0]:
            closing = json.loads(frozen_floor[0])
        tool_capacity = summary["limits"]["max_tool_calls"] - summary["tool_calls"] - closing.get("tool_calls", 0)
        tool_calls_per_arm = max(0, tool_capacity // 2)
        input_estimate = max(*reasoner_sizes, verifier_size) + 2_048
        output_cap = pipeline.adapter.max_tokens
        return {
            "input_estimate": input_estimate,
            "output_cap": output_cap,
            "model_calls": 3,
            "http_attempts": retries,
            "tool_calls": tool_calls_per_arm,
            "time_seconds": timeout * retries * 3,
        }

    def execution_factory(connection, job_id, _pair_id, _report, _gate):
        config = frozen_config(connection, job_id)
        problem, model_port = make_ports(connection, job_id, config)
        engine = FaithfulInterventionEngine(connection, connection_lock=connection_lock)
        ledger = RunBudgetLedger(connection=connection, connection_lock=connection_lock)
        tool_port = RegistryToolPort(pipeline.registry) if pipeline.registry else None
        executor = NativeCheckpointExecutor(
            engine,
            config=config,
            problem=problem,
            model_port=model_port,
            verifier_port=model_port,
            tool_port=tool_port,
        )
        return executor, ledger

    return reservation_estimator, execution_factory


def __harness(database_path, config, problem, model_port, registry):
    """Create an identity-checking Harness used only to measure request sizes."""
    from .solver_harness import SolverHarness

    return SolverHarness(
        database_path=database_path,
        config=config,
        model_port=model_port,
        verifier_port=model_port,
        meta_port=model_port,
        tool_port=RegistryToolPort(registry) if registry else None,
    )
