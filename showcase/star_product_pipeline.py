"""Limited STAR bridge inside the existing Job/S3 execution boundary."""

from langgraph.graph import END, START, StateGraph

from .adapters import InternModelAdapter
from .run_budget import RunBudgetLimits, current_budget, public_solver_call_id
from .run_control import RunStopped, check_control
from .solver_harness import SolverHarness
from .solver_harness.controller import advance_product
from .solver_harness.final_binding import delivery_verification
from .solver_harness.intern_port import InternModelPort
from .solver_harness.result import export_result
from .solver_harness.tool_ports import RegistryToolPort
from .star_product_candidates import candidate_projection
from .star_product_config import limited_config
from .star_product_events import decision_fields, public_solver_event_id
from .star_product_modes import mode_identity
from .star_product_recovery import recovery_projection, resume_solver

PUBLIC_TOOL_NAMES = frozenset({"polynomial_check", "python_math"})


class StarProductPipeline:
    execution_mode = "star_limited"

    def __init__(self, database_path, *, adapter=None, evidence_kind="live", budget=None,
                 features=None, registry=None, hint_mode="none"):
        if evidence_kind not in {"live", "scripted", "fault_injection"}:
            raise ValueError("star_evidence_kind_invalid")
        if adapter is not None and not isinstance(adapter, InternModelAdapter):
            raise ValueError("star_adapter_invalid")
        self.database_path = database_path
        self.adapter = adapter or InternModelAdapter(client_timeout=180, client_retry=1)
        self.evidence_kind = evidence_kind
        if budget is not None and not isinstance(budget, RunBudgetLimits):
            raise ValueError("star_budget_invalid")
        self.budget = budget or RunBudgetLimits(max_model_calls=3, max_http_attempts=3, max_tool_calls=0)
        self.config = limited_config(self.budget, features, registry)
        if hint_mode not in {"none", "meta_auto"}:
            raise ValueError("star_hint_mode_invalid")
        self.config["hint_mode"] = hint_mode
        self.registry = registry
        self.checkpointer = None

    def run(self, run_id, problem, *, verification_mode="auto", emit=None, solver_hint=None,
            retry_call=None, solver_mode="star_limited"):
        if solver_mode not in {"star_limited", "star_limited_best_effort"}:
            raise ValueError("star_mode_invalid")
        check_control()
        if current_budget() is None or self.checkpointer is None:
            raise RuntimeError("star_requires_product_control")
        sink = emit or (lambda _event: None)
        port = InternModelPort(self.adapter, original_problem=problem)
        config = {**self.config, **({"hint_mode": "user_hint"} if solver_hint is not None else {}),
                  "features": {**self.config["features"], "candidate_registry": True,
                               "best_effort": solver_mode == "star_limited_best_effort"}}

        def observe(run, event):
            if event:
                public_event_id = public_solver_event_id(run, event)
                sink({"type": "solver_progress", "job_id": run_id,
                      "solver_event_id": public_event_id,
                      "solver_revision": event.get("state_revision", 0),
                      "solver_event_type": event["type"],
                      "node_name": "star", "step_id": public_event_id,
                      "title": "STAR " + event["type"],
                      "summary": event["type"],
                      "solver": projection(run),
                      **decision_fields(event, run["state"], port.invocations)})

        def solve():
            with SolverHarness(database_path=self.database_path, config=config,
                               model_port=port, verifier_port=port,
                               meta_port=port,
                               tool_port=RegistryToolPort(self.registry) if self.registry else None,
                               event_observer=observe) as harness:
                existing = harness._state_store.get_run(run_id)
                harness._product_recovery = existing is not None
                from .solver_harness.budget import HardBudgetStop
                from .solver_harness.calls import CallInterrupted

                try:
                    run = (resume_solver(harness, problem, run_id, retry_call) if existing else
                           harness.solve(problem, {"run_id": run_id, "user_hint": solver_hint}))
                except (CallInterrupted, HardBudgetStop):
                    run = harness.get_run(run_id)
                except RunStopped as exc:
                    if solver_mode != "star_limited_best_effort" or exc.category != "run_deadline_exhausted":
                        raise
                    run = harness.get_run(run_id)
                try:
                    run = advance_product(harness, run, problem)
                except RunStopped as exc:
                    if solver_mode != "star_limited_best_effort" or exc.category != "run_deadline_exhausted":
                        raise
                    run = harness.get_run(run_id)
                from .solver_harness.best_effort import run_best_effort

                run = run_best_effort(harness, run)
                math = run["state"]
                answer = export_result(run)["final_response"]
                bound, verification = delivery_verification(run, answer)
                from .star_product_candidates import selection_verification

                verification = selection_verification(run, answer, verification)
                reviewed = math["status"] == "completed_llm_reviewed" and bound
                attempts = []
                for call in port.invocations:
                    for attempt in call["request_attempts"]:
                        public_attempt = dict(attempt)
                        if "solver_call_id" in public_attempt:
                            public_attempt["solver_call_id"] = public_solver_call_id(
                                run_id, public_attempt["solver_call_id"]
                            )
                        attempts.append(public_attempt)
                result = {
                    **mode_identity(solver_mode), "run_id": run_id,
                    "execution_mode": solver_mode, "evidence_kind": self.evidence_kind,
                    "solver": projection(run, answer=answer),
                    "status": "COMPLETED" if reviewed and verification_mode != "required" else "NEEDS_REVIEW",
                    "stage": math["phase"].lower(),
                    "final_response": answer,
                    "summary": "受限 STAR：探索、润色和新整题审查；不代表完整参考能力",
                    "verification": verification,
                    "request_attempts": attempts,
                    "tool_results": public_tools(math),
                    "error": None if reviewed and verification_mode != "required" else {"category": "verification_needs_review" if reviewed else "star_needs_review"},
                }
                check_control(allow_expired_selection=math.get("best_effort_decision") is not None)
                return result

        builder = StateGraph(dict)
        builder.add_node("star_projection", lambda state: state)
        builder.add_edge(START, "star_projection")
        builder.add_edge("star_projection", END)
        graph = builder.compile(checkpointer=self.checkpointer)
        graph_config = {"configurable": {"thread_id": run_id}}
        result = solve()
        result = graph.invoke(result, graph_config, durability="sync")
        sink({"type": "final_result" if result["status"] == "COMPLETED" else "needs_review",
              "job_id": run_id, "node_name": "terminal", "step_id": "terminal",
              "title": "受限 STAR 已完成" if result["status"] == "COMPLETED" else "受限 STAR 需要复核",
              "message": "star_needs_review", "data": {"type": "text", "summary": result["summary"]}})
        return result


