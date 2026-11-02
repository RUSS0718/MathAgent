"""Freeze, authorize and run one #97 Intern S2 batch in separate steps."""

import argparse
import json
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
sys.path.insert(0, str(ROOT))
DEFAULT_DRAFT = ARTIFACTS / "issue-97-prereg" / "draft-v5.json"
DEFAULT_MANIFEST = ARTIFACTS / "issue-97-prereg" / "manifest-v5-preview.json"
DEFAULT_LIVE_MANIFEST = ARTIFACTS / "issue-97-prereg" / "live-manifest-v5.json"


def build_parser():
    """Build a CLI that requires a frozen hash and explicit live confirmation."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    freeze = commands.add_parser(
        "freeze-live", help="freeze a non-dispatchable registration from a supported draft"
    )
    freeze.add_argument("--draft-version", choices=("v5", "v7"))
    freeze.add_argument("--draft", type=Path)
    freeze.add_argument("--manifest", type=Path)
    authorize = commands.add_parser("authorize-live", help="authorize an exact reviewed preview hash")
    authorize.add_argument("--draft-version", choices=("v5", "v7"))
    authorize.add_argument("--manifest", type=Path, required=True)
    authorize.add_argument("--manifest-sha256", required=True)
    authorize.add_argument("--authorized-manifest", type=Path)
    authorize.add_argument("--confirm-live", action="store_true", required=True)
    run = commands.add_parser("run-live", help="run one frozen batch through live Intern S2")
    run.add_argument("--draft-version", choices=("v5", "v7"))
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--manifest-sha256", required=True)
    run.add_argument("--archive", type=Path, required=True)
    run.add_argument("--answer-output", type=Path,
                     help="exclusive public-answer JSONL file directly under artifacts/issue-97-answers")
    run.add_argument("--execute-live", action="store_true", required=True)
    return parser


def _version_paths(version):
    """Return the historical default artifact paths for an explicitly selected CLI version."""
    if version == "v7":
        preregistration = ARTIFACTS / "issue-97-prereg"
        return (
            preregistration / "draft-v7.json",
            preregistration / "manifest-v7-preview.json",
            preregistration / "live-manifest-v7.json",
        )
    return DEFAULT_DRAFT, DEFAULT_MANIFEST, DEFAULT_LIVE_MANIFEST


def _require_draft_version(record, version):
    """Reject an explicitly selected CLI version when the artifact carries another version."""
    if version is None:
        return
    expected = f"issue-97-nonstream-draft-{version}"
    if record.get("version", record.get("draft_version")) != expected:
        raise ValueError("star_readiness_draft_version_mismatch")


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
    """Write an unapproved source-bound preview for review before live authorization."""
    from showcase.star_readiness_coordinator import current_source_identity
    from showcase.star_readiness_registration import adapt_draft, digest

    default_draft, default_manifest, _ = _version_paths(args.draft_version)
    manifest_path = _inside_artifacts(args.manifest or default_manifest)
    if manifest_path.exists():
        raise ValueError("star_readiness_manifest_already_exists")
    draft_path = _inside_artifacts(args.draft or default_draft)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    _require_draft_version(draft, args.draft_version)
    source = current_source_identity()
    manifest = adapt_draft(draft, current_source=source)
    manifest_hash = digest(manifest)
    _write_once(manifest_path, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({
        "manifest": str(manifest_path.relative_to(ROOT)),
        "sha256": manifest_hash,
        "dispatchable": False,
    }, ensure_ascii=False, sort_keys=True))
    return 0


def _authorize(args):
    """Authorize the reviewed preview hash without overwriting either registration."""
    from showcase.star_readiness_coordinator import current_source_identity
    from showcase.star_readiness_registration import authorize_live_registration, digest

    _, _, default_live_manifest = _version_paths(args.draft_version)
    preview_path = _inside_artifacts(args.manifest)
    manifest_path = _inside_artifacts(args.authorized_manifest or default_live_manifest)
    if manifest_path.exists():
        raise ValueError("star_readiness_manifest_already_exists")
    preview = json.loads(preview_path.read_text(encoding="utf-8"))
    _require_draft_version(preview, args.draft_version)
    manifest = authorize_live_registration(
        preview,
        expected_sha256=args.manifest_sha256,
        current_source=current_source_identity(),
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
    model = manifest["model"]

    client = InternChatClient(
        timeout=model["request_timeout_seconds"],
        retry=model["retry"],
        thinking_mode=model["thinking_mode"],
        provider_endpoint_only=True,
    )
    if client.api_base != manifest["provider_endpoint"] or client.api_base != INTERN_S2_LIVE_ENDPOINT:
        raise ValueError("star_readiness_live_provider_mismatch")
    if client.model != model["name"]:
        raise ValueError("star_readiness_live_model_mismatch")
    return InternModelAdapter(
        client=client,
        model_id=model["name"],
        temperature=model["temperature"],
        max_tokens=model["max_output_tokens"],
        client_timeout=model["request_timeout_seconds"],
        client_retry=model["retry"],
        thinking_mode=model["thinking_mode"],
    )


def _run(args):
    """Execute the registered batch in a unique, ignored archive directory."""
    from showcase.star_readiness_answer_delivery import AnswerOutput
    from showcase.star_readiness_coordinator import StarReadinessCoordinator
    from showcase.star_readiness_registration import digest

    manifest_path = _inside_artifacts(args.manifest)
    archive_path = _inside_artifacts(args.archive)
    if archive_path.exists():
        raise ValueError("star_readiness_archive_already_exists")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require_draft_version(manifest, args.draft_version)
    if digest(manifest) != args.manifest_sha256:
        raise ValueError("star_readiness_registration_identity_mismatch")
    answer_path = getattr(args, "answer_output", None)
    output = (AnswerOutput(_inside_artifacts(answer_path), artifacts=ARTIFACTS,
                           archive=archive_path) if answer_path is not None else nullcontext())
    with output as sink:
        adapter = _build_adapter(manifest)
        coordinator = StarReadinessCoordinator(
            archive_path,
            adapters={"nonstream": adapter},
            manifest=manifest,
            manifest_sha256=args.manifest_sha256,
            evidence_kind="live",
            **({"answer_sink": sink} if sink is not None else {}),
        )
        result = coordinator.run()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["stop_reason"] == "completed" else 1


def main(argv=None):
    """Dispatch only the explicitly selected registration or live-run operation."""
    args = build_parser().parse_args(argv)
    try:
        if args.command == "freeze-live":
            return _freeze(args)
        if args.command == "authorize-live":
            return _authorize(args)
        return _run(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc) if isinstance(exc, ValueError) else type(exc).__name__}),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
