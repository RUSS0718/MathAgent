"""Bind existing Harness operations to one durable route snapshot."""

from copy import deepcopy

from .harness import SolverHarness
from .harness_config import SolverValidationError


class RouteHarness(SolverHarness):
    """Reuse step, verifier, challenge and call lifecycle without a second solver."""

    def __init__(self, parent, run_id, route_id, action_id):
        self.__dict__.update(parent.__dict__)
        self._parent = parent
        self._route_run_id = run_id
        self._route_id = route_id
        self._action_id = action_id
        self._product_recovery = True
        self._owns_showcase_store = False

    def get_run(self, run_id, *, problem=None):
        """Read a branch without marking other live workers as abandoned."""
        parent = self._state_store.get_run(run_id)
        route = parent["state"]["population"]["routes"][self._route_id]
        state = deepcopy(route["snapshot"])
        revision = route.get("revision", 0)
        state["state_revision"] = revision
        if parent["state"]["phase"] == "TERMINAL":
            state.update(phase="TERMINAL", status=parent["state"]["status"])
        return {"run_id": run_id, "state": state, "state_revision": revision,
                "events": deepcopy(route.get("events", []))}

    def _commit_event(self, run_id, *, expected_revision, event, state_updates=None,
                      current=None, route_authorized=False):
        """Commit the local revision under the parent's atomic ownership fence."""
        from .population_store import command

        if run_id != self._route_run_id:
            raise SolverValidationError("population_route_run_mismatch")
        from .progress import review_progress

        updates = deepcopy(state_updates or {})
        progress = review_progress(self.get_run(run_id)["state"], event, updates)
        updates.update(progress)
        command(self._parent, run_id, "route_commit", route_id=self._route_id,
                action_id=self._action_id, expected_route_revision=expected_revision,
                event=dict(event), updates=updates)
        return self.get_run(run_id)

    def dispatch(self, run, operation, request):
        """Keep the physical request bound to its already admitted WorkUnit."""
        from .population_budget import bind_population_action

        policy = self._config.get("population_policy", {})
        with bind_population_action(self._action_id, self._population_owner):
            return super().dispatch(run, operation, {
                **request, "route_id": self._route_id, "population_action_id": self._action_id,
                "timeout_seconds": policy.get("request_timeout_seconds"),
                "retry_limit": policy.get("retry_limit", 1),
            })
