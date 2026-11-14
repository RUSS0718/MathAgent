"""Autonomous serial experiments and explicit, provenance-checked result references."""

import hashlib
import json
from copy import deepcopy

from .faithful_intervention_records import FaithfulInterventionError, _encode


def _digest(value):
    return hashlib.sha256(_encode(value).encode()).hexdigest()


def _dependency_versions(state, target):
    return _digest(
        {
            "accepted": state.get("accepted_results", []),
            "classified": state.get("verified_results_ledger", []),
            "steps": {k: v for k, v in state.get("steps", {}).items() if k != target},
        }
    )


def result_reference(engine, pair_id, arm, result_id=None):
    """Return an immutable reference to a native reviewed report, never its ledger."""
    report = engine.get_pair(pair_id)
    row = engine._connection.execute(
        "SELECT state_json FROM faithful_intervention_children WHERE pair_id=? AND arm=?",
        (pair_id, arm),
    ).fetchone()
    if row is None:
        raise FaithfulInterventionError("result_source_missing")
    child = json.loads(row[0])
    target = engine.get_action(report["arms"][arm]["action_id"]).target
    step = child["steps"][target]
    frozen = json.loads(
        engine._connection.execute(
            "SELECT checkpoint_json FROM faithful_intervention_pairs WHERE pair_id=?", (pair_id,)
        ).fetchone()[0]
    )["state"]
    grade = "llm_reviewed"
    if result_id is not None:
        from .proof_graph_sources import dependency_closure, importable_ledger_rows

        rows, rejected = importable_ledger_rows(child, child.get("verified_results_ledger", []))
        rows, _ = dependency_closure(
            rows,
            {r["source_id"] for r in rejected},
            {
                key
                for key, step in child.get("steps", {}).items()
                if step.get("verification", {}).get("valid") is True
                and step["verification"].get("verdict") == "ACCEPT"
            },
        )
        source = next((row for row, _ in rows if row["result_id"] == result_id), None)
        if source is None:
            raise FaithfulInterventionError("source_proof_not_applicable")
        grade = source["evidence_level"]
    return {
        "result_id": result_id,
        "evidence_grade": grade,
        "pair_id": pair_id,
        "arm": arm,
        "run_id": report["run_id"],
        "checkpoint_hash": report["checkpoint_hash"],
        "source_version": _digest(child),
        "problem_hash": child["problem_hash"],
        "config_hash": child["config_hash"],
        "specification_version": child.get("specification_version"),
        "premises": deepcopy(child["problem_spec"].get("assumptions", [])),
        "scope": target,
        "plan_version": child["plan_version"],
        "dependencies": deepcopy(child["plan"]["steps"]),
        "dependency_versions": _dependency_versions(frozen, target),
        "report_hash": _digest(step.get("report", {})),
    }


def _applicability(run, engine, reference):
    """Revalidate the same provenance and Run boundary at adoption and consumption."""
    state = run["state"]
    reason = "applicable_reviewed_result"
    try:
        actual = result_reference(
            engine, reference["pair_id"], reference["arm"], reference.get("result_id")
        )
        if reference != actual:
            reason = "source_version_changed"
        elif any(
            actual[k] != state.get(k)
            for k in ("problem_hash", "config_hash", "specification_version", "plan_version")
        ):
            reason = "premise_or_version_changed"
        elif actual["run_id"] != run["run_id"] or actual["scope"] != state.get("current_step"):
            reason = "scope_changed"
        elif actual["premises"] != state["problem_spec"].get("assumptions", []):
            reason = "premises_changed"
        elif actual["dependencies"] != state["plan"]["steps"] or actual[
            "dependency_versions"
        ] != _dependency_versions(state, actual["scope"]):
            reason = "dependencies_changed"
        else:
            report = engine.get_pair(actual["pair_id"])
            if report["arms"][actual["arm"]].get("evidence_integrity") != "verified":
                reason = "source_review_not_verified"
    except FaithfulInterventionError:
        reason = "source_proof_not_applicable"
    except (KeyError, TypeError):
        reason = "result_source_missing"
    return reason


