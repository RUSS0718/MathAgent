from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from showcase.experiment_manifest import manifest_digest
from showcase.experiment_sources import source_identity
from showcase.experiment_transport import profile_fingerprint
from showcase.stream_preference import VERIFIED_STREAM_PROFILES, profile_set_fingerprint
from tests.test_showcase_experiment_cli import _manifest


class ExperimentCliProcessTest(unittest.TestCase):
    def _inputs(self, root: Path) -> tuple[dict, list[str]]:
        manifest = _manifest(source_identity())
        manifest["transport"] = {
            "policy": "stream_first",
            "profile_set_fingerprint": profile_set_fingerprint(),
            "calls": [
                {
                    "call_id": "explore",
                    "profile_fingerprint": profile_fingerprint(VERIFIED_STREAM_PROFILES[0]),
                }
            ],
        }
        digest = manifest_digest(manifest)
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        config_path = root / "applied-config.json"
        config_path.write_text(
            json.dumps({"schema_version": 1, "model": manifest["model"]}),
            encoding="utf-8",
        )
        sample_root = root / "samples"
        sample_root.mkdir()
        (sample_root / "sample.txt").write_bytes(b"x+1=2\n")
        sample_map_path = root / "sample-map.json"
        sample_map_path.write_text(
            json.dumps({"sample-01": {"input": "sample.txt", "text": "sample.txt"}}),
            encoding="utf-8",
        )
        common = [
            "experiment",
            "preflight",
            "--manifest",
            str(manifest_path),
            "--sha256",
            digest,
            "--applied-config",
            str(config_path),
            "--sample-root",
            str(sample_root),
            "--sample-map",
            str(sample_map_path),
            "--output-root",
            str(root / "runs"),
        ]
        return manifest, common

    def _run_child(
        self,
        args: list[str],
        source: str,
        *,
        env: dict[str, str] | None = None,
        input_data: str = "",
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", source, *args],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONUTF8": "1", **(env or {})},
            capture_output=True,
            input=input_data,
            text=True,
            timeout=20,
            check=False,
        )

    def test_public_main_preflight_uses_explicit_inputs_without_constructing_client(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _manifest_value, args = self._inputs(Path(temporary))
            child = """
import os
import sys
import json
import hashlib
import showcase.cli as cli
import showcase.experiment_cli as experiment_cli
manifest_path = sys.argv[sys.argv.index('--manifest') + 1]
manifest = json.loads(open(manifest_path, encoding='utf-8').read())
model = {key: manifest['model'][key] for key in (
    'name', 'thinking_mode', 'temperature', 'max_output_tokens',
    'request_timeout_seconds', 'retry')}
projection = {
    'schema_version': 1, 'status': 'available', 'model': model,
    'solver_modes': [manifest['model']['solver_mode']],
    'verification_modes': [manifest['model']['verification_mode']],
    'transport': {'policy': manifest['transport']['policy'],
                  'profile_set_fingerprint': manifest['transport']['profile_set_fingerprint']},
}
projection['config_sha256'] = hashlib.sha256(json.dumps(
    projection, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
def fetch(base_url, timeout):
    assert base_url == 'http://127.0.0.1:8090'
    assert timeout == 1200.0
    return {'applied_model_config': projection}
experiment_cli.fetch_public_capabilities = fetch
class ForbiddenClient:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('showcase_client_constructed')
cli.ShowcaseClient = ForbiddenClient
raise SystemExit(cli.main(sys.argv[1:]))
"""
            result = self._run_child(args, child)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ready"])
        self.assertEqual(0, report["dispatch_count"])
        self.assertNotIn("x+1=2", result.stdout + result.stderr)

    def test_preflight_fails_closed_when_server_applied_config_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _manifest_value, args = self._inputs(Path(temporary))
            result = self._run_child(
                args,
                "import showcase.experiment_cli as e; e.fetch_public_capabilities = lambda *_: {}; "
                "import sys; from showcase.cli import main; raise SystemExit(main(sys.argv[1:]))",
            )

        self.assertEqual(1, result.returncode)
        report = json.loads(result.stdout)
        self.assertEqual(["experiment_server_model_config_mismatch"], report["errors"])
        self.assertEqual(0, report["dispatch_count"])
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_run_rejects_non_tty_before_registration_or_client_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, args = self._inputs(root)
            args[1] = "run"
            args.extend(
                [
                    "--run-id",
                    "cli-run-01",
                    "--authorize-sha256",
                    manifest_digest(manifest),
                    "--authorize-evidence-kind",
                    manifest["evidence_kind"],
                ]
            )
            child = """
import sys
import showcase.cli as cli
real_run = cli.run
def observed_run(args, *, experiment_context=None):
    with open(__import__('os').environ['EVENTS'], 'a', encoding='utf-8') as stream:
        stream.write('run\\n')
    return real_run(args, experiment_context=experiment_context)
cli.run = observed_run
class ForbiddenClient:
    def __init__(self, *args, **kwargs):
        raise AssertionError('client_bootstrap_before_confirmation')
cli.ShowcaseClient = ForbiddenClient
raise SystemExit(cli.main(sys.argv[1:]))
"""
            run_dir = root / "runs" / "cli-run-01"
            events_path = root / "events.txt"
            result = self._run_child(args, child, env={"EVENTS": str(events_path)})

        self.assertEqual(1, result.returncode)
        self.assertEqual(
            {"error": "experiment_terminal_confirmation_required"}, json.loads(result.stderr)
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(run_dir.exists())
        self.assertFalse(events_path.exists())
        self.assertNotIn("x+1=2", result.stdout + result.stderr)

    def test_tty_confirmation_precedes_lazy_bootstrap_after_registration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, args = self._inputs(root)
            manifest["evidence_kind"] = "provider_live"
            manifest["authorization"]["execution_authorized"] = True
            digest = manifest_digest(manifest)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            args[1] = "run"
            args[5] = digest
            args.extend(
                [
                    "--run-id",
                    "cli-run-01",
                    "--authorize-sha256",
                    digest,
                    "--authorize-evidence-kind",
                    "provider_live",
                ]
            )
            run_dir = root / "runs" / "cli-run-01"
            events_path = root / "events.txt"
            child = """
import os
import sys
import showcase.cli as cli
import showcase.experiment_cli as experiment_cli
import json
import hashlib
manifest = json.loads(open(sys.argv[sys.argv.index('--manifest') + 1], encoding='utf-8').read())
model = {key: manifest['model'][key] for key in (
    'name', 'thinking_mode', 'temperature', 'max_output_tokens',
    'request_timeout_seconds', 'retry')}
projection = {
    'schema_version': 1, 'status': 'available', 'model': model,
    'solver_modes': [manifest['model']['solver_mode']],
    'verification_modes': [manifest['model']['verification_mode']],
    'transport': {'policy': manifest['transport']['policy'],
                  'profile_set_fingerprint': manifest['transport']['profile_set_fingerprint']},
}
projection['config_sha256'] = hashlib.sha256(json.dumps(
    projection, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
experiment_cli.fetch_public_capabilities = lambda *_: {'applied_model_config': projection}
real_stdin = sys.stdin
class TtyInput:
    def isatty(self): return True
    def readline(self): return real_stdin.readline()
sys.stdin = TtyInput()
real_confirm = cli.confirm_cli_invocation
def observed_confirm(args):
    authorization = real_confirm(args)
    with open(os.environ['EVENTS'], 'a', encoding='utf-8') as stream:
        stream.write('authorized\\n')
    return authorization
cli.confirm_cli_invocation = observed_confirm
class ObservedClient:
    def __init__(self, *args, **kwargs):
        status = __import__('json').loads(open(os.environ['STATUS'], encoding='utf-8').read())
        assert status['phase'] == 'starting'
        with open(os.environ['EVENTS'], 'a', encoding='utf-8') as stream:
            stream.write('client-created\\n')
    def bootstrap(self):
        with open(os.environ['EVENTS'], 'a', encoding='utf-8') as stream:
            stream.write('bootstrap\\n')
        raise ValueError('experiment_bootstrap_timing_probe')
cli.ShowcaseClient = ObservedClient
raise SystemExit(cli.main(sys.argv[1:]))
"""
            env = {"EVENTS": str(events_path), "STATUS": str(run_dir / "status.json")}
            result = self._run_child(
                args,
                child,
                env=env,
                input_data=f"authorize {digest} {manifest['evidence_kind']} cli-run-01\n",
            )
            self.assertEqual(1, result.returncode, result.stderr)
            self.assertEqual(
                {"error": "experiment_bootstrap_timing_probe"},
                json.loads(result.stderr.splitlines()[-1]),
            )
            self.assertNotIn("Traceback", result.stderr)
            self.assertTrue((run_dir / "manifest.json").is_file())
            self.assertEqual(
                ["authorized", "client-created", "bootstrap"],
                events_path.read_text(encoding="utf-8").splitlines(),
            )
            self.assertNotIn("x+1=2", result.stdout + result.stderr)

    def test_wrong_tty_confirmation_stops_before_registration_or_client(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest, args = self._inputs(root)
            args[1] = "run"
            digest = manifest_digest(manifest)
            args.extend(
                [
                    "--run-id",
                    "cli-run-01",
                    "--authorize-sha256",
                    digest,
                    "--authorize-evidence-kind",
                    manifest["evidence_kind"],
                ]
            )
            run_dir = root / "runs" / "cli-run-01"
            child = """
import sys
import showcase.cli as cli
real_stdin = sys.stdin
class TtyInput:
    def isatty(self): return True
    def readline(self): return real_stdin.readline()
sys.stdin = TtyInput()
raise SystemExit(cli.main(sys.argv[1:]))
"""
            result = self._run_child(args, child, input_data="wrong\n")

        self.assertEqual(1, result.returncode)
        self.assertEqual(
            {"error": "experiment_invocation_confirmation_mismatch"},
            json.loads(result.stderr.splitlines()[-1]),
        )
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(run_dir.exists())

    def test_applied_config_rejects_unallowlisted_credential_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _manifest_value, args = self._inputs(root)
            config_path = root / "applied-config.json"
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["api_key"] = "must-not-be-accepted-or-printed"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            child = """
import sys
import showcase.cli as cli
class ForbiddenClient:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('showcase_client_constructed')
cli.ShowcaseClient = ForbiddenClient
raise SystemExit(cli.main(sys.argv[1:]))
"""
            result = self._run_child(args, child)

        self.assertEqual(1, result.returncode)
        self.assertIn("experiment_model_config_invalid", result.stderr)
        self.assertEqual(1, len(result.stderr.splitlines()))
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("must-not-be-accepted-or-printed", result.stdout + result.stderr)
        self.assertNotIn("api_key", result.stdout + result.stderr)

    def test_malformed_manifest_reports_one_safe_error_line(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _manifest_value, args = self._inputs(root)
            manifest_path = root / "manifest.json"
            manifest_path.write_text('{"prompt":"do-not-print-this-payload",', encoding="utf-8")
            result = self._run_child(
                args,
                "import sys; from showcase.cli import main; raise SystemExit(main(sys.argv[1:]))",
            )

        self.assertEqual(1, result.returncode)
        self.assertEqual({"error": "experiment_manifest_unreadable"}, json.loads(result.stderr))
        self.assertEqual(1, len(result.stderr.splitlines()))
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("do-not-print-this-payload", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
