"""A clarification preceding a route must not poison later graph refreshes."""

import unittest
from copy import deepcopy

from showcase.solver_harness.route_graph_refresh import refreshed_routes
from showcase.solver_harness.routes import (
    register_route,
    transition_route,
    validate_route_state_patch,
)


class RouteSpecificationRefreshTest(unittest.TestCase):
    def state(self):
        state = {"problem_spec": {"specification_version": 2},
                 "failure_records": [{"kind": "problem_spec_change",
                                      "from_specification_version": 1,
                                      "to_specification_version": 2}],
                 "proof_graph": {"current_version": 2, "snapshots": [
                     {"graph_version": 1},
                     {"graph_version": 2, "not_imported_records": [
                         {"reason": "conjecture_not_importable", "source_id": "new"}]}]}}
        state.update(register_route(state, frontier=[{"goal": "a"}], graph_version=1))
        state["route_registry"][0].update(status="active", needs_reevaluation=True)
        return state

    def test_clarification_before_route_allows_additive_refresh(self):
        state = self.state()
        self.assertEqual(2, state["route_registry"][0].get("specification_version"))
        refreshed = refreshed_routes(state)
        self.assertIsNotNone(refreshed)
        self.assertFalse(refreshed[0]["needs_reevaluation"])
        self.assertTrue(state["route_registry"][0]["needs_reevaluation"])
        self.assertEqual("conjecture_not_importable", state["proof_graph"]["snapshots"][-1]
                         ["not_imported_records"][0]["reason"])

    def test_stale_legacy_and_conflicting_routes_remain_blocked(self):
        for mode in ("stale", "legacy", "conflict"):
            with self.subTest(mode=mode):
                state = self.state()
                if mode == "stale":
                    state["problem_spec"]["specification_version"] = 3
                elif mode == "legacy":
                    state["route_registry"][0].pop("specification_version", None)
                else:
                    state["proof_graph"]["snapshots"][-1]["propositions"] = {
                        "p": {"status": "refuted"}}
                self.assertIsNone(refreshed_routes(state))

    def test_persisted_binding_cannot_be_changed_removed_or_backfilled(self):
        for mode in ("changed", "removed", "backfilled", "boolean", "float"):
            with self.subTest(mode=mode):
                state = self.state()
                if mode == "backfilled":
                    state["route_registry"][0].pop("specification_version", None)
                elif mode == "boolean":
                    state["route_registry"][0]["specification_version"] = 1
                routes = deepcopy(state["route_registry"])
                if mode == "removed":
                    routes[0].pop("specification_version", None)
                elif mode == "boolean":
                    routes[0]["specification_version"] = True
                elif mode == "float":
                    routes[0]["specification_version"] = 2.0
                else:
                    routes[0]["specification_version"] = 3
                with self.assertRaisesRegex(ValueError, "route_identity_rewrite"):
                    validate_route_state_patch(state, {}, {"route_registry": routes,
                        "route_lineage": [*state["route_lineage"], {"event": "test_transition"}]},
                        authorized=True)

    def test_current_binding_survives_validated_registration_and_transition(self):
        state = {"problem_spec": {"specification_version": 2}}
        patch = register_route(state, frontier=[{"goal": "a"}], graph_version=1)
        validate_route_state_patch(state, {}, patch, authorized=True)
        state.update(patch)
        patch = transition_route(state, state["active_route_id"], "active")
        validate_route_state_patch(state, {}, patch, authorized=True)
        self.assertEqual(2, patch["route_registry"][0]["specification_version"])

    def test_legacy_route_without_specification_changes_still_refreshes(self):
        state = self.state()
        state["route_registry"][0].pop("specification_version")
        state["failure_records"] = []
        refreshed = refreshed_routes(state)
        self.assertIsNotNone(refreshed)
        self.assertNotIn("specification_version", refreshed[0])
        self.assertFalse(refreshed[0]["needs_reevaluation"])

    def test_new_route_binding_must_match_current_specification(self):
        state = {"problem_spec": {"specification_version": 2}}
        for version in (None, 1, True):
            with self.subTest(version=version):
                patch = register_route(state, frontier=[{"goal": "a"}], graph_version=1)
                if version is None:
                    patch["route_registry"][0].pop("specification_version", None)
                else:
                    patch["route_registry"][0]["specification_version"] = version
                with self.assertRaisesRegex(ValueError, "route_specification_version_invalid"):
                    validate_route_state_patch(state, {}, patch, authorized=True)
