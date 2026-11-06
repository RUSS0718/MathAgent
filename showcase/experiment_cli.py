"""CLI parser and local command routing for frozen experiment Runs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


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

    pair_verify = actions.add_parser("pair-verify", help="read-only verification of a saved pair")
    pair_verify.add_argument("--pair-id", required=True)
    pair_verify.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))

    pair = actions.add_parser("pair", help="record readiness-gated pair admission")
    pair.add_argument("--manifest", type=Path, required=True)
    pair.add_argument("--sha256", required=True)
    pair.add_argument("--authorize-sha256", required=True)
    pair.add_argument("--authorize-evidence-kind", required=True)
    pair.add_argument("--readiness-report", type=Path, required=True)
    pair.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))
    pair.add_argument("--applied-config", type=Path, required=True)
    pair.add_argument("--sample-root", type=Path, required=True)
    pair.add_argument("--sample-map", type=Path, required=True)


def execute_experiment_command(
    args: argparse.Namespace,
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    dependencies = dict(context or {})
    from .experiment_runner import load_manifest, preflight_manifest, read_status
    from .experiment_samples import FileSampleHashResolver, load_sample_map
    from .experiment_sources import (
        FileAppliedModelConfig,
        StaticServerAppliedModelConfigAdapter,
        source_identity,
    )
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

    if args.action == "pair-verify":
        from .experiment_pair_verification import verify_experiment_pair

        read_client = dependencies.get("read_client")
        state_path = None
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", args.pair_id):
            state_path = args.output_root / "pairs" / args.pair_id / "status.json"
        if read_client is None and state_path is not None and state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                state = {}
            dispatch_count = state.get("dispatch_count") if isinstance(state, dict) else None
            if type(dispatch_count) is int and dispatch_count > 0:
                read_client = _create_read_client(args)
        result = verify_experiment_pair(
            args.pair_id, output_root=args.output_root,
            read_client=read_client,
        )
        return result, 0 if result["status"] == "PASS" else 1

    if args.action == "pair":
        return _execute_pair_command(args, dependencies)

    manifest = load_manifest(args.manifest) if args.action != "resume" else None
    dependencies.setdefault("current_source", source_identity())
    dependencies.setdefault("transport_adapter", ExperimentTransportAdapter())
    if "trusted_model_config" not in dependencies:
        dependencies["trusted_model_config"] = FileAppliedModelConfig(args.applied_config)
    if "server_model_config" not in dependencies:
        capabilities = dependencies.get("server_capabilities")
        if capabilities is None:
            capabilities = fetch_public_capabilities(args.base_url, args.timeout)
        projection = (
            capabilities.get("applied_model_config") if isinstance(capabilities, dict) else None
        )
        dependencies["server_model_config"] = StaticServerAppliedModelConfigAdapter(projection)
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
            server_model_config=dependencies.get("server_model_config"),
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


def _execute_pair_command(
    args: argparse.Namespace, dependencies: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Run both frozen arms through public Jobs and preserve fail-closed readiness."""
    from .experiment_pair import (
        load_pair_manifest,
        load_readiness_report,
        run_pair,
    )

    pair = load_pair_manifest(args.manifest)
    try:
        receipt = load_readiness_report(args.readiness_report)
    except ValueError:
        receipt = None
    dependencies.setdefault(
        "readiness_verifier",
        lambda report: _verify_pair_readiness(args, dependencies, pair, report),
    )

    if "pair_job_adapter_factory" not in dependencies:
        dependencies["pair_runtime_preparer"] = lambda: _prepare_pair_runtime(
            args, dependencies
        )
        dependencies["pair_job_adapter_factory"] = lambda pair, arm_name, arm: (
            _create_public_pair_job_adapter(
                args, dependencies, pair, arm_name, arm, receipt
            )
        )
    dependencies.setdefault(
        "pair_arm_verifier",
        lambda run_id, *, output_root, context: _verify_pair_arm(
            run_id, pair, {**context, "cli_args": args}, output_root=output_root
        ),
    )

    result = run_pair(
        pair,
        expected_sha256=args.sha256,
        readiness_report=receipt,
        output_root=args.output_root,
        context=dependencies,
    )
    return result, 0 if result["status"] == "PASS" else 1


