"""Offline diagnostic registration, rehearsal, fake batches and read-only monitor."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from showcase.star_diagnostic import DiagnosticJob, socket_free  # noqa: E402
from showcase.star_diagnostic_monitor import monitor  # noqa: E402
from showcase.star_diagnostic_registration import dry_run, freeze, validate  # noqa: E402


def artifact_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to((ROOT / "artifacts").resolve()):
        raise ValueError("diagnostic_path_requires_ignored_artifacts")
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Socket-free #102 diagnostic runner; offline only")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("freeze", "dry-run", "fake-run", "monitor"):
        sub = commands.add_parser(name)
        if name != "monitor":
            sub.add_argument("--registration", required=True)
        if name == "freeze":
            sub.add_argument("--plan", required=True, help="private JSON in ignored artifacts")
        if name in {"fake-run", "monitor"}:
            sub.add_argument("--archive", required=True)
        if name == "fake-run":
            sub.add_argument("--sha256", required=True, help="exact digest printed by freeze")
            sub.add_argument("--outcomes", help="comma-separated offline fake outcomes, one per planned request")
            sub.add_argument("--control-only", action="store_true", help="P first three included requests")
            sub.add_argument("--continue-p", action="store_true", help="same P archive and cumulative ledger")
    args = parser.parse_args(argv)
    try:
        with socket_free():
            if args.command == "monitor":
                result = monitor(artifact_path(args.archive))
            else:
                registration = artifact_path(args.registration)
                if args.command == "freeze":
                    value = json.loads(artifact_path(args.plan).read_text(encoding="utf-8"))
                    result = dry_run(freeze(value, registration))
                else:
                    manifest = json.loads((registration / "manifest.json").read_text(encoding="utf-8"))
                    validate(manifest, check_source=True)
                    if args.command == "dry-run":
                        result = dry_run(manifest)
                    else:
                        if args.sha256 != manifest["sha256"]:
                            raise ValueError("diagnostic_expected_digest_mismatch")
                        job = DiagnosticJob(registration, artifact_path(args.archive))
                        result = job.run(outcomes=args.outcomes.split(",") if args.outcomes else None,
                                         limit=3 if args.control_only else None, continuation=args.continue_p)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0 if result["status"] in {"ready", "not_started", "completed", "control_complete"} else 1
    except (OSError, ValueError, RuntimeError, KeyError, TypeError):
        # Do not echo exception payload, source inputs, provider data or paths.
        print(json.dumps({"status": "rejected", "category": "diagnostic_contract_or_storage_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
