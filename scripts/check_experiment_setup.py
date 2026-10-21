"""Credential-free, offline validation of the proposed research setup contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from os import devnull
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTIONS = {"r1", "r2", "r3", "r4", "r5"}


class SetupError(ValueError):
    """A fixed public failure category without configuration contents."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SetupError("arguments_invalid")


def _git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
    # Do not inherit credentials/configuration; even partial clones cannot fetch.
    try:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *arguments],
            cwd=ROOT,
            capture_output=True,
            check=False,
            timeout=15,
            env={
                "GIT_ALLOW_PROTOCOL": "",
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": devnull,
            },
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError("git_unavailable") from exc


def _repo_path(value: object, category: str) -> Path:
    if not isinstance(value, str) or not value:
        raise SetupError(category)
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise SetupError(category)
    return path


def _artifact_path(value: object) -> Path:
    path = _repo_path(value, "artifact_path_invalid")
    relative = path.relative_to(ROOT)
    if relative.parts[:1] != ("artifacts",):
        raise SetupError("artifact_path_invalid")
    ignored = _git("check-ignore", "-q", "--", relative.as_posix())
    tracked = _git("ls-files", "--", relative.as_posix())
    if ignored.returncode != 0 or tracked.returncode != 0 or tracked.stdout:
        raise SetupError("artifact_path_invalid")
    return path


def _check_directions(config: dict) -> int:
    directions = config.get("directions")
    if (
        not isinstance(directions, list)
        or len(directions) != 5
        or any(not isinstance(item, dict) for item in directions)
    ):
        raise SetupError("directions_invalid")
    ids = [item.get("id") for item in directions]
    branches = [item.get("branch") for item in directions]
    if (
        any(not isinstance(value, str) or not value.strip() for value in ids + branches)
        or set(ids) != DIRECTIONS
        or len(set(branches)) != 5
    ):
        raise SetupError("directions_invalid")
    documents = set()
    for direction in directions:
        for field in ("prd", "technical_spec", "adr"):
            path = _repo_path(direction.get(field), "direction_document_invalid")
            if path.suffix != ".md" or not path.is_file() or path in documents:
                raise SetupError("direction_document_invalid")
            documents.add(path)
    archive = config.get("archive")
    if not isinstance(archive, dict) or archive.get("raw_in_git") is not False:
        raise SetupError("archive_invalid")
    raw_root = _artifact_path(archive.get("raw_root"))
    if raw_root.exists() and not raw_root.is_dir():
        raise SetupError("archive_invalid")
    return len(documents)


def _check_baseline(config: dict) -> dict:
    base = config.get("base_commit")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", base):
        raise SetupError("baseline_invalid")
    base = base.lower()
    kind = _git("cat-file", "-t", base)
    source = _git("show", f"{base}:BASELINE.json")
    if kind.returncode != 0 or kind.stdout.strip() != b"commit" or source.returncode != 0:
        raise SetupError("baseline_invalid")
    try:
        manifest = json.loads(source.stdout)
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, dict) or not files:
            raise SetupError("baseline_invalid")
        current_path = ROOT / "BASELINE.json"
        if current_path.resolve() != current_path:
            raise SetupError("baseline_mismatch")
        current = current_path.read_bytes()
        if source.stdout != current:
            raise SetupError("baseline_mismatch")
        for name, expected in files.items():
            if (
                not isinstance(name, str)
                or not (
                    name in {"user_agent.py", "requirements.txt"}
                    or (name.startswith("implementations/") and name.endswith(".py"))
                )
                or not isinstance(expected, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected)
            ):
                raise SetupError("baseline_invalid")
            path = _repo_path(name, "baseline_invalid")
            if path != ROOT / name or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise SetupError("baseline_mismatch")
    except (OSError, UnicodeError) as exc:
        raise SetupError("baseline_mismatch") from exc
    except json.JSONDecodeError as exc:
        raise SetupError("baseline_invalid") from exc
    head = _git("rev-parse", "--verify", "HEAD")
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=normal")
    if head.returncode != 0 or status.returncode != 0 or branch.returncode not in (0, 1):
        raise SetupError("git_unavailable")
    return {
        "base_commit": base,
        "current_commit": head.stdout.decode("ascii").strip(),
        "branch": branch.stdout.decode("utf-8", errors="replace").strip() or None,
        "dirty": bool(status.stdout),
        "baseline_manifest_sha256": {
            "base": hashlib.sha256(source.stdout).hexdigest(),
            "current": hashlib.sha256(current).hexdigest(),
        },
        "protected_files_checked": len(files),
    }


