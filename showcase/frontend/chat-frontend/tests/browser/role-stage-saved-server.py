"""Loopback-only saved-data fixture for the #199 browser acceptance test.

The worker stays disabled. Fixtures use the normal Solver commit boundary; the
browser reads the actual authenticated Flask routes, without API interception.
This is deterministic presentation evidence, never a real mathematics experiment.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from flask import jsonify, request

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.solver_harness import SolverHarness
from showcase.star_product_events import decision_fields, public_solver_event_id
from showcase.star_product_pipeline import projection


def create_fixture_app(folder):
    app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": folder,
                      "SHOWCASE_WORKER_ENABLED": False})
    service = app.extensions["showcase_workspace_service"]
    session = service.create_session("local-user")
    problem = "固定保存夹具：对任意实数 x，平方非负。"
    job, _ = service.create_job(user_id="local-user", session_id=session,
                               problem=problem,
                               idempotency_key=str(uuid4()),
                               budget_limits=RunBudgetLimits())
    job_id = job["job_id"]
    service.store.start_job(job_id, execution_mode="fake")
    harness = SolverHarness(database_path=service.store.database_path, config={})
    harness.solve(problem, {"run_id": job_id})

    def save_plan(version):
        before = harness.get_run(job_id)
        run = harness.commit_event(job_id, expected_revision=before["state_revision"],
            event={"event_id": f"saved-plan-{version}",
                   "type": "initial_plan_generated" if version == 1 else "plan_replaced"},
            state_updates={"plan_version": version, "plan": {"version": version, "steps": [
                {"step_id": f"internal-step-{version}", "title": f"保存目标第 {version} 版",
                 "objective": rf"对任意实数 $x$，$(x-{version})^2\geq 0$；等号当且仅当 $x={version}$。",
                 "depends_on": [], "argument": "PRIVATE_ARGUMENT_MUST_NOT_LEAK"}]}})
        event = run["events"][-1]
        service.store.append_event(job_id, {
            "type": "solver_progress", "solver_event_type": event["type"],
            "solver_event_id": public_solver_event_id(run, event),
            "solver": projection(run), **decision_fields(event, run["state"])})
        return event["role_stage_source"]

    old_source = save_plan(1)
    current_source = save_plan(2)
    service.store.fail_job(job_id, "fixture_stopped_after_saved_results")

    @app.get("/_role-stage-fixture")
    def fixture():
        return jsonify(session_id=session, job_id=job_id, old_source=old_source,
                       current_source=current_source, evidence_kind="controlled_saved_fixture")

    @app.get("/_role-stage-audit")
    def audit():
        # Authentication maintenance is intentionally outside this business audit.
        connection = service.store._connection
        tables = ("workspace_jobs", "workspace_events", "runs", "events",
                  "solver_states", "solver_events", "run_budgets")
        saved = {table: [dict(row) for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid')]
                 for table in tables}
        encoded = json.dumps(saved, sort_keys=True, ensure_ascii=False)
        state = harness.get_run(job_id)["state"]
        return jsonify(business_digest=hashlib.sha256(encoded.encode()).hexdigest(),
                       state_revision=state["state_revision"],
                       calls=state.get("calls", {}), counters=state.get("counters", {}),
                       worker_enabled=False)

    # Only this loopback test server exposes synthetic fixture/audit data. Actual
    # /api routes retain their normal owner and reviewer authorization hooks.
    def fixture_request():
        if request.path == "/_role-stage-fixture":
            return fixture()
        if request.path == "/_role-stage-audit":
            return audit()
        return None

    app.before_request_funcs[None].insert(0, fixture_request)

    app.extensions["role_stage_fixture_harness"] = harness
    return app


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="role-stage-saved-") as folder:
        fixture_app = create_fixture_app(folder)
        try:
            fixture_app.run(host="127.0.0.1", port=5182, use_reloader=False)
        finally:
            fixture_app.extensions["role_stage_fixture_harness"].close()
            for name in ("loopback_store", "showcase_workspace_service", "showcase_run_service"):
                fixture_app.extensions[name].close()
