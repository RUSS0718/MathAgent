"""Exercise scoped mathematical support at the single-route request boundary."""

import json
import tempfile
import unittest
from pathlib import Path

from test_runtime_math_verification import ANSWER, CHECKS, PROBLEM, increment

from ricl_runtime import Runtime
from ricl_runtime.derivations import DerivationScope, ScopedDerivationGraph
from ricl_runtime.port import ModelReply


class ScriptedDerivationPort:
    name = "scripted-derivations"

    def __init__(self, *steps):
        self.steps = iter(steps)
        self.prompts = []

    def complete(self, problem):
        self.prompts.append(problem)
        step = next(self.steps)
        return ModelReply(step(problem) if callable(step) else step)


def delivered(prompt):
    _, separator, context = prompt.partition("Previously verified public claims:\n")
    return json.loads(context.split("\n\n", 1)[0]) if separator else []


def open_goals(prompt):
    _, _, context = prompt.partition("Open verification goals:\n")
    return json.loads(context.split("\n\n", 1)[0])


class RuntimeScopedDerivationsTests(unittest.TestCase):
    def run_script(self, port, **runtime_options):
        with tempfile.TemporaryDirectory() as directory:
            run = Runtime(port, **runtime_options).run(
                PROBLEM, reasoning_state_enabled=True, model_request_limit=6,
                output_root=Path(directory),
            )
            trace = [
                json.loads(line)
                for line in Path(run["artifacts"]["trace"]).read_text(encoding="utf-8").splitlines()
            ]
        return run, trace

    def test_submitted_claims_build_dependencies_and_later_request_reports_use(self):
        def finish(prompt):
            evidence_ids = [item["evidence_id"] for item in delivered(prompt)]
            reply = json.loads(increment(*CHECKS[2:]))
            reply["used_evidence_ids"] = [*evidence_ids, "not_delivered"]
            return json.dumps(reply)

        port = ScriptedDerivationPort(increment(*CHECKS[:2], answer="I squared the equation."), finish)
        run, trace = self.run_script(port)

        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "verified")
        graph = run["derivations"]
        by_kind = {row["kind"]: row for row in graph["supports"]}
        necessary = by_kind["necessary_conditions"]
        constraint = by_kind["candidate_constraint"]
        coverage = by_kind["candidate_coverage"]
        substitution = by_kind["original_equation_filter"]
        self.assertEqual(coverage["premise_ids"], [constraint["proposition_id"]])
        self.assertCountEqual(substitution["premise_ids"], [necessary["proposition_id"], coverage["proposition_id"]])
        self.assertEqual(substitution["scope"], {"domain": "reals", "assumptions": []})
        self.assertEqual(len({row["derivation_id"] for row in graph["supports"]}), 4)
        requests = [event for event in trace if event["event"] == "model_request_sent"]
        self.assertEqual(requests[1]["delivered_check_evidence_ids"], [necessary["evidence_id"], constraint["evidence_id"]])
        uses = [event for event in trace if event["event"] == "derivation_references_reported"]
        self.assertEqual(uses[0]["status"], "unknown")
        self.assertEqual(uses[1]["request_id"], requests[1]["request_id"])
        self.assertEqual(uses[1]["used_evidence_ids"], requests[1]["delivered_check_evidence_ids"])
        self.assertNotIn("not_delivered", json.dumps(trace))

    def test_controlled_revocation_retains_alternative_and_unrelated_support_across_requests(self):
        equivalent = {**CHECKS[1], "direction": "equivalent", "rhs_nonnegative": True}
        factorization = {**CHECKS[2], "factor_constants": ["2", "-3"]}
        partial = {**CHECKS[3], "rejected": []}
        revocations = iter((None, "exact_quadratic_discriminant", "exact_squared_constraint", None))

        def recheck(supports):
            method = next(revocations)
            evidence_ids = [
                support.evidence_id for support in supports
                if support.method == method and not support.scope.assumptions
            ]
            return evidence_ids

        def cite_coverage(prompt):
            reply = json.loads(increment(answer="The exact factorization still covers both roots."))
            reply["used_evidence_ids"] = [
                item["evidence_id"] for item in delivered(prompt) if item["kind"] == "candidate_coverage"
            ]
            reply["revoked_evidence_ids"] = [
                item["evidence_id"] for item in delivered(prompt) if item["kind"] == "necessary_conditions"
            ]
            return json.dumps(reply)

        port = ScriptedDerivationPort(
            increment(*CHECKS[:3], partial, answer="The positive candidate satisfies the original."),
            increment(equivalent, factorization, CHECKS[3], answer="Both squared candidates were tested."),
            cite_coverage,
            increment(answer="I need to repair the missing derivation."),
        )
        run, trace = self.run_script(port, math_evidence_recheck=recheck)

        self.assertEqual(len(port.prompts), 4)
        graph = run["derivations"]
        supports = graph["supports"]
        coverages = [item for item in supports if item["kind"] == "candidate_coverage"]
        self.assertEqual(len(coverages), 2)
        self.assertEqual(len({item["proposition_id"] for item in coverages}), 1)
        self.assertEqual(len({item["derivation_id"] for item in coverages}), 2)
        self.assertEqual(
            [item["reason"] for item in delivered(port.prompts[2]) if item["kind"] == "candidate_coverage"],
            ["exact_quadratic_factorization"],
        )
        self.assertTrue(all(not item["derivation"]["scope"]["assumptions"]
                            for prompt in port.prompts for item in delivered(prompt)))
        self.assertEqual(
            [(item["kind"], item["goal_id"] is not None) for item in delivered(port.prompts[3])],
            [("necessary_conditions", True), ("original_equation_filter", False)],
        )
        local_constraint = next(item for item in supports if item["scope"]["assumptions"])
        self.assertTrue(local_constraint["valid"])
        self.assertFalse(local_constraint["applicable"])
        revocations = [event for event in trace if event["event"] == "derivation_revoked"]
        self.assertEqual(revocations[0]["reopened_goal_ids"], [])
        self.assertEqual(revocations[0]["lost_proposition_ids"], [])
        self.assertCountEqual(
            revocations[1]["reopened_goal_ids"],
            [
                goal["id"] for goal in run["verification"]["goals"]
                if goal["kind"] in {"candidate_constraint", "candidate_coverage", "original_equation_filter"}
            ],
        )
        self.assertEqual(open_goals(port.prompts[2]), [])
        self.assertCountEqual(
            [goal["id"] for goal in open_goals(port.prompts[3])],
            revocations[1]["reopened_goal_ids"],
        )
        self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
        self.assertEqual(run["verification"]["status"], "unknown")
        requests = [event for event in trace if event["event"] == "model_request_sent"]
        use = next(event for event in trace if event["event"] == "derivation_references_reported"
                   and event["request_id"] == requests[2]["request_id"])
        self.assertEqual(use["used_evidence_ids"], [coverages[1]["evidence_id"]])

    def test_repeating_a_check_with_a_model_method_label_does_not_add_support(self):
        port = ScriptedDerivationPort(
            increment(*CHECKS[:3], answer="I found the squared candidates."),
            increment({**CHECKS[2], "method": "independent"}, answer="I repeated the candidates."),
        )
        run, _ = self.run_script(port)
        self.assertEqual(run["run"]["stop_reason"], "no_progress")
        coverages = [row for row in run["derivations"]["supports"] if row["kind"] == "candidate_coverage"]
        self.assertEqual(len(coverages), 1)

    def test_recheck_prevents_binding_answer_to_a_revoked_certificate(self):
        def recheck(supports):
            return [support.evidence_id for support in supports if support.kind == "candidate_constraint"]

        port = ScriptedDerivationPort(increment(*CHECKS), increment(answer=ANSWER))
        run, trace = self.run_script(port, math_evidence_recheck=recheck)
        self.assertEqual(run["result"]["answer"], ANSWER)
        self.assertEqual(run["verification"]["status"], "unknown")
        self.assertEqual(run["verification"]["completeness"]["status"], "unknown")
        self.assertTrue(all(event["status"] == "unknown" for event in trace
                            if event["event"] == "verification_completed"))


class ScopedDerivationGraphTests(unittest.TestCase):
    def test_circular_alternatives_lose_support_in_fork_without_affecting_parent(self):
        parent = ScopedDerivationGraph()
        scope = DerivationScope()

        def add(claim, method, premises=()):
            return parent.add(
                {"kind": claim, "status": "verified", "goal_id": claim, "evidence": {"claim": claim},
                 "evidence_id": method},
                criterion_goal_id=claim, request_id="request", method=method,
                scope=scope, premise_ids=premises,
            )

        root = add("A", "root")
        dependent = add("B", "from_a", (root.proposition_id,))
        alternate = add("A", "from_b", (dependent.proposition_id,))
        branch = parent.fork()
        change = branch.revoke(root.evidence_id, scope=scope)
        self.assertCountEqual(change.invalidated_evidence_ids,
                              [root.evidence_id, dependent.evidence_id, alternate.evidence_id])
        self.assertEqual(branch.applicable(scope), ())
        self.assertEqual(len(parent.applicable(scope)), 3)
