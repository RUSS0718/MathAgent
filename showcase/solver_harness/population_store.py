"""Atomic ownership, route snapshots, action reservations and late settlement."""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy
from datetime import UTC, datetime

from .storage import _SOLVER_STORAGE_LOCK, _json


class PopulationConflict(ValueError):
    """A route action is stale, duplicated, or outside the frozen policy."""


def initial_population():
    return {
        "schema_version": "population-v1", "owner": None, "epoch": 0,
        "routes": {}, "actions": {}, "round": 0, "round_members": [],
        "opportunities": [], "rating": None, "delivery": {"status": "pending"},
        "settlement": {"status": "settled"}, "freeze": None,
    }


def command(harness, run_id, operation, **args):
    """Apply one population transition with owner checks and a single SQLite CAS."""
    connection = harness._state_store._connection
    observer_payload = None
    with _SOLVER_STORAGE_LOCK:
        if connection.in_transaction:
            raise PopulationConflict("population_transaction_nested")
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state_json,problem_hash,config_hash,state_revision FROM solver_states WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise PopulationConflict("population_run_missing")
            state = json.loads(row["state_json"])
            population = deepcopy(state.get("population"))
            if not isinstance(population, dict) or state.get("population_policy", {}).get("enabled") is not True:
                raise PopulationConflict("population_policy_missing")
            event, updates = _transition(
                connection, state, population, operation, args,
                owner_token=deepcopy(harness._population_owner),
            )
            if not updates and event is None:
                connection.rollback()
                return harness._state_store.get_run(run_id)
            if updates.get("proof_graph") is not None:
                raise PopulationConflict("proof_graph_is_storage_managed")

            candidate = {**state, **updates}
            if ((candidate.get("proof_graph_policy") or {}).get("enabled") is True
                    and event is not None and event.get("type") in {"step_reviewed", "population_evidence_accepted"}):
                from .proof_graph import evolve_proof_graph

                persisted_receipts = {
                    receipt["receipt_id"]: receipt
                    for prior in connection.execute(
                        "SELECT event_json FROM solver_events WHERE run_id=? ORDER BY sequence",
                        (run_id,),
                    )
                    for saved in [json.loads(prior[0])]
                    for receipt in [saved.get("receipt")]
                    if saved.get("type") == "tool_receipt" and isinstance(receipt, dict)
                    and isinstance(receipt.get("receipt_id"), str)
                }
                graph_patch, graph_summary = evolve_proof_graph(candidate, event, persisted_receipts)
                if graph_patch is not None:
                    updates["proof_graph"] = graph_patch
                    event["proof_graph"] = graph_summary
            next_revision = int(row["state_revision"]) + 1
            now = datetime.now(UTC).isoformat()
            state.update(updates)
            state.update(state_revision=next_revision, updated_at=now)
            stored = dict(event or {})
            if operation == "patch":
                stored["event_id"] = f"{stored['event_id']}-{next_revision}"
            elif operation == "route_commit":
                stored["event_id"] = f"population-{stored['action_id']}-{stored['event_id']}"
            stored.update(run_id=run_id, state_revision=next_revision, created_at=now)
            digest = hashlib.sha256(_canonical({"event": stored, "updates": updates}).encode()).hexdigest()
            stored["_request_hash"] = digest
            connection.execute(
                "UPDATE solver_states SET state_json=?,state_revision=?,updated_at=? WHERE run_id=? AND state_revision=?",
                (_json(state), next_revision, now, run_id, row["state_revision"]),
            )
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence),0)+1 FROM solver_events WHERE run_id=?", (run_id,),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO solver_events(run_id,sequence,event_id,state_revision,event_json,created_at) VALUES(?,?,?,?,?,?)",
                (run_id, sequence, stored["event_id"], next_revision, _json(stored), now),
            )
            connection.commit()
            result = harness._state_store.get_run(run_id)
            observer_payload = (result, {key: value for key, value in stored.items() if key != "_request_hash"})
        except BaseException:
            connection.rollback()
            raise
    if observer_payload is not None and harness._event_observer is not None:
        harness._event_observer(*observer_payload)
    return observer_payload[0] if observer_payload else harness._state_store.get_run(run_id)


