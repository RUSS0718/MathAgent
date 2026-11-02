from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def _manifest(source_identity: dict[str, object]) -> dict[str, object]:
    sample_bytes = b"x+1=2\n"
    sample_hash = hashlib.sha256(sample_bytes).hexdigest()
    return {
        "schema_version": 1,
        "manifest_id": "demo-run-01",
        "evidence_kind": "scripted",
        "source_identity": source_identity,
        "model": {
            "name": "intern-s2",
            "thinking_mode": True,
            "temperature": 0.2,
            "max_output_tokens": 512,
            "request_timeout_seconds": 60,
            "retry": 0,
            "solver_mode": "star_reference",
            "verification_mode": "auto",
        },
        "transport": {
            "policy": "stream_first",
            "profile_set_fingerprint": "c" * 64,
            "calls": [{"call_id": "explore", "profile_fingerprint": "d" * 64}],
        },
        "samples": [
            {
                "id": "sample-01",
                "source_ref": "sample-01",
                "type": "simple",
                "input_sha256": sample_hash,
                "text_sha256": sample_hash,
            }
        ],
        "run_limits": {
            "max_model_calls": 2,
            "max_http_attempts": 3,
            "max_tool_calls": 1,
            "max_tokens": 4096,
            "max_runtime_seconds": 120,
        },
        "batch_limits": {
            "runs": 1,
            "logical_calls": 2,
            "http_attempts": 3,
            "tool_calls": 1,
            "charged_tokens": 4096,
            "wall_seconds": 120,
        },
        "stop_on": [
            "unknown_transport",
            "incomplete_or_unresolved_usage",
            "failure",
            "cancel",
            "hard_limit",
            "source_or_config_change",
            "ledger_or_binding_defect",
        ],
        "authorization": {"scope": "demo-run-01", "execution_authorized": False},
    }


class ExperimentManifestTest(unittest.TestCase):
    def test_manifest_digest_is_canonical_and_schema_is_strict(self) -> None:
        from showcase.experiment_manifest import manifest_digest, validate_manifest

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)

        self.assertEqual(
            manifest_digest(manifest), manifest_digest(dict(reversed(list(manifest.items()))))
        )
        self.assertEqual(manifest, validate_manifest(manifest))
        invalid = dict(manifest, unreviewed_default=True)
        with self.assertRaisesRegex(ValueError, "experiment_manifest_invalid"):
            validate_manifest(invalid)

    def test_transport_manifest_binds_policy_profile_set_and_each_call(self) -> None:
        from showcase.experiment_manifest import validate_manifest

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        for transport in (
            {
                "policy": "legacy",
                "profile_set_fingerprint": "c" * 64,
                "calls": [{"call_id": "explore", "profile_fingerprint": "d" * 64}],
            },
            {
                "policy": "legacy",
                "transport": "nonstream",
                "profile_set_fingerprint": "c" * 64,
                "calls": [
                    {
                        "call_id": "explore",
                        "transport": "nonstream",
                        "reason": "provider_profile_unverified",
                    }
                ],
            },
            {"policy": "stream_first", "profile_set_fingerprint": "c" * 64, "calls": []},
            {
                "policy": "stream_first",
                "profile_set_fingerprint": "c" * 64,
                "calls": [{"call_id": "explore", "profile_fingerprint": "bad"}],
            },
            {
                "policy": "stream_first",
                "profile_set_fingerprint": "c" * 64,
                "calls": [
                    {"call_id": "explore", "profile_fingerprint": "d" * 64},
                    {"call_id": "explore", "profile_fingerprint": "e" * 64},
                ],
            },
        ):
            with self.subTest(transport=transport):
                manifest = _manifest(source)
                manifest["transport"] = transport
                with self.assertRaisesRegex(ValueError, "experiment_manifest_invalid"):
                    validate_manifest(manifest)

    def test_legacy_nonstream_manifest_is_a_distinct_frozen_policy(self) -> None:
        from showcase.experiment_manifest import manifest_digest, validate_manifest

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        stream = _manifest(source)
        legacy = _manifest(source)
        legacy["transport"] = {
            "policy": "legacy",
            "transport": "nonstream",
            "profile_set_fingerprint": "c" * 64,
            "calls": [
                {
                    "call_id": "explore",
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "capability_limit": "verified_stream_profiles_empty",
                }
            ],
        }

        self.assertEqual(legacy, validate_manifest(legacy))
        self.assertNotEqual(manifest_digest(stream), manifest_digest(legacy))

    def test_sample_refs_reject_local_paths(self) -> None:
        from showcase.experiment_manifest import validate_manifest

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        for reference in (
            "../tests/test.md",
            "tests/test.md",
            "C:\\private\\prompt.txt",
            "/private/prompt.txt",
            ".env",
            "artifacts/raw/prompt.txt",
            "file:///private/prompt.txt",
        ):
            with self.subTest(reference=reference):
                invalid = _manifest(source)
                invalid["samples"][0]["source_ref"] = reference
                with self.assertRaisesRegex(ValueError, "experiment_manifest_invalid"):
                    validate_manifest(invalid)


