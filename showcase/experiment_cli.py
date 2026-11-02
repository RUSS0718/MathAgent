"""CLI parser and local command routing for frozen experiment Runs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


class InvocationAuthorization:
    """One-command authorization bound to the exact manifest, evidence, and Run."""

    def __init__(self, manifest_sha256: str, evidence_kind: str, run_id: str) -> None:
        self.manifest_sha256 = manifest_sha256
        self.evidence_kind = evidence_kind
        self.run_id = run_id
        self._used = False

    def authorize(self, manifest_sha256: str, evidence_kind: str, run_id: str) -> bool:
        allowed = (
            not self._used
            and manifest_sha256 == self.manifest_sha256
            and evidence_kind == self.evidence_kind
            and run_id == self.run_id
        )
        self._used = True
        return allowed


def add_experiment_parser(subparsers: Any) -> None:
    experiment = subparsers.add_parser("experiment", help="frozen experiment Run controls")
    actions = experiment.add_subparsers(dest="action", required=True)

    for action in ("preflight", "run", "resume"):
        command = actions.add_parser(action)
        command.add_argument("--manifest", type=Path, required=action != "resume")
        command.add_argument("--sha256", required=True)
        command.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))
        command.add_argument("--applied-config", type=Path, required=True)
        command.add_argument("--sample-root", type=Path, required=True)
        command.add_argument("--sample-map", type=Path, required=True)
        if action in {"run", "resume"}:
            command.add_argument("--run-id", required=True)
            command.add_argument("--authorize-sha256", required=True)
            command.add_argument("--authorize-evidence-kind", required=True)

    status = actions.add_parser("status")
    status.add_argument("--run-id", required=True)
    status.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))

    verify = actions.add_parser("verify")
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))

    export = actions.add_parser("export")
    export.add_argument("--run-id", required=True)
    export.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))
    export.add_argument("--output", type=Path, required=True)


def execute_experiment_command(
    args: argparse.Namespace,
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    dependencies = dict(context or {})
    from .experiment_runner import load_manifest, preflight_manifest, read_status
    from .experiment_samples import FileSampleHashResolver, load_sample_map
    from .experiment_sources import FileAppliedModelConfig, source_identity
    from .experiment_transport import ExperimentTransportAdapter

    if args.action == "status":
        return read_status(args.run_id, output_root=args.output_root), 0

    if args.action == "verify":
        from .experiment_verification import verify_experiment_run

        status = read_status(args.run_id, output_root=args.output_root)
        records = status.get("run_records")
        client = dependencies.get("read_client")
        if records and client is None:
            client = _create_read_client(args)
        result = verify_experiment_run(
            args.run_id,
            output_root=args.output_root,
            read_client=client,
        )
        return result, 0 if result["status"] == "PASS" else 1

    if args.action == "export":
        from .experiment_verification import export_experiment_report

        result = export_experiment_report(
            args.run_id,
            output_root=args.output_root,
            output=args.output,
        )
        return result, 0 if result["status"] == "PASS" else 1

    manifest = load_manifest(args.manifest) if args.action != "resume" else None
    dependencies.setdefault("current_source", source_identity())
    dependencies.setdefault("transport_adapter", ExperimentTransportAdapter())
    if "trusted_model_config" not in dependencies:
        dependencies["trusted_model_config"] = FileAppliedModelConfig(args.applied_config)
    if "sample_resolver" not in dependencies:
        dependencies["sample_resolver"] = FileSampleHashResolver(
            args.sample_root, load_sample_map(args.sample_map)
        )
    if args.action in {"run", "resume"}:
        dependencies.setdefault(
            "job_adapter_factory",
            lambda: _create_public_job_adapter(args, dependencies, manifest),
        )

    if args.action == "preflight":
        result = preflight_manifest(
            manifest,
            expected_sha256=args.sha256,
            current_source=dependencies["current_source"],
            trusted_model_config=dependencies.get("trusted_model_config"),
            sample_resolver=dependencies.get("sample_resolver"),
            transport_adapter=dependencies["transport_adapter"],
        )
        return result, 0 if result["ready"] else 1

    if "authorization" not in dependencies:
        raise ValueError("experiment_invocation_confirmation_required")
    from .experiment_execution import resume_batch, run_batch

    if args.action == "run":
        result = run_batch(
            manifest,
            expected_sha256=args.sha256,
            run_id=args.run_id,
            output_root=args.output_root,
            context=dependencies,
        )
    else:
        result = resume_batch(
            args.run_id,
            expected_sha256=args.sha256,
            output_root=args.output_root,
            context=dependencies,
        )
    return result, 0


def confirm_cli_invocation(args: argparse.Namespace) -> InvocationAuthorization:
    """Require a terminal confirmation bound to the exact frozen Run tuple."""
    from .experiment_execution_state import load_registered_manifest
    from .experiment_manifest import is_executable_evidence_kind, manifest_digest
    from .experiment_runner import load_manifest

    manifest = (
        load_manifest(args.manifest)
        if args.action == "run"
        else load_registered_manifest(Path(args.output_root) / args.run_id)
    )
    digest = manifest_digest(manifest)
    if not is_executable_evidence_kind(manifest["evidence_kind"]):
        raise ValueError("experiment_evidence_kind_unavailable")
    if (
        manifest["evidence_kind"] == "provider_live"
        and manifest["authorization"]["execution_authorized"] is not True
    ):
        raise ValueError("experiment_live_authorization_required")
    if (
        digest != args.sha256
        or digest != args.authorize_sha256
        or manifest["evidence_kind"] != args.authorize_evidence_kind
    ):
        raise ValueError("experiment_invocation_authorization_mismatch")
    if not sys.stdin.isatty():
        raise ValueError("experiment_terminal_confirmation_required")
    phrase = f"authorize {digest} {manifest['evidence_kind']} {args.run_id}"
    print(f"Type '{phrase}' to authorize this invocation:", file=sys.stderr)
    if sys.stdin.readline().rstrip("\r\n") != phrase:
        raise ValueError("experiment_invocation_confirmation_mismatch")
    return InvocationAuthorization(digest, manifest["evidence_kind"], args.run_id)


def _create_public_job_adapter(
    args: argparse.Namespace, dependencies: dict[str, Any], manifest: dict[str, Any] | None
) -> Any:
    from .cli import ShowcaseClient
    from .experiment_execution_state import load_registered_manifest
    from .experiment_job_adapter import PublicExperimentJobAdapter

    runtime_manifest = manifest or load_registered_manifest(Path(args.output_root) / args.run_id)
    client = ShowcaseClient(args.base_url, args.cookie_file, args.timeout)
    return PublicExperimentJobAdapter(
        client,
        runtime_manifest,
        dependencies["trusted_model_config"],
        dependencies["sample_resolver"],
        dependencies["transport_adapter"],
    )


def _create_read_client(args: argparse.Namespace) -> Any:
    """Bootstrap the existing authenticated client for read-only evidence GETs."""
    from .cli import ShowcaseClient

    client = ShowcaseClient(args.base_url, args.cookie_file, args.timeout)
    client.bootstrap()
    return client
