"""Isolated, durable Solver checkpoint children for one action plus review."""

import hashlib
import json
from copy import deepcopy

from ..run_budget import RunBudgetLedger
from ..storage import SQLiteStore
from .aprs import verified_gain
from .calls import CallInterrupted
from .faithful_intervention_records import BranchOutcome, FaithfulInterventionError, _encode
from .harness import SolverHarness
from .progress import METHOD_IDS


class CheckpointHarness(SolverHarness):
    """Namespace new calls/sessions while retaining inherited checkpoint identities."""

    def _commit_event(self, run_id, *, event, **kwargs):
        event = {**event, 'event_id': self.namespace_call_id(event['event_id'])}
        return super()._commit_event(run_id, event=event, **kwargs)

    def namespace_call_id(self, call_id):
        """Return the call identity used by both branch dispatch and evidence owners."""
        prefix = f"{self.branch_id}:"
        return call_id if call_id.startswith(prefix) else f"{prefix}{call_id}"

    def dispatch(self, run, operation, request):
        # Keep call and session identities isolated to this child branch.
        request = dict(request)
        if request.get("call_id"):
            request["call_id"] = self.namespace_call_id(request["call_id"])
        if request.get("session_key"):
            request["session_key"] = f"{self.branch_id}:{request['session_key']}"
        if request.get("role") in {"reasoner", "reason_noncoding"}:
            request["step"] = {**request["step"], "method_id": self.action.parameters["method_id"]}
        return super().dispatch(run, operation, request)


