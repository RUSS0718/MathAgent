"""Claim only this native arm's persistent parent-ledger reservations."""

import json
import time
from uuid import uuid4

from ..run_budget import BudgetExhausted, public_solver_call_id
from .faithful_intervention_records import FaithfulInterventionError


class NativeArmLedger:
    """Fence paused-parent dispatch and settlement by pair, arm and reservation."""

    def __init__(self, ledger, report, arm, gate):
        self._parent = ledger
        self.run_id = report["run_id"]
        self.pair_id = report["pair_id"]
        self.role = report["budget_reservation"]["arm_roles"][arm]
        self.branch_id = report["arms"][arm]["branch_id"]
        self.report, self.gate = report, gate
        self.connection = ledger.connection
        self.attempts_per_call = (report["budget_reservation"]["http_attempts"]
                                  // report["budget_reservation"]["logical_calls"])

    def stream_timeout_policy(self, run_id):
        if run_id != self.run_id:
            raise FaithfulInterventionError("intervention_cross_arm_access")
        return self._parent.stream_timeout_policy(run_id)

    def snapshot(self, run_id):
        """Expose consumed arm resources to native admission, excluding future holds."""
        from ..run_budget import _summary

        if run_id != self.run_id:
            raise FaithfulInterventionError("intervention_cross_arm_access")
        state = json.loads(self._parent._read_row(run_id)[0])
        state.pop("intervention_resources", None)
        reserved = self.report["budget_reservation"]
        state["actions"] = [item for item in state["actions"]
                            if item.get("reservation_id") == self.pair_id
                            and item.get("role") == self.role and item["status"] != "pre_reserved"]
        state["limits"] = {**state["limits"],
                           "max_model_calls": reserved["logical_calls"] // 2,
                           "max_http_attempts": reserved["http_attempts"] // 2,
                           "max_tokens": reserved["token_ceiling"] // 2,
                           "max_tool_calls": reserved.get("tool_calls", 0) // 2}
        state["deadline_at"] = min(state["deadline_at"], getattr(self, "deadline_at", state["deadline_at"]))
        return _summary(state)

    def _check(self, run_id, state):
        if run_id != self.run_id:
            raise FaithfulInterventionError("intervention_cross_arm_access")
        self.gate.assert_paused(connection=self.connection, job_id=self.report["job_id"],
                                run_id=run_id, checkpoint_revision=self.report["checkpoint_revision"])
        if time.time() >= min(state["deadline_at"], getattr(self, "deadline_at", state["deadline_at"])):
            raise BudgetExhausted("run_deadline_exhausted")

    def claim_native_call(self, run_id, role, solver_call_id=None):
        with self._parent._transaction(run_id) as state:
            self._check(run_id, state)
            held = next((item for item in state["actions"]
                         if item.get("reservation_id") == self.pair_id
                         and item.get("role") == self.role and item["kind"] == "logical"
                         and item["status"] == "pre_reserved"), None)
            if held is None:
                return None
            held.update(status="reserved", solver_call_id=solver_call_id, native_role=role)
            return held["id"]

    def reserve(self, run_id, kind, **kwargs):
        if kind not in {"http", "tool"}:
            raise BudgetExhausted("intervention_reservation_required")
        with self._parent._transaction(run_id) as state:
            self._check(run_id, state)
            held = next((item for item in state["actions"]
                         if item.get("reservation_id") == self.pair_id
                         and item.get("role") == self.role and item["kind"] == kind
                         and item["status"] == "pre_reserved"
                         and (kind == "tool" or item.get("logical_call_id") == kwargs.get("logical_call_id"))), None)
            if held is None:
                raise BudgetExhausted("intervention_arm_reservation_exhausted")
            if (kwargs.get("input_estimate", 0) > held["input_estimate"]
                    or kwargs.get("output_cap", 0) > held["output_cap"]):
                raise BudgetExhausted("intervention_reservation_too_small")
            action_id = kwargs.get("attempt_id") or f"{self.branch_id}:tool:{uuid4().hex}"
            if any(item["id"] == action_id for item in state["actions"]):
                raise BudgetExhausted("intervention_attempt_identity_conflict")
            held.update(id=action_id, status="reserved", tool_call_id=kwargs.get("tool_call_id"),
                        solver_call_id=kwargs.get("solver_call_id"))
            if kind == "http":
                logical = next(item for item in state["actions"]
                               if item["id"] == kwargs.get("logical_call_id"))
                held["native_role"] = logical.get("native_role")
                held["solver_call_id"] = logical.get("solver_call_id")
            event = kwargs.get("attempt_event")
            if event is not None:
                from llm_response import public_attempt

                held["public_attempt"] = {
                    **public_attempt(event, run_id=run_id, role=self.role),
                    "solver_call_id": public_solver_call_id(run_id, held.get("solver_call_id")),
                    "started_at_utc": event.get("started_at_utc"),
                    "dispatch_status": "reserved_dispatch_unconfirmed",
                }
            return action_id, max(0.001, min(state["deadline_at"], getattr(
                self, "deadline_at", state["deadline_at"])) - time.time())

    def settle(self, run_id, action_id, event):
        if run_id != self.run_id:
            raise FaithfulInterventionError("intervention_cross_arm_settlement")
        row = json.loads(self._parent._read_row(run_id)[0])
        if not any(item["id"] == action_id and item.get("role") == self.role
                   and item.get("reservation_id") == self.pair_id for item in row["actions"]):
            raise FaithfulInterventionError("intervention_cross_arm_settlement")
        return self._parent.settle(run_id, action_id, event)


def native_arm_budget(ledger, report, arm, gate):
    """Create a budget whose slots and original deadline remain parent-owned."""
    from .faithful_intervention_execution import ArmBudget

    if report["budget_reservation"].get("time_seconds", 0) <= 0:
        raise FaithfulInterventionError("native_time_reservation_required")
    proxy = NativeArmLedger(ledger, report, arm, gate)
    budget = ArmBudget(proxy, report["run_id"], proxy.role)
    seconds = report["budget_reservation"].get("time_seconds", 0) / 2
    if seconds:
        budget.deadline_at = min(budget.absolute_deadline(), time.time() + seconds)
        proxy.deadline_at = budget.deadline_at
    return budget
