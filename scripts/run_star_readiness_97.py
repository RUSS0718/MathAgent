"""Freeze and run the caller-authorized #97 Intern S2 batch once."""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
sys.path.insert(0, str(ROOT))
DEFAULT_DRAFT = ARTIFACTS / "issue-97-prereg" / "draft-v3.json"
DEFAULT_MANIFEST = ARTIFACTS / "issue-97-prereg" / "live-manifest.json"


def build_parser():
    """Build a CLI that requires a frozen hash and explicit live confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser("freeze-live", help="create a dispatchable v3 live registration")
    freeze.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    freeze.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    freeze.add_argument("--confirm-live", action="store_true", required=True)
    run = commands.add_parser("run-live", help="run one frozen batch through live Intern S2")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--manifest-sha256", required=True)
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--execute-live", action="store_true", required=True)
    return parser


def _inside_artifacts(path):
    """Resolve a user path and require it to stay below the ignored artifacts root."""
    resolved = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        resolved.relative_to(ARTIFACTS.resolve())
    except ValueError:
        raise ValueError("star_readiness_artifact_path_invalid") from None
    return resolved


def _write_once(path, content):
    """Create one artifact without replacing an earlier registration or report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _freeze(args):
    """Write the confirmed source-bound registration and its independent hash file."""
    from showcase.star_readiness_coordinator import current_source_identity
    from showcase.star_readiness_registration import (
        adapt_draft,
        authorize_live_registration,
        digest,
    )

    manifest_path = _inside_artifacts(args.manifest)
    if manifest_path.exists():
        raise ValueError("star_readiness_manifest_already_exists")
    draft_path = _inside_artifacts(args.draft)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    source = current_source_identity()
    base = adapt_draft(draft, current_source=source)
    manifest = authorize_live_registration(
        base,
        expected_sha256=digest(base),
        current_source=source,
        explicit_authorization=args.confirm_live,
        authorization_date=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
    )
    manifest_hash = digest(manifest)
    _write_once(manifest_path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "manifest": str(manifest_path.relative_to(ROOT)),
        "sha256": manifest_hash,
        "dispatchable": True,
    }, ensure_ascii=False, sort_keys=True))
    return 0


def _build_adapter(manifest):
    """Build the exact nonstream adapter without sending a provider request."""
    from llm_client import InternChatClient
    from showcase.adapters import InternModelAdapter
    from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT
    from showcase.star_readiness_registration import MODEL

    client = InternChatClient(
        timeout=MODEL["request_timeout_seconds"],
        retry=MODEL["retry"],
        thinking_mode=MODEL["thinking_mode"],
        provider_endpoint_only=True,
    )
    if client.api_base != manifest["provider_endpoint"] or client.api_base != INTERN_S2_LIVE_ENDPOINT:
        raise ValueError("star_readiness_live_provider_mismatch")
    if client.model != MODEL["name"]:
        raise ValueError("star_readiness_live_model_mismatch")
    return InternModelAdapter(
        client=client,
        model_id=MODEL["name"],
        temperature=MODEL["temperature"],
        max_tokens=MODEL["max_output_tokens"],
        client_timeout=MODEL["request_timeout_seconds"],
        client_retry=MODEL["retry"],
        thinking_mode=MODEL["thinking_mode"],
    )


def _run(args):
    """Execute the registered batch in a unique, ignored archive directory."""
    from showcase.star_readiness_coordinator import StarReadinessCoordinator
    from showcase.star_readiness_registration import digest

    manifest_path = _inside_artifacts(args.manifest)
    archive_path = _inside_artifacts(args.archive)
    if archive_path.exists():
        raise ValueError("star_readiness_archive_already_exists")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if digest(manifest) != args.manifest_sha256:
        raise ValueError("star_readiness_registration_identity_mismatch")
    adapter = _build_adapter(manifest)
    coordinator = StarReadinessCoordinator(
        archive_path,
        adapters={"nonstream": adapter},
        manifest=manifest,
        manifest_sha256=args.manifest_sha256,
        evidence_kind="live",
    )
    result = coordinator.run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["stop_reason"] == "completed" else 1


def main(argv=None):
    """Dispatch only the explicitly selected registration or live-run operation."""
    args = build_parser().parse_args(argv)
    try:
        return _freeze(args) if args.command == "freeze-live" else _run(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