def adopt_result(harness, run, engine, reference):
    """Persist an adoption/rejection; branch authority is never copied to the parent."""
    from ..run_control import check_control

    check_control()
    state = run["state"]
    reason = _applicability(run, engine, reference)
    accepted = reason == "applicable_reviewed_result"
    record = {
        "reference": deepcopy(reference),
        "status": "adopted" if accepted else "rejected",
        "reason": reason,
        "evidence_grade": reference["evidence_grade"] if accepted else None,
    }
    projection = deepcopy(state.get("serial_intervention") or {})
    projection["adoptions"] = [*projection.get("adoptions", []), record]
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"serial-adoption-{run['state_revision']}",
            "type": "serial_result_adoption",
            "status": record["status"],
            "reason": reason,
        },
        state_updates={"serial_intervention": projection},
    )


def applicable_results(harness, run):
    """Recheck references at consumption time; retain the reviewed-step evidence grade."""
    from .faithful_intervention import FaithfulInterventionEngine

    engine = FaithfulInterventionEngine(harness._state_store._connection)
    results = []
    for item in (run["state"].get("serial_intervention") or {}).get("adoptions", []):
        if item["status"] != "adopted":
            continue
        ref = item["reference"]
        try:
            if _applicability(run, engine, ref) != "applicable_reviewed_result":
                continue
            row = engine._connection.execute(
                "SELECT state_json FROM faithful_intervention_children WHERE pair_id=? AND arm=?",
                (ref["pair_id"], ref["arm"]),
            ).fetchone()
            child = json.loads(row[0])
            results.append(
                {
                    "reference": ref,
                    "evidence_grade": item["evidence_grade"],
                    "report": child["steps"][ref["scope"]]["report"],
                }
            )
        except (KeyError, TypeError, FaithfulInterventionError):
            continue
    return results


class SerialGate:
    """Fence native arms on the controller-owned serial checkpoint and hard stop."""

    def assert_paused(self, *, connection, job_id, run_id, checkpoint_revision):
        from ..run_control import check_control

        check_control()
        row = connection.execute(
            "SELECT state_json,state_revision FROM solver_states WHERE run_id=?", (run_id,)
        ).fetchone()
        state = json.loads(row[0]) if row else {}
        if (
            job_id != run_id
            or row is None
            or row[1] != checkpoint_revision
            or state.get("phase") == "TERMINAL"
            or (state.get("serial_intervention") or {}).get("status") != "reserved"
        ):
            raise FaithfulInterventionError("serial_intervention_checkpoint_changed")


def _commit(harness, run, projection, **updates):
    from ..run_control import check_control

    check_control()
    return harness.commit_event(
        run["run_id"],
        expected_revision=run["state_revision"],
        event={
            "event_id": f"serial-intervention-{run['state_revision']}",
            "type": "serial_intervention",
            "status": projection["status"],
        },
        state_updates={"serial_intervention": projection, **updates},
    )


def advance(harness, run, problem):
    if run["state"].get("population_policy", {}).get("enabled") or run["state"].get("execution_serial_route"):
        return run
    return _advance_serial(harness, run, problem)


