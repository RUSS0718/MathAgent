"""Supervised fixed-image Lean execution for the constrained formal backend."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import secrets
import subprocess
import time
import uuid
from collections.abc import Mapping
from typing import Any

from .container_output import supervise

POLICY = "docker-lean-v1"
REQUIRED_LABELS = {
    "mathagent.lean.policy": POLICY,
}


class LeanDockerExecutor:
    """Run one fixed Lean service in a bounded, read-only, offline container."""

    def __init__(self, *, manifest: Mapping[str, Any], timeout_seconds: float = 30.0,
                 max_output_bytes: int = 16000) -> None:
        if timeout_seconds <= 0 or max_output_bytes <= 0:
            raise ValueError("lean_limits_invalid")
        self.manifest = load_trusted_manifest(manifest)
        self.image = self.manifest["image"]
        self.environment_hash = self.manifest["deployment_manifest_sha256"]
        self.timeout_seconds = float(timeout_seconds)
        self.max_output_bytes = int(max_output_bytes)
        self._receipt_key = secrets.token_bytes(32)

    def execute(self, source: str, *, run_id: str, call_id: str,
                timeout_seconds: float | None = None, max_output_bytes: int | None = None,
                resource_limits: Mapping[str, Any] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        requested = dict(resource_limits or {})
        memory = requested.get("memory_mb", 1024)
        cpus = requested.get("cpu_count", 1)
        output_limit = self.max_output_bytes if max_output_bytes is None else max_output_bytes
        timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
        if (type(memory) is not int or memory <= 0 or isinstance(cpus, bool)
                or not isinstance(cpus, (float, int)) or not math.isfinite(cpus) or cpus <= 0
                or type(output_limit) is not int or output_limit <= 0
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("formal_limits_invalid")
        memory, cpus = min(1024, memory), min(1, cpus)
        output_limit, timeout = min(self.max_output_bytes, output_limit), min(self.timeout_seconds, timeout)
        outcome: dict[str, Any] = {
            "run_id": run_id, "call_id": call_id,
            "source_hash": hashlib.sha256(source.encode("utf-8")).hexdigest()
            if isinstance(source, str) else None,
            "resource_limits": {"memory_mb": memory, "cpu_count": cpus,
                                "max_output_bytes": output_limit, "timeout_seconds": timeout},
            "status": "unavailable", "executed": False, "exit_code": None,
            "stdout": "", "stderr": "", "cleanup_verified": True,
            "unknown_outcome": False, "timeout": False,
            "environment": self._environment(),
            "duration_seconds": 0.0, "observed_output_bytes": 0,
        }
        if not isinstance(source, str) or not source.strip():
            outcome.update(status="error", error="lean_source_invalid")
            outcome["duration_seconds"] = time.monotonic() - started
            return outcome
        source_bytes = source.encode("utf-8")
        if len(source_bytes) > 64_000:
            outcome.update(status="error", error="lean_source_too_large")
            outcome["duration_seconds"] = time.monotonic() - started
            return outcome
        try:
            identity = self._command([
                "image", "inspect", self.image, "--format", "{{json .}}"
            ])
            if identity.returncode:
                outcome.update(status="unavailable", error="lean_image_unavailable")
                return self._finish(outcome, started)
            image = json.loads(identity.stdout)
            labels = image.get("Config", {}).get("Labels") or {}
            actual = {"mathagent.lean.policy": labels.get("mathagent.lean.policy")}
            expected = dict(REQUIRED_LABELS)
            if (
                image.get("Id") != self.image
                or actual != expected
                or any(labels.get(name) != value
                       for name, value in self.manifest.get("labels", {}).items())
            ):
                outcome.update(status="unavailable", error="lean_image_identity_invalid")
                return self._finish(outcome, started)
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
            outcome.update(status="unavailable", error="lean_image_unavailable")
            return self._finish(outcome, started)

        name = "mathagent-lean-" + uuid.uuid4().hex
        create_attempted = False
        stdout = stderr = b""
        try:
            create_attempted = True
            created = self._command([
                "create", "--name", name, "--pull=never", "--network=none",
                "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                "--user=65534:65534", f"--memory={memory}m", f"--memory-swap={memory}m",
                f"--cpus={cpus}", "--pids-limit=64", "--ulimit=cpu=25:30",
                "--ulimit=fsize=16777216:16777216", "--log-driver=none",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
                "--label=mathagent.run_id=" + run_id,
                "--label=mathagent.call_id=" + call_id,
                "--label=mathagent.lean.policy=" + POLICY,
                "-i", self.image, "lean", "--stdin",
            ])
            if created.returncode:
                outcome.update(status="unavailable", error="lean_container_create_failed")
            else:
                process = subprocess.Popen(
                    ["docker", "start", "-a", "-i", name],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                # Source is sent only on stdin to the fixed launcher; no shell or arbitrary argv.
                process.stdin.write(source_bytes)
                process.stdin.close()
                outcome["executed"] = True
                streams = supervise(
                    process, limit=output_limit, timeout=timeout,
                    kill=lambda: self._command(["kill", name]),
                )
                stdout, stderr = streams["stdout"], streams["stderr"]
                inspect = self._command(["inspect", name, "--format", "{{json .State}}"])
                state = json.loads(inspect.stdout) if inspect.returncode == 0 else {}
                cleanup_verified = inspect.returncode == 0 and state.get("Running") is False
                reason = streams.get("reason")
                status = reason or (
                    "success" if cleanup_verified and state.get("ExitCode") == 0
                    else "error" if cleanup_verified and type(state.get("ExitCode")) is int
                    else "unknown"
                )
                outcome.update(
                    status=status, exit_code=state.get("ExitCode"),
                    cleanup_verified=cleanup_verified,
                    timeout=reason == "timeout",
                    stdout=stdout.decode("utf-8", errors="replace"),
                    stderr=stderr.decode("utf-8", errors="replace"),
                    observed_output_bytes=streams.get("observed_output_bytes", 0),
                    retained_output_bytes=len(stdout) + len(stderr),
                )
        except (OSError, subprocess.SubprocessError, ValueError, TypeError, AttributeError):
            outcome.update(status="unknown", error="lean_execution_unavailable",
                           unknown_outcome=True)
        finally:
            if create_attempted:
                outcome["cleanup_verified"] = self._cleanup(name)
                if not outcome["cleanup_verified"]:
                    outcome["termination_reason"] = outcome["status"]
                    outcome.update(status="unknown", unknown_outcome=True,
                                   error="lean_cleanup_unverified")
                elif outcome["status"] == "unknown":
                    outcome["unknown_outcome"] = True
        return self._finish(outcome, started)

    def _finish(self, outcome: dict[str, Any], started: float) -> dict[str, Any]:
        outcome["duration_seconds"] = time.monotonic() - started
        outcome["observed_output_bytes"] = int(outcome.get("observed_output_bytes", 0))
        outcome.setdefault("retained_output_bytes", 0)
        outcome["truncated"] = bool(
            outcome["observed_output_bytes"] > outcome.get("retained_output_bytes", 0)
            or outcome.get("status") == "output_limit"
        )
        outcome["receipt_signature"] = self._signature(outcome)
        return outcome

    def _signature(self, outcome):
        payload = {key: value for key, value in outcome.items() if key != "receipt_signature"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        return hmac.new(self._receipt_key, encoded, hashlib.sha256).hexdigest()

    def verify_receipt(self, outcome):
        """Authenticate a native receipt from this running isolated executor."""
        try:
            return hmac.compare_digest(self._signature(outcome), outcome.get("receipt_signature", ""))
        except (TypeError, ValueError, AttributeError):
            return False

    def _cleanup(self, name: str) -> bool:
        try:
            self._command(["kill", name])
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            inspected = self._command(["inspect", name, "--format", "{{json .State}}"])
            if inspected.returncode:
                if "no such object" in inspected.stderr.lower():
                    return True
                return False
            state = json.loads(inspected.stdout)
            if state.get("Running") is not False:
                return False
        except (OSError, subprocess.SubprocessError, ValueError, TypeError):
            return False
        try:
            removed = self._command(["rm", "-f", name])
        except (OSError, subprocess.SubprocessError):
            return False
        if removed.returncode:
            return "no such object" in removed.stderr.lower()
        remaining = self._command(["ps", "-a", "--filter", "name=" + name, "--format", "{{.Names}}"])
        return remaining.returncode == 0 and not remaining.stdout.strip()

    def _environment(self) -> dict[str, Any]:
        return {
            "image": self.image,
            "deployment_manifest_sha256": self.environment_hash,
            "labels": dict(self.manifest.get("labels", {})),
            "policy": POLICY,
        }

    @staticmethod
    def _command(args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", *args], capture_output=True, text=True,
            timeout=15, check=False,
        )


def load_trusted_manifest(value: Any) -> dict[str, Any]:
    """Validate an operator-provided manifest against the pinned image digest."""
    manifest = _validate_manifest(value)
    expected = manifest.get("deployment_manifest_sha256")
    if expected != manifest_digest(manifest):
        raise ValueError("lean_manifest_digest_invalid")
    build = manifest.get("build_manifest")
    if not isinstance(build, Mapping):
        raise ValueError("lean_build_manifest_invalid")
    payload = {key: item for key, item in build.items() if key != "build_manifest_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode()
    build_hash = hashlib.sha256(encoded).hexdigest()
    labels = manifest["labels"]
    if (manifest.get("build_manifest_sha256") != build_hash
            or labels.get("mathagent.lean.build_manifest_sha256") != build_hash
            or any(labels.get("mathagent.lean." + key) != build.get(key)
                   for key in ("lean_version", "mathlib_version", "toolchain", "template_version"))):
        raise ValueError("lean_build_identity_mismatch")
    audit = manifest.get("dependency_audit", {})
    if (audit.get("passed") is not True or not audit.get("packages")
            or audit.get("mathlib_revision") != build.get("mathlib_commit")
            or audit.get("toolchain") != build.get("toolchain")):
        raise ValueError("lean_dependency_audit_incomplete")
    return manifest


def manifest_digest(manifest: Mapping[str, Any]) -> str:
    import hashlib

    payload = {key: value for key, value in manifest.items()
               if key != "deployment_manifest_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("lean_manifest_invalid")
    manifest = json.loads(json.dumps(value, ensure_ascii=False))
    image = manifest.get("image")
    if not isinstance(image, str) or not __import__("re").fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("lean_image_digest_invalid")
    labels = manifest.get("labels")
    if not isinstance(labels, Mapping):
        raise ValueError("lean_manifest_labels_invalid")
    if labels.get("mathagent.lean.policy") != POLICY:
        raise ValueError("lean_manifest_policy_invalid")
    labels = {str(key): str(item) for key, item in labels.items()}
    required = {
        "mathagent.lean.policy", "mathagent.lean.lean_version",
        "mathagent.lean.mathlib_version", "mathagent.lean.toolchain",
        "mathagent.lean.template_version", "mathagent.lean.build_manifest_sha256",
    }
    if not required.issubset(labels):
        raise ValueError("lean_manifest_labels_invalid")
    manifest["labels"] = labels
    manifest_digest_value = manifest.get("deployment_manifest_sha256")
    if not isinstance(manifest_digest_value, str) or not __import__("re").fullmatch(
        r"^[0-9a-f]{64}$", manifest_digest_value
    ):
        raise ValueError("lean_manifest_digest_invalid")
    return manifest


__all__ = ["LeanDockerExecutor", "load_trusted_manifest", "manifest_digest", "POLICY"]