def _transition(connection, state, population, operation, args, *, owner_token):
    owner = population.get("owner")
    run_id = state["run_id"]
    if operation not in {"outcome", "claim", "physical_settlement"}:
        from ..run_control import RunStopped
        from .product_control import controlled_patch

        probe_event = {"event_id": f"population-control-{operation}", "type": f"population_{operation}"}
        try:
            controlled_patch(connection, run_id, probe_event, {"population": population})
        except RunStopped:
            if not (operation == "patch" and state.get("phase") == "TERMINAL"
                    and set(args.get("updates", {})) <= {"delivery", "settlement", "last_observed_at"}):
                raise
    if operation == "claim":
        owner_id = args["owner_id"]
        takeover = args.get("takeover") is True
        if owner and owner.get("id") == owner_id and not takeover:
            return None, {}
        if owner and not takeover:
            raise PopulationConflict("population_already_owned")
        epoch = int(population.get("epoch", 0)) + 1
        population["epoch"] = epoch
        population["owner"] = {"id": owner_id, "epoch": epoch}
        if takeover:
            for action in population["actions"].values():
                if action.get("status") == "inflight":
                    action.update(status="unknown", unknown_since_epoch=epoch)
                    resource_use = _action_cost(connection, run_id, action["action_id"], action)
                    action["resource_use"] = resource_use
                    action["settlement_status"] = (
                        "pending" if resource_use.get("settlement_pending") else "settled"
                    )
                    if action["settlement_status"] == "settled":
                        _release_unused_holds(connection, run_id, action["action_id"])
                    route = population["routes"].get(action.get("route_id"), {})
                    route["status"] = "unknown"
            population["settlement"] = _settlement_summary(population)
        return _event("population_owner_claimed", epoch=epoch), {"population": population}

    if operation == "outcome":
        action = population["actions"].get(args["action_id"])
        if action is None:
            raise PopulationConflict("population_action_missing")
        status = args["status"]
        if status not in {"completed", "unknown", "failed"}:
            raise PopulationConflict("population_outcome_invalid")
        stale_owner = action.get("owner") != owner or action.get("epoch") != (owner or {}).get("epoch")
        if stale_owner and action.get("status") == "unknown":
            action["physical_outcome"] = status
            resource_use = _action_cost(connection, run_id, action["action_id"], action)
            action["resource_use"] = resource_use
            action["settlement_status"] = (
                "pending" if resource_use.get("settlement_pending") else "settled"
            )
            if action["settlement_status"] == "settled":
                _release_unused_holds(connection, run_id, action["action_id"])
            population["actions"][action["action_id"]] = action
            population["settlement"] = _settlement_summary(population)
            return _event("population_stale_physical_outcome", action_id=action["action_id"],
                          outcome=status), {"population": population}
        if action.get("status") == status:
            return None, {}
        action.update(status=status, completed_at=datetime.now(UTC).isoformat())
        action["late_of_terminal"] = state.get("phase") == "TERMINAL"
        action["resource_use"] = _action_cost(connection, run_id, action["action_id"], action)
        action["settlement_status"] = (
            "pending" if action["resource_use"].get("settlement_pending") else "settled"
        )
        if status in {"completed", "failed"}:
            _release_unused_holds(connection, run_id, action["action_id"])
        route = population["routes"].get(action["route_id"])
        if route is not None and not action["late_of_terminal"] and population.get("freeze") is None:
            route["status"] = {"completed": "pending_commit", "unknown": "unknown", "failed": "stalled"}[status]
        population["settlement"] = _settlement_summary(population)
        return _event("population_action_settled", action_id=action["action_id"], outcome=status,
                      late_of_terminal=action["late_of_terminal"]), {"population": population}

    if operation == "physical_settlement":
        action = population["actions"].get(args["action_id"])
        if action is None or action.get("status") != "unknown":
            return None, {}
        resource_use = _action_cost(connection, run_id, action["action_id"], action)
        if resource_use.get("settlement_pending"):
            return None, {}
        if action.get("settlement_status") == "settled":
            return None, {}
        _release_unused_holds(connection, run_id, action["action_id"])
        action["settlement_status"] = "settled"
        action["resource_use"] = resource_use
        action["physically_settled_at"] = datetime.now(UTC).isoformat()
        population["actions"][action["action_id"]] = action
        population["settlement"] = _settlement_summary(population)
        return _event("population_physical_settlement", action_id=action["action_id"]), {
            "population": population,
        }

    if operation == "execution_intent":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        return _event("execution_switch_intent", **args["projection"]), {
            "execution_switch": deepcopy(args["projection"])}

    if operation == "execution_checkpoint":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if state["state_revision"] != args["expected_revision"]:
            return None, {}
        switch = deepcopy(state["execution_switch"])
        if switch["status"] == "switched":
            return None, {}
        actions = list(population["actions"].values())
        calls = list(state.get("calls", {}).values())
        unknown = (any(a.get("status") == "unknown" for a in actions)
                   or any(c.get("status") == "unknown_outcome" for c in calls))
        pending = (any(a.get("status") == "inflight" or a.get("settlement_status") == "pending"
                       or (a.get("status") == "completed" and not a.get("accepted")) for a in actions)
                   or any(c.get("status") in {"dispatched", "streaming"} for c in calls))
        if unknown or pending:
            switch["status"] = "needs_review" if unknown else "converging"
            if switch == state["execution_switch"]:
                return None, {}
            return _event("execution_switch_blocked"), {"execution_switch": switch,
                **({"status": "interrupted"} if unknown else {})}
        from .population_evidence import validate_dependencies

        candidates = [r for r in population["routes"].values()
                      if r.get("status") in {"eligible", "active"}
                      and r.get("snapshot", {}).get("phase") == "STEP_EXECUTE"
                      and r["snapshot"].get("current_step")
                      and r["snapshot"].get("specification_version") == state.get("specification_version")
                      and validate_dependencies(state, r.get("dependencies", []))[0]]
        if not candidates:
            switch["status"] = "rejected"
            switch["reason"] = "no_current_serial_checkpoint"
            return _event("execution_switch_rejected"), {"execution_switch": switch}
        from .population_schedule import round_schedule

        ranking = round_schedule({**population, "round_members": [], "opportunities": []})["order"]
        selected = next((rid for rid in ranking if rid in {r["route_id"] for r in candidates}),
                        candidates[0]["route_id"])
        switch.update(status="switched", current_mode=switch["target"],
                      checkpoint_revision=state["state_revision"] + 1)
        history = [*state.get("execution_switch_history", []), deepcopy(switch)]
        checkpoint = {"revision": switch["checkpoint_revision"], "route_id": selected,
                      "route_revision": population["routes"][selected]["revision"],
                      "specification_version": state.get("specification_version"),
                      "config_hash": state.get("config_hash"),
                      "source_revision": state["state_revision"],
                      "snapshot_hash": hashlib.sha256(_canonical(population["routes"][selected]["snapshot"]).encode()).hexdigest()}
        return _event("execution_switched", **switch), {
            "execution_switch": switch, "execution_switch_history": history,
            "serial_checkpoint": checkpoint if switch["target"] == "serial" else None,
            "serial_checkpoint_snapshot": deepcopy(population["routes"][selected]["snapshot"])
                if switch["target"] == "serial" else None,
            "execution_serial_route": selected if switch["target"] == "serial" else None,
            "phase": "POPULATION", "status": "running"}

    if operation == "patch":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        updates = deepcopy(args.get("updates", {}))
        terminal = state.get("phase") == "TERMINAL"
        allowed = {"round", "round_members", "opportunities", "order", "rating", "paused_reason",
                   "last_observed_at", "freeze", "delivery", "settlement", "cancelled_at",
                   "closing_reserve"}
        if not isinstance(updates, dict) or set(updates) - allowed:
            raise PopulationConflict("population_patch_invalid")
        if terminal and set(updates) - {"delivery", "settlement", "last_observed_at"}:
            raise PopulationConflict("population_terminal_frozen")
        if all(population.get(key) == value for key, value in updates.items()):
            return None, {}
        if "rating" in updates:
            rating = updates["rating"]
            history = population.setdefault("rating_history", [])
            entry = {"round": updates.get("round", population.get("round", 0)),
                     "rating": deepcopy(rating)}
            if not history or history[-1] != entry:
                history.append(entry)
        population.update(updates)
        return _event("population_updated", changed=sorted(updates)), {"population": population}

    if operation == "register_route":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        route_id, digest = args["route_id"], args["frontier_digest"]
        existing = population["routes"].get(route_id)
        if existing is not None:
            if (existing.get("frontier_digest") == digest
                    and existing.get("snapshot") == args.get("snapshot")):
                return None, {}
            raise PopulationConflict("population_route_identity_conflict")
        if any(item.get("frontier_digest") == digest for item in population["routes"].values()):
            raise PopulationConflict("duplicate_route_frontier")
        parent_route_id = args.get("parent_route_id")
        if parent_route_id is not None and parent_route_id not in population["routes"]:
            raise PopulationConflict("population_parent_route_missing")
        snapshot = deepcopy(args["snapshot"])
        objectives = {item.get("objective") for item in snapshot.get("plan", {}).get("steps", [])
                      if isinstance(item, dict) and isinstance(item.get("objective"), str)}
        prior_objectives = {
            item.get("objective")
            for previous in population["routes"].values()
            for item in previous.get("snapshot", {}).get("plan", {}).get("steps", [])
            if isinstance(item, dict) and isinstance(item.get("objective"), str)
        }
        route = {
            "route_id": route_id, "frontier_digest": digest,
            "parent_route_id": parent_route_id,
            "plan_version": snapshot.get("plan_version"),
            "revision": snapshot.get("state_revision", 0),
            "owner": deepcopy(owner), "snapshot": snapshot, "events": [],
            "dependencies": deepcopy(args.get("dependencies", [])),
            "status": "eligible", "produced": [], "adopted": [], "costs": {},
            "evidence_quality": 0, "novelty": len(objectives - prior_objectives),
            "inflight_action_id": None,
        }
        population["routes"][route_id] = route
        return _event("population_route_registered", route_id=route_id), {"population": population}

    if operation == "admit":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if population.get("freeze") is not None or state.get("phase") == "TERMINAL":
            raise PopulationConflict("population_exploration_frozen")
        if (state.get("execution_switch") or {}).get("status") in {"converging", "needs_review"}:
            raise PopulationConflict("execution_switch_converging")
        if state.get("execution_serial_route") not in {None, args["route_id"]}:
            raise PopulationConflict("execution_serial_route_required")
        route_id, action_id = args["route_id"], args["action_id"]
        existing_action = population["actions"].get(action_id)
        if existing_action is not None:
            if (existing_action.get("route_id") == route_id
                    and existing_action.get("owner") == owner
                    and existing_action.get("reservation") == args.get("reservation")
                    and existing_action.get("dependencies") == args.get("dependencies", [])):
                return None, {}
            raise PopulationConflict("population_action_identity_conflict")
        route = population["routes"].get(route_id)
        if route is None or route.get("status") not in {"eligible", "active", "stalled"}:
            raise PopulationConflict("population_route_not_eligible")
        if route.get("inflight_action_id"):
            raise PopulationConflict("population_route_already_inflight")
        if args.get("adopt_evidence") is True:
            from .population_evidence import prepare_adoption, validate_dependencies

            valid, reason = validate_dependencies(state, args.get("dependencies", []))
            if not valid:
                raise PopulationConflict(reason)
            adoption, dependencies = prepare_adoption(state, route["snapshot"])
            if dependencies != args.get("dependencies", []):
                raise PopulationConflict("population_adoption_changed")
            route["snapshot"].update(adoption)
            route["adopted"] = sorted(set(route.get("adopted", []))
                                      | set(adoption["adopted_result_ids"]))
        if action_id in population["actions"]:
            raise PopulationConflict("population_action_identity_conflict")
        capacity = state["population_policy"].get("capacity", {})
        if capacity.get("status") not in {"verified", "controlled"}:
            raise PopulationConflict("population_capacity_unverified")
        active_http = [item for item in population["actions"].values()
                       if item.get("status") == "inflight"
                       or (item.get("status") == "unknown"
                           and item.get("settlement_status") == "pending")]
        active_workers = [item for item in population["actions"].values()
                          if item.get("status") == "inflight"]
        if (len(active_http) >= capacity.get("max_inflight", 0)
                or len(active_workers) >= capacity.get("worker_slots", 0)):
            raise PopulationConflict("population_capacity_exhausted")
        population["closing_reserve"] = _reserve_budget(
            connection, run_id, action_id, args["reservation"], args["closing_reserve"],
            population.get("closing_reserve", {}), population.get("actions", {}).values(),
        )
        action = {
            "action_id": action_id, "route_id": route_id,
            "status": "inflight", "settlement_status": "pending", "owner": deepcopy(owner),
            "epoch": owner["epoch"], "dependencies": deepcopy(args.get("dependencies", [])),
            "reservation": deepcopy(args["reservation"]),
            "closing_reserve": deepcopy(args["closing_reserve"]),
            "admitted_revision": state["state_revision"] + 1,
            "started_at": datetime.now(UTC).isoformat(), "accepted": False,
        }
        population["actions"][action_id] = action
        population["settlement"] = _settlement_summary(population)
        route.update(status="active", inflight_action_id=action_id,
                     dependencies=deepcopy(args.get("dependencies", [])),
                     owner=deepcopy(owner))
        if route_id not in population.get("opportunities", []):
            population["opportunities"] = [*population.get("opportunities", []), route_id]
        return _event("population_action_admitted", route_id=route_id, action_id=action_id), {"population": population}

    if operation == "retry":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if population.get("freeze") is not None or state.get("phase") == "TERMINAL":
            raise PopulationConflict("population_exploration_frozen")
        retry = args.get("retry_call")
        if not isinstance(retry, dict) or set(retry) != {"call_id", "new_call_id"}:
            raise PopulationConflict("population_retry_identity_invalid")
        old_call = state.get("calls", {}).get(retry["call_id"])
        try:
            valid_id = (isinstance(retry["new_call_id"], str)
                        and str(uuid.UUID(retry["new_call_id"])) == retry["new_call_id"])
        except (ValueError, AttributeError):
            valid_id = False
        if (old_call is None or not valid_id or retry["new_call_id"] in state.get("calls", {})
                or old_call.get("status") not in {"dispatched", "streaming", "unknown_outcome"}):
            raise PopulationConflict("population_retry_identity_invalid")
        action = population["actions"].get(old_call.get("action_id"))
        route = population["routes"].get(old_call.get("route_id"))
        if (action is None or action.get("status") != "unknown" or route is None
                or route.get("status") != "unknown"):
            raise PopulationConflict("population_retry_action_not_unknown")
        route["snapshot"]["authorized_retry"] = {
            "call_id": retry["call_id"], "new_call_id": retry["new_call_id"],
        }
        route["snapshot"]["status"] = "running"
        route["revision"] += 1
        route["snapshot"]["state_revision"] = route["revision"]
        route.update(status="eligible", inflight_action_id=None, owner=deepcopy(owner))
        return _event("population_retry_authorized", route_id=route["route_id"],
                      action_id=action["action_id"], new_call_id=retry["new_call_id"]), {
            "population": population,
        }

    if operation == "route_commit":
        route = population["routes"].get(args["route_id"])
        action = population["actions"].get(args["action_id"])
        if route is None or action is None or action.get("route_id") != route.get("route_id"):
            raise PopulationConflict("population_action_route_mismatch")
        event = deepcopy(args["event"])
        updates = deepcopy(args.get("updates", {}))
        audit_only = (event.get("type") in {"call_audit", "call_activity"}
                      and set(updates) <= {"calls", "status"})
        current_epoch_action = (owner is not None and owner_token == owner
                                and action.get("owner") == owner
                                and action.get("status") == "inflight")
        if not current_epoch_action and not audit_only:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if population.get("freeze") is not None and not audit_only:
            raise PopulationConflict("population_exploration_frozen")
        if route is None or route.get("inflight_action_id") != action["action_id"]:
            if not audit_only:
                raise PopulationConflict("population_action_route_mismatch")
        prior_event = next((item for item in route.get("events", [])
                            if item.get("event_id") == event.get("event_id")
                            and item.get("action_id") == action["action_id"]), None)
        if prior_event is not None:
            if prior_event != {**event, "route_id": route["route_id"],
                               "action_id": action["action_id"], "state_revision": prior_event.get("state_revision") }:
                raise PopulationConflict("population_route_event_conflict")
            return None, {}
        if not audit_only and route.get("revision") != args["expected_route_revision"]:
            raise PopulationConflict("population_route_revision_conflict")
        if {"population", "population_policy", "run_id", "problem_hash", "config_hash"} & updates.keys():
            raise PopulationConflict("population_route_patch_forbidden")
        local_state = deepcopy(route["snapshot"])
        if state.get("phase") == "TERMINAL":
            if event.get("type") not in {"call_audit", "call_activity"} or set(updates) - {"calls"}:
                raise PopulationConflict("population_terminal_frozen")
        if not audit_only:
            from ..run_control import RunStopped
            from .product_control import controlled_patch

            controlled_patch(connection, run_id, event, {"population": population})
        local_state.update(updates)
        local_state["state_revision"] = route["revision"] + 1
        if event.get("type") == "step_reviewed" and local_state.get("phase") == "META_DECIDE":
            plan_steps = local_state.get("plan", {}).get("steps", [])
            reviewed = next((index for index, item in enumerate(plan_steps)
                             if item.get("step_id") == event.get("step_id")), None)
            if reviewed is not None and reviewed + 1 < len(plan_steps):
                local_state["phase"] = "STEP_EXECUTE"
                local_state["current_step"] = plan_steps[reviewed + 1]["step_id"]
            else:
                local_state["phase"] = "FINAL_GENERATE"
                local_state["current_step"] = None
        if (not audit_only and (local_state.get("proof_graph_policy") or {}).get("enabled") is True
                and event.get("type") == "step_reviewed"):
            from .proof_graph import evolve_proof_graph

            receipts = {
                receipt["receipt_id"]: receipt
                for route_event in route.get("events", [])
                for receipt in [route_event.get("receipt")]
                if route_event.get("type") == "tool_receipt" and isinstance(receipt, dict)
                and isinstance(receipt.get("receipt_id"), str)
            }
            if event.get("type") == "tool_receipt" and isinstance(event.get("receipt"), dict):
                receipts[event["receipt"]["receipt_id"]] = event["receipt"]
            graph, _summary = evolve_proof_graph(local_state, event, receipts)
            if graph is not None:
                local_state["proof_graph"] = graph
        route["snapshot"] = local_state
        route["revision"] += 1
        route_event = {**event, "route_id": route["route_id"], "action_id": action["action_id"],
                       "state_revision": route["revision"]}
        route["events"].append(route_event)
        calls = deepcopy(state.get("calls", {}))
        for call_id, call in updates.get("calls", {}).items():
            saved = calls.get(call_id)
            if saved is not None and (saved.get("route_id"), saved.get("action_id")) != (route["route_id"], action["action_id"]):
                historical = {key: value for key, value in saved.items()
                              if key not in {"route_id", "action_id"}}
                if historical != call and saved != call:
                    raise PopulationConflict("population_call_identity_conflict")
                local_state["calls"][call_id] = deepcopy(saved)
                continue
            calls[call_id] = {**deepcopy(call), "route_id": route["route_id"], "action_id": action["action_id"]}
            local_state["calls"][call_id] = deepcopy(calls[call_id])
        population["routes"][route["route_id"]] = route
        event.update(route_id=route["route_id"], action_id=action["action_id"],
                     route_revision=route["revision"])
        return event, {"population": population, "calls": calls}

    if operation == "accept":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        action = population["actions"].get(args["action_id"])
        if action is None or action.get("status") != "completed":
            raise PopulationConflict("population_action_not_completed")
        if action.get("accepted"):
            return None, {}
        if population.get("freeze") is not None or state.get("phase") == "TERMINAL":
            action.update(accepted=True, acceptance_reason="population_frozen")
            population["actions"][action["action_id"]] = action
            return _event("population_late_action_archived", action_id=action["action_id"]), {"population": population}
        route = population["routes"][action["route_id"]]
        # The current owner revalidates a durable receipt without changing its execution owner.
        action["acceptance_owner"] = deepcopy(owner)
        route["acceptance_owner"] = deepcopy(owner)
        from .population_evidence import merge_route_evidence

        deltas, audit = merge_route_evidence(state, route, action, {
            "run_id": run_id, "state": route["snapshot"],
            "events": route["events"], "state_revision": route["revision"],
        })
        if not audit.get("accepted"):
            action.update(accepted=True, acceptance_reason=audit.get("reason"))
            route["snapshot"].pop("authorized_retry", None)
            route.update(status="stalled", inflight_action_id=None)
            population["actions"][action["action_id"]] = action
            population["routes"][route["route_id"]] = route
            return _event("population_action_rejected", action_id=action["action_id"], reason=audit.get("reason")), {"population": population}
        updates = {}
        for key, values in deltas.items():
            if key in {"steps", "plan"}:
                updates[key] = {**state.get(key, {}), **values}
            elif key in {"verified_results_ledger", "obligation_evidence_ledger", "accepted_results"}:
                prior = state.get(key, [])
                if key == "verified_results_ledger":
                    known = {item.get("result_id") for item in prior}
                    values = [item for item in values if item.get("result_id") not in known]
                if key == "obligation_evidence_ledger":
                    known = {item.get("evidence_id") for item in prior}
                    values = [item for item in values if item.get("evidence_id") not in known]
                updates[key] = [*prior, *values]
            else:
                updates[key] = values
        if "obligation_ledger" not in updates and updates.get("obligation_evidence_ledger"):
            from .obligation_evidence import update_obligation_ledger

            updates["obligation_ledger"] = update_obligation_ledger(
                state["problem_spec"], state.get("obligation_ledger", []),
                updates["obligation_evidence_ledger"],
            )
        action.update(accepted=True, merged_result_ids=audit["merged_result_ids"])
        route["snapshot"].pop("authorized_retry", None)
        route["costs"] = _route_costs(population, route["route_id"])
        new_credit = audit.get("merged_obligation_ids", []) or audit["merged_result_ids"]
        route.update(status="eligible", inflight_action_id=None,
                     produced=sorted(set(route.get("produced", [])) | set(new_credit)),
                     evidence_quality=len(set(route.get("produced", [])) | set(new_credit)))
        population["actions"][action["action_id"]] = action
        population["routes"][route["route_id"]] = route
        updates["population"] = population
        source_event = next((item for item in reversed(route["events"])
                             if item.get("event_id") in audit["source_event_ids"]), {})
        event = {**deepcopy(source_event),
                 "event_id": f"population-evidence-accepted-{action['action_id']}",
                 "type": audit.get("type", "step_reviewed"), "route_id": route["route_id"],
                 "action_id": action["action_id"],
                 "source_event_ids": audit["source_event_ids"],
                 "report_call_ids": audit["report_call_ids"],
                 "review_call_ids": audit["review_call_ids"],
                 "merged_result_ids": audit["merged_result_ids"],
                 "merged_obligation_ids": audit.get("merged_obligation_ids", [])}
        return event, updates

    if operation == "review_rejected":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if state.get("state_revision") != args.get("expected_revision"):
            raise PopulationConflict("population_review_revision_conflict")
        if state.get("phase") != "FINAL_GENERATE" or population.get("freeze") is None:
            raise PopulationConflict("population_review_recovery_not_frozen")
        candidate_key = args.get("candidate_key")
        attempts = state.get("final_solution_attempts", [])
        attempt = attempts[-1] if attempts else None
        review = attempt.get("review") if isinstance(attempt, dict) else None
        if (not isinstance(candidate_key, str)
                or not isinstance(attempt, dict)
                or attempt.get("session_key") != candidate_key
                or not isinstance(review, dict)
                or review.get("verdict") != "REJECT"):
            raise PopulationConflict("population_review_candidate_mismatch")

        routes = population.get("routes", {})
        legal_route_ids = set()
        for route_id, route in routes.items():
            snapshot = route.get("snapshot", {})
            current_step = snapshot.get("current_step")
            step_ids = {item.get("step_id") for item in snapshot.get("plan", {}).get("steps", [])
                        if isinstance(item, dict)}
            step = snapshot.get("steps", {}).get(current_step, {})
            verification = step.get("verification", {})
            action_id = route.get("inflight_action_id")
            action = population.get("actions", {}).get(action_id) if action_id else None
            if (route.get("status") == "frozen"
                    and (not action_id or action and action.get("status") == "inflight")
                    and snapshot.get("phase") == "STEP_EXECUTE"
                    and isinstance(current_step, str)
                    and current_step in step_ids
                    and not (verification.get("verdict") == "ACCEPT"
                             and verification.get("valid") is True)):
                legal_route_ids.add(route_id)
        if not legal_route_ids:
            return None, {}

        from .population_recovery import evidence_fingerprint

        evidence_hash = args.get("evidence_hash")
        if evidence_hash != evidence_fingerprint(state):
            raise PopulationConflict("population_review_evidence_changed")
        for route_id, route in routes.items():
            if route.get("status") != "frozen":
                continue
            action_id = route.get("inflight_action_id")
            action = population.get("actions", {}).get(action_id) if action_id else None
            if route_id in legal_route_ids:
                route["status"] = (
                    "unknown" if action and action.get("status") == "unknown"
                    else "active" if action_id else "eligible"
                )
            elif route.get("snapshot", {}).get("phase") == "FINAL_GENERATE" and not action_id:
                route["status"] = "finished"
            elif action_id:
                route["status"] = "unknown" if action and action.get("status") == "unknown" else "active"
            else:
                route["status"] = "stalled"
        population["freeze"] = None
        population["rejected_evidence"] = {
            "candidate_key": candidate_key,
            "evidence_hash": evidence_hash,
            "state_revision": state["state_revision"],
        }
        return _event("population_final_review_rejected", candidate_key=candidate_key,
                      evidence_hash=evidence_hash,
                      restored_routes=sorted(legal_route_ids)), {
            "population": population,
            "phase": "POPULATION",
            "status": "running",
        }

    if operation == "freeze":
        if owner is None or owner_token != owner:
            raise PopulationConflict("population_owner_epoch_mismatch")
        if population.get("freeze") is not None:
            return None, {}
        candidate = deepcopy(args.get("candidate", {}))
        population["freeze"] = {"candidate": candidate, "state_revision": state["state_revision"] + 1,
                                "frozen_at": datetime.now(UTC).isoformat(),
                                "pending_actions": sorted(
                                    item["action_id"] for item in population["actions"].values()
                                    if item.get("status") in {"inflight", "unknown"}
                                )}
        for route in population["routes"].values():
            if route.get("status") in {"eligible", "active", "stalled"}:
                route["status"] = "frozen"
        population["round_members"] = []
        return _event("population_frozen", frozen_revision=state["state_revision"] + 1), {"population": population}

    raise PopulationConflict("population_operation_unknown")


