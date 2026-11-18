"""Current proof receipts stay authoritative without decoding unrelated audit rows."""

import json
import sys
import unittest
from unittest.mock import patch

from showcase.solver_harness import SolverHarness
from showcase.solver_harness.proof_graph import evolve_proof_graph
from showcase.solver_harness.storage import SolverPersistenceError


class SolverReceiptScanTest(unittest.TestCase):
    def test_public_commit_skips_unrelated_receipt_scan_decodes(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve("question", {"run_id": "receipt-scan"})
            for index in range(12):
                run = harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": f"noise-{index}", "type": "call_activity",
                           "scan_marker": "unrelated-history"},
                )
            loads = json.loads
            unrelated = []

            def counted(value, *args, **kwargs):
                caller = sys._getframe(1)
                while caller is not None:
                    if (caller.f_code.co_name == "commit_event"
                            and caller.f_code.co_filename.replace("\\", "/").endswith("solver_harness/storage.py")):
                        if "unrelated-history" in value:
                            unrelated.append(value)
                        break
                    caller = caller.f_back
                return loads(value, *args, **kwargs)

            with patch("showcase.solver_harness.storage.json.loads", side_effect=counted):
                saved = harness.commit_event(
                    run["run_id"], expected_revision=run["state_revision"],
                    event={"event_id": "save-progress", "type": "call_activity"},
                )
            self.assertEqual(0, len(unrelated), "receipt discovery decoded unrelated audit history")
            self.assertEqual(len(run["events"]) + 1, len(saved["events"]))
            self.assertEqual(saved["events"], harness.get_run(run["run_id"])["events"])

    def test_candidate_filter_keeps_python_last_key_and_receipt_order(self):
        with SolverHarness(config={"features": {"proof_graph": True}}) as harness:
            run = harness.solve("question", {"run_id": "receipt-semantics"})
            other = harness.solve("other", {"run_id": "other-receipts"})
            connection = harness._showcase_store._connection

            def insert(target, suffix, fields):
                raw = ('{"run_id":' + json.dumps(target["run_id"])
                       + ',"event_id":' + json.dumps(suffix) + ',' + fields + '}')
                connection.execute(
                    "INSERT INTO solver_events VALUES (?, (SELECT COALESCE(MAX(sequence),0)+1 "
                    "FROM solver_events WHERE run_id=?), ?, ?, ?, ?)",
                    (target["run_id"], target["run_id"], suffix,
                     target["state_revision"], raw, target["state"]["updated_at"]),
                )
                connection.commit()

            insert(run, "first", '"type":"tool_receipt","receipt":{"receipt_id":"r","value":1}')
            insert(run, "last-type", '"type":"call_activity","type":"tool_receipt",'
                   '"receipt":{"receipt_id":"ignored","receipt_id":"r","value":2}')
            insert(run, "not-receipt", '"type":"tool_receipt","type":"call_activity",'
                   '"receipt":{"receipt_id":"r","value":99}')
            insert(run, "escaped", '"t\\u0079pe":"tool_receipt",'
                   '"receipt":{"receipt_id":"escaped","value":3}')
            insert(run, "shape", '"type":"tool_receipt","receipt":[]')
            insert(run, "wrong-type", '"type":12,"receipt":{"receipt_id":"bad"}')
            insert(other, "foreign", '"type":"tool_receipt","receipt":{"receipt_id":"r","value":99}')
            seen = []

            def capture(state, event, receipts):
                seen.append(receipts)
                return evolve_proof_graph(state, event, receipts)

            def commit(suffix):
                current = harness.get_run(run["run_id"])
                with patch("showcase.solver_harness.proof_graph.evolve_proof_graph", side_effect=capture):
                    return harness.commit_event(
                        run["run_id"], expected_revision=current["state_revision"],
                        event={"event_id": suffix, "type": "call_activity"},
                    )

            saved = commit("observe-current")
            self.assertEqual({"r": {"receipt_id": "r", "value": 2},
                              "escaped": {"receipt_id": "escaped", "value": 3}}, seen[-1])
            # Same revision edits must be read again, never served from a cache.
            connection.execute("DELETE FROM solver_events WHERE run_id=? AND event_id IN ('first','last-type')",
                               (run["run_id"],))
            connection.execute("UPDATE solver_events SET event_json=replace(event_json, '\"value\":3', '\"value\":4') "
                               "WHERE run_id=? AND event_id='escaped'", (run["run_id"],))
            connection.commit()
            commit("observe-edited")
            self.assertEqual({"escaped": {"receipt_id": "escaped", "value": 4}}, seen[-1])
            self.assertGreater(len(saved["events"]), 1)

    def test_malformed_and_nonobject_rows_still_fail_inside_commit(self):
        for raw in ('{"broken":', '[]', 'null', '1', '"text"'):
            with self.subTest(raw=raw), SolverHarness(config={"features": {"proof_graph": True}}) as harness:
                run = harness.solve("question", {"run_id": "invalid-receipt-event"})
                connection = harness._showcase_store._connection
                connection.execute("UPDATE solver_events SET event_json=? WHERE run_id=? AND sequence=1",
                                   (raw, run["run_id"]))
                connection.commit()
                # A pre-existing validated projection must not hide current DB corruption.
                with self.assertRaises((SolverPersistenceError, AttributeError)):
                    harness._state_store.commit_event(
                        run["run_id"], expected_revision=run["state_revision"],
                        event={"event_id": "cannot-hide-corruption", "type": "call_activity"},
                        state_updates={}, request_hash="public-corruption-witness", validated_run=run,
                    )
                self.assertEqual(run["state_revision"], connection.execute(
                    "SELECT state_revision FROM solver_states WHERE run_id=?", (run["run_id"],)
                ).fetchone()[0])


if __name__ == "__main__":
    unittest.main()
