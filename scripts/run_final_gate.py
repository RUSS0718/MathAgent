"""Run the credential-free final validation stages in an isolated run directory."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "cache",
    "dist",
    "node_modules",
}
IGNORED_FILE = Path("tests") / "test.md"


def _timestamp() -> str:
    """Return a timezone-aware timestamp suitable for the run manifest."""

    return dt.datetime.now(dt.UTC).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON by replacing a same-directory temporary file."""

    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _fingerprint(payload: Any) -> str:
    """Hash a canonical JSON representation without exposing file contents."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative_path(value: str) -> str:
    """Normalize a Git path for portable manifest output."""

    return Path(value.replace("\\", "/")).as_posix()


def _ignored_path(relative: str, run_dir: Path, root: Path) -> bool:
    """Return whether a repository-relative path is outside the source snapshot."""

    path = Path(relative)
    if path == IGNORED_FILE or any(part in IGNORED_DIRECTORY_NAMES for part in path.parts):
        return True
    try:
        run_relative = run_dir.relative_to(root)
    except ValueError:
        return False
    return path == run_relative or path.is_relative_to(run_relative)


def _git_output(root: Path, arguments: list[str]) -> str | None:
    """Read a NUL-delimited Git listing, falling back when Git is unavailable."""

    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return completed.stdout if completed.returncode == 0 else None


def _parse_status(status_output: str) -> dict[str, str]:
    """Map Git porcelain paths to their two-character status codes."""

    entries = status_output.split("\0")
    result: dict[str, str] = {}
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if not entry or len(entry) < 4:
            continue
        code, path = entry[:2], _relative_path(entry[3:])
        result[path] = code
        if "R" in code or "C" in code:
            if index < len(entries) and entries[index]:
                result[_relative_path(entries[index])] = code
                index += 1
    return result


def _current_files(root: Path) -> set[str]:
    """List current regular files using portable repository-relative paths."""

    return {
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    }


def _snapshot_source(root: Path, run_dir: Path) -> dict[str, Any]:
    """Capture tracked and untracked source fingerprints without requiring a clean tree."""

    git_available = (root / ".git").exists()
    tracked_output = _git_output(root, ["ls-files", "-z"]) if git_available else None
    untracked_output = (
        _git_output(root, ["ls-files", "--others", "--exclude-standard", "-z"])
        if git_available
        else None
    )
    status_output = (
        _git_output(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
        if git_available
        else None
    )
    if tracked_output is None or untracked_output is None or status_output is None:
        tracked_paths: set[str] = set()
        untracked_paths = _current_files(root)
        statuses: dict[str, str] = {}
    else:
        tracked_paths = {
            _relative_path(path)
            for path in tracked_output.split("\0")
            if path
        }
        untracked_paths = {
            _relative_path(path)
            for path in untracked_output.split("\0")
            if path
        }
        statuses = _parse_status(status_output)

    tracked_paths = {path for path in tracked_paths if not _ignored_path(path, run_dir, root)}
    untracked_paths = {path for path in untracked_paths if not _ignored_path(path, run_dir, root)}

    def entries(paths: set[str], default_status: str) -> list[dict[str, Any]]:
        result = []
        for relative in sorted(paths):
            path = root / Path(relative)
            item: dict[str, Any] = {
                "path": relative,
                "status": statuses.get(relative, default_status),
            }
            try:
                item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                item["sha256"] = None
                item["missing"] = True
            result.append(item)
        return result

    tracked = entries(tracked_paths, "tracked")
    untracked = entries(untracked_paths, "??")
    dirty_tracked = [item for item in tracked if item["status"] != "tracked"]
    dirty_untracked = [item for item in untracked if item["status"] == "??"]
    source_files = {"tracked": tracked, "untracked": untracked}
    return {
        "captured_at": _timestamp(),
        "source_hash": _fingerprint(source_files),
        "files": source_files,
        "dirty_tracked": dirty_tracked,
        "dirty_untracked": dirty_untracked,
        "dirty_tracked_fingerprint": _fingerprint(dirty_tracked),
        "dirty_untracked_fingerprint": _fingerprint(dirty_untracked),
    }


def _npm_command() -> str:
    """Resolve npm without relying on Windows shell command resolution."""

    names = ("npm.cmd", "npm") if os.name == "nt" else ("npm", "npm.cmd")
    for name in names:
        resolved = shutil.which(name)
        if resolved:
            return resolved
    raise RuntimeError("npm_not_found")


def _stages(root: Path, run_dir: Path, require_reference: bool) -> list[dict[str, Any]]:
    """Build the six standard final-gate stages for one run."""

    uv = ["uv", "run", "python"]
    release = [*uv, "scripts/check_showcase_release.py"]
    if require_reference:
        release.append("--require-reference")
    npm = _npm_command()
    frontend = root / "showcase" / "frontend" / "chat-frontend"
    return [
        {"name": "fast", "command": [*uv, "scripts/check_fast.py"], "cwd": root},
        {
            "name": "offline",
            "command": [
                *uv,
                "scripts/check.py",
                "--offline",
                "--report-dir",
                str(run_dir / "repository-check"),
            ],
            "cwd": root,
        },
        {"name": "release", "command": release, "cwd": root},
        {
            "name": "frontend-install",
            "command": [npm, "ci", "--no-audit", "--no-fund"],
            "cwd": frontend,
        },
        {
            "name": "frontend-audit",
            "command": [npm, "audit", "--audit-level=high"],
            "cwd": frontend,
        },
        {"name": "frontend-check", "command": [npm, "run", "check"], "cwd": frontend},
    ]


def _save_status(path: Path, status: dict[str, Any], started: float) -> None:
    """Refresh elapsed time and atomically persist the public run status."""

    status["elapsed_seconds"] = round(time.monotonic() - started, 3)
    _atomic_write_json(path, status)


def _run_stage(
    stage: dict[str, Any],
    run_dir: Path,
    status: dict[str, Any],
    status_path: Path,
    started: float,
) -> int:
    """Execute one stage into its own log and return its child exit code."""

    name = stage["name"]
    log_path = run_dir / f"{name}.log"
    status.update({"current_stage": name, "child_pid": None})
    _save_status(status_path, status, started)
    environment = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    with log_path.open("x", encoding="utf-8", buffering=1) as log:
        log.write("COMMAND " + json.dumps(stage["command"], ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            stage["command"],
            cwd=stage["cwd"],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            shell=False,
        )
        status["child_pid"] = process.pid
        _save_status(status_path, status, started)
        code = process.wait()
        log.write(f"\nEXIT_CODE {code}\n")
        log.flush()
    status["child_pid"] = None
    _save_status(status_path, status, started)
    return code


def _argument_parser() -> argparse.ArgumentParser:
    """Create the parameterized final-gate CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="repository root")
    parser.add_argument("--output-dir", type=Path, required=True, help="parent for run outputs")
    parser.add_argument("--run-id", required=True, help="new run directory name")
    parser.add_argument(
        "--require-reference",
        action="store_true",
        help="require the selected Reference tests in the release gate",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the final gate and return the first child failure or runner failure."""

    args = _argument_parser().parse_args(argv)
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    if not root.is_dir():
        print(f"final_gate=FAIL root_missing:{root}", file=sys.stderr)
        return 2
    if not args.run_id or Path(args.run_id).name != args.run_id:
        print("final_gate=FAIL invalid_run_id", file=sys.stderr)
        return 2

    run_dir = output_dir / args.run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"final_gate=FAIL run_exists:{run_dir}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"final_gate=FAIL output_dir:{type(exc).__name__}", file=sys.stderr)
        return 2

    started = time.monotonic()
    status_path = run_dir / "status.json"
    status: dict[str, Any] = {
        "run_id": args.run_id,
        "pid": os.getpid(),
        "start_time": _timestamp(),
        "current_stage": "starting",
        "completed": 0,
        "total": 6,
        "elapsed_seconds": 0.0,
        "final_status": "running",
        "status": "running",
        "child_pid": None,
    }
    _save_status(status_path, status, started)

    before: dict[str, Any] | None = None
    exit_code = 1
    try:
        before = _snapshot_source(root, run_dir)
        ignored = ["artifacts", "cache", "tests/test.md"]
        if run_dir.is_relative_to(root):
            ignored.append(str(run_dir.relative_to(root)))
        manifest: dict[str, Any] = {
            "run_id": args.run_id,
            "root": str(root),
            "ignored": sorted(ignored),
            "before": before,
            "after": None,
        }
        manifest_path = run_dir / "source-manifest.json"
        _atomic_write_json(manifest_path, manifest)
        stages = _stages(root, run_dir, args.require_reference)
        status["total"] = len(stages)
        _save_status(status_path, status, started)
        exit_code = 0
        for stage in stages:
            code = _run_stage(stage, run_dir, status, status_path, started)
            if code:
                status.update(
                    {
                        "final_status": "failed",
                        "status": "failed",
                        "failure_stage": stage["name"],
                        "exit_code": code,
                    }
                )
                exit_code = code
                print(f"final_gate=FAIL stage={stage['name']} exit_code={code}", file=sys.stderr)
                break
            status["completed"] += 1
            _save_status(status_path, status, started)
        else:
            status["current_stage"] = "completed"
    except BaseException as exc:
        status.update(
            {
                "final_status": "runner_error",
                "status": "runner_error",
                "runner_error": type(exc).__name__,
            }
        )
        exit_code = 1
        print(f"final_gate=FAIL runner_error={type(exc).__name__}", file=sys.stderr)
    finally:
        try:
            after = _snapshot_source(root, run_dir)
            if before is not None:
                manifest["after"] = after
                _atomic_write_json(manifest_path, manifest)
                source_changed = before["source_hash"] != after["source_hash"]
                status["source_changed"] = source_changed
                if status["final_status"] == "running":
                    if source_changed:
                        status.update({"final_status": "source_changed", "status": "source_changed"})
                        exit_code = 1
                        print("final_gate=FAIL source_changed", file=sys.stderr)
                    else:
                        status.update({"final_status": "passed", "status": "passed"})
        except BaseException as exc:
            status.update(
                {
                    "final_status": "runner_error",
                    "status": "runner_error",
                    "runner_error": type(exc).__name__,
                }
            )
            exit_code = 1
            print(f"final_gate=FAIL runner_error={type(exc).__name__}", file=sys.stderr)
        _save_status(status_path, status, started)

    if status["final_status"] == "passed":
        print("final_gate=PASS")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