def _reserve_budget(connection, run_id, action_id, reservation, closing, prior_floor, active_actions):
    row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise PopulationConflict("population_shared_budget_unavailable")
    from ..run_budget import _summary

    ledger = json.loads(row[0])
    summary = _summary(ledger)
    expected = reservation.get("calls")
    if not isinstance(expected, list) or not expected:
        raise PopulationConflict("population_work_reservation_invalid")
    closing = _max_resources(prior_floor or {}, closing or {})
    needed_calls = len(expected) + closing.get("model_calls", 0)
    needed_http = sum(call.get("http_attempts", 1) for call in expected) + closing.get("http_attempts", 0)
    needed_tokens = sum(
        (call.get("input_estimate", 0) + call.get("output_cap", 0)) * call.get("http_attempts", 1)
        for call in expected
    ) + closing.get("tokens", 0)
    needed_tools = reservation.get("tool_calls", 0) + closing.get("tool_calls", 0)
    active_time = max((item.get("reservation", {}).get("time_seconds", 0)
                       for item in active_actions
                       if item.get("status") in {"inflight", "unknown"}), default=0)
    requested_time = max(active_time, reservation.get("time_seconds", 0)) + closing.get("time_seconds", 0)
    limits = ledger["limits"]
    if (summary["logical_calls"] + needed_calls > limits["max_model_calls"]
            or summary["http_attempts"] + needed_http > limits["max_http_attempts"]
            or summary["charged_tokens"] + needed_tokens > limits["max_tokens"]
            or summary["tool_calls"] + needed_tools > limits["max_tool_calls"]
            or time_remaining(ledger) < requested_time):
        raise PopulationConflict("population_closing_reserve_unavailable")
    for call_index, call in enumerate(expected):
        logical_id = f"population:{action_id}:logical:{call_index}"
        ledger["actions"].append({
            "id": logical_id, "kind": "logical", "logical_call_id": logical_id,
            "solver_call_id": None, "role": call["role"], "tool_call_id": None,
            "input_estimate": 0, "output_cap": 0,
            "population_action_id": action_id, "status": "pre_reserved",
            "usage": _empty_usage(),
        })
        for attempt in range(call.get("http_attempts", 1)):
            hold_id = f"population:{action_id}:http:{call_index}:{attempt}"
            ledger["actions"].append({
                "id": hold_id, "kind": "http", "logical_call_id": logical_id,
                "solver_call_id": None, "role": call["role"], "tool_call_id": None,
                "input_estimate": call["input_estimate"], "output_cap": call["output_cap"],
                "population_action_id": action_id, "status": "pre_reserved",
                "usage": _empty_usage(),
            })
    for tool_index in range(reservation.get("tool_calls", 0)):
        ledger["actions"].append({
            "id": f"population:{action_id}:tool:{tool_index}", "kind": "tool",
            "logical_call_id": None, "solver_call_id": None, "role": "*",
            "tool_call_id": None, "input_estimate": 0, "output_cap": 0,
            "population_action_id": action_id, "status": "pre_reserved",
            "usage": _empty_usage(),
        })
    connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?", (_canonical(ledger), run_id))
    return closing


