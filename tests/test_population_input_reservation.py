"""Actual HTTP input growth preserves sibling holds, closing floors and ownership."""

import unittest

from showcase.run_budget import BudgetExhausted, bind_budget
from showcase.solver_harness.population_budget import bind_population_action
from showcase.solver_harness.population_store import command
from tests import test_population_store as fixture

RUN_ID = fixture.RUN_ID


class PopulationInputReservationTest(unittest.TestCase):
    setUp = fixture.PopulationStoreTests.setUp
    tearDown = fixture.PopulationStoreTests.tearDown
    _admit = fixture.PopulationStoreTests._admit

    def claim(self):
        self._admit()
        self.enterContext(bind_budget(self.budget))
        self.enterContext(bind_population_action("action-a", self.harness._population_owner))
        return self.budget.model_call("reasoner", solver_call_id="actual-reasoner")

    def dispatch(self, call, input_size, *, output_cap=10):
        return call.before_attempt({"attempt_id": "actual-http", "max_tokens": output_cap,
                                   "role": "reasoner"}, input_size)

    def assert_unchanged(self, before):
        after = self.budget.snapshot()
        for key in ("logical_calls", "http_attempts", "charged_tokens", "reserved_tokens",
                    "local_input_estimate", "deadline_at"):
            self.assertEqual(before[key], after[key], key)
        self.assertEqual([], self.ledger.attempts(RUN_ID))

    def test_exact_input_can_grow_to_original_root_minus_closing_floor(self):
        call = self.claim()
        deadline = self.budget.snapshot()["deadline_at"]
        self.assertGreater(self.dispatch(call, 70), 0)
        summary = self.budget.snapshot()
        self.assertEqual((1, 1, 80, 70), (summary["logical_calls"], summary["http_attempts"],
                                         summary["charged_tokens"], summary["local_input_estimate"]))
        self.assertEqual(deadline, summary["deadline_at"])
        self.assertEqual("actual-http", self.ledger.attempts(RUN_ID)[0]["attempt_id"])

    def test_growth_cannot_consume_the_closing_floor(self):
        call = self.claim()
        before = self.budget.snapshot()
        with self.assertRaises(BudgetExhausted):
            self.dispatch(call, 71)
        self.assert_unchanged(before)

    def test_growth_cannot_consume_another_actions_http_hold(self):
        snapshot = self.run["state"]["population"]["routes"]["route-a"]["snapshot"]
        command(self.harness, RUN_ID, "register_route", route_id="route-b",
                frontier_digest="frontier-b", snapshot=snapshot)
        command(self.harness, RUN_ID, "admit", route_id="route-b", action_id="action-b",
                reservation={"calls": [{"role": "reasoner", "input_estimate": 20,
                                         "output_cap": 10, "http_attempts": 1}],
                             "time_seconds": 2},
                closing_reserve={"tokens": 20, "time_seconds": 1}, dependencies=[])
        call = self.claim()
        before = self.budget.snapshot()
        with self.assertRaises(BudgetExhausted):
            self.dispatch(call, 41)
        self.assert_unchanged(before)
        self.assertGreater(self.dispatch(call, 40), 0)
        self.assertEqual(80, self.budget.snapshot()["charged_tokens"])

    def test_growth_preserves_the_admitted_output_cap(self):
        call = self.claim()
        before = self.budget.snapshot()
        with self.assertRaisesRegex(BudgetExhausted, "finalization_reservation_too_small"):
            self.dispatch(call, 40, output_cap=11)
        self.assert_unchanged(before)

    def test_growth_cannot_dispatch_after_answer_freeze(self):
        call = self.claim()
        command(self.harness, RUN_ID, "freeze", candidate={"text_hash": "frozen"})
        before = self.budget.snapshot()
        with self.assertRaisesRegex(BudgetExhausted, "population_exploration_frozen"):
            self.dispatch(call, 40)
        self.assert_unchanged(before)

    def test_growth_cannot_dispatch_from_a_stale_owner(self):
        call = self.claim()
        command(self.harness, RUN_ID, "claim", owner_id="replacement", takeover=True)
        before = self.budget.snapshot()
        with self.assertRaisesRegex(BudgetExhausted, "population_owner_epoch_mismatch"):
            self.dispatch(call, 40)
        self.assert_unchanged(before)
