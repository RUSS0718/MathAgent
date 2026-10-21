"""LangGraph is the sole scheduler for live role execution and safe resume."""

from __future__ import annotations

import time

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .run_control import check_control


def execute_live_graph(pipeline, initial, problem, verification_mode, sink):
    """Adapt the existing role implementations to one checkpointed Run graph."""
    run_id = initial["run_id"]
    started = time.monotonic()
    calls = [0]

    def node(name, action):
        def execute(state):
            check_control()
            initial["active_node"] = name
            state = dict(state)
            state["active_node"] = name
            state.update(action(state))
            check_control()
            return state

        return execute

    def gate(state):
        if pipeline.pause_after_planner:
            interrupt({"category": "waiting_input", "stage": "planned"})
        return {}

    def solver(state):
        candidate, _messages = pipeline._solver(
            run_id, problem.strip(), state["plan"], sink, started, state, calls
        )
        return {"candidate": candidate, "tool_results": state["tool_results"]}

    builder = StateGraph(dict)
    actions = {
        "intake": lambda state: {
            "stage": "planning",
            "input_length": len(pipeline._intake(run_id, problem, sink)),
        },
        "planner": lambda state: {
            "plan": pipeline._planner(run_id, problem.strip(), sink, started, calls)
        },
        "input_gate": gate,
        "solver": solver,
        "verifier": lambda state: {
            "verification": pipeline._verifier(
                run_id, state["candidate"], state["tool_results"], verification_mode, sink, started
            )
        },
        "synthesizer": lambda state: {
            "final_response": pipeline._synthesizer(
                run_id,
                problem.strip(),
                state["plan"],
                state["candidate"],
                state["verification"],
                sink,
                started,
                calls,
            )
        },
    }
    previous = START
    for name, action in actions.items():
        builder.add_node(name, node(name, action))
        builder.add_edge(previous, name)
        previous = name
    builder.add_edge(previous, END)
    if pipeline.checkpointer is None:
        pipeline.checkpointer = InMemorySaver()
    graph = builder.compile(checkpointer=pipeline.checkpointer)
    config = {"configurable": {"thread_id": run_id}}
    existing = graph.get_state(config)
    if existing.values:
        if not existing.interrupts:
            from .live_pipeline import PipelineFailure

            raise PipelineFailure(
                "checkpoint_needs_review", "该 checkpoint 不能安全自动重放", review=True
            )
        result = graph.invoke(Command(resume=True), config, durability="sync")
    else:
        result = graph.invoke(initial, config, durability="sync")
    if result.get("__interrupt__"):
        result = {**result, "status": "WAITING_INPUT", "stage": "planned"}
        result.pop("__interrupt__", None)
    return result