def _positive(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and value > 0
    except OverflowError:
        return False


def _check_budgets(config: dict) -> None:
    required = {
        "api_probe": "max_models_queries max_generation_attempts max_tokens_per_attempt "
        "max_inflight requests_per_minute",
        "calibration": "independent_problems strategies paired_repeats_for_tool_problems "
        "max_runs max_generation_attempts max_logical_calls_per_run max_tokens_per_attempt "
        "max_requested_output_tokens_per_run max_input_tokens_estimate_per_attempt "
        "accounted_plus_reserved_tokens_limit max_runtime_seconds_per_run "
        "max_batch_active_seconds max_inflight requests_per_minute",
    }
    stages = config.get("stages")
    if not isinstance(stages, dict) or set(stages) != {"offline", *required}:
        raise SetupError("budget_invalid")
    offline = stages["offline"]
    if (
        not isinstance(offline, dict)
        or set(offline) != {"max_generation_attempts"}
        or type(offline["max_generation_attempts"]) is not int
        or offline["max_generation_attempts"] != 0
    ):
        raise SetupError("budget_invalid")
    for stage_name, fields in required.items():
        stage = stages[stage_name]
        if not isinstance(stage, dict):
            raise SetupError("budget_invalid")
        for key in fields.split():
            value = stage.get(key)
            if key in {"max_runtime_seconds_per_run", "max_batch_active_seconds"}:
                valid = _positive(value)
            else:
                valid = type(value) is int and value > 0
            if not valid:
                raise SetupError("budget_invalid")
    probe_retries = stages["api_probe"].get("automatic_retries")
    retries = stages["calibration"].get("automatic_retries_per_logical_call")
    money_limit = stages["calibration"].get("money_limit")
    if (
        type(probe_retries) is not int
        or probe_retries != 0
        or type(retries) is not int
        or retries < 0
        or (money_limit is not None and not _positive(money_limit))
    ):
        raise SetupError("budget_invalid")


def main() -> int:
    report = {"schema_version": 1, "network_requests": 0, "planned_not_implemented": True}
    output_path = None
    parser = _Parser(description=__doc__)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--config", default="experiments/campaign.json")
    parser.add_argument("--output", help="save JSON only inside ignored artifacts/")
    try:
        args = parser.parse_args()
        if not args.offline:
            raise SetupError("offline_required")
        if args.output:
            output_path = _artifact_path(args.output)
            if output_path.suffix != ".json":
                output_path = None
                raise SetupError("artifact_path_invalid")
        config_path = (ROOT / args.config).resolve()
        if not config_path.is_relative_to(ROOT) or config_path.suffix != ".json":
            raise SetupError("config_path_invalid")
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if (
            not isinstance(config, dict)
            or type(config.get("schema_version")) is not int
            or config["schema_version"] != 1
        ):
            raise SetupError("config_invalid")
        if config.get("allow_network") is not False:
            raise SetupError("network_not_allowed")
        if config.get("profile") != "research_experimental" or config.get("model") != "intern-s2":
            raise SetupError("experiment_identity_invalid")
        if config.get("thinking_mode") is not True:
            raise SetupError("thinking_required")
        features = config.get("features")
        if (
            not isinstance(features, dict)
            or set(features) != DIRECTIONS
            or any(value is not False for value in features.values())
        ):
            raise SetupError("features_must_be_disabled")
        _check_budgets(config)
        document_count = _check_directions(config)
        report.update(_check_baseline(config))
        report["counts"] = {
            "directions": 5,
            "direction_documents": document_count,
            "disabled_features": len(features),
            "protected_files": report.pop("protected_files_checked"),
        }
        report.update(status="ok", category="offline_contract_valid")
    except SetupError as exc:
        report.update(status="error", category=str(exc))
    except (OSError, ValueError, TypeError, RuntimeError):
        report.update(status="error", category="config_invalid")
    if output_path is not None:
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
            )
        except OSError:
            report.update(status="error", category="output_write_failed")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
