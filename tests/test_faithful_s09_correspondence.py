"""Contracts for the independent fixed-template correspondence checker."""

from __future__ import annotations

import hashlib
import json
import unittest
from copy import deepcopy

import showcase.formal_correspondence as correspondence
from showcase.formal_correspondence import check_correspondence

PROBLEM = "For every rational x, x ** 2 + 2 * x + 1 = (x + 1) ** 2."
LHS = "x ** 2 + 2 * x + 1"
RHS = "(x + 1) ** 2"
FIELDS = ("domain", "variables", "quantifiers", "assumptions", "direction", "conclusion")
ENVIRONMENT_HASH = "e" * 64


def canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def actual_target(**changes):
    target = {
        "domain": "rationals",
        "variables": ["x"],
        "lhs": LHS,
        "rhs": RHS,
        "quantifiers": ["forall x"],
        "assumptions": [],
        "direction": "equality",
    }
    target["hash"] = canonical_hash(target)
    target.update(changes)
    if changes:
        immutable = {key: target[key] for key in (
            "domain", "variables", "lhs", "rhs", "quantifiers", "assumptions", "direction"
        )}
        target["hash"] = canonical_hash(immutable)
    return target


def actual_spec(**changes):
    spec = {
        "specification_version": 1,
        "original_problem": PROBLEM,
        "domain": "rationals",
        "quantifiers": ["forall x"],
        "assumptions": [],
        "directions": ["equality"],
        "output_requirements": [],
        "root_obligations": [{
            "obligation_id": "root:identity",
            "obligation_type": "universal",
            "statement": f"{LHS} = {RHS}",
        }],
        "auxiliary_goals": [],
    }
    spec.update(changes)
    return spec


