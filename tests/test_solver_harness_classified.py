"""Controller verification of classified outcomes and ledger compatibility."""

import unittest

from showcase.solver_harness.classified import (
    build_entries,
    declarations,
    outcome_counts,
)
from showcase.solver_harness.finalize import valid_facts
from showcase.star_product_summary import progress_summary

REVIEW = "run:step-verifier:1:s2"
SUFFIX = ""


def state(*, steps=None, accepted=None, ledger=None, receipts=None):
    return {
        "steps": steps if steps is not None else {
            "s1": {"verification": {"valid": True, "verdict": "ACCEPT"}},
        },
        "accepted_results": accepted or [],
        "verified_results_ledger": ledger or [],
        "tool_receipts": receipts or [],
    }


def outcome(category="Lemma", statement="A forward direction holds", scope="boundary case",
            **extra):
    return {"category": category, "statement": statement, "scope": scope, **extra}


class BuildEntriesTest(unittest.TestCase):
    def test_valid_lemma_anchors_to_report_and_dependencies(self):
        reply = {"classified_outcomes": [
            outcome(claim_indexes=[0], dependencies=["s1"]),
            outcome(statement="Second result", claim_indexes=[], dependencies=["s2:outcome-1"]),
        ]}
        entries, rejections = build_entries(
            state(), reply, step_id="s2", report={"claims": [{"statement": "claim"}]},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual([], rejections)
        self.assertEqual(["s2:outcome-1", "s2:outcome-2"],
                         [entry["result_id"] for entry in entries])
        self.assertEqual([REVIEW, REVIEW], [entry["review_call_id"] for entry in entries])
        self.assertEqual([["s1"], ["s2:outcome-1"]],
                         [entry["dependencies"] for entry in entries])
        self.assertEqual(["llm_reviewed", "llm_reviewed"],
                         [entry["evidence_level"] for entry in entries])
        self.assertTrue(all(entry["proven"] and not entry["invalidated"]
                            for entry in entries))

    def test_unknown_category_statement_and_scope_are_rejected(self):
        reply = {"classified_outcomes": [
            outcome(category="Theorem"),
            outcome(statement="   "),
            outcome(scope=""),
            {},
        ]}
        entries, rejections = build_entries(
            state(), reply, step_id="s2", report={"claims": []},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual([], entries)
        self.assertEqual(["unknown_category", "missing_statement", "missing_scope",
                          "unknown_category"],
                         [item["reason"] for item in rejections])

    def test_report_source_must_reference_existing_claims(self):
        reply = {"classified_outcomes": [
            outcome(claim_indexes=[0]),
            outcome(claim_indexes=[1]),
            outcome(claim_indexes=[-1]),
            outcome(claim_indexes="all"),
        ]}
        entries, rejections = build_entries(
            state(), reply, step_id="s2", report={"claims": [{"statement": "claim"}]},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual(["s2:outcome-1"], [entry["result_id"] for entry in entries])
        self.assertEqual(["invalid_report_source"] * 3,
                         [item["reason"] for item in rejections])

    def test_forged_or_unexecuted_receipts_are_rejected(self):
        receipts = [{"receipt_id": "tool:r:5:0", "executed": True, "status": "success"},
                    {"receipt_id": "tool:r:6:0", "executed": False, "status": "not_executed"},
                    {"receipt_id": "tool:r:7:0", "executed": True, "status": "timeout"}]
        reply = {"classified_outcomes": [
            outcome(category="Computation", receipt_ids=["tool:r:5:0"]),
            outcome(category="Computation", receipt_ids=["tool:forged"]),
            outcome(category="Computation", receipt_ids=["tool:r:6:0"]),
            outcome(category="Computation", receipt_ids=["tool:r:7:0"]),
        ]}
        entries, rejections = build_entries(
            state(receipts=receipts), reply, step_id="s2", report={"claims": []},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual(["s2:outcome-1"], [entry["result_id"] for entry in entries])
        self.assertEqual("tool_verified", entries[0]["evidence_level"])
        self.assertEqual(["unverified_tool_receipt"] * 3,
                         [item["reason"] for item in rejections])

    def test_computation_without_any_real_receipt_is_rejected(self):
        reply = {"classified_outcomes": [outcome(category="Computation")]}
        entries, rejections = build_entries(
            state(), reply, step_id="s2", report={"claims": []},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual([], entries)
        self.assertEqual(["unsupported_computation"], [item["reason"] for item in rejections])

    def test_unknown_stale_cyclic_and_forward_dependencies_are_rejected(self):
        ledger = [{"result_id": "old:outcome-1", "category": "Lemma", "invalidated": True},
                  {"result_id": "old:outcome-2", "category": "Conjecture"}]
        reply = {"classified_outcomes": [
            outcome(dependencies=["s1"]),
            outcome(dependencies=["s2:outcome-2"]),
            outcome(dependencies=["s2:outcome-1"]),
            outcome(dependencies=["ghost"]),
            outcome(dependencies=["old:outcome-1"]),
            outcome(dependencies=["old:outcome-2"]),
        ]}
        entries, rejections = build_entries(
            state(ledger=ledger), reply, step_id="s2", report={"claims": []},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual(["s2:outcome-1", "s2:outcome-2"],
                         [entry["result_id"] for entry in entries])
        self.assertEqual([["s1"], ["s2:outcome-1"]],
                         [entry["dependencies"] for entry in entries])
        self.assertEqual(["cyclic_dependency", "unknown_dependency", "unknown_dependency",
                          "unknown_dependency"],
                         [item["reason"] for item in rejections])

    def test_step_ids_of_unaccepted_steps_are_not_established_dependencies(self):
        steps = {"s1": {"verification": {"valid": True, "verdict": "ACCEPT"}},
                 "s2": {"verification": {"valid": True, "verdict": "CHALLENGE"}}}
        reply = {"classified_outcomes": [outcome(dependencies=["s2"])]}
        entries, rejections = build_entries(
            state(steps=steps), reply, step_id="s3", report={"claims": []},
            review_call_id=REVIEW, suffix=SUFFIX, plan_version=1, attempt_index=0)
        self.assertEqual([], entries)
        self.assertEqual(["unknown_dependency"], [item["reason"] for item in rejections])

    def test_suffixes_keep_identities_unique_across_re_reviews(self):
        reply = {"classified_outcomes": [outcome()]}
        first, _ = build_entries(state(), reply, step_id="s2", report={"claims": []},
                                 review_call_id=REVIEW, suffix="", plan_version=1,
                                 attempt_index=0)
        second, _ = build_entries(state(), reply, step_id="s2", report={"claims": []},
                                  review_call_id=REVIEW, suffix="-challenge-1",
                                  plan_version=1, attempt_index=0)
        third, _ = build_entries(state(), reply, step_id="s2", report={"claims": []},
                                 review_call_id=REVIEW, suffix="-attempt-1",
                                 plan_version=1, attempt_index=1)
        self.assertEqual(["s2:outcome-1"], [entry["result_id"] for entry in first])
        self.assertEqual(["s2:outcome-1-challenge-1"], [entry["result_id"] for entry in second])
        self.assertEqual(["s2:outcome-1-attempt-1"], [entry["result_id"] for entry in third])

    def test_declarations_ignores_absent_and_malformed_payloads(self):
        self.assertEqual([], declarations(None))
        self.assertEqual([], declarations({}))
        self.assertEqual([], declarations({"classified_outcomes": "all of it"}))
        self.assertEqual([], declarations({"classified_outcomes": ["nope", 7]}))
        self.assertEqual(1, len(declarations({"classified_outcomes": [outcome()]})))

    def test_outcome_counts_preserve_category_order(self):
        entries = [{"category": "Lemma"}, {"category": "Conjecture"}, {"category": "Lemma"}]
        self.assertEqual({"Lemma": 2, "Conjecture": 1}, outcome_counts(entries))


class LedgerCompatibilityTest(unittest.TestCase):
    def test_valid_facts_merge_proven_ledger_entries_and_exclude_conjectures(self):
        ledger = [
            {"result_id": "s2:outcome-1", "category": "Lemma", "statement": "proven lemma",
             "scope": "boundary", "source": "s2", "evidence_level": "llm_reviewed",
             "dependencies": ["s1"], "proven": True},
            {"result_id": "s2:outcome-2", "category": "Conjecture", "statement": "open guess",
             "scope": "whole", "source": "s2", "evidence_level": "conjecture",
             "dependencies": [], "proven": False},
            {"result_id": "s2:outcome-3", "category": "Lemma", "statement": "dead lemma",
             "scope": "boundary", "source": "s2", "evidence_level": "llm_reviewed",
             "dependencies": [], "proven": True, "invalidated": True},
        ]
        facts = valid_facts({"plan": {"steps": [
            {"step_id": "s1", "objective": "o"}]},
            "steps": {"s1": {"verification": {"valid": True, "verdict": "ACCEPT"}}},
            "accepted_results": [],
            "verified_results_ledger": ledger})
        self.assertEqual(["proven lemma"], [fact["statement"] for fact in facts])

    def test_old_records_without_types_or_sources_are_never_fabricated(self):
        # A historical Run has no ledger and accepted records without identity
        # or classification; reading and projection must not invent either.
        historical = {
            "plan": {"steps": [{"step_id": "s1", "objective": "o"}]},
            "steps": {"s1": {"verification": {"valid": True, "verdict": "ACCEPT"}}},
            "accepted_results": [{"category": "step_result", "statement": "old fact",
                                  "source": "s1", "evidence_level": "llm_reviewed",
                                  "dependencies": []}],
            "verified_results_ledger": [],
        }
        summary = progress_summary(historical)
        self.assertEqual([], summary["classified_results"])
        self.assertEqual(["old fact"], [fact["statement"] for fact in valid_facts(historical)])
        # Even a hand-written legacy ledger row without category, identity or
        # evidence level stays inert: it is never upgraded into a classified
        # proven outcome and never becomes a final-synthesis premise.
        legacy = {**historical, "verified_results_ledger": [
            {"statement": "legacy row", "source": "s1"}]}
        summary = progress_summary(legacy)
        self.assertEqual([], summary["classified_results"])
        self.assertEqual(["old fact"], [fact["statement"] for fact in valid_facts(legacy)])

    def test_progress_summary_redacts_scope_and_hashes_statements(self):
        import hashlib
        import unicodedata
        state = {"plan": {}, "steps": {}, "accepted_results": [], "failure_records": [],
                 "verified_results_ledger": [
                     {"result_id": "s1:outcome-1", "category": "Lemma",
                      "statement": "a lemma", "scope": "token: abc",
                      "evidence_level": "llm_reviewed", "proven": True}]}
        entries = progress_summary(state)["classified_results"]
        self.assertEqual(1, len(entries))
        self.assertEqual("Lemma", entries[0]["category"])
        self.assertTrue(entries[0]["proven"])
        self.assertFalse(entries[0]["invalidated"])
        self.assertNotIn("abc", entries[0]["scope"])
        canonical = unicodedata.normalize("NFC", "a lemma".replace("\r\n", "\n"))
        self.assertEqual(hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                         entries[0]["statement_digest"])
        self.assertNotIn("a lemma", str(entries))


if __name__ == "__main__":
    unittest.main()
