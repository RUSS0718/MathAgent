"""Pure domain contracts for independent S03 problem specifications."""

import unittest

from showcase.solver_harness.obligation_evidence import (
    collect_obligation_evidence,
    update_obligation_ledger,
)
from showcase.solver_harness.specification import (
    bind_plan_work_units,
    normalize_problem_spec,
    normalize_work_units,
    prerequisites_satisfied,
    root_obligation_count,
    validate_evidence_category,
)


def sample_spec(**updates):
    value = {
        "specification_version": 4,
        "original_problem": "  Find every integer n satisfying n² = 1.\nGive the full set.  ",
        "domain": "integers",
        "quantifiers": ["for every integer n"],
        "assumptions": ["n is an integer"],
        "directions": ["necessary", "sufficient"],
        "output_requirements": ["list every solution", "explain completeness"],
        "root_obligations": [
            {
                "obligation_id": "root:necessary",
                "obligation_type": "Universal",
                "statement": "Every solution satisfies n = 1 or n = -1.",
            },
            {
                "obligation_id": "root:sufficient",
                "obligation_type": "universal",
                "statement": "Both listed values satisfy the equation.",
            },
        ],
        "auxiliary_goals": [{"goal_id": "aux:factor", "description": "Factor n² - 1."}],
    }
    value.update(updates)
    return value