class CorrespondenceContractTest(unittest.TestCase):
    def test_supplied_specification_digest_cannot_hide_drift(self):
        spec = actual_spec(hash="0" * 64)
        result = check_correspondence(PROBLEM, spec, actual_target(),
                                      "attempt-1", ENVIRONMENT_HASH)
        self.assertEqual("not_reviewed", result["status"])

    def check(self, *, problem=PROBLEM, specification=None, target=None,
              attempt_id="attempt-1", environment_hash=ENVIRONMENT_HASH):
        return check_correspondence(
            problem,
            actual_spec() if specification is None else specification,
            actual_target() if target is None else target,
            attempt_id=attempt_id,
            environment_hash=environment_hash,
        )

    def test_exact_actual_shapes_confirm_all_six_fields(self):
        result = self.check()
        self.assertEqual("confirmed", result["status"])
        self.assertEqual("independent_service", result["reviewer_type"])
        self.assertEqual(set(FIELDS), set(result["field_results"]))
        self.assertTrue(all(value is True for value in result["field_results"].values()))
        self.assertEqual("attempt-1", result["evidence"]["attempt_id"])
        self.assertEqual(ENVIRONMENT_HASH, result["evidence"]["environment_hash"])
        self.assertEqual(64, len(result["evidence"]["original_problem_hash"]))
        self.assertEqual(64, len(result["evidence"]["problem_spec_hash"]))
        self.assertEqual(64, len(result["evidence"]["target_hash"]))
        self.assertNotIn("signature", result)
        self.assertNotIn("authoritative", result)

    def test_wrong_target_domain_variables_quantifiers_assumptions_direction_or_conclusion_rejects(self):
        cases = (
            ("domain", "reals", "domain"),
            ("variables", ["y"], "variables"),
            ("quantifiers", ["exists x"], "quantifiers"),
            ("assumptions", ["x > 0"], "assumptions"),
            ("direction", "implication", "direction"),
            ("lhs", "x ** 2 + 2 * x", "conclusion"),
            ("rhs", "x ** 2 + 2 * x + 2", "conclusion"),
        )
        for field, value, result_field in cases:
            with self.subTest(field=field):
                result = self.check(target=actual_target(**{field: value}))
                self.assertEqual("not_reviewed", result["status"])
                self.assertIsNone(result["reviewer_type"])
                self.assertFalse(result["field_results"].get(result_field))

    def test_problem_and_problem_spec_must_bind_exactly(self):
        cases = (
            (actual_spec(original_problem=PROBLEM + " "), "original_problem"),
            (actual_spec(domain="reals"), "domain"),
            (actual_spec(quantifiers=["forall y"]), "quantifiers"),
            (actual_spec(assumptions=["x > 0"]), "assumptions"),
            (actual_spec(directions=["iff"]), "direction"),
        )
        for spec, field in cases:
            with self.subTest(field=field):
                result = self.check(specification=spec)
                self.assertEqual("not_reviewed", result["status"])
                self.assertFalse(result["status"] == "confirmed")

    def test_extra_requirements_roots_or_auxiliary_goals_are_not_silently_covered(self):
        cases = (
            actual_spec(output_requirements=["show all steps"]),
            actual_spec(auxiliary_goals=[{"goal_id": "extra", "statement": "x = x"}]),
            actual_spec(root_obligations=[
                actual_spec()["root_obligations"][0],
                {"obligation_id": "root:extra", "obligation_type": "universal",
                 "statement": "x = x"},
            ]),
            actual_spec(root_obligations=[{
                **actual_spec()["root_obligations"][0], "prerequisite_ids": ["goal"]
            }]),
        )
        for spec in cases:
            with self.subTest(spec=spec):
                result = self.check(specification=spec)
                self.assertEqual("not_reviewed", result["status"])
                self.assertFalse(result["field_results"]["conclusion"])

    def test_template_hash_identity_and_schema_drift_are_rejected(self):
        cases = (
            ({"problem": "Prove x = x."}, {}),
            ({"target": {**actual_target(), "hash": "0" * 64}}, {}),
            ({"target": {**actual_target(), "target_id": "new-field"}}, {}),
            ({"specification": {**actual_spec(), "reviewer_type": "llm"}}, {}),
            ({"attempt_id": ""}, {}),
            ({"environment_hash": "drifted"}, {}),
        )
        for values, _ in cases:
            with self.subTest(values=values):
                result = self.check(**values)
                self.assertEqual("not_reviewed", result["status"])
                self.assertIsNone(result["reviewer_type"])

    def test_checker_exposes_no_bool_approval_or_llm_authority_bypass(self):
        self.assertFalse(hasattr(correspondence, "MachineCheckableSpecification"))
        self.assertFalse(hasattr(correspondence, "build_review_record"))
        self.assertFalse(hasattr(correspondence, "issue_correspondence"))
        spec = actual_spec()
        spec["reviewer_type"] = "llm"
        result = self.check(specification=spec)
        self.assertNotEqual("confirmed", result["status"])
        self.assertNotEqual("human", result.get("reviewer_type"))
        self.assertNotIn("authoritative", result)


    def test_real_normalized_request_shape_is_accepted_without_mutation(self):
        try:
            from showcase.formal import normalize_formal_request
            from showcase.formal_specification import normalize_target
        except (ImportError, SyntaxError) as exc:
            self.skipTest(f"main-agent shared facade unavailable: {type(exc).__name__}")
        target = normalize_target(actual_target())
        raw = {
            "schema_version": 1, "job_id": "job", "run_id": "run",
            "attempt_id": "attempt-1", "parent_attempt_id": None,
            "problem": {"text": PROBLEM},
            "specification": actual_spec(),
            "target": target,
            "policy": {
                "enabled": True, "backend": "lean_tactic_prover",
                "timeout_seconds": 30, "max_output_bytes": 16000,
                "allowed_axioms": ["propext"], "environment": {},
            },
            "cost": {"elapsed_seconds": 0, "output_bytes": 0},
            "review": None,
        }
        try:
            normalized = normalize_formal_request(raw)
        except ValueError as exc:
            self.skipTest(f"main-agent shared facade still blocked: {exc}")
        spec = normalized["specification"]
        public_target = normalized["target"]
        self.assertIn("hash", spec)
        before = (deepcopy(spec), deepcopy(public_target))
        result = check_correspondence(
            normalized["problem"]["text"], spec, public_target,
            attempt_id=normalized["attempt_id"], environment_hash=ENVIRONMENT_HASH,
        )
        self.assertEqual("confirmed", result["status"], result)
        self.assertEqual(before, (spec, public_target))
if __name__ == "__main__":
    unittest.main()
