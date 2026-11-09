"""S09 constrained formal backend public contracts."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from showcase.tools import ToolRegistry


def request(**changes):
    value = {
        "schema_version": 1,
        "job_id": "job-1",
        "run_id": "run-1",
        "attempt_id": "attempt-1",
        "parent_attempt_id": None,
        "problem": {"text": "Prove (x+1)^2 = x^2+2*x+1 for every rational x.", "hash": ""},
        "specification": {
            "specification_version": 1,
            "original_problem": "Prove (x+1)^2 = x^2+2*x+1 for every rational x.",
            "domain": "rationals",
            "quantifiers": ["forall x"],
            "assumptions": [],
            "directions": ["equality"],
            "output_requirements": [],
            "root_obligations": [{
                "obligation_id": "root:identity",
                "obligation_type": "universal",
                "statement": "(x+1)^2 = x^2+2*x+1",
            }],
            "auxiliary_goals": [],
        },
        "target": {
            "domain": "rationals",
            "variables": ["x"],
            "lhs": "(x + 1) ** 2",
            "rhs": "x ** 2 + 2 * x + 1",
            "quantifiers": ["forall x"],
            "assumptions": [],
            "direction": "equality",
        },
        "policy": {
            "enabled": True,
            "backend": "lean_tactic_prover",
            "timeout_seconds": 30,
            "max_output_bytes": 16000,
            "allowed_axioms": ["propext", "Classical.choice", "Quot.sound"],
            "environment": {},
        },
        "cost": {"elapsed_seconds": 0.0, "output_bytes": 0, "unknown": False},
        "review": None,
    }
    value.update(changes)
    return value


class BackendRegistryContractTest(unittest.TestCase):
    def test_default_is_disabled_and_registration_reuses_tool_registry(self):
        from showcase.formal import BackendRegistry, register_formal

        calls = []
        backend = _Backend(lambda req: calls.append(req) or _success(req))
        formal = BackendRegistry()
        formal.register(
            backend, target_types=("rational-polynomial-identity-v1",),
            maximum_grade="L2", environment_identity={"image": "sha256:test"},
            input_format="formal-request-v1", output_format="formal-attempt-v1",
            deterministic=True,
        )
        tools = ToolRegistry()
        spec = register_formal(tools, backend)
        self.assertEqual("lean_tactic_prover", spec.name)
        self.assertIn("formal_verification", spec.capabilities)
        selected = formal.select(request()["target"], {})
        self.assertIsNone(selected)
        disabled = request()
        disabled["policy"] = {**disabled["policy"], "enabled": False}
        result = backend.invoke(disabled)
        self.assertEqual("disabled", result["status"])
        self.assertIsNone(result["grade"])
        self.assertEqual([], calls)
        self.assertEqual({}, result["cost"]["usage"])

    def test_registry_selects_only_explicit_requested_backend(self):
        from showcase.formal import BackendRegistry

        registry = BackendRegistry()
        registry.register(
            _Backend(lambda req: _success(req)),
            target_types=("rational-polynomial-identity-v1",),
            maximum_grade="L2", environment_identity={"image": "sha256:test"},
            input_format="formal-request-v1", output_format="formal-attempt-v1",
            deterministic=True,
        )
        policy = {"enabled": True, "backend": "lean_tactic_prover",
                  "allowed_backends": ["lean_tactic_prover"]}
        self.assertEqual("lean_tactic_prover", registry.select(request()["target"], policy).name)
        with self.assertRaisesRegex(ValueError, "unknown_backend"):
            registry.select(request()["target"], {"enabled": True, "backend": "alpha_proof"})
        with self.assertRaisesRegex(ValueError, "formal_target_unsupported"):
            registry.select({**request()["target"], "domain": "reals"}, policy)
        self.assertEqual("rational-polynomial-identity-v1", registry.describe()[0]["target_types"][0])


class GoldTemplateContractTest(unittest.TestCase):
    def test_safe_ast_builds_fixed_rational_identity_template(self):
        from showcase.formal import build_polynomial_identity_source

        spec = request()["target"]
        source = build_polynomial_identity_source(spec)
        self.assertIn("import Mathlib", source)
        self.assertIn("#print axioms", source)
        self.assertIn("#print", source)
        self.assertIn("ring", source)
        self.assertNotIn("run_cmd", source)
        self.assertNotIn("import Lean", source)

    def test_wrong_domain_quantifier_or_direction_is_not_supported(self):
        from showcase.formal import build_polynomial_identity_source, normalize_formal_request

        reverse = {**request()["target"], "lhs": "x ** 2 + 2 * x + 1", "rhs": "(x + 1) ** 2"}
        with self.assertRaisesRegex(ValueError, "unsupported_quantifiers"):
            normalize_formal_request({**request(), "target": {**reverse, "quantifiers": ["exists x"]}})
        for change, reason in (
            ({"domain": "reals"}, "unsupported_domain"),
            ({"quantifiers": ["exists x"], "domain": "rationals"}, "unsupported_quantifiers"),
            ({"direction": "implication"}, "unsupported_direction"),
            ({"assumptions": ["x != 0"]}, "unsupported_assumptions"),
            ({"variables": ["x", "y"]}, "unsupported_variables"),
            ({"lhs": "__import__('os')"}, "unsafe_expression"),
        ):
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError, reason):
                    build_polynomial_identity_source({**request()["target"], **change})

    def test_wrong_problem_spec_targets_cannot_become_l3(self):
        from showcase.formal import build_specification_records

        spec = request()["specification"]
        target = request()["target"]
        records = build_specification_records("Prove (x+1)^2 = x^2+2*x+1 for every rational x.",
                                              spec, target)
        self.assertEqual({"original_to_spec", "spec_to_target", "target_to_environment"},
                         set(records))
        changed = {**spec, "domain": "reals"}
        with self.assertRaisesRegex(ValueError, "spec_target_mismatch"):
            build_specification_records("Prove (x+1)^2 = x^2+2*x+1 for every rational x.",
                                        changed, target)


class VerifyContractTest(unittest.TestCase):
    def test_kernel_pass_plus_recursive_axiom_audit_and_cleanup_is_l2(self):
        from showcase.formal import ProofArtifact, normalize_formal_request

        req = normalize_formal_request(request())
        artifact = ProofArtifact(
            status="solved", kernel_exit=0, accepted=True, cleanup_verified=True,
            environment_hash="env-hash", target_hash=req["target"]["hash"],
            source_hash="1111111111111111111111111111111111111111111111111111111111111111", proof_hash="2222222222222222222222222222222222222222222222222222222222222222",
            print_axioms_raw="#print axioms polynomial_identity\n'polynomial_identity' depends on axioms: [propext]",
            print_proof_raw="theorem polynomial_identity : True := True.intro",
            axioms=["propext"], dependency_audit={"passed": True, "recursive": True},
        )
        self.assertEqual("L2", artifact.grade(trusted_environment_hash="env-hash"))
        for change, expected in (
            ({"accepted": False}, None), ({"cleanup_verified": False}, None),
            ({"axioms": ["propext", "sorryAx"]}, None),
            ({"axioms": ["propext", "MyCompany.trustMe"]}, None),
            ({"environment_hash": "drifted"}, None),
            ({"print_axioms_raw": ""}, None),
            ({"dependency_audit": {"passed": False, "recursive": True}}, None),
        ):
            with self.subTest(change=change):
                dynamic = ProofArtifact(**{**artifact.__dict__, **change})
                actual = dynamic.grade(allowed_axioms={"propext"}, trusted_environment_hash="env-hash")
                self.assertEqual(expected, actual)

    def test_l3_requires_server_authority_review_bound_to_full_identity(self):
        from showcase.formal import ProofArtifact, ReviewAuthority

        authority = ReviewAuthority(
            {"server-reviewer": "secret"},
            {"server-reviewer": {"type": "independent_service"}},
        )
        identity = {
            "problem_hash": "1" * 64, "spec_hash": "2" * 64,
            "target_hash": "3" * 64, "environment_hash": "4" * 64,
            "attempt_hash": "5" * 64,
        }
        record = authority.issue({
            "review_id": "review-1", "reviewer_authority_id": "server-reviewer",
            "reviewer_type": "independent_service", **identity, "approved": True,
            "field_results": {
                "domain": True, "variables": True, "quantifiers": True,
                "assumptions": True, "direction": True, "conclusion": True,
            },
        })
        artifact = ProofArtifact(
            status="solved", kernel_exit=0, accepted=True, cleanup_verified=True,
            environment_hash=identity["environment_hash"], target_hash=identity["target_hash"],
            source_hash="6" * 64, proof_hash="7" * 64,
            print_axioms_raw="#print axioms polynomial_identity\\n'polynomial_identity' depends on axioms: [propext]",
            print_proof_raw="theorem polynomial_identity : True := True.intro",
            axioms=["propext"], dependency_audit={"passed": True, "recursive": True},
        )
        self.assertEqual("L3", artifact.grade(
            allowed_axioms={"propext"}, trusted_environment_hash=identity["environment_hash"],
            review=record.to_dict(), review_authority=authority, identity=identity,
        ))
        fake = {**record.to_dict(), "signature": "forged"}
        self.assertEqual("L2", artifact.grade(
            allowed_axioms={"propext"}, trusted_environment_hash=identity["environment_hash"],
            review=fake, review_authority=authority, identity=identity,
        ))
        foreign = {**identity, "attempt_hash": "8" * 64}
        self.assertEqual("L2", artifact.grade(
            allowed_axioms={"propext"}, trusted_environment_hash=identity["environment_hash"],
            review=record.to_dict(), review_authority=authority, identity=foreign,
        ))

    def test_output_truncation_cleanup_failure_and_incomplete_audit_never_reach_l2(self):
        from showcase.formal import ProofArtifact

        base = dict(
            status="solved", kernel_exit=0, accepted=True, cleanup_verified=True,
            environment_hash="4" * 64, target_hash="3" * 64,
            source_hash="6" * 64, proof_hash="7" * 64,
            print_axioms_raw="#print axioms polynomial_identity\n'polynomial_identity' depends on axioms: []",
            print_proof_raw="theorem polynomial_identity : True := True.intro",
            axioms=[], dependency_audit={"passed": True, "recursive": True},
        )
        self.assertEqual("L2", ProofArtifact(**base).grade(
            allowed_axioms=set(), trusted_environment_hash=base["environment_hash"]))
        for change in (
            {"logs": {"truncated": True}},
            {"cleanup_verified": False},
            {"kernel_exit": 1},
            {"dependency_audit": {"passed": True, "recursive": False}},
            {"print_axioms_raw": "axioms"},
            {"print_proof_raw": "theorem proof"},
            {"axioms": ["sorryAx"]},
            {"axioms": ["privateAxiom"]},
        ):
            with self.subTest(change=change):
                self.assertIsNone(ProofArtifact(**{**base, **change}).grade(
                    allowed_axioms=set(), trusted_environment_hash=base["environment_hash"]))

    def test_explicit_empty_axiom_policy_and_native_result_parser_are_strict(self):
        from showcase.formal import (
            LeanTacticProver,
            normalize_formal_request,
            serialize_attempt_result,
        )

        req = request()
        req["policy"]["allowed_axioms"] = []
        normalized = normalize_formal_request(req)
        self.assertEqual([], normalized["policy"]["allowed_axioms"])
        fake_target = {**req["target"], "hash": "0" * 64}
        with self.assertRaisesRegex(ValueError, "target_hash_mismatch"):
            normalize_formal_request({**req, "target": fake_target})

        class Executor:
            environment_hash = "4" * 64
            manifest = {"deployment_manifest_sha256": "4" * 64,
                        "dependency_audit": {"passed": True, "packages": ["fixture-pinned"]}}

            def execute(self, source, *, run_id, call_id, **kwargs):
                return {
                    "status": "success", "exit_code": 0, "accepted": True,
                    "cleanup_verified": True, "truncated": False,
                    "duration_seconds": 1.25, "observed_output_bytes": 100,
                    "environment": {"deployment_manifest_sha256": "4" * 64},
                    "stdout": "theorem polynomial_identity : True := True.intro\n"
                              "'polynomial_identity' does not depend on any axioms\n",
                    "axiom_violations": [], "recursive_audit": True,
                }

        prover = LeanTacticProver(Executor())
        result = prover.invoke(req)
        self.assertEqual("solved", result["status"])
        self.assertEqual("L2", result["grade"])
        self.assertEqual(1.25, result["cost"]["elapsed_seconds"])
        self.assertEqual(set(("schema_version", "status", "grade", "attempt_id",
                              "parent_attempt_id", "reason", "proof_artifact",
                              "specifications", "cost", "lineage")), set(result))
        failed = serialize_attempt_result({
            "status": "partial", "attempt_id": "a", "parent_attempt_id": "p",
            "reason": "partial", "proof_artifact": {"x": 1},
            "specifications": {"s": 1}, "cost": {"elapsed_seconds": 2, "output_bytes": 3},
            "lineage": {"parent_attempt_id": "p", "attempts": ["p"]},
        })
        self.assertIsNone(failed["grade"])
        self.assertEqual({"x": 1}, failed["proof_artifact"])
    def test_attempt_retry_creates_new_identity_and_preserves_unknown_cost(self):
        from showcase.formal import create_attempt, finalize_attempt

        first = create_attempt(request(), attempt_id="attempt-new")
        first = finalize_attempt(first, status="unknown", reason="provider unknown",
                                 cost={"elapsed_seconds": 4.2, "output_bytes": 900,
                                       "usage": {"wall_seconds": 4.2, "unknown": True}})
        child = create_attempt(first, attempt_id="attempt-2", backend="lemma_backend")
        self.assertEqual("attempt-new", child["parent_attempt_id"])
        self.assertEqual(4.2, child["cost"]["lineage"]["elapsed_seconds"])
        self.assertTrue(child["cost"]["lineage"]["unknown"])
        with self.assertRaisesRegex(ValueError, "attempt_identity_reused"):
            create_attempt(first, attempt_id="attempt-new")

    def test_statuses_never_upgrade_and_partial_or_timeout_keep_cost(self):
        from showcase.formal import serialize_attempt_result

        for status in ("partial", "failed", "timeout", "error", "unavailable",
                       "unsupported", "unknown", "disabled"):
            with self.subTest(status=status):
                result = serialize_attempt_result({
                    "schema_version": 1, "status": status, "grade": "L2",
                    "attempt_id": "a", "parent_attempt_id": None,
                    "reason": status, "proof_artifact": {"accepted": True},
                    "cost": {"elapsed_seconds": 1.5, "output_bytes": 7},
                    "lineage": {"parent_attempt_id": None},
                    "specifications": {},
                })
                self.assertIsNone(result["grade"])
                self.assertEqual(1.5, result["cost"]["elapsed_seconds"])
                self.assertEqual(7, result["cost"]["output_bytes"])

    def test_lineage_mismatch_is_unknown(self):
        from showcase.solver_harness.formal_integration import (
            FormalIntegrationState,
            run_formal_verification,
        )

        req = request()
        req["policy"]["enabled"] = True
        def wrong_lineage(value):
            result = _success(value, attempt_id="other")
            result["cost"] = {"elapsed_seconds": 1.5, "output_bytes": 7,
                              "unknown": False}
            return result

        backend = _Backend(wrong_lineage)
        state = FormalIntegrationState(
            job_id=req["job_id"], run_id=req["run_id"],
            problem=req["problem"]["text"], problem_spec=req["specification"],
            policy=req["policy"], target=req["target"],
        )
        result = run_formal_verification(state, backend=backend, target=req["target"])
        self.assertEqual("unknown", result["current"]["status"])
        self.assertIsNone(result["current"]["grade"])
        self.assertTrue(result["current"]["cost"]["unknown"])
        self.assertEqual(1.5, result["current"]["cost"]["elapsed_seconds"])
        self.assertEqual(7, result["current"]["cost"]["output_bytes"])
        self.assertIsNone(result["current"]["proof_artifact"])


class DockerSupervisionContractTest(unittest.TestCase):
    def test_docker_launcher_uses_stdin_and_fail_closed_cleanup(self):
        from showcase.formal_docker import LeanDockerExecutor

        manifest = _manifest()
        completed = []

        class Process:
            stdin = _Pipe()
            stdout = _Pipe()
            stderr = _Pipe()
            def poll(self):
                return 0 if self.stdout.closed else None
            def wait(self, timeout=None):
                return 0
            def kill(self):
                completed.append("kill")

        fake = Process()
        image_info = json.dumps({"Id": manifest["image"], "Config": {"Labels": manifest["labels"]}})
        state_info = json.dumps({"Running": False, "ExitCode": 0})

        def command(args):
            if args[0:2] == ["image", "inspect"]:
                return _completed(image_info)
            if args[0] == "inspect":
                return _completed(state_info)
            return _completed("")

        with patch("showcase.formal_docker.subprocess.run"), patch(
                "showcase.formal_docker.subprocess.Popen", return_value=fake
        ), patch("showcase.formal_docker.supervise", return_value={
            "stdout": b"accepted", "stderr": b"", "observed_output_bytes": 8,
            "reason": None}) as supervised, patch.object(
                LeanDockerExecutor, "_command", side_effect=command) as docker_command:
            executor = LeanDockerExecutor(manifest=manifest, timeout_seconds=2, max_output_bytes=64)
            result = executor.execute("theorem polynomial_identity : True := by trivial",
                                      run_id="run", call_id="attempt", timeout_seconds=1,
                                      max_output_bytes=32,
                                      resource_limits={"memory_mb": 512, "cpu_count": 0.5})
        self.assertTrue(result["executed"], result)
        self.assertTrue(result["cleanup_verified"], result)
        self.assertEqual("accepted", result["stdout"])
        supervised.assert_called_once()
        self.assertEqual(32, supervised.call_args.kwargs["limit"])
        self.assertEqual(1, supervised.call_args.kwargs["timeout"])
        created = next(call.args[0] for call in docker_command.call_args_list
                       if call.args[0][0] == "create")
        self.assertIn("--memory=512m", created)
        self.assertIn("--cpus=0.5", created)
        self.assertTrue(executor.verify_receipt(result))
        self.assertFalse(executor.verify_receipt({**result, "stdout": "forged"}))
        self.assertLessEqual(fake.stdin.written, 128)
        self.assertTrue(any(call.args[0][0:2] == ["image", "inspect"]
                            for call in docker_command.call_args_list))


class FormalExecutorIntegrationTest(unittest.TestCase):
    def test_unavailable_executor_never_claims_l2(self):
        from showcase.formal import LeanTacticProver

        class Unavailable:
            def execute(self, *_args, **_kwargs):
                return {"status": "unavailable", "executed": False,
                        "cleanup_verified": True, "environment": {},
                        "duration_seconds": 0.1, "observed_output_bytes": 0,
                        "stdout": "", "stderr": "lean unavailable"}
        result = LeanTacticProver(Unavailable()).invoke(request())
        self.assertEqual("unavailable", result["status"])
        self.assertIsNone(result["grade"])


class _Pipe:
    def __init__(self):
        import io
        self.value = io.BytesIO()
        self.closed = False
    def write(self, value):
        self.value.write(value)
        return len(value)
    @property
    def written(self):
        return len(self.value.getvalue())
    def read1(self, _size):
        return b""
    def close(self):
        self.closed = True


class _Backend:
    name = "lean_tactic_prover"
    timeout_seconds = 1
    parameters_schema = {"type": "object"}

    def __init__(self, verify):
        self._verify = verify
        self.calls = []

    def invoke(self, value):
        self.calls.append(value)
        if not value.get("policy", {}).get("enabled", False):
            return {"schema_version": 1, "status": "disabled", "grade": None,
                    "attempt_id": value.get("attempt_id"),
                    "parent_attempt_id": value.get("parent_attempt_id"),
                    "cost": {"usage": {}}, "lineage": {}}
        result = self._verify(value)
        result.setdefault("attempt_id", value["attempt_id"])
        result.setdefault("parent_attempt_id", value.get("parent_attempt_id"))
        return result

    def verify(self, value):
        return self.invoke(value)


def _success(value, attempt_id=None):
    return {"schema_version": 1, "status": "solved", "grade": "L2",
            "attempt_id": attempt_id or value.get("attempt_id"),
            "parent_attempt_id": value.get("parent_attempt_id"),
            "proof_artifact": {}, "specifications": {},
            "cost": {"elapsed_seconds": 0, "output_bytes": 0}, "lineage": {}}


def _completed(stdout):
    from subprocess import CompletedProcess
    return CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _manifest():
    import hashlib

    build = {"lean_version": "4.19.0", "mathlib_version": "v4.19.0",
             "mathlib_commit": "fixture-mathlib", "toolchain": "leanprover/lean4:v4.19.0",
             "template_version": "rational-polynomial-v1",
             "policy": {"allowed_axioms": ["propext", "Classical.choice", "Quot.sound"]}}
    build_hash = hashlib.sha256(json.dumps(build, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
    labels = {
        "mathagent.lean.policy": "docker-lean-v1",
        "mathagent.lean.lean_version": "4.19.0",
        "mathagent.lean.mathlib_version": "v4.19.0",
        "mathagent.lean.toolchain": "leanprover/lean4:v4.19.0",
        "mathagent.lean.template_version": "rational-polynomial-v1",
        "mathagent.lean.build_manifest_sha256": build_hash,
    }
    value = {"image": "sha256:" + "1" * 64, "labels": labels,
            "build_manifest": build, "build_manifest_sha256": build_hash,
            "dependency_audit": {"passed": True, "packages": ["fixture-pinned"],
                                 "mathlib_revision": build["mathlib_commit"],
                                 "toolchain": build["toolchain"]},
            "deployment_manifest_sha256": "3" * 64}
    from showcase.formal_docker import manifest_digest
    value["deployment_manifest_sha256"] = manifest_digest(value)
    return value


if __name__ == "__main__":
    unittest.main()
