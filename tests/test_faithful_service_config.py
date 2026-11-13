"""Unified service configuration must preserve admission and public boundaries."""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tests.test_faithful_s03_job import CAPACITY_POLICY


class FaithfulServiceConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "service.json"
        self.value = {
            "version": "faithful-service-v1",
            "python_image_id": "sha256:" + "a" * 64,
            "context_capacity": CAPACITY_POLICY,
            "budget": {"max_model_calls": 48, "max_http_attempts": 48,
                       "max_tool_calls": 8, "max_tokens": 262144,
                       "max_runtime_seconds": 1100},
        }

    def load(self):
        from showcase.faithful_service_config import load_faithful_config

        self.path.write_text(json.dumps(self.value), encoding="utf-8")
        return load_faithful_config(self.path)

    def test_serial_features_are_added_to_core(self):
        from showcase.star_product_config import CORE_FEATURES

        config = self.load()
        features = config["SHOWCASE_STAR_FULL_FEATURES"]
        for name in CORE_FEATURES | {"stream_activity", "context_pack", "problem_spec",
                                     "progress_scheduling", "proof_graph", "serial_routes"}:
            self.assertIs(features[name], True, name)
        self.assertNotIn("concurrent_routes", features)
        self.assertTrue(config["SHOWCASE_PRESENTATION_ENABLED"])
        self.assertTrue(config["SHOWCASE_F7_SYSTEM_VIEW_ENABLED"])
        self.assertNotIn("SHOWCASE_FORMAL_BACKEND", config)
        self.assertFalse(config["SHOWCASE_POPULATION_MEMORY_ENABLED"])

    def test_missing_or_invalid_prerequisites_are_rejected(self):
        for field in ("budget", "python_image_id", "context_capacity"):
            with self.subTest(field=field):
                saved = self.value.pop(field)
                with self.assertRaises(ValueError):
                    self.load()
                self.value[field] = saved
        self.value["python_image_id"] = "latest"
        with self.assertRaises(ValueError):
            self.load()

    def test_population_requires_verified_capacity(self):
        self.value["population"] = {"capacity": {
            "service_id": "intern", "max_inflight": 2, "worker_slots": 2,
            "evidence_ref": "controlled-fixture", "status": "controlled"},
            "budget": self.value["budget"]}
        with self.assertRaisesRegex(ValueError, "population_capacity_unverified"):
            self.load()

    def test_unknown_fields_and_versions_are_rejected(self):
        self.value["credential"] = "must-not-be-accepted"
        with self.assertRaises(ValueError):
            self.load()
        del self.value["credential"]
        self.value["version"] = "future"
        with self.assertRaises(ValueError):
            self.load()

    def test_population_timeout_is_explicit_and_preserves_root_limits(self):
        self.value["population"] = {"capacity": {
            "service_id": "intern", "max_inflight": 2, "worker_slots": 2,
            "evidence_ref": "existing-two-slot-observation", "status": "verified"},
            "budget": self.value["budget"], "request_timeout_seconds": 30}
        config = self.load()
        self.assertEqual(30, config["SHOWCASE_STAR_POPULATION_REQUEST_TIMEOUT_SECONDS"])
        self.assertEqual(1100, config["SHOWCASE_STAR_FULL_BUDGET"].max_runtime_seconds)
        self.assertEqual(180, config["SHOWCASE_STAR_ADAPTER"].client_timeout)
        for invalid in (0, True, 181, float("inf")):
            self.value["population"]["request_timeout_seconds"] = invalid
            with self.subTest(timeout=invalid), self.assertRaises(ValueError):
                self.load()

    def test_cli_defaults_preserved_and_fake_config_rejected(self):
        from showcase.server_cli import parse_server_args

        args, config = parse_server_args([])
        self.assertEqual("fake", config["SHOWCASE_MODE"])
        self.assertEqual(8090, args.port)
        self.assertFalse(config["SHOWCASE_STAR_FULL_ENABLED"])
        with self.assertRaises(SystemExit):
            parse_server_args(["--faithful-config", str(self.path)])

    def test_cli_loads_explicit_live_configuration(self):
        from showcase.server_cli import parse_server_args

        self.load()
        _, config = parse_server_args(["--mode", "live", "--faithful-config",
                                       str(self.path), "--data-dir", self.temp.name])
        self.assertTrue(config["SHOWCASE_STAR_FULL_ENABLED"])
        self.assertTrue(config["SHOWCASE_FAITHFUL_INTERVENTION_ENABLED"])
        self.assertEqual(self.temp.name, config["SHOWCASE_DATA_DIR"])

    def test_check_requires_explicit_configuration(self):
        from showcase.server_cli import parse_server_args

        with self.assertRaises(SystemExit):
            parse_server_args(["--check-runtime"])

    def test_runtime_check_rejects_missing_stream_adapter_without_dispatch(self):
        from showcase.adapters import InternModelAdapter
        from showcase.faithful_service_check import check_runtime
        from showcase.flask_app import create_app
        from showcase.request_transport import INTERN_S2_LIVE_ENDPOINT

        config = self.load()
        config["SHOWCASE_STAR_ADAPTER"] = InternModelAdapter(
            max_tokens=32768, thinking_mode=False, client_timeout=180, client_retry=3)
        with patch.dict(os.environ, {"INTERN_API_KEY": "controlled-only",
                                    "INTERN_MODEL": "intern-s2",
                                    "INTERN_API_BASE": INTERN_S2_LIVE_ENDPOINT}), patch(
                "showcase.star_product_readiness.isolated_readiness",
                return_value={"available": True, "reason": None}), patch(
                "llm_client.requests.post") as outbound:
            app = create_app({**config, "TESTING": True, "SHOWCASE_DATA_DIR": self.temp.name,
                              "SHOWCASE_WORKER_ENABLED": False})
            output = io.StringIO()
            with redirect_stdout(output):
                code = check_runtime(app)
            self.assertEqual(1, code, output.getvalue())
            self.assertIn("stream_adapter_unavailable", output.getvalue())
            outbound.assert_not_called()