def _create_public_pair_job_adapter(
    args: argparse.Namespace,
    dependencies: dict[str, Any],
    pair: dict[str, Any],
    arm_name: str,
    arm: dict[str, Any],
    readiness_report: dict[str, Any] | None,
) -> Any:
    """Construct the arm adapter only after frozen Run registration begins."""
    from .experiment_job_adapter import PublicExperimentPairJobAdapter

    _prepare_pair_runtime(args, dependencies)

    client = _pair_showcase_client(args, dependencies)
    return PublicExperimentPairJobAdapter(
        client,
        arm["manifest"],
        dependencies["trusted_model_config"],
        dependencies["sample_resolver"],
        dependencies["transport_adapter"],
        pair=pair,
        arm=arm_name,
        readiness_report=readiness_report or {},
    )


def _pair_showcase_client(args: argparse.Namespace, dependencies: dict[str, Any]) -> Any:
    """Return one bootstrapped authenticated client for pair admission and Jobs."""
    from .cli import ShowcaseClient

    client = dependencies.get("showcase_client")
    if client is None:
        client = ShowcaseClient(args.base_url, args.cookie_file, args.timeout)
        dependencies["showcase_client"] = client
    client.bootstrap()
    return client


def _verify_pair_readiness(
    args: argparse.Namespace,
    dependencies: dict[str, Any],
    pair: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Ask the authenticated Showcase service to verify readiness without dispatch."""
    from .experiment_pair import pair_manifest_digest

    result = _pair_showcase_client(args, dependencies).request(
        "POST",
        f"/api/experiments/pairs/{pair['pair_id']}/readiness",
        payload={
            "pair_manifest": pair,
            "pair_sha256": pair_manifest_digest(pair),
            "readiness_report": report,
        },
    )
    return result if isinstance(result, dict) else {"status": "UNKNOWN"}


def _prepare_pair_runtime(args: argparse.Namespace, dependencies: dict[str, Any]) -> None:
    """Load trusted execution inputs lazily, after readiness admission succeeds."""
    from .experiment_samples import FileSampleHashResolver, load_sample_map
    from .experiment_sources import (
        FileAppliedModelConfig,
        StaticServerAppliedModelConfigAdapter,
        source_identity,
    )
    from .experiment_transport import ExperimentTransportAdapter

    dependencies.setdefault("current_source", source_identity())
    dependencies.setdefault("transport_adapter", ExperimentTransportAdapter())
    dependencies.setdefault("trusted_model_config", FileAppliedModelConfig(args.applied_config))
    if "server_model_config" not in dependencies:
        capabilities = dependencies.get("server_capabilities")
        if capabilities is None:
            capabilities = fetch_public_capabilities(args.base_url, args.timeout)
        projection = capabilities.get("applied_model_config") if isinstance(capabilities, dict) else None
        dependencies["server_model_config"] = StaticServerAppliedModelConfigAdapter(projection)
    dependencies.setdefault(
        "sample_resolver",
        FileSampleHashResolver(args.sample_root, load_sample_map(args.sample_map)),
    )


def _verify_pair_arm(
    run_id: str,
    pair: dict[str, Any],
    context: dict[str, Any],
    *,
    output_root: Path,
) -> dict[str, Any]:
    """Independently verify the ordinary Run and each pair-bound public Job."""
    from .experiment_pair_verification import (
        _read_sample_evidence,
        _sample_outcome,
        verify_pair_arm_component_config,
    )
    from .experiment_runner import read_status
    from .experiment_verification import verify_experiment_run

    client = context.get("read_client")
    if client is None:
        client = _pair_showcase_client(context["cli_args"], context)
    report = verify_experiment_run(run_id, output_root=output_root, read_client=client)
    arm_name = next(
        name for name in ("baseline", "variant") if pair[name]["run_id"] == run_id
    )
    run_dir = output_root / run_id
    run_status = read_status(run_id, output_root=output_root)
    expected_ids = [sample["id"] for sample in pair[arm_name]["manifest"]["samples"]]
    records = run_status.get("run_records")
    if not isinstance(records, list) or len(records) != len(expected_ids):
        return {"status": "UNKNOWN", "reason": "experiment_pair_sample_evidence_unavailable"}
    run_records = {
        item.get("sample_id"): item for item in records if isinstance(item, dict)
    }
    if len(run_records) != len(records):
        return {"status": "UNKNOWN", "reason": "experiment_pair_sample_evidence_unavailable"}
    outcomes = []
    configs = []
    for sample_id in expected_ids:
        item = _read_sample_evidence(run_dir, sample_id)
        identity = run_records.get(sample_id)
        if not isinstance(item, dict) or not isinstance(identity, dict):
            return {"status": "UNKNOWN", "reason": "experiment_pair_sample_evidence_unavailable"}
        component = verify_pair_arm_component_config(
            client, identity.get("job_id", ""), pair, arm_name
        )
        if component["status"] != "PASS":
            return {"status": component["status"], "reason": component["reason"]}
        configs.append(component["applied_component_config"])
        outcomes.append(_sample_outcome(
            item, report.get("status", "UNKNOWN"), stop_reason=report.get("stop_reason")
        ))
    if len(set(json.dumps(value, sort_keys=True) for value in configs)) != 1:
        return {"status": "FAIL", "reason": "experiment_pair_applied_config_mismatch"}
    return {
        "status": report.get("status", "UNKNOWN"),
        "reason": "experiment_pair_arm_not_verified" if report.get("status") != "PASS" else None,
        "applied_component_config": configs[0] if configs else None,
        "sample_outcomes": outcomes,
        "run_verification": report,
    }


def confirm_cli_invocation(args: argparse.Namespace) -> InvocationAuthorization:
    """Require a terminal confirmation bound to the exact frozen Run tuple."""
    from .experiment_execution_state import load_registered_manifest
    from .experiment_manifest import is_executable_evidence_kind, manifest_digest
    from .experiment_runner import load_manifest

    if args.action == "pair":
        from .experiment_pair import load_pair_manifest, pair_manifest_digest

        pair = load_pair_manifest(args.manifest)
        digest = pair_manifest_digest(pair)
        evidence_kind = pair["baseline"]["manifest"]["evidence_kind"]
        if (
            digest != args.sha256
            or digest != args.authorize_sha256
            or evidence_kind != args.authorize_evidence_kind
            or pair["variant"]["manifest"]["evidence_kind"] != evidence_kind
        ):
            raise ValueError("experiment_invocation_authorization_mismatch")
        if not is_executable_evidence_kind(evidence_kind):
            raise ValueError("experiment_evidence_kind_unavailable")
        if evidence_kind == "provider_live" and any(
            pair[name]["manifest"]["authorization"]["execution_authorized"] is not True
            for name in ("baseline", "variant")
        ):
            raise ValueError("experiment_live_authorization_required")
        if not sys.stdin.isatty():
            raise ValueError("experiment_terminal_confirmation_required")
        phrase = f"authorize {digest} {evidence_kind} {pair['pair_id']}"
        print(f"Type '{phrase}' to authorize this invocation:", file=sys.stderr)
        if sys.stdin.readline().rstrip("\r\n") != phrase:
            raise ValueError("experiment_invocation_confirmation_mismatch")
        return InvocationAuthorization(digest, evidence_kind, pair["pair_id"])

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


def fetch_public_capabilities(base_url: str, timeout: float) -> dict[str, Any]:
    """Fetch only the public capabilities route without loading cookies or credentials."""
    request = Request(
        base_url.rstrip("/") + "/api/capabilities",
        headers={"Accept": "application/json", "Cache-Control": "no-cache"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError, TimeoutError):
        raise ValueError("experiment_server_capabilities_unavailable") from None
    if not isinstance(value, dict):
        raise ValueError("experiment_server_capabilities_unavailable")
    return value


def _create_public_job_adapter(
    args: argparse.Namespace, dependencies: dict[str, Any], manifest: dict[str, Any] | None
) -> Any:
    from .cli import ShowcaseClient
    from .experiment_execution_state import load_registered_manifest
    from .experiment_job_adapter import PublicExperimentJobAdapter

    runtime_manifest = manifest or load_registered_manifest(Path(args.output_root) / args.run_id)
    client = dependencies.get("showcase_client") or ShowcaseClient(
        args.base_url, args.cookie_file, args.timeout
    )
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
