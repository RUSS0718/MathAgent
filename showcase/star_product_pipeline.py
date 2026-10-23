"""Limited STAR bridge inside the existing Job/S3 execution boundary."""

from langgraph.graph import END, START, StateGraph

from .adapters import InternModelAdapter
from .run_budget import RunBudgetLimits, current_budget, public_solver_call_id
from .run_control import check_control
from .solver_harness import SolverHarness
from .solver_harness.controller import advance_product
from .solver_harness.intern_port import InternModelPort
from .solver_harness.result import export_result
from .solver_harness.tool_ports import RegistryToolPort
from .star_product_config import limited_config
from .star_product_events import decision_fields, public_solver_event_id
from .star_product_modes import mode_identity


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

    def run(self, run_id, problem, *, verification_mode="auto", emit=None, solver_hint=None):
        check_control()
        if current_budget() is None or self.checkpointer is None:
            raise RuntimeError("star_requires_product_control")
        sink = emit or (lambda _event: None)
        port = InternModelPort(self.adapter, original_problem=problem)
        config = {**self.config, **({"hint_mode": "user_hint"} if solver_hint is not None else {})}

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
                      "solver": projection(run), **decision_fields(event, run["state"])})

        def solve():
            with SolverHarness(database_path=self.database_path, config=config,
                               model_port=port, verifier_port=port,
                               meta_port=port,
                               tool_port=RegistryToolPort(self.registry) if self.registry else None,
                               event_observer=observe) as harness:
                run = harness.solve(problem, {"run_id": run_id, "user_hint": solver_hint})
                run = advance_product(harness, run, problem)
                math = run["state"]
                reviewed = math["status"] == "completed_llm_reviewed"
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
                    **mode_identity(self.execution_mode), "run_id": run_id,
                    "execution_mode": self.execution_mode, "evidence_kind": self.evidence_kind,
                    "solver": projection(run),
                    "status": "COMPLETED" if reviewed and verification_mode != "required" else "NEEDS_REVIEW",
                    "stage": math["phase"].lower(),
                    "final_response": export_result(run)["final_response"],
                    "summary": "受限 STAR：探索、润色和新整题审查；不代表完整参考能力",
                    "verification": {"status": "unknown", "findings": [
                        "llm_whole_review_accepted" if reviewed else "whole_review_not_accepted",
                        "not_a_formal_or_complete_proof"]},
                    "request_attempts": attempts,
                    "tool_results": [],
                    "error": None if reviewed and verification_mode != "required" else {"category": "verification_needs_review" if reviewed else "star_needs_review"},
                }
                check_control()
                return result

        builder = StateGraph(dict)
        builder.add_node("star_projection", lambda state: state)
        builder.add_edge(START, "star_projection")
        builder.add_edge("star_projection", END)
        graph = builder.compile(checkpointer=self.checkpointer)
        graph_config = {"configurable": {"thread_id": run_id}}
        # Until SP-08 validates safe stage recovery, never replay an interrupted graph.
        if graph.get_state(graph_config).values:
            raise RuntimeError("star_checkpoint_needs_review")
        result = solve()
        result = graph.invoke(result, graph_config, durability="sync")
        sink({"type": "final_result" if result["status"] == "COMPLETED" else "needs_review",
              "job_id": run_id, "node_name": "terminal", "step_id": "terminal",
              "title": "受限 STAR 已完成" if result["status"] == "COMPLETED" else "受限 STAR 需要复核",
              "message": "star_needs_review", "data": {"type": "text", "summary": result["summary"]}})
        return result


def projection(run):
    state = run["state"]
    return {"run_id": run["run_id"], "state_revision": run["state_revision"],
            "phase": state["phase"], "status": state["status"],
            "config_hash": state["config_hash"], "checkpoint_thread_id": run["run_id"]}
