"""Trusted Showcase configuration for the opt-in Python tool."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from showcase.profile import SHOWCASE_PROFILE
from showcase.star_product_runtime import create_star_product_pipeline

IMAGE = "sha256:" + "a" * 64


class StarProductRuntimeTest(unittest.TestCase):
    def test_python_is_unavailable_without_explicit_server_image_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ):
                os.environ.pop("SHOWCASE_STAR_PYTHON_IMAGE_ID", None)
                pipeline = create_star_product_pipeline("unused.sqlite3", storage_root=Path(folder),
                    config={"SHOWCASE_STAR_ENABLED": True})
        self.assertIsNone(pipeline.registry)
        self.assertNotIn("python_math", pipeline.config["allowed_tools"])

    def test_exact_local_image_configuration_registers_isolated_python(self):
        with tempfile.TemporaryDirectory() as folder:
            pipeline = create_star_product_pipeline("unused.sqlite3", storage_root=Path(folder),
                config={"SHOWCASE_STAR_ENABLED": True, "SHOWCASE_STAR_PYTHON_IMAGE_ID": IMAGE})
            tools = pipeline.registry.describe()
            self.assertEqual(["polynomial_check", "python_math"], [tool["name"] for tool in tools])
            self.assertEqual(["calculation", "isolated_mathematical_python"], tools[1]["capabilities"])
            self.assertEqual([SHOWCASE_PROFILE], tools[1]["allowed_profiles"])
            self.assertEqual(20.0, tools[1]["timeout_seconds"])
            self.assertEqual(["polynomial_check", "python_math"], pipeline.config["allowed_tools"])
            self.assertTrue(pipeline.config["features"]["final_generation"])
            self.assertTrue(pipeline.config["features"]["final_solution_review"])
            self.assertEqual(2, pipeline.budget.max_tool_calls)
            self.assertEqual(Path(folder) / "tool_artifacts", pipeline.registry.container_python_executor.artifacts.root)

    def test_config_rejects_tags_and_non_digest_image_values(self):
        for value in ("mathagent-python:sp09", "python:3.11-slim", "C:/tmp/image.tar", "sha256:xyz"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                with self.assertRaisesRegex(ValueError, "star_python_image_id_invalid"):
                    create_star_product_pipeline("unused.sqlite3", storage_root=Path(folder),
                        config={"SHOWCASE_STAR_ENABLED": True, "SHOWCASE_STAR_PYTHON_IMAGE_ID": value})


if __name__ == "__main__":
    unittest.main()