class ProblemSpecificationTest(unittest.TestCase):
    def test_preserves_original_problem_and_normalizes_specification_fields(self):
        original = sample_spec()["original_problem"]
        spec = normalize_problem_spec(sample_spec())

        self.assertEqual(original, spec["original_problem"])
        self.assertEqual(4, spec["specification_version"])
        self.assertEqual("integers", spec["domain"])
        self.assertEqual(["for every integer n"], spec["quantifiers"])
        self.assertEqual(["n is an integer"], spec["assumptions"])
        self.assertEqual(["necessary", "sufficient"], spec["directions"])
        self.assertEqual(["list every solution", "explain completeness"],
                         spec["output_requirements"])
        self.assertEqual("universal", spec["root_obligations"][0]["obligation_type"])

    def test_rejects_missing_or_invalid_specification_version(self):
        for version in (None, 0, -1, True, "4"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    normalize_problem_spec(sample_spec(specification_version=version))

    def test_requires_a_nonempty_original_problem_without_rewriting_it(self):
        with self.assertRaises(ValueError):
            normalize_problem_spec(sample_spec(original_problem=" \n "))

    def test_generates_stable_root_ids_from_normalized_obligation_content(self):
        obligation = {"obligation_type": "Extremum Bound", "statement": "f(x) >= 0"}
        first = normalize_problem_spec(sample_spec(root_obligations=[obligation]))
        second = normalize_problem_spec(sample_spec(root_obligations=[
            {"statement": "f(x) >= 0", "obligation_type": "extremum_bound"}
        ]))

        self.assertEqual(first["root_obligations"][0]["obligation_id"],
                         second["root_obligations"][0]["obligation_id"])
        self.assertTrue(first["root_obligations"][0]["obligation_id"].startswith("root:"))
        self.assertEqual("extremum_bound", first["root_obligations"][0]["obligation_type"])

    def test_rejects_duplicate_root_ids_including_duplicate_generated_ids(self):
        duplicate = {"obligation_type": "format", "statement": "Use exact form."}
        with self.assertRaises(ValueError):
            normalize_problem_spec(sample_spec(root_obligations=[duplicate, duplicate]))

        roots = sample_spec()["root_obligations"]
        roots[1]["obligation_id"] = roots[0]["obligation_id"]
        with self.assertRaises(ValueError):
            normalize_problem_spec(sample_spec(root_obligations=roots))

    def test_progress_denominator_counts_roots_and_excludes_auxiliary_goals(self):
        spec = normalize_problem_spec(sample_spec())

        self.assertEqual(2, root_obligation_count(spec))
        self.assertEqual(1, len(spec["auxiliary_goals"]))

    def test_normalizes_many_to_many_work_unit_mappings(self):
        spec = normalize_problem_spec(sample_spec())
        roots = [item["obligation_id"] for item in spec["root_obligations"]]
        units = normalize_work_units([
            {"work_unit_id": "derive", "obligation_ids": roots},
            {"work_unit_id": "verify", "obligation_ids": roots},
        ], spec["root_obligations"])

        self.assertEqual(2, root_obligation_count(spec))
        self.assertEqual(roots, units[0]["obligation_ids"])
        self.assertEqual(roots, units[1]["obligation_ids"])

    def test_splitting_work_units_does_not_change_root_denominator(self):
        spec = normalize_problem_spec(sample_spec())
        roots = [item["obligation_id"] for item in spec["root_obligations"]]
        normalize_work_units([
            {"work_unit_id": "necessary", "obligation_ids": [roots[0]]},
            {"work_unit_id": "sufficient", "obligation_ids": [roots[1]]},
        ], spec["root_obligations"])

        self.assertEqual(2, root_obligation_count(spec))

    def test_rejects_work_units_with_unknown_roots_or_uncovered_roots(self):
        spec = normalize_problem_spec(sample_spec())
        roots = [item["obligation_id"] for item in spec["root_obligations"]]
        with self.assertRaises(ValueError):
            normalize_work_units([
                {"work_unit_id": "bad", "obligation_ids": ["root:missing"]}
            ], spec["root_obligations"])
        with self.assertRaises(ValueError):
            normalize_work_units([
                {"work_unit_id": "partial", "obligation_ids": [roots[0]]}
            ], spec["root_obligations"])

    def test_work_unit_prerequisites_are_an_and_condition(self):
        units = normalize_work_units([
            {"work_unit_id": "left", "obligation_ids": ["root:left"]},
            {"work_unit_id": "right", "obligation_ids": ["root:right"]},
            {"work_unit_id": "join", "obligation_ids": ["root:left", "root:right"],
             "prerequisites": ["left", "right"]},
        ], [
            {"obligation_id": "root:left"},
            {"obligation_id": "root:right"},
        ])

        self.assertFalse(prerequisites_satisfied(units[2], {"left"}))
        self.assertTrue(prerequisites_satisfied(units[2], {"left", "right"}))
        self.assertTrue(prerequisites_satisfied(units[0], set()))

    def test_problem_spec_rejects_cyclic_root_prerequisites(self):
        with self.assertRaisesRegex(ValueError, "acyclic"):
            normalize_problem_spec(sample_spec(root_obligations=[
                {"obligation_id": "root:left", "obligation_type": "universal",
                 "statement": "Left.", "prerequisite_ids": ["root:right"]},
                {"obligation_id": "root:right", "obligation_type": "universal",
                 "statement": "Right.", "prerequisite_ids": ["root:left"]},
            ]))

    def test_rejects_unknown_and_self_work_unit_prerequisites(self):
        roots = [{"obligation_id": "root:one"}]
        for prerequisites in (["missing"], ["unit"]):
            with self.subTest(prerequisites=prerequisites):
                with self.assertRaises(ValueError):
                    normalize_work_units([
                        {"work_unit_id": "unit", "obligation_ids": ["root:one"],
                         "prerequisites": prerequisites}
                    ], roots)

    def test_accepts_matching_evidence_categories(self):
        spec = normalize_problem_spec(sample_spec())

        validate_evidence_category(spec, "root:necessary", "universal_proof")
        validate_evidence_category(spec, "root:sufficient", "universal_proof")

    def test_rejects_evidence_category_that_does_not_match_obligation_type(self):
        spec = normalize_problem_spec(sample_spec())

        with self.assertRaises(ValueError):
            validate_evidence_category(spec, "root:necessary", "existence_witness")
        with self.assertRaises(ValueError):
            validate_evidence_category(spec, "root:necessary", "reasoner_claim")

    def test_rejects_evidence_for_non_root_or_unknown_obligation(self):
        spec = normalize_problem_spec(sample_spec())

        with self.assertRaises(ValueError):
            validate_evidence_category(spec, "aux:factor", "universal_proof")
        with self.assertRaises(ValueError):
            validate_evidence_category(spec, "root:unknown", "universal_proof")

    def test_collects_reviewer_evidence_and_keeps_uncovered_root_open(self):
        spec = normalize_problem_spec(sample_spec())
        report = {"claims": [{"statement": "necessary proof"}]}
        evidence, rejected = collect_obligation_evidence(
            spec,
            [{"obligation_id": "root:necessary", "evidence_category": "universal_proof",
              "claim_indexes": [0]}],
            report=report,
            run_id="run-1",
            review_call_id="review-1",
            state_revision=7,
            work_unit_id="derive",
            work_unit_obligation_ids=["root:necessary"],
            plan_version=2,
            attempt_index=0,
        )
        ledger = update_obligation_ledger(spec, [], evidence)

        self.assertEqual([], rejected)
        self.assertEqual("satisfied", ledger[0]["status"])
        self.assertEqual("open", ledger[1]["status"])
        self.assertEqual("review-1", evidence[0]["review_call_id"])

    def test_rejects_candidate_number_or_wrong_evidence_as_root_coverage(self):
        spec = normalize_problem_spec(sample_spec())
        evidence, rejected = collect_obligation_evidence(
            spec,
            [
                {"obligation_id": "root:necessary", "evidence_category": "existence_witness",
                 "claim_indexes": [0]},
                {"obligation_id": "root:sufficient", "evidence_category": "universal_proof",
                 "claim_indexes": []},
            ],
            report={"claims": [{"statement": "2"}]},
            run_id="run-1",
            review_call_id="review-1",
            state_revision=7,
            work_unit_id="derive",
            work_unit_obligation_ids=["root:necessary", "root:sufficient"],
            plan_version=1,
            attempt_index=0,
        )

        self.assertEqual([], evidence)
        self.assertEqual({"evidence_category_mismatch", "invalid_report_source"},
                         {item["reason"] for item in rejected})

    def test_extremum_bound_does_not_cover_attainment(self):
        spec = normalize_problem_spec(sample_spec(root_obligations=[
            {"obligation_id": "root:bound", "obligation_type": "extremum_bound",
             "statement": "f(x) is at most 4."},
            {"obligation_id": "root:attainment", "obligation_type": "extremum_attainment",
             "statement": "Some x attains 4."},
        ]))
        evidence, rejected = collect_obligation_evidence(
            spec,
            [{"obligation_id": "root:bound", "evidence_category": "upper_bound_proof",
              "claim_indexes": [0]}],
            report={"claims": [{"statement": "f(x) <= 4 for all x"}]},
            run_id="run-2",
            review_call_id="bound-review", work_unit_id="bound",
            work_unit_obligation_ids=["root:bound"], plan_version=1,
            state_revision=11,
            attempt_index=0,
        )
        ledger = update_obligation_ledger(spec, [], evidence)

        self.assertEqual([], rejected)
        self.assertEqual("satisfied", ledger[0]["status"])
        self.assertEqual("open", ledger[1]["status"])
        self.assertEqual(2, root_obligation_count(spec))

    def test_pell_multi_requirement_progress_ignores_auxiliary_and_work_unit_counts(self):
        spec = normalize_problem_spec({
            "specification_version": 1, "original_problem": "List Pell solutions below B.",
            "domain": "positive integer pairs", "quantifiers": ["for all solutions in range"],
            "assumptions": ["the bound B is fixed"], "directions": ["complete enumeration"],
            "output_requirements": ["filter by parity", "use ordered pairs"],
            "root_obligations": [
                {"obligation_id": "root:list", "obligation_type": "enumeration", "statement": "List all."},
                {"obligation_id": "root:complete", "obligation_type": "completeness", "statement": "No omissions."},
                {"obligation_id": "root:filter", "obligation_type": "filtering", "statement": "Apply parity."},
                {"obligation_id": "root:format", "obligation_type": "format", "statement": "Use ordered pairs."},
            ],
            "auxiliary_goals": [{"goal_id": "aux:recurrence", "description": "derive recurrence"}],
        })
        plan, units = bind_plan_work_units({"version": 1, "steps": [
            {"step_id": "derive", "title": "derive", "objective": "derive list",
             "obligation_ids": ["root:list", "root:complete"], "auxiliary_goal_ids": ["aux:recurrence"]},
            {"step_id": "filter", "title": "filter", "objective": "filter values",
             "obligation_ids": ["root:filter"], "depends_on": ["derive"]},
            {"step_id": "format", "title": "format", "objective": "format output",
             "obligation_ids": ["root:format"]},
        ]}, spec)

        self.assertEqual(4, root_obligation_count(spec))
        self.assertEqual(3, len(units))
        self.assertEqual(3, len(plan["steps"]))
        self.assertEqual(["derive"], units[1]["prerequisites"])
        self.assertEqual(4, len({item for unit in units for item in unit["obligation_ids"]}))


if __name__ == "__main__":
    unittest.main()
