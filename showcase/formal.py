"""Stable facade for constrained formal verification backends."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .formal_artifact import (
    DEFAULT_ALLOWED_AXIOMS,
    STATUSES,
    ProofArtifact,
    ReviewAuthority,
    ReviewRecord,
    attempt_hash,
    create_attempt,
    finalize_attempt,
    serialize_attempt_result,
)
from .formal_specification import (
    TEMPLATE_VERSION,
    build_polynomial_identity_source,
    build_specification_records,
    normalize_formal_request,
    normalize_target,
)
from .profile import SHOWCASE_PROFILE

FORMAL_POLICY_VERSION = "formal-v1"
RATIONAL_POLYNOMIAL_TARGET = "rational-polynomial-identity-v1"


class BackendRegistry:
    """Register only real backends and resolve one explicit request policy."""

    def __init__(self) -> None:
        self._backends: dict[str, Any] = {}

    def register(
        self,
        backend: Any,
        *,
        target_types: tuple[str, ...],
        maximum_grade: str,
        environment_identity: Mapping[str, Any],
        input_format: str,
        output_format: str,
        deterministic: bool,
        unavailable_reason: str | None = None,
    ) -> Any:
        name = getattr(backend, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("backend_identity_invalid")
        if name in self._backends:
            raise ValueError("backend_already_registered")
        if (not target_types or any(not isinstance(item, str) or not item for item in target_types)
                or maximum_grade not in {"L1", "L2", "L3"}
                or not isinstance(environment_identity, Mapping)
                or not input_format or not output_format
                or type(deterministic) is not bool
                or (unavailable_reason is not None and not isinstance(unavailable_reason, str))):
            raise ValueError("backend_registration_invalid")
        self._backends[name] = {
            "backend": backend,
            "id": name,
            "target_types": tuple(dict.fromkeys(target_types)),
            "maximum_grade": maximum_grade,
            "environment_identity": dict(environment_identity),
            "input_format": input_format,
            "output_format": output_format,
            "deterministic": deterministic,
            "unavailable_reason": unavailable_reason,
        }
        return backend

    def select(self, target: Any, policy: Any) -> Any | None:
        if not isinstance(policy, Mapping) or policy.get("enabled") is not True:
            return None
        name = policy.get("backend", policy.get("requested_backend"))
        if not isinstance(name, str) or not name:
            raise ValueError("backend_required")
        registration = self._backends.get(name)
        if registration is None:
            raise ValueError("unknown_backend")
        if registration["unavailable_reason"] is not None:
            raise ValueError("formal_backend_unavailable")
        allowed = policy.get("allowed_backends")
        if isinstance(allowed, (list, tuple)) and name not in allowed:
            raise ValueError("formal_backend_unsupported")
        expected_environment = policy.get("environment")
        registered_environment = registration["environment_identity"]
        if isinstance(expected_environment, Mapping) and any(
            key in registered_environment and registered_environment[key] != value
            for key, value in expected_environment.items()
        ):
            raise ValueError("formal_environment_drift")
        try:
            normalize_target(target)
        except (TypeError, ValueError) as exc:
            raise ValueError("formal_target_unsupported") from exc
        if RATIONAL_POLYNOMIAL_TARGET not in registration["target_types"]:
            raise ValueError("formal_target_unsupported")
        return registration["backend"]

    def describe(self) -> list[dict[str, Any]]:
        """Expose the registered backend contract without its implementation object."""
        return [{
            **{key: value for key, value in item.items() if key != "backend"},
            "target_types": list(item["target_types"]),
        } for item in self._backends.values()]

    def get(self, backend_id: str) -> Any | None:
        registration = self._backends.get(backend_id)
        return None if registration is None else registration["backend"]

    def metadata(self, backend_id: str) -> Mapping[str, Any] | None:
        registration = self._backends.get(backend_id)
        return None if registration is None else {
            key: value for key, value in registration.items() if key != "backend"
        }

    def verify_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            backend = self.select(request.get("target"), request.get("policy"))
        except ValueError as exc:
            return serialize_attempt_result({
                "status": "unknown", "grade": None,
                "attempt_id": request.get("attempt_id"),
                "parent_attempt_id": request.get("parent_attempt_id"),
                "cost": dict(request.get("cost") or {}),
                "lineage": {}, "proof_artifact": None, "specifications": {},
                "reason": str(exc),
            })
        if backend is None:
            return serialize_attempt_result({
                "status": "disabled", "grade": None,
                "attempt_id": request.get("attempt_id"),
                "parent_attempt_id": request.get("parent_attempt_id"),
                "cost": {"elapsed_seconds": 0, "output_bytes": 0, "usage": {}},
                "lineage": {}, "proof_artifact": None, "specifications": {},
                "reason": "formal_disabled",
            })
        try:
            result = backend.invoke(request)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            result = {
                "status": "error", "grade": None,
                "attempt_id": request.get("attempt_id"),
                "parent_attempt_id": request.get("parent_attempt_id"),
                "cost": dict(request.get("cost") or {}), "lineage": {},
                "proof_artifact": None, "specifications": {}, "reason": type(exc).__name__,
            }
        if not isinstance(result, Mapping):
            result = {
                "status": "unknown", "grade": None,
                "attempt_id": request.get("attempt_id"),
                "parent_attempt_id": request.get("parent_attempt_id"),
                "cost": {"elapsed_seconds": 0, "output_bytes": 0, "usage": {}},
                "lineage": {}, "reason": "formal_result_invalid",
            }
        if result.get("attempt_id") != request.get("attempt_id") or result.get(
            "parent_attempt_id"
        ) != request.get("parent_attempt_id"):
            result = {
                **dict(result), "status": "unknown", "grade": None,
                "reason": "attempt_lineage_mismatch",
            }
        return serialize_attempt_result(result)


def register_formal(registry: Any, backend: Any):
    return registry.register(
        backend.name,
        backend.invoke,
        capabilities=("formal_verification", "polynomial_identity"),
        allowed_profiles=(SHOWCASE_PROFILE,),
        timeout_seconds=getattr(backend, "timeout_seconds", 30.0),
        experimental=True,
        parameters_schema={
            "type": "object",
            "required": [
                "schema_version", "job_id", "run_id", "attempt_id", "target", "policy",
            ],
        },
    )


def register_formal_backend(registry: BackendRegistry, backend: Any):
    """Register the actual Lean service and its fixed polynomial-goal profile."""
    manifest = getattr(getattr(backend, "executor", None), "manifest", {})
    build = manifest.get("build_manifest", {}) if isinstance(manifest, Mapping) else {}
    environment = {
        "image": manifest.get("image"),
        "deployment_manifest_sha256": manifest.get("deployment_manifest_sha256"),
        "build_manifest_sha256": manifest.get("build_manifest_sha256"),
        "lean_version": build.get("lean_version"),
        "lean_commit": build.get("lean_commit"),
        "mathlib_version": build.get("mathlib_version"),
        "mathlib_commit": build.get("mathlib_commit"),
        "toolchain": build.get("toolchain"),
        "template_version": build.get("template_version"),
    }
    environment = {key: value for key, value in environment.items() if value is not None}
    return registry.register(
        backend,
        target_types=(RATIONAL_POLYNOMIAL_TARGET,),
        maximum_grade="L3" if getattr(backend, "review_service", None) is not None else "L2",
        environment_identity=environment,
        input_format="formal-request-v1",
        output_format="formal-attempt-v1",
        deterministic=True,
        unavailable_reason=(getattr(backend, "unavailable_reason", None)
                            or ("formal_environment_identity_unavailable"
                                if hasattr(getattr(backend, "executor", None), "manifest")
                                and not environment else None)),
    )


class LeanTacticProver:
    name = "lean_tactic_prover"

    def __init__(self, executor: Any, *, timeout_seconds: float = 30.0,
                 review_authority: ReviewAuthority | None = None) -> None:
        self.executor = executor
        self.timeout_seconds = timeout_seconds
        from .formal_correspondence import IndependentSpecificationReviewer

        self.review_service = (IndependentSpecificationReviewer(review_authority)
                               if review_authority is not None else None)

    def _environment_matches(self, requested):
        manifest = self.executor.manifest
        build = manifest.get("build_manifest", {})
        identity = {key: build.get(key) for key in (
            "lean_version", "lean_commit", "mathlib_version", "mathlib_commit",
            "toolchain", "template_version")}
        identity.update(deployment_manifest_sha256=self.executor.environment_hash,
                        build_manifest_sha256=manifest.get("build_manifest_sha256"),
                        image=manifest.get("image"), image_id=manifest.get("image"))
        return all(key in identity and identity[key] == value for key, value in requested.items())

    def invoke(self, value: Mapping[str, Any]) -> dict[str, Any]:
        try:
            request = normalize_formal_request(value)
        except ValueError as exc:
            return serialize_attempt_result({
                "status": "unsupported", "grade": None,
                "attempt_id": value.get("attempt_id") if isinstance(value, Mapping) else None,
                "parent_attempt_id": value.get("parent_attempt_id")
                if isinstance(value, Mapping) else None,
                "cost": dict(value.get("cost") or {}) if isinstance(value, Mapping) else {},
                "lineage": {}, "reason": str(exc),
            })
        policy = request["policy"]
        if not policy["enabled"]:
            return serialize_attempt_result({
                "status": "disabled", "grade": None, "attempt_id": request["attempt_id"],
                "parent_attempt_id": request["parent_attempt_id"],
                "cost": {"elapsed_seconds": 0, "output_bytes": 0, "usage": {}},
                "lineage": {}, "reason": "formal_disabled",
            })
        try:
            source = build_polynomial_identity_source(request["target"])
            execution = self.executor.execute(
                source, run_id=request["run_id"], call_id=request["attempt_id"],
                timeout_seconds=policy["timeout_seconds"],
                max_output_bytes=policy["max_output_bytes"],
                resource_limits=policy["resource_limits"],
            )
        except ValueError as exc:
            return serialize_attempt_result({
                "status": "unsupported", "grade": None, "attempt_id": request["attempt_id"],
                "parent_attempt_id": request["parent_attempt_id"],
                "cost": dict(request["cost"]), "lineage": {}, "reason": str(exc),
            })
        status = execution.get("status", "unknown")
        if status == "success":
            status = "solved"
        if status == "output_limit" and execution.get("cleanup_verified") is True:
            status = "error"
        status = status if status in STATUSES else "unknown"
        from .formal_kernel import resource_usage

        cost = {
            "elapsed_seconds": execution.get("duration_seconds", 0) or 0,
            "output_bytes": execution.get("observed_output_bytes", 0) or 0,
            "usage": {
                "wall_seconds": execution.get("duration_seconds", 0) or 0,
                "output_bytes": execution.get("observed_output_bytes", 0) or 0,
                **resource_usage(execution.get("stderr", "")),
            },
            "unknown": status in {"unknown", "unknown_outcome"},
        }
        import hashlib

        proof = {**dict(execution), "source": source,
                 "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                 "target_hash": request["target"]["hash"]}
        records = request["specifications"]
        grade = None
        reason = execution.get("reason") or execution.get("error") or (
            "formal_output_limit" if execution.get("status") == "output_limit" else None)
        if execution.get("status") == "success":
            from .formal_kernel import kernel_artifact

            trusted = getattr(self.executor, "environment_hash", None)
            actual = execution.get("environment", {}).get("deployment_manifest_sha256")
            expected = policy["environment"].get("deployment_manifest_sha256", trusted)
            try:
                if (not trusted or actual != trusted or expected != trusted
                        or not self._environment_matches(policy["environment"])):
                    raise ValueError("formal_environment_drift")
                dependencies = self.executor.manifest.get("dependency_audit", {})
                if dependencies.get("passed") is not True or not dependencies.get("packages"):
                    raise ValueError("formal_dependency_audit_incomplete")
                artifact = kernel_artifact(
                    execution, source=source, target_hash=request["target"]["hash"],
                    environment_hash=trusted, allowed_axioms=policy["allowed_axioms"],
                )
                grade = artifact.grade(
                    allowed_axioms=set(policy["allowed_axioms"]),
                    trusted_environment_hash=trusted,
                )
                proof = {**artifact.to_dict(), "source": source, "execution_receipt": execution,
                         "environment": dict(self.executor.manifest)}
                records["target_to_environment"].update({
                    "environment_hash": trusted, "source_hash": artifact.source_hash,
                    "proof_hash": artifact.proof_hash, "attempt_hash": attempt_hash(request),
                    "kernel_result": artifact.status,
                })
                status = "solved" if grade else "failed"
                reason = artifact.reason
                if grade == "L2" and self.review_service is not None:
                    review, correspondence = self.review_service.review(request, artifact)
                    proof["correspondence"] = correspondence
                    if review is not None:
                        identity = {
                            "problem_hash": request["problem"]["hash"],
                            "spec_hash": records["original_to_spec"]["problem_spec_hash"],
                            "target_hash": request["target"]["hash"],
                            "environment_hash": trusted, "attempt_hash": attempt_hash(request),
                        }
                        grade = artifact.grade(
                            allowed_axioms=set(policy["allowed_axioms"]),
                            trusted_environment_hash=trusted, review=review,
                            review_authority=self.review_service, identity=identity,
                        )
                        proof["independent_review"] = review
                        for record in records.values():
                            record.update(review_status="reviewed",
                                          review_record_hash=review["record_hash"])
            except ValueError as exc:
                status, reason = "failed", str(exc)
        return serialize_attempt_result({
            "status": status, "grade": grade,
            "attempt_id": request["attempt_id"],
            "parent_attempt_id": request["parent_attempt_id"],
            "cost": cost,
            "lineage": {"parent_attempt_id": request["parent_attempt_id"]},
            "proof_artifact": proof,
            "specifications": records,
            "reason": reason,
        })

    def verify_result(self, value, result):
        """Recheck a signed isolated receipt at the public acceptance boundary."""
        import hashlib

        from .formal_docker import LeanDockerExecutor
        from .formal_kernel import kernel_artifact

        try:
            if not isinstance(self.executor, LeanDockerExecutor):
                return None
            request = normalize_formal_request(value)
            if not self._environment_matches(request["policy"]["environment"]):
                return None
            proof = result.get("proof_artifact") or {}
            execution = proof.get("execution_receipt") or {}
            source = build_polynomial_identity_source(request["target"])
            if (not self.executor.verify_receipt(execution)
                    or execution.get("executed") is not True
                    or execution.get("run_id") != request["run_id"]
                    or execution.get("call_id") != request["attempt_id"]
                    or execution.get("source_hash") != hashlib.sha256(source.encode()).hexdigest()
                    or execution.get("environment", {}).get("deployment_manifest_sha256")
                    != self.executor.environment_hash
                    or not self.executor.manifest.get("dependency_audit", {}).get("passed")):
                return None
            allowed = set(request["policy"]["allowed_axioms"])
            registered = set(self.executor.manifest.get("build_manifest", {}).get(
                "policy", {}).get("allowed_axioms", []))
            if allowed - registered:
                return None
            limits = execution.get("resource_limits", {})
            requested = request["policy"]
            resources = requested.get("resource_limits", {})
            if (limits.get("timeout_seconds", float("inf")) > requested["timeout_seconds"]
                    or limits.get("max_output_bytes", float("inf")) > requested["max_output_bytes"]
                    or limits.get("memory_mb", float("inf")) > resources.get("memory_mb", 1024)
                    or limits.get("cpu_count", float("inf")) > resources.get("cpu_count", 1)):
                return None
            artifact = kernel_artifact(execution, source=source,
                                       target_hash=request["target"]["hash"],
                                       environment_hash=self.executor.environment_hash,
                                       allowed_axioms=allowed)
            if (proof.get("source_hash") != artifact.source_hash
                    or proof.get("proof_hash") != artifact.proof_hash):
                return None
            identity = {
                "problem_hash": request["problem"]["hash"],
                "spec_hash": request["specifications"]["original_to_spec"]["problem_spec_hash"],
                "target_hash": request["target"]["hash"],
                "environment_hash": self.executor.environment_hash,
                "attempt_hash": attempt_hash(request),
            }
            return artifact.grade(
                allowed_axioms=allowed, trusted_environment_hash=self.executor.environment_hash,
                review=proof.get("independent_review") if result.get("grade") == "L3" else None,
                review_authority=self.review_service, identity=identity,
            )
        except (ValueError, TypeError, KeyError, AttributeError):
            return None


__all__ = [
    "BackendRegistry", "DEFAULT_ALLOWED_AXIOMS", "FORMAL_POLICY_VERSION", "LeanTacticProver",
    "RATIONAL_POLYNOMIAL_TARGET",
    "ProofArtifact", "ReviewAuthority", "ReviewRecord", "STATUSES", "TEMPLATE_VERSION",
    "attempt_hash", "build_polynomial_identity_source", "build_specification_records",
    "create_attempt", "finalize_attempt", "normalize_formal_request", "normalize_target",
    "register_formal", "register_formal_backend", "serialize_attempt_result",
]
