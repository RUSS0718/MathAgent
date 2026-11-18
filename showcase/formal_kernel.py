"""Interpret complete native Lean kernel output for the registered theorem."""

from __future__ import annotations

import hashlib
import re

from .formal_artifact import ProofArtifact


def resource_usage(stderr: str) -> dict[str, int | None]:
    """Read measurements emitted by the fixed container launcher, if available."""
    result = {}
    for field, marker in (("memory_peak_bytes", "S09_MEMORY_PEAK_BYTES"),
                          ("cpu_usage_usec", "S09_CPU_USAGE_USEC")):
        values = re.findall(rf"^{marker}=([0-9]+)$", stderr, re.MULTILINE)
        result[field] = int(values[0]) if len(values) == 1 else None
    return result


def parse_kernel_output(stdout: str) -> tuple[str, str, list[str]]:
    """Require one printed proof and one recursive native axiom report."""
    pattern = (
        r"^'polynomial_identity' (?:depends on axioms: \[([^\]\n]*)\]"
        r"|does not depend on any axioms)\s*$"
    )
    matches = list(re.finditer(pattern, stdout, re.MULTILINE))
    if len(matches) != 1:
        raise ValueError("native_axiom_audit_missing_or_ambiguous")
    match = matches[0]
    proof = stdout[:match.start()].strip()
    if (not proof.startswith("theorem polynomial_identity") or "..." in proof
            or "⋯" in proof or "sorryAx" in proof or stdout[match.end():].strip()):
        raise ValueError("native_proof_missing_or_incomplete")
    axioms = [name.strip() for name in (match.group(1) or "").split(",") if name.strip()]
    if len(axioms) != len(set(axioms)) or any(
        not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_'.]*", name) for name in axioms
    ):
        raise ValueError("native_axiom_audit_invalid")
    return proof, match.group(0).strip(), axioms


def kernel_artifact(execution, *, source, target_hash, environment_hash, allowed_axioms):
    """Bind a native result to the exact source, target, and trusted environment."""
    stdout = execution.get("stdout", "")
    proof, audit, axioms = parse_kernel_output(stdout)
    def digest(text):
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    passed = (execution.get("status") == "success" and execution.get("exit_code") == 0
              and execution.get("cleanup_verified") is True
              and not execution.get("truncated")
              and not (set(axioms) - set(allowed_axioms)) and "sorryAx" not in axioms)
    artifact = ProofArtifact(
        status="solved" if passed else "failed", kernel_exit=execution.get("exit_code"),
        accepted=passed, cleanup_verified=execution.get("cleanup_verified") is True,
        environment_hash=environment_hash, target_hash=target_hash,
        source_hash=digest(source), proof_hash=digest(proof),
        print_axioms_raw="#print axioms polynomial_identity\n" + audit,
        print_proof_raw="#print polynomial_identity\n" + proof,
        axioms=axioms, dependency_audit={
            "passed": passed, "recursive": True, "method": "Lean.collectAxioms",
            "declaration": "polynomial_identity", "environment_hash": environment_hash,
        },
        logs={"stdout": stdout, "stderr": execution.get("stderr", ""),
              "truncated": execution.get("truncated", False)},
        reason=None if passed else "kernel_or_axiom_policy_rejected",
    )
    return artifact