def projection(run, *, answer=None):
    state = run["state"]
    status = state["status"]
    if answer is not None and status == "completed_llm_reviewed":
        bound, _ = delivery_verification(run, answer)
        if not bound:
            status = "completed_unverified"
    return {"run_id": run["run_id"], "state_revision": run["state_revision"],
            "phase": state["phase"], "status": status,
            "config_hash": state["config_hash"], "checkpoint_thread_id": run["run_id"],
            "recovery": recovery_projection(run),
            **candidate_projection(run)}


def public_tools(state):
    receipts = state.get("tool_receipts", [])
    plan = state.get("plan") or {}
    ordinals = {
        step["step_id"]: f"步骤 {index}"
        for index, step in enumerate(plan.get("steps", []), 1)
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    tools = []
    for item in receipts:
        receipt = {key: value for key, value in item.items() if key not in {"input", "output"}}
        if "tool" in item:
            tool_name = item.get("tool")
            public_name = tool_name if isinstance(tool_name, str) and tool_name in PUBLIC_TOOL_NAMES else "unsupported"
        else:
            public_name = "python_math" if item.get("source") == "docker_isolated" else "polynomial_check"
        if "tool" in receipt:
            receipt["tool"] = public_name
        step_id = receipt.get("step_id")
        ordinal = ordinals.get(step_id)
        if ordinal is None:
            receipt.pop("step_id", None)
        else:
            receipt["step_id"] = ordinal
        tools.append({"name": public_name,
            "status": item["status"], "tool_call_id": item["receipt_id"],
            "result_summary": "Finite computation only; not a completeness proof",
            "receipt": receipt})
    return tools