def _max_resources(left, right):
    return {key: max(left.get(key, 0), right.get(key, 0))
            for key in {"model_calls", "http_attempts", "tokens", "tool_calls", "time_seconds"}}


def _release_unused_holds(connection, run_id, action_id):
    row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return
    raw = row[0]
    ledger = json.loads(raw)
    ledger["actions"] = [item for item in ledger["actions"]
                         if not (item.get("population_action_id") == action_id
                                 and item.get("status") == "pre_reserved")]
    connection.execute("UPDATE run_budgets SET ledger_json=? WHERE run_id=?", (_canonical(ledger), run_id))


def _empty_usage():
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


def _action_cost(connection, run_id, action_id, action):
    row = connection.execute("SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        return {"tokens": None, "http_attempts": None, "tool_calls": None,
                "time_seconds": None, "cost_known": False, "settlement_pending": True}
    ledger = json.loads(row[0])
    attempts = [item for item in ledger["actions"]
                if item.get("population_action_id") == action_id
                and item.get("kind") == "http" and item.get("status") != "pre_reserved"]
    tools = [item for item in ledger["actions"]
             if item.get("population_action_id") == action_id
             and item.get("kind") == "tool" and item.get("status") != "pre_reserved"]
    pending = any((item.get("status") in {"reserved", "pending", "unknown"}
                   or (item.get("status") == "error"
                       and any(item.get("usage", {}).get(key) is None
                               for key in ("prompt_tokens", "completion_tokens", "total_tokens"))))
                  for item in ledger["actions"]
                  if item.get("population_action_id") == action_id
                  and item.get("kind") in {"http", "tool"})
    usage_fields = ("prompt_tokens", "completion_tokens", "total_tokens")
    known = bool(attempts) and all(all(type(item.get("usage", {}).get(key)) is int
                                       for key in usage_fields) for item in attempts)
    return {
        "tokens": sum(item["usage"]["total_tokens"] for item in attempts) if known else None,
        "http_attempts": len(attempts), "tool_calls": len(tools),
        "time_seconds": max(0.0, _parse_time(action.get("completed_at"))
                            - _parse_time(action.get("started_at"))),
        "cost_known": known,
        "settlement_pending": pending,
    }