class NativeCheckpointExecutor:
    """Run native step execution and Verifier acceptance on a private SQLite child.

    Child state retains the parent's frozen math identity. New calls and sessions
    carry the arm identity; private child snapshots/events are stored separately
    from parent Solver tables. No API accepts a caller-supplied branch outcome.
    """

    def __init__(self, engine, *, config, problem, model_port, verifier_port, tool_port=None):
        self.engine, self.config, self.problem = engine, deepcopy(config), problem
        self.model_port, self.verifier_port, self.tool_port = model_port, verifier_port, tool_port
        with engine._lock:
            engine._connection.execute(
                "CREATE TABLE IF NOT EXISTS faithful_intervention_analysis_plans ("
                "pair_id TEXT PRIMARY KEY,payload_json TEXT NOT NULL,"
                "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            engine._connection.execute(
                "CREATE TABLE IF NOT EXISTS faithful_intervention_children ("
                "branch_id TEXT PRIMARY KEY,pair_id TEXT NOT NULL,arm TEXT NOT NULL,"
                "checkpoint_hash TEXT NOT NULL,state_json TEXT NOT NULL,events_json TEXT NOT NULL,"
                "status TEXT NOT NULL)"
            )
            engine._connection.execute(
                "CREATE TABLE IF NOT EXISTS faithful_intervention_reviews ("
                "review_id TEXT PRIMARY KEY,pair_id TEXT NOT NULL,source_branch_id TEXT NOT NULL,"
                "review_branch_id TEXT NOT NULL,arm TEXT NOT NULL,checkpoint_hash TEXT NOT NULL,"
                "state_json TEXT NOT NULL,events_json TEXT NOT NULL,status TEXT NOT NULL,"
                "UNIQUE(pair_id,arm))"
            )

    def validate_checkpoint(self, state, action, *, is_control=False):
        """Reject unsupported or in-flight actions before creating either child."""
        if (state.get("phase") != "STEP_EXECUTE" or not isinstance(state.get("problem_spec"), dict)
                or state.get("route_policy", {}).get("enabled") is not True
                or state.get("population_policy", {}).get("enabled") is True):
            raise FaithfulInterventionError("native_checkpoint_requires_serial_step")
        if self.config.get("features", {}).get("stream_recovery") is not True:
            raise FaithfulInterventionError("native_checkpoint_requires_call_audit")
        step = next((item for item in (state.get("plan") or {}).get("steps", [])
                     if item.get("step_id") == state.get("current_step")), None)
        if step is None or action.target != step["step_id"]:
            raise FaithfulInterventionError("native_action_target_mismatch")
        review = state.get("steps", {}).get(step["step_id"], {}).get("verification", {})
        if review.get("valid") is True and review.get("verdict") == "ACCEPT":
            raise FaithfulInterventionError("native_checkpoint_has_completed_step")
        if (action.action_type != "reasoning_method" or set(action.parameters) != {"method_id"}
                or not isinstance(action.parameters["method_id"], str)
                or action.parameters["method_id"] not in METHOD_IDS
                or action.parameters["method_id"] == "unknown"):
            raise FaithfulInterventionError("native_action_not_supported")
        if is_control and action.parameters["method_id"] != step.get("method_id"):
            raise FaithfulInterventionError("native_control_action_mismatch")
        if any(item.get("status") in {"dispatched", "unknown_outcome"}
               for item in state.get("calls", {}).values()):
            raise FaithfulInterventionError("native_checkpoint_has_unknown_call")

    def validate_identity(self, checkpoint):
        """Check the actual Harness identity before changing the pair to running."""
        if hashlib.sha256(self.problem.encode()).hexdigest() != checkpoint["problem_hash"]:
            raise FaithfulInterventionError("native_problem_identity_mismatch")
        with SolverHarness(config=self.config) as admission:
            if (admission._config_hash != checkpoint["config_hash"]
                    or checkpoint["state"].get("config_hash") != checkpoint["config_hash"]
                    or checkpoint["state"].get("problem_hash") != checkpoint["problem_hash"]
                    or admission._context_policy != checkpoint["state"].get("context_policy")):
                raise FaithfulInterventionError("native_configuration_identity_mismatch")

    def __call__(self, *, checkpoint, action, branch_id, arm, budget, budget_role):
        self.validate_checkpoint(checkpoint["state"], action, is_control=arm == "control")
        if hashlib.sha256(self.problem.encode()).hexdigest() != checkpoint["problem_hash"]:
            raise FaithfulInterventionError("native_problem_identity_mismatch")
        pair_id = branch_id.rsplit(":", 1)[0]
        local = SQLiteStore()
        try:
            self._clone(local._connection, checkpoint, budget)
            before = verified_gain(checkpoint["state"])

            def observe(run, event):
                self._persist(pair_id, branch_id, arm, checkpoint, run, "running")
                self._mirror_budget(local._connection, checkpoint, budget)

            with CheckpointHarness(store=local, config=self.config,
                                   model_port=self.model_port, verifier_port=self.verifier_port,
                                   tool_port=self.tool_port, event_observer=observe) as harness:
                harness.branch_id = branch_id
                harness.action = action
                run = harness.get_run(checkpoint["run_id"], problem=self.problem)
                self._persist(pair_id, branch_id, arm, checkpoint, run, "running")
                from ..run_control import RunStopped
                from .budget import HardBudgetStop
                from .step import run_step
                from .verification import verify_step

                limits = budget.snapshot()["limits"]
                reported_run = None
                try:
                    run = run_step(harness, run, problem=self.problem, plan=run["state"]["plan"],
                                   model_port=self.model_port,
                                   max_model_calls=limits["max_model_calls"],
                                   max_runtime_seconds=limits["max_runtime_seconds"])
                    reported_run = deepcopy(run)
                    run = verify_step(harness, run, problem=self.problem,
                                      verifier_port=self.verifier_port,
                                      max_model_calls=limits["max_model_calls"],
                                      max_runtime_seconds=limits["max_runtime_seconds"])
                except (CallInterrupted, HardBudgetStop, RunStopped):
                    run = harness.get_run(checkpoint["run_id"])
                review = run["state"].get("steps", {}).get(action.target, {}).get("verification", {})
                reviewed = review.get("valid") is True and review.get("verdict") == "ACCEPT"
                recheck = {}
                if reviewed and reported_run is not None:
                    recheck = self._independent_branch_review(
                        pair_id, branch_id, checkpoint, action, budget, reported_run,
                        limits=limits,
                    )
                    reviewed = recheck.get("valid") is True and recheck.get("verdict") == "ACCEPT"
                measured_state = recheck.get("state", run["state"])
                gain = sorted(set(verified_gain(measured_state)) - set(before))
                self._persist(pair_id, branch_id, arm, checkpoint, run, "reviewed" if reviewed else "incomplete")
                return BranchOutcome(
                    "completed" if reviewed else "incomplete", len(gain) if reviewed else None,
                    {"branch_id": branch_id, "state_revision": run["state_revision"],
                     "review": "accepted" if review.get("verdict") == "ACCEPT" and reviewed else "not_accepted",
                     "branch_verifier_verdict": review.get("verdict"),
                     "independent_recheck_verdict": recheck.get("verdict"),
                     "current_verified_gain": gain,
                     "parent_merge": "not_merged_parent_checkpoint_preserved"},
                    tuple({"event_id": event["event_id"], "type": event["type"],
                           "state_revision": event["state_revision"]}
                          for event in run["events"]
                          if event["state_revision"] > checkpoint["state_revision"]),
                )
        except CallInterrupted:
            # The parent ledger determines whether this interrupted call was
            # physically dispatched and therefore has an unknown outcome.
            return BranchOutcome("incomplete")
        finally:
            local.close()

    def _independent_branch_review(self, pair_id, source_branch_id, checkpoint, action,
                                   budget, reported_run, *, limits):
        """Run a fresh Verifier call against the saved report in an isolated child."""
        review_branch_id = source_branch_id + ":recheck"
        store = SQLiteStore()
        try:
            self._clone_snapshot(store._connection, checkpoint, budget, reported_run)

            def observe(run, _event):
                self._persist_review(pair_id, source_branch_id, review_branch_id,
                                     checkpoint, run, "running")
                self._mirror_budget(store._connection, checkpoint, budget)

            with CheckpointHarness(
                store=store, config=self.config, model_port=self.model_port,
                verifier_port=self.verifier_port, tool_port=self.tool_port,
                event_observer=observe,
            ) as harness:
                harness.branch_id = review_branch_id
                harness.action = action
                run = harness.get_run(checkpoint["run_id"], problem=self.problem)
                self._persist_review(pair_id, source_branch_id, review_branch_id,
                                     checkpoint, run, "dispatching")
                from .verification import verify_step

                run = verify_step(
                    harness, run, problem=self.problem, verifier_port=self.verifier_port,
                    max_model_calls=limits["max_model_calls"],
                    max_runtime_seconds=limits["max_runtime_seconds"], round_number=1,
                )
                verification = run["state"].get("steps", {}).get(action.target, {}).get(
                    "verification", {}
                )
                self._persist_review(
                    pair_id, source_branch_id, review_branch_id, checkpoint, run,
                    "reviewed" if verification.get("valid") is True else "rejected",
                )
                return {**verification, "state": run["state"]}
        except CallInterrupted:
            return {"valid": False, "verdict": None}
        finally:
            store.close()

    def _clone(self, connection, checkpoint, budget):
        """Copy this Run only, preserving its committed history byte-for-byte."""
        source = self.engine._connection
        run_id = checkpoint["run_id"]
        row = source.execute("SELECT * FROM solver_states WHERE run_id=?", (run_id,)).fetchone()
        if checkpoint['state'].get('serial_checkpoint_source'):
            row = list(row)
            row[1] = _encode(checkpoint['state'])
        connection.execute("INSERT INTO solver_states VALUES (?,?,?,?,?,?,?)", tuple(row))
        for event in source.execute("SELECT * FROM solver_events WHERE run_id=? ORDER BY sequence", (run_id,)):
            connection.execute("INSERT INTO solver_events VALUES (?,?,?,?,?,?)", tuple(event))
        connection.commit()
        RunBudgetLedger(connection=connection)
        self._mirror_budget(connection, checkpoint, budget)

    def _clone_snapshot(self, connection, checkpoint, budget, snapshot):
        """Seed a recheck child from one immutable pre-review branch snapshot."""
        row = list(self.engine._connection.execute(
            "SELECT * FROM solver_states WHERE run_id=?", (checkpoint["run_id"],)
        ).fetchone())
        state = snapshot["state"]
        row[1], row[4], row[6] = _encode(state), state["state_revision"], state["updated_at"]
        connection.execute("INSERT INTO solver_states VALUES (?,?,?,?,?,?,?)", tuple(row))
        for sequence, event in enumerate(snapshot["events"], 1):
            connection.execute(
                "INSERT INTO solver_events VALUES (?,?,?,?,?,?)",
                (checkpoint["run_id"], sequence, event["event_id"], event["state_revision"],
                 _encode(event), event.get("created_at", state["updated_at"])),
            )
        connection.commit()
        RunBudgetLedger(connection=connection)
        self._mirror_budget(connection, checkpoint, budget)

    def _persist_review(self, pair_id, source_branch_id, review_branch_id,
                        checkpoint, run, status):
        checkpoint_hash = hashlib.sha256(_encode(checkpoint).encode()).hexdigest()
        arm = "control" if source_branch_id.endswith(":control") else "intervention"
        review_id = pair_id + ":" + arm + ":recheck"
        with self.engine._lock, self.engine._connection:
            self.engine._connection.execute(
                "INSERT INTO faithful_intervention_reviews VALUES (?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(pair_id,arm) DO UPDATE SET review_branch_id=excluded.review_branch_id,"
                "state_json=excluded.state_json,events_json=excluded.events_json,status=excluded.status",
                (review_id, pair_id, source_branch_id, review_branch_id, arm,
                 checkpoint_hash, _encode(run["state"]), _encode(run["events"]), status),
            )

    def _mirror_budget(self, connection, checkpoint, budget):
        run_id = checkpoint["run_id"]
        row = self.engine._connection.execute(
            "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
        current = json.loads(row[0])
        frozen = deepcopy(checkpoint.get("budget_checkpoint"))
        if frozen is None:
            raise FaithfulInterventionError("native_checkpoint_budget_missing")
        frozen["actions"].extend(item for item in current["actions"]
                                 if item.get("reservation_id") == budget.ledger.pair_id
                                 and item.get("role") == budget.ledger.role
                                 and item.get("status") != "pre_reserved")
        connection.execute("INSERT OR REPLACE INTO run_budgets(run_id,ledger_json) VALUES (?,?)",
                           (run_id, _encode(frozen)))
        connection.commit()

    def _persist(self, pair_id, branch_id, arm, checkpoint, run, status):
        with self.engine._lock, self.engine._connection:
            self.engine._connection.execute(
                "INSERT INTO faithful_intervention_children VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(branch_id) DO UPDATE SET state_json=excluded.state_json,"
                "events_json=excluded.events_json,status=excluded.status",
                (branch_id, pair_id, arm, hashlib.sha256(_encode(checkpoint).encode()).hexdigest(),
                 _encode(run["state"]), _encode(run["events"]), status),
            )


def execute_native_pair(engine, pair_id, *, executor, ledger, job_gate):
    """Admit only the native executor; derive outcomes from child Solver evidence."""
    if not isinstance(executor, NativeCheckpointExecutor):
        raise FaithfulInterventionError("native_executor_required")
    report = engine.get_pair(pair_id)
    row = engine._connection.execute(
        "SELECT checkpoint_json FROM faithful_intervention_pairs WHERE pair_id=?", (pair_id,)).fetchone()
    checkpoint = json.loads(row[0])
    executor.validate_identity(checkpoint)
    for arm in ("control", "intervention"):
        executor.validate_checkpoint(
            checkpoint["state"], engine.get_action(report["arms"][arm]["action_id"]),
            is_control=arm == "control",
        )
    from .faithful_intervention_execution import _save, execute_pair
    from .faithful_intervention_native_budget import native_arm_budget

    if report["status"] != "reserved":
        return report
    if (report["budget_reservation"].get("time_seconds", 0) <= 0
            or report["budget_reservation"]["logical_calls"] < 6):
        raise FaithfulInterventionError("native_action_review_reservation_required")
    analysis = {"primary_metric": "current_verified_gain_count",
                "uncertainty_method": "descriptive_only_no_interval_registered",
                "unit": "single_proof_action"}
    engine._register("faithful_intervention_analysis_plans", "pair_id", pair_id,
                     _encode(analysis), None)
    report.update(branch_engine="native_solver_checkpoint", parent_resume="checkpoint_preserved",
                  policy_version=checkpoint["state"]["route_policy"]["policy_version"],
                  problem_hash=checkpoint["problem_hash"], config_hash=checkpoint["config_hash"],
                  analysis_plan=analysis,
                  analysis_plan_hash=hashlib.sha256(_encode(analysis).encode()).hexdigest(),
                  **{key: analysis[key] for key in ("primary_metric", "uncertainty_method")})
    _save(engine, report)
    report = execute_pair(engine, pair_id, execute_branch=executor, ledger=ledger,
                          job_gate=job_gate, budget_factory=native_arm_budget)
    report.update(branch_engine="native_solver_checkpoint", parent_resume="checkpoint_preserved")
    from .faithful_intervention_effects import recheck_native_report
    from .faithful_intervention_execution import project_report

    report = project_report(recheck_native_report(engine._connection, report))
    report["status"] = "completed" if report["evaluable_pairs"] else "incomplete"
    _save(engine, report)
    return report