def _advance_serial(harness, run, problem):
    """Ask once at a reviewed serial obstacle and execute existing symmetric native F4."""
    from ..run_budget import BudgetExhausted, RunBudgetLedger
    from .calls import CallInterrupted
    from .faithful_intervention import FaithfulInterventionEngine
    from .faithful_intervention_native import NativeCheckpointExecutor, execute_native_pair
    from .progress import METHOD_IDS

    state = run["state"]
    projection = state.get("serial_intervention")
    # One bounded experiment per ordinary serial task. Population composition is #177.
    if (
        not getattr(harness, "_intervention_enabled", False)
        or state.get("serial_intervention_permission") != {"enabled": True, "version": "serial-intervention-v1"}
        or not state.get("autonomous_routes")
        or harness._meta_port is None
    ):
        return run
    if projection and projection["status"] not in {"deciding", "reserved"}:
        return run
    if not projection:
        if state.get("phase") != "META_DECIDE" or not state.get("current_step"):
            return run
        if any(
            c.get("status") in {"dispatched", "unknown_outcome"}
            for c in state.get("calls", {}).values()
        ):
            return run
        projection = {
            **({k: state['population_intervention'][k] for k in ('origin', 'route_id', 'source_version')}
               if state.get('population_intervention', {}).get('origin') == 'population' else {}),
            "status": "deciding",
            "decision": None,
            "pair_id": None,
            "adoptions": [],
            "continuation": "pending",
            "call_id": f"serial-intervention:{run['run_id']}:{run['state_revision']}",
        }
        run = _commit(harness, run, projection)
    if projection["status"] == "deciding":
        call = run["state"].get("calls", {}).get(projection["call_id"])
        if call:
            if call["status"] != "completed":
                raise CallInterrupted(run["run_id"], projection["call_id"])
            proposal = call["response"]
        else:
            from .budget import budget_reason

            if budget_reason(
                run["state"],
                {
                    "max_model_calls": harness._config.get("max_model_calls", 2),
                    "max_total_duration_seconds": harness._config.get(
                        "max_total_duration_seconds", 3600
                    ),
                },
            ):
                return _commit(
                    harness,
                    run,
                    {**projection, "status": "skipped", "continuation": "main_task_continues"},
                )
            request = {
                "role": "meta",
                "serial_intervention_decision": True,
                "problem": problem,
                "call_id": projection["call_id"],
                "run_id": run["run_id"],
                "session_key": f"serial-intervention:{run['run_id']}",
                "plan": run["state"]["plan"],
                "obstacle": run["state"].get("progress", {}),
                "steps": run["state"].get("steps", {}),
                "allowed_tools": [],
                "instruction": "Choose keep or intervene for this reviewed mathematical obstacle. "
                "Intervene only for a falsifiable mathematical hypothesis, selecting one distinct "
                "controlled reasoning method. Never intervene for transport failure. "
                "Return decision, reason, hypothesis (falsifiable public summary), method_id. "
                "Both arms and independent reviews share the original budget; final whole review remains required.",
            }
            run = _commit(
                harness,
                run,
                projection,
                counters={
                    **run["state"]["counters"],
                    "model_calls": run["state"]["counters"]["model_calls"] + 1,
                },
            )
            proposal = dict(
                harness.dispatch(
                    run, harness._meta_port.complete, harness.prepare_request(run, request)
                )
            )
            run = harness.get_run(run["run_id"])
        from ..redaction import redact

        if proposal.get("decision") not in {"keep", "intervene"} or any(
            not isinstance(proposal.get(k), str) for k in ("reason", "hypothesis", "method_id")
        ):
            raise ValueError("invalid_serial_intervention_decision")
        projection = {
            **projection,
            "decision": redact(
                {k: proposal[k][:400] for k in ("decision", "reason", "hypothesis", "method_id")}
            ),
        }
        step = next(
            s for s in run["state"]["plan"]["steps"] if s["step_id"] == run["state"]["current_step"]
        )
        if (
            proposal["decision"] != "intervene"
            or proposal["method_id"] not in METHOD_IDS - {"unknown"}
            or proposal["method_id"] == step.get("method_id")
            or not proposal["hypothesis"].strip()
        ):
            return _commit(
                harness,
                run,
                {**projection, "status": "skipped", "continuation": "main_task_continues"},
            )
        projection.update(status="reserved", pair_id=projection["call_id"] + ":pair")
        run = _commit(harness, run, projection, phase="STEP_EXECUTE")
    engine = FaithfulInterventionEngine(harness._state_store._connection)
    executor = NativeCheckpointExecutor(
        engine,
        config=harness._config,
        problem=problem,
        model_port=harness._model_port,
        verifier_port=harness._verifier_port,
        tool_port=harness._tool_port,
    )
    ledger = RunBudgetLedger(connection=engine._connection)
    pair_id = projection["pair_id"]
    try:
        try:
            report = engine.get_pair(pair_id)
            if report["run_id"] != run["run_id"] or report["job_id"] != run["run_id"]:
                raise FaithfulInterventionError("serial_intervention_pair_owner_changed")
        except KeyError:
            step = next(
                s
                for s in run["state"]["plan"]["steps"]
                if s["step_id"] == run["state"]["current_step"]
            )
            for arm, method in (
                ("control", step["method_id"]),
                ("intervention", projection["decision"]["method_id"]),
            ):
                engine.register_action(
                    {
                        "action_id": pair_id + ":" + arm,
                        "action_type": "reasoning_method",
                        "target": step["step_id"],
                        "parameters": {"method_id": method},
                    }
                )
            engine.register_hypothesis(
                {
                    "hypothesis_id": pair_id + ":hypothesis",
                    "failure_category": "method_mismatch",
                    "evidence": {"decision_call_id": projection["call_id"]},
                    "candidate_action_ids": [pair_id + ":control", pair_id + ":intervention"],
                    "falsification_criteria": {"condition": projection["decision"]["hypothesis"]},
                }
            )
            from .population_runtime import _estimates

            estimate, closing = _estimates(
                harness,
                {
                    **run,
                    "state": {
                        **run["state"],
                        "population_policy": {
                            **(
                                run["state"].get("autonomous_routes", {}).get("population_policy")
                                or {}
                            ),
                            "max_challenge_rounds": 0,
                            "retry_limit": 1,
                            "request_timeout_seconds": harness._model_port.adapter.applied_config().get(
                                "request_timeout_seconds"
                            )
                            or 30,
                        },
                    },
                },
                {"snapshot": run["state"]},
                problem,
            )
            calls = estimate["calls"]
            reservation = {
                "model_calls": 3,
                "input_estimate": max(c["input_estimate"] for c in calls),
                "output_cap": max(c["output_cap"] for c in calls),
                "http_attempts": max(c["http_attempts"] for c in calls),
                "tool_calls": 0,
                "time_seconds": int(estimate["time_seconds"] * 3 / len(calls)),
            }
            report = engine.reserve_pair(
                job_id=run["run_id"],
                run_id=run["run_id"],
                job_gate=SerialGate(),
                expected_revision=run["state_revision"],
                hypothesis_id=pair_id + ":hypothesis",
                control_action_id=pair_id + ":control",
                intervention_action_id=pair_id + ":intervention",
                pair_id=pair_id,
                seed=0,
                reservation=reservation,
            )
        report = execute_native_pair(
            engine, pair_id, executor=executor, ledger=ledger, job_gate=SerialGate()
        )
    except (BudgetExhausted, ValueError) as error:
        return _commit(
            harness,
            harness.get_run(run["run_id"]),
            {
                **projection,
                "status": "skipped",
                "reason": str(error),
                "continuation": "main_task_continues",
            },
            phase="META_DECIDE",
        )
    if (
        report.get("unknown_pairs")
        or report.get("status") == "running"
        or any(
            a.get("status") in {"dispatching", "running", "unknown_outcome"}
            for a in report["arms"].values()
        )
    ):
        return _commit(harness, run, {**projection, "status": "needs_review"})
    if report["arms"]["intervention"].get("evidence_integrity") == "verified":
        run = adopt_result(harness, run, engine, result_reference(engine, pair_id, "intervention"))
        projection = run["state"]["serial_intervention"]
    projection = {**projection, "status": report["status"], "continuation": "main_task_continues"}
    reusable = applicable_results(harness, run)
    if reusable:
        # Reuse the referenced argument as a main-task report. The parent Verifier
        # establishes its own authority; neither child ledger nor its verdict is copied.
        step_id = run["state"]["current_step"]
        projection["review_id"] = _digest(reusable[-1]["reference"])
        from .report_sources import native_material

        material = native_material(engine, reusable[-1]['reference'])
        source_id = 'native-report:' + _digest(material)
        run = _commit(
            harness,
            run,
            projection,
            phase="STEP_VERIFY",
            native_report_sources={**run['state'].get('native_report_sources', {}), source_id: material},
            steps={
                **run["state"]["steps"],
                step_id: {
                    **run["state"]["steps"].get(step_id, {}),
                    "report": reusable[-1]["report"],
                    "status": "REPORTED",
                },
            },
        )
        from .verification import verify_step

        return verify_step(
            harness,
            run,
            problem=problem,
            verifier_port=harness._verifier_port,
            max_model_calls=harness._config.get("max_model_calls", 2),
            max_runtime_seconds=harness._config.get("max_total_duration_seconds", 3600),
        )
    return _commit(harness, run, projection, phase="META_DECIDE")


def public_projection(projection):
    """Whitelist public identity and summaries; keep math premises and reports private."""
    return {
        **{
            k: deepcopy(projection.get(k))
            for k in ("status", "decision", "pair_id", "continuation", "reason")
        },
        **{k: deepcopy(projection[k]) for k in ("origin", "route_id", "source_version") if k in projection},
        "adoptions": [
            {
                **{k: item.get(k) for k in ("status", "reason", "evidence_grade")},
                "reference": {
                    k: item["reference"].get(k)
                    for k in ("pair_id", "arm", "source_version", "scope")
                },
            }
            for item in projection.get("adoptions", [])
        ],
    }
