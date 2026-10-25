"""Opt-in arbitrary mathematical Python executes only in a restricted container."""

import json
import re
import subprocess
import time
import uuid

from .container_output import supervise
from .tool_artifacts import ToolArtifactStore

POLICY = "docker-python-v1"
MAX_SOURCE_BYTES = 32000
IMAGE_LABELS = {
    "mathagent.python.policy": POLICY,
    "mathagent.python.base_sha256": "b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377",
    "mathagent.python.version": "3.11.17",
    "mathagent.python.sympy": "1.14.0",
    "mathagent.python.numpy": "2.3.4",
    "mathagent.python.mpmath": "1.3.0",
}


class DockerPythonExecutor:
    # The wall/CPU budget is calibrated for real mathematical scripts: live
    # ALIGN-10 batches kept losing natural computations (sympy imports, DP
    # over 10^4 states) to the old 8s wall / 3s CPU caps, turning every
    # explore computation into an unknown timeout. Upstream budgets code at
    # 600s; 20s stays far below while letting multi-second scripts finish.
    # Everything else (network=none, memory caps, output caps, fail-closed
    # cleanup verification) is unchanged.
    def __init__(self, *, image, artifact_root, timeout_seconds=20, max_output_bytes=16000):
        if not isinstance(image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise ValueError("star_python_image_id_invalid")
        self.image = image
        self.artifacts = ToolArtifactStore(artifact_root)
        self.timeout_seconds = timeout_seconds
        self.max_output_bytes = max_output_bytes

    def execute(self, code, *, run_id, call_id, input_payload=None, canceled=lambda: False):
        started = time.monotonic()
        outcome = {"status": "unavailable", "executed": False, "exit_code": None,
                   "sandbox_policy_version": POLICY, "image": self.image,
                   "stdout": "", "stderr": "", "cleanup_verified": True,
                   "timeout": False, "unknown_outcome": False}
        if not isinstance(code, str):
            outcome.update(status="rejected", error="source_must_be_text")
            return self._persist(outcome, run_id, call_id, b"", b"", started)
        source = code.encode("utf-8")
        try:
            encoded_input = json.dumps(
                input_payload if input_payload is not None else {"code": code},
                sort_keys=True, ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError):
            outcome.update(status="rejected", error="input_not_serializable")
            return self._persist(outcome, run_id, call_id, b"", b"", started)
        if len(source) > MAX_SOURCE_BYTES or len(encoded_input) > MAX_SOURCE_BYTES:
            outcome.update(status="rejected", error="source_too_large")
            return self._persist(outcome, run_id, call_id, b"", b"", started)
        outcome["code_ref"] = self.artifacts.put(
            run_id, call_id, "code", source, media_type="text/x-python")
        outcome["input_ref"] = self.artifacts.put(
            run_id, call_id, "input", encoded_input, media_type="application/json")
        try:
            image = self._command(["image", "inspect", self.image, "--format", "{{json .}}"])
            if image.returncode:
                return self._persist(outcome, run_id, call_id, b"", b"", started)
            image_info = json.loads(image.stdout)
            labels = image_info.get("Config", {}).get("Labels") or {}
            if image_info.get("Id") != self.image or any(
                labels.get(key) != value for key, value in IMAGE_LABELS.items()
            ):
                outcome["error"] = "python_image_identity_invalid"
                return self._persist(outcome, run_id, call_id, b"", b"", started)
            outcome["environment"] = {"image_id": self.image, "policy": POLICY,
                "base_sha256": IMAGE_LABELS["mathagent.python.base_sha256"],
                "python": IMAGE_LABELS["mathagent.python.version"],
                "libraries": {name.removeprefix("mathagent.python."): version
                    for name, version in IMAGE_LABELS.items() if name in {
                        "mathagent.python.sympy", "mathagent.python.numpy", "mathagent.python.mpmath"}}
            }
        except (OSError, subprocess.SubprocessError):
            return self._persist(outcome, run_id, call_id, b"", b"", started)
        except (AttributeError, TypeError, ValueError):
            outcome["error"] = "python_image_identity_invalid"
            return self._persist(outcome, run_id, call_id, b"", b"", started)

        name = "mathagent-python-" + uuid.uuid4().hex
        create_attempted = False
        stdout = stderr = b""
        try:
            create_attempted = True
            created = self._command([
                "create", "--name", name, "--pull=never", "--network=none", "--read-only",
                "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                "--label=mathagent.run_id=" + run_id, "--label=mathagent.call_id=" + call_id,
                "--label=mathagent.sandbox.policy=" + POLICY,
                "--memory=256m", "--memory-swap=256m", "--cpus=.5", "--pids-limit=32",
                "--ulimit=cpu=10:15", "--ulimit=fsize=1048576:1048576", "--log-driver=none",
                "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=8m,mode=1777", "-i", self.image,
                "python", "-I", "-u", "-c", "import sys; exec(compile(sys.stdin.buffer.read(), '<math>', 'exec'))",
            ])
            if created.returncode:
                outcome.update(status="unavailable", error="container_create_failed")
            else:
                process = subprocess.Popen(["docker", "start", "-a", "-i", name],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                process.stdin.write(source)
                process.stdin.close()
                outcome["executed"] = True
                streams = supervise(process, limit=self.max_output_bytes, timeout=self.timeout_seconds,
                                    canceled=canceled, kill=lambda: self._command(["kill", name]))
                stdout, stderr = streams["stdout"], streams["stderr"]
                state = self._command(["inspect", name, "--format", "{{json .State}}"])
                info = json.loads(state.stdout) if state.returncode == 0 else {}
                cleanup_verified = state.returncode == 0 and info.get("Running") is False
                status = streams["reason"] or (
                    "success" if cleanup_verified and info.get("ExitCode") == 0
                    else "tool_error" if cleanup_verified and type(info.get("ExitCode")) is int
                    else "unknown_outcome"
                )
                outcome.update(status=status, exit_code=info.get("ExitCode"),
                    signal=(info["ExitCode"] - 128 if type(info.get("ExitCode")) is int
                        and 128 <= info["ExitCode"] <= 255 else None),
                    oom_killed=info.get("OOMKilled"), cleanup_verified=cleanup_verified,
                    timeout=streams["reason"] == "timeout",
                    observed_output_bytes=streams["observed_output_bytes"],
                    retained_output_bytes=len(stdout) + len(stderr))
        except (OSError, subprocess.SubprocessError, ValueError):
            outcome.update(status="unknown_outcome", error="container_execution_unavailable",
                unknown_outcome=True)
        finally:
            if create_attempted:
                outcome["cleanup_verified"] = self._cleanup(name)
                if not outcome["cleanup_verified"]:
                    outcome["termination_reason"] = outcome["status"]
                    outcome.update(status="unknown_outcome", unknown_outcome=True)
                elif outcome["status"] == "unknown_outcome":
                    outcome["unknown_outcome"] = True
        return self._persist(outcome, run_id, call_id, stdout, stderr, started)

    def _cleanup(self, name):
        try:
            self._command(["kill", name])
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            inspected = self._command(["inspect", name, "--format", "{{json .State}}"])
            if inspected.returncode:
                if "no such object" in inspected.stderr.lower() or "no such container" in inspected.stderr.lower():
                    return True
                return False
            state = json.loads(inspected.stdout)
            if state.get("Running") is True:
                self._command(["kill", name])
            removed = self._command(["rm", "-f", name])
            return removed.returncode == 0
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            return False

    def _persist(self, outcome, run_id, call_id, stdout, stderr, started):
        try:
            outcome["stdout"] = stdout.decode("utf-8", errors="replace")
            outcome["stderr"] = stderr.decode("utf-8", errors="replace")
            outcome["stdout_ref"] = self.artifacts.put(run_id, call_id, "stdout", stdout)
            outcome["stderr_ref"] = self.artifacts.put(run_id, call_id, "stderr", stderr)
            outcome["duration_seconds"] = time.monotonic() - started
            outcome["receipt_ref"] = self.artifacts.receipt(run_id, call_id, outcome)
        except (OSError, TypeError, ValueError):
            if outcome.get("executed"):
                outcome["termination_reason"] = outcome["status"]
                outcome.update(status="unknown_outcome", unknown_outcome=True,
                    error="artifact_persistence_failed")
            else:
                outcome.update(status="unavailable", error="artifact_persistence_failed")
        return outcome

    @staticmethod
    def _command(args):
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=15, check=False)