def _route_costs(population, route_id):
    completed = [item for item in population["actions"].values()
                 if item.get("route_id") == route_id and item.get("status") == "completed"]
    metrics = [item.get("resource_use", {}) for item in completed]
    if not metrics:
        return {"tokens": None, "http_attempts": 0, "tool_calls": 0,
                "time_seconds": 0, "cost_known": False}
    return {
        "tokens": (sum(item["tokens"] for item in metrics)
                   if all(type(item.get("tokens")) is int for item in metrics) else None),
        "http_attempts": sum(item.get("http_attempts", 0) for item in metrics),
        "tool_calls": sum(item.get("tool_calls", 0) for item in metrics),
        "time_seconds": sum(item.get("time_seconds", 0) for item in metrics),
        "cost_known": all(item.get("cost_known") is True for item in metrics),
    }


def _settlement_summary(population):
    actions = list(population.get("actions", {}).values())
    pending = sum(item.get("settlement_status") == "pending" for item in actions)
    unknown = sum(item.get("status") == "unknown" for item in actions)
    return {"status": "pending" if pending else "settled",
            "unknown_count": unknown, "pending_count": pending}


def _parse_time(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0.0


def time_remaining(ledger):
    import time

    return max(0.0, ledger["deadline_at"] - time.time())


def _event(kind, **values):
    return {"event_id": f"population-{kind}-{hashlib.sha256(_canonical(values).encode()).hexdigest()[:20]}",
            "type": kind, **values}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
