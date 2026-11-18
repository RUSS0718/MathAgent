"""Finite representation compatibility preserves unreviewed raw specifications."""

import unittest
from copy import deepcopy

from showcase.formal_specification import build_specification_records, canonical_identity
from showcase.solver_harness.formal_generation import select_formalization

# Minimal saved assessment fixture; no database or provider response is needed.
CHINESE_SPEC = {
    "assumptions": [], "auxiliary_goals": [], "directions": ["equality"],
    "domain": "有理数", "original_problem": "证明：对任意有理数 x，x+x=2*x。",
    "output_requirements": ["证明"], "quantifiers": ["∀x ∈ ℚ"],
    "root_obligations": [{"direction": "equality", "obligation_id": "O1",
        "obligation_type": "universal", "statement": "对任意有理数 x，x + x = 2 * x"}],
    "specification_version": 1,
}
RATIONAL_TARGET = {
    "assumptions": [], "direction": "equality", "domain": "rationals",
    "lhs": "x + x", "quantifiers": ["forall x"], "rhs": "2 * x", "variables": ["x"],
}
SPEC_HASH = "b3bbd02da1f058039ba461d1999f10bc2bd0bd50f35965daf753305b28807868"
PROBLEM_HASH = "dded72a43e8eb1dcf15ea9729f59e3a132b803a64b826f721d045adf2c283475"


class FormalSpecificationTest(unittest.TestCase):
    def test_chinese_records_preserve_spec_identity_and_unreviewed_scope(self):
        spec = deepcopy(CHINESE_SPEC)
        records = build_specification_records(spec["original_problem"], spec, RATIONAL_TARGET)
        self.assertEqual(CHINESE_SPEC, spec)
        self.assertEqual(SPEC_HASH, canonical_identity(spec))
        original = records["original_to_spec"]
        self.assertEqual(PROBLEM_HASH, original["original_problem_hash"])
        self.assertEqual(SPEC_HASH, original["problem_spec_hash"])
        self.assertEqual("有理数", original["scope"])
        self.assertEqual(spec["root_obligations"], original["root_obligations"])
        self.assertEqual(SPEC_HASH, records["spec_to_target"]["problem_spec_hash"])
        for record in records.values():
            self.assertEqual("not_reviewed", record["review_status"])
            self.assertIsNone(record["review_record_hash"])

    def test_finite_aliases_bind_to_the_same_normalized_single_variable(self):
        for variable in ("x", "y_1"):
            target = {**RATIONAL_TARGET, "variables": [variable],
                "quantifiers": [f"forall {variable}"], "lhs": f"{variable} + {variable}",
                "rhs": f"2 * {variable}"}
            for domain in ("rationals", "rational", "rational numbers", "有理数", " RATIONALS "):
                for quantifier in (f"forall {variable}", f"∀{variable} ∈ ℚ"):
                    with self.subTest(variable=variable, domain=domain, quantifier=quantifier):
                        spec = {**deepcopy(CHINESE_SPEC), "domain": domain,
                                "quantifiers": [quantifier]}
                        before = deepcopy(spec)
                        selected = select_formalization({"status": "proposed",
                            "obligation_ids": ["O1"], "target": target}, spec, "intake:1")
                        self.assertEqual("proposed", selected["status"])
                        records = build_specification_records(spec["original_problem"], spec, target)
                        self.assertEqual(canonical_identity(before),
                                         records["original_to_spec"]["problem_spec_hash"])
                        self.assertEqual(before, spec)

    def test_incompatible_specs_fail_closed_at_both_boundaries(self):
        changes = (
            *({"domain": domain} for domain in ("reals", "integers", "实数", "整数",
                "positive rationals", "正有理数", "有理数或实数", "ℚ+")),
            *({"quantifiers": quantifiers} for quantifiers in (
                ["exists x"], ["∃x ∈ ℚ"], ["∀x ∈ ℝ"], ["∀x ∈ ℤ"],
                ["∀x ∈ ℚ, x > 0"], ["∀y ∈ ℚ"], ["forall y"],
                ["∀x,y ∈ ℚ"], ["forall x", "forall y"], [],
                ["for every rational x"], ["∀x ∈ ℚ or x is real"],
            )),
            {"assumptions": ["x > 0"]}, {"directions": ["equality", "necessity"]},
            {"directions": ["inequality"]}, {"directions": []},
        )
        for change in changes:
            with self.subTest(change=change):
                spec = {**deepcopy(CHINESE_SPEC), **change}
                before = deepcopy(spec)
                selected = select_formalization({"status": "proposed",
                    "obligation_ids": ["O1"], "target": RATIONAL_TARGET}, spec, "intake:1")
                self.assertEqual("unsupported", selected["status"])
                self.assertEqual("spec_target_mismatch", selected["reason"])
                self.assertNotIn("target", selected)
                with self.assertRaisesRegex(ValueError, "spec_target_mismatch"):
                    build_specification_records(spec["original_problem"], spec, RATIONAL_TARGET)
                self.assertEqual(before, spec)

    def test_target_restrictions_and_obligation_ids_remain_authoritative(self):
        for change in ({"domain": "reals"}, {"variables": ["x", "y"]},
                       {"quantifiers": ["exists x"]}, {"assumptions": ["x > 0"]},
                       {"direction": "inequality"}, {"lhs": "y + y"}):
            with self.subTest(change=change):
                target = {**RATIONAL_TARGET, **change}
                selected = select_formalization({"status": "proposed",
                    "obligation_ids": ["O1"], "target": target}, CHINESE_SPEC, "intake:1")
                self.assertEqual("unsupported", selected["status"])
                with self.assertRaises(ValueError):
                    build_specification_records(CHINESE_SPEC["original_problem"], CHINESE_SPEC, target)
        selected = select_formalization({"status": "proposed", "obligation_ids": ["missing"],
            "target": RATIONAL_TARGET}, CHINESE_SPEC, "intake:1")
        self.assertEqual("formal_obligations_invalid", selected["reason"])

    def test_chinese_correspondence_stays_unreviewed_and_whole_requirement_unmet(self):
        from showcase.formal_correspondence import check_correspondence
        from showcase.formal_requirements import assess_formal_requirement
        from showcase.formal_specification import normalize_target, public_target

        target = public_target(normalize_target(RATIONAL_TARGET))
        records = build_specification_records(CHINESE_SPEC["original_problem"], CHINESE_SPEC, target)
        audit = check_correspondence(CHINESE_SPEC["original_problem"], CHINESE_SPEC,
                                     target, "attempt:1", "e" * 64)
        self.assertEqual("not_reviewed", audit["status"])
        self.assertEqual("fixed_template_not_matched", audit["reason"])
        self.assertIsNone(audit["reviewer_type"])
        # Synthetic receipt only: even a claimed L3 cannot bypass absent review.
        records["target_to_environment"]["environment_hash"] = "e" * 64
        current = {"attempt_id": "attempt:1", "status": "solved", "specifications": records,
            "proof_artifact": {"accepted": True, "kernel_exit": 0, "cleanup_verified": True,
                               "target_hash": target["hash"], "environment_hash": "e" * 64}}
        for grade in ("L2", "L3"):
            formal = {"current_attempt_id": "attempt:1", "status": "solved", "grade": grade,
                      "current": {**current, "grade": grade}}
            assessment = assess_formal_requirement({"require_formal": True, "target": target},
                                                   formal, CHINESE_SPEC)
            self.assertEqual("unmet", assessment["status"])
            self.assertEqual([], assessment["covered_obligation_ids"])