class ExperimentSourceIdentityTest(unittest.TestCase):
    def test_all_file_readers_reject_reserved_path_before_open(self) -> None:
        from showcase.experiment_runner import load_manifest
        from showcase.experiment_sources import (
            FileAppliedModelConfig,
            is_sensitive_path,
            load_sample_map,
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reserved = root / "tests" / "test.md"
            reserved.parent.mkdir()
            reserved.write_text("fixture only", encoding="utf-8")
            relative = Path("tests") / "test.md"
            windows_case = str(reserved).replace("/", "\\").upper()

            self.assertTrue(is_sensitive_path(relative))
            self.assertTrue(is_sensitive_path(windows_case))

            original_open = Path.open

            def reject_reserved_open(path: Path, *args, **kwargs):
                normalized = str(path).replace("\\", "/").casefold()
                if normalized.endswith("/tests/test.md"):
                    raise AssertionError("reserved fixture was opened")
                return original_open(path, *args, **kwargs)

            previous_cwd = Path.cwd()
            import os

            os.chdir(root)
            try:
                for reader in (
                    lambda: load_manifest(relative),
                    lambda: FileAppliedModelConfig(relative),
                    lambda: load_sample_map(relative),
                ):
                    with patch.object(Path, "open", reject_reserved_open):
                        with self.assertRaises(ValueError):
                            reader()
                with patch.object(Path, "open", reject_reserved_open):
                    with self.assertRaises(ValueError):
                        load_manifest(reserved)
                    with self.assertRaises(ValueError):
                        FileAppliedModelConfig(reserved)
                    with self.assertRaises(ValueError):
                        load_sample_map(reserved)
            finally:
                os.chdir(previous_cwd)

    def test_source_changes_are_detected_but_reserved_markdown_is_never_read(self) -> None:
        from showcase.experiment_sources import source_identity

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "showcase").mkdir()
            (root / "tests").mkdir()
            source = root / "showcase" / "experiment_runner.py"
            source.write_text("VERSION = 1\n", encoding="utf-8")
            reserved = root / "tests" / "test.md"
            reserved.write_text("private reserved content", encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
            )
            subprocess.run(["git", "config", "user.name", "Experiment test"], cwd=root, check=True)
            subprocess.run(["git", "add", "showcase/experiment_runner.py"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)

            original_read_bytes = Path.read_bytes

            def guarded_read_bytes(path: Path) -> bytes:
                if path == reserved:
                    raise AssertionError("reserved test file was read")
                return original_read_bytes(path)

            with patch.object(Path, "read_bytes", guarded_read_bytes):
                clean = source_identity(root)
                reserved.write_text("changed reserved content", encoding="utf-8")
                reserved_only = source_identity(root)
                self.assertEqual(clean, reserved_only)
                source.write_text("VERSION = 2\n", encoding="utf-8")
                changed = source_identity(root)

            self.assertEqual("clean", clean["dirty_status"])
            self.assertEqual("dirty", changed["dirty_status"])
            self.assertEqual(["showcase/experiment_runner.py"], changed["dirty_paths"])
            self.assertNotEqual(clean["source_sha256"], changed["source_sha256"])


class ExperimentRegistrationTest(unittest.TestCase):
    def test_preflight_rejects_unapproved_execution_evidence_kinds(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest
        from showcase.experiment_sources import FileSampleHashResolver, StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        for evidence_kind in ("live", "arbitrary"):
            manifest = _manifest(source)
            manifest["evidence_kind"] = evidence_kind
            with (
                self.subTest(evidence_kind=evidence_kind),
                tempfile.TemporaryDirectory() as temporary,
            ):
                root = Path(temporary)
                (root / "sample.txt").write_bytes(b"x+1=2\n")
                result = preflight_manifest(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    current_source=source,
                    trusted_model_config=StaticModelConfigAdapter(manifest["model"]),
                    sample_resolver=FileSampleHashResolver(
                        root, {"sample-01": {"input": "sample.txt", "text": "sample.txt"}}
                    ),
                    transport_adapter=MockTransportAdapter(),
                )
            self.assertFalse(result["ready"])
            self.assertEqual("failed", result["checks"]["evidence_kind"])
            self.assertIn("experiment_evidence_kind_unavailable", result["errors"])
            self.assertEqual(0, result["dispatch_count"])

    def test_provider_live_preflight_requires_manifest_authorization(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest
        from showcase.experiment_sources import FileSampleHashResolver, StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["evidence_kind"] = "provider_live"
        manifest["authorization"]["execution_authorized"] = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "sample.txt").write_bytes(b"x+1=2\n")
            result = preflight_manifest(
                manifest,
                expected_sha256=manifest_digest(manifest),
                current_source=source,
                trusted_model_config=StaticModelConfigAdapter(manifest["model"]),
                sample_resolver=FileSampleHashResolver(
                    root, {"sample-01": {"input": "sample.txt", "text": "sample.txt"}}
                ),
                transport_adapter=MockTransportAdapter(),
            )
            self.assertTrue(result["ready"])

            manifest["authorization"]["execution_authorized"] = False
            denied = preflight_manifest(
                manifest,
                expected_sha256=manifest_digest(manifest),
                current_source=source,
                trusted_model_config=StaticModelConfigAdapter(manifest["model"]),
                sample_resolver=FileSampleHashResolver(
                    root, {"sample-01": {"input": "sample.txt", "text": "sample.txt"}}
                ),
                transport_adapter=MockTransportAdapter(),
            )
        self.assertFalse(denied["ready"])
        self.assertIn("experiment_live_authorization_required", denied["errors"])

    def test_registration_is_immutable_and_status_is_machine_readable(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest, read_status, register_run
        from showcase.experiment_sources import FileSampleHashResolver, StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["samples"][0]["source_ref"] = "https://example.invalid/problem/1"
        from showcase.experiment_manifest import validate_manifest

        self.assertEqual(manifest, validate_manifest(manifest))
        manifest["samples"][0]["source_ref"] = "sample-01"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data_root = root / "samples"
            (data_root / "problems").mkdir(parents=True)
            (data_root / "problems" / "one.txt").write_bytes(b"x+1=2\n")
            sample_resolver = FileSampleHashResolver(
                data_root,
                {"sample-01": {"input": "problems/one.txt", "text": "problems/one.txt"}},
            )
            model_config = StaticModelConfigAdapter(manifest["model"])
            transport = MockTransportAdapter()
            preflight = preflight_manifest(
                manifest,
                expected_sha256=manifest_digest(manifest),
                current_source=source,
                trusted_model_config=model_config,
                sample_resolver=sample_resolver,
                transport_adapter=transport,
            )
            self.assertTrue(preflight["ready"])
            self.assertEqual(0, preflight["dispatch_count"])
            self.assertTrue(all(value == "passed" for value in preflight["checks"].values()))

            registered = register_run(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id="run-01",
                output_root=root,
                current_source=source,
                trusted_model_config=model_config,
                sample_resolver=sample_resolver,
                transport_adapter=transport,
            )
            status = read_status("run-01", output_root=root)

            self.assertEqual(registered, status)
            self.assertEqual("registered", status["phase"])
            self.assertEqual(0, status["completed"])
            self.assertEqual(1, status["total"])
            self.assertIsNone(status["stop_reason"])
            self.assertEqual([], status["log_tail"])
            self.assertIsInstance(status["pid"], int)
            self.assertTrue(status["process_created_at"].endswith("Z"))
            self.assertTrue((root / "run-01" / "manifest.json").is_file())

            with self.assertRaisesRegex(ValueError, "experiment_run_exists"):
                register_run(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id="run-01",
                    output_root=root,
                    current_source=source,
                    trusted_model_config=model_config,
                    sample_resolver=sample_resolver,
                    transport_adapter=transport,
                )

    def test_preflight_leaves_unverified_model_and_samples_unchecked(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        result = preflight_manifest(
            manifest,
            expected_sha256=manifest_digest(manifest),
            current_source=source,
            trusted_model_config=None,
            sample_resolver=None,
            transport_adapter=None,
        )

        self.assertFalse(result["ready"])
        self.assertEqual("not_checked", result["checks"]["model"])
        self.assertEqual("not_checked", result["checks"]["samples"])
        self.assertEqual(0, result["dispatch_count"])

    def test_preflight_fails_when_trusted_model_or_sample_hashes_differ(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest
        from showcase.experiment_sources import FileSampleHashResolver, StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        with tempfile.TemporaryDirectory() as temporary:
            data_root = Path(temporary)
            (data_root / "sample.txt").write_bytes(b"different content")
            result = preflight_manifest(
                manifest,
                expected_sha256=manifest_digest(manifest),
                current_source=source,
                trusted_model_config=StaticModelConfigAdapter(
                    dict(manifest["model"], name="other")
                ),
                sample_resolver=FileSampleHashResolver(
                    data_root,
                    {"sample-01": {"input": "sample.txt", "text": "sample.txt"}},
                ),
                transport_adapter=MockTransportAdapter(),
            )

        self.assertFalse(result["ready"])
        self.assertEqual("failed", result["checks"]["model"])
        self.assertEqual("failed", result["checks"]["samples"])
        self.assertEqual(0, result["dispatch_count"])

    def test_preflight_rejects_provider_retry_configuration(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_runner import preflight_manifest
        from showcase.experiment_sources import StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["model"]["retry"] = 1
        result = preflight_manifest(
            manifest,
            expected_sha256=manifest_digest(manifest),
            current_source=source,
            trusted_model_config=StaticModelConfigAdapter(manifest["model"]),
            sample_resolver=None,
            transport_adapter=MockTransportAdapter(),
        )

        self.assertFalse(result["ready"])
        self.assertEqual("failed", result["checks"]["retry"])
        self.assertIn("experiment_retry_unsupported", result["errors"])
        self.assertEqual(0, result["dispatch_count"])

    def test_sample_resolver_rejects_sensitive_paths_and_symlinks_outside_root(self) -> None:
        from showcase.experiment_sources import FileSampleHashResolver

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "data"
            root.mkdir()
            (root / "problems").mkdir()
            (root / "problems" / "safe.txt").write_bytes(b"safe\n")
            outside = Path(temporary) / "outside.txt"
            outside.write_bytes(b"secret prompt\n")
            for relative in (
                "../outside.txt",
                "tests/test.md",
                ".env",
                "artifacts/raw/prompt.txt",
            ):
                with self.subTest(relative=relative):
                    resolver = FileSampleHashResolver(
                        root,
                        {"sample-01": {"input": relative, "text": relative}},
                    )
                    with patch.object(
                        Path, "read_bytes", side_effect=AssertionError("unexpected read")
                    ) as read:
                        with self.assertRaisesRegex(ValueError, "experiment_sample_source_invalid"):
                            resolver.hashes({"source_ref": "sample-01"})
                        read.assert_not_called()

            candidate = root / "problems" / "escape.txt"
            candidate.write_bytes(b"internal placeholder")
            resolver = FileSampleHashResolver(
                root,
                {"sample-01": {"input": "problems/escape.txt", "text": "problems/escape.txt"}},
            )
            original_resolve = Path.resolve

            def escaped_resolve(path: Path, strict: bool = False) -> Path:
                if path == candidate:
                    return outside
                return original_resolve(path, strict=strict)

            with patch.object(Path, "resolve", new=escaped_resolve):
                with patch.object(
                    Path, "read_bytes", side_effect=AssertionError("unexpected read")
                ) as read:
                    with self.assertRaisesRegex(ValueError, "experiment_sample_source_invalid"):
                        resolver.hashes({"source_ref": "sample-01"})
                    read.assert_not_called()


class MockTransportAdapter:
    def validate_manifest_transport(self, transport: dict[str, object]) -> None:
        self.transport = transport


class ExperimentTransportAdapterTest(unittest.TestCase):
    @staticmethod
    def _controlled_profile():
        from showcase.stream_preference import StreamProfile

        return StreamProfile(
            endpoint="http://127.0.0.1:5000/api/v1/chat/completions",
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(("user", ("content", "role")),),
            evidence_kind="controlled_test",
            status="controlled_test",
        )

    def _transport(self, profile):
        from showcase.experiment_transport import profile_fingerprint
        from showcase.stream_preference import profile_set_fingerprint, select_transport

        client = SimpleNamespace(
            api_base=profile.endpoint,
            model=profile.model,
            thinking_mode=profile.thinking_mode,
            loopback_only=True,
        )
        adapter = SimpleNamespace(
            _get_client=lambda: client,
            model_id=profile.model,
            temperature=profile.temperature,
            max_tokens=profile.max_tokens,
            thinking_mode=profile.thinking_mode,
            stream_complete=lambda *_args, **_kwargs: iter(()),
        )
        decision = select_transport(
            adapter,
            [{"role": "user", "content": "controlled"}],
            policy="stream_first",
            profiles=(profile,),
        )
        return {
            "policy": "stream_first",
            "profile_set_fingerprint": profile_set_fingerprint((profile,)),
            "calls": [
                {
                    "call_id": "explore",
                    "profile_fingerprint": decision.get("profile_fingerprint")
                    or profile_fingerprint(profile),
                }
            ],
        }

    def test_transport_adapter_accepts_only_exact_controlled_profile_identities(self) -> None:
        from showcase.experiment_transport import StreamFirstTransportAdapter

        profile = self._controlled_profile()
        adapter = StreamFirstTransportAdapter(profiles=(profile,))
        transport = self._transport(profile)
        adapter.validate_manifest_transport(transport)

        wrong_set = dict(transport, profile_set_fingerprint="0" * 64)
        with self.assertRaisesRegex(ValueError, "experiment_transport_profile_invalid"):
            adapter.validate_manifest_transport(wrong_set)
        wrong_call = dict(
            transport, calls=[{"call_id": "explore", "profile_fingerprint": "1" * 64}]
        )
        with self.assertRaisesRegex(ValueError, "experiment_transport_profile_invalid"):
            adapter.validate_manifest_transport(wrong_call)

    def test_transport_adapter_rejects_unregistered_provider_live_claim(self) -> None:
        from showcase.experiment_transport import ExperimentTransportAdapter
        from showcase.stream_preference import StreamProfile

        claimed = StreamProfile(
            endpoint="https://chat.intern-ai.org.cn/api/v1/chat/completions",
            model="intern-s2",
            temperature=0.2,
            max_tokens=256,
            thinking_mode=True,
            messages_schema=(("user", ("content", "role")),),
            evidence_kind="provider_live",
            status="provider_live_verified",
        )
        with self.assertRaisesRegex(ValueError, "experiment_transport_profile_invalid"):
            ExperimentTransportAdapter(profiles=(claimed,))

    def test_transport_adapter_accepts_explicit_legacy_nonstream_run_separately(self) -> None:
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_transport import ExperimentTransportAdapter
        from showcase.stream_preference import profile_set_fingerprint

        transport = {
            "policy": "legacy",
            "transport": "nonstream",
            "profile_set_fingerprint": profile_set_fingerprint(()),
            "calls": [
                {
                    "call_id": "explore",
                    "transport": "nonstream",
                    "reason": "provider_profile_unverified",
                    "capability_limit": "verified_stream_profiles_empty",
                }
            ],
        }
        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        manifest["transport"] = transport
        adapter = ExperimentTransportAdapter(profiles=())

        adapter.validate_manifest_transport(transport)
        self.assertEqual(64, len(manifest_digest(manifest)))
        invalid = dict(transport, calls=[dict(transport["calls"][0], reason="unspecified")])
        with self.assertRaisesRegex(ValueError, "experiment_transport_profile_invalid"):
            adapter.validate_manifest_transport(invalid)


class ExperimentCliTest(unittest.TestCase):
    def test_parser_accepts_preflight_run_status_and_resume(self) -> None:
        from showcase.cli import build_parser

        parser = build_parser()
        inputs = [
            "--applied-config",
            "config.json",
            "--sample-root",
            "samples",
            "--sample-map",
            "map.json",
        ]
        cases = (
            (
                ["experiment", "preflight", "--manifest", "m.json", "--sha256", "a" * 64, *inputs],
                "preflight",
            ),
            (
                [
                    "experiment",
                    "run",
                    "--manifest",
                    "m.json",
                    "--sha256",
                    "a" * 64,
                    "--run-id",
                    "run-01",
                    "--authorize-sha256",
                    "a" * 64,
                    "--authorize-evidence-kind",
                    "scripted",
                    *inputs,
                ],
                "run",
            ),
            (["experiment", "status", "--run-id", "run-01"], "status"),
            (
                [
                    "experiment",
                    "resume",
                    "--run-id",
                    "run-01",
                    "--sha256",
                    "a" * 64,
                    "--authorize-sha256",
                    "a" * 64,
                    "--authorize-evidence-kind",
                    "scripted",
                    *inputs,
                ],
                "resume",
            ),
        )
        for argv, action in cases:
            with self.subTest(action=action):
                args = parser.parse_args(argv)
                self.assertEqual("experiment", args.command)
                self.assertEqual(action, args.action)

    def test_preflight_cli_does_not_construct_remote_client(self) -> None:
        from showcase.cli import build_parser, run

        args = build_parser().parse_args(
            [
                "experiment",
                "preflight",
                "--manifest",
                "missing.json",
                "--sha256",
                "a" * 64,
                "--applied-config",
                "config.json",
                "--sample-root",
                "samples",
                "--sample-map",
                "map.json",
            ]
        )
        with patch(
            "showcase.cli.ShowcaseClient", side_effect=AssertionError("remote client created")
        ):
            with self.assertRaisesRegex(ValueError, "experiment_manifest_unreadable"):
                run(args)

    def test_preflight_cli_checks_injected_trusted_inputs_without_remote_client(self) -> None:
        from showcase.cli import build_parser, run
        from showcase.experiment_manifest import manifest_digest
        from showcase.experiment_sources import FileSampleHashResolver, StaticModelConfigAdapter

        source = {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
        manifest = _manifest(source)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sample = root / "sample.txt"
            sample.write_bytes(b"x+1=2\n")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            context = {
                "current_source": source,
                "trusted_model_config": StaticModelConfigAdapter(manifest["model"]),
                "sample_resolver": FileSampleHashResolver(
                    root, {"sample-01": {"input": "sample.txt", "text": "sample.txt"}}
                ),
                "transport_adapter": MockTransportAdapter(),
            }
            args = build_parser().parse_args(
                [
                    "experiment",
                    "preflight",
                    "--manifest",
                    str(manifest_path),
                    "--sha256",
                    manifest_digest(manifest),
                    "--applied-config",
                    str(root / "config.json"),
                    "--sample-root",
                    str(root),
                    "--sample-map",
                    str(root / "map.json"),
                ]
            )
            with patch(
                "showcase.cli.ShowcaseClient", side_effect=AssertionError("remote client created")
            ):
                with patch("showcase.cli._print") as print_result:
                    result_code = run(args, experiment_context=context)

        self.assertEqual(0, result_code)
        report = print_result.call_args.args[0]
        self.assertTrue(report["ready"])
        self.assertEqual(0, report["dispatch_count"])

    def test_status_cli_does_not_construct_remote_client(self) -> None:
        from showcase.cli import build_parser, run

        args = build_parser().parse_args(["experiment", "status", "--run-id", "missing-run"])
        with patch(
            "showcase.cli.ShowcaseClient", side_effect=AssertionError("remote client created")
        ):
            with self.assertRaisesRegex(ValueError, "experiment_run_not_found"):
                run(args)


if __name__ == "__main__":
    unittest.main()
