"""Public configuration snapshot checks for the #97 readiness runner."""

import copy
import unittest
from types import SimpleNamespace

from showcase.star_readiness_configuration import validate_server_configuration
from showcase.star_readiness_registration import STAR_REFERENCE_CONFIGURATION


class _Pipeline:
    def __init__(self, preset, tools, image_id):
        self.preset = preset
        self.registry = SimpleNamespace(
            describe=lambda: [{"name": name} for name in tools],
            container_python_executor=SimpleNamespace(image=image_id),
        )

    def preset_config(self, mode):
        if mode != "star_reference":
            raise AssertionError(mode)
        return copy.deepcopy(self.preset)


def _server(*, preset=None, tools=None, image_id=None):
    expected = STAR_REFERENCE_CONFIGURATION
    actual_preset = copy.deepcopy(expected["preset"] if preset is None else preset)
    actual_preset.update(
        max_model_calls=0,
        max_tool_calls=0,
        max_total_duration_seconds=0,
    )
    pipeline = _Pipeline(
        actual_preset,
        expected["registered_tools"] if tools is None else tools,
        expected["isolation_image_id"] if image_id is None else image_id,
    )
    service = SimpleNamespace(star_pipeline=pipeline)
    return SimpleNamespace(app=SimpleNamespace(extensions={
        "showcase_workspace_service": service,
    }))


class StarReadinessConfigurationTest(unittest.TestCase):
    def test_validates_and_returns_static_configuration_when_startup_budget_is_zero(self):
        expected = copy.deepcopy(STAR_REFERENCE_CONFIGURATION)

        archived = validate_server_configuration(_server(), expected)

        self.assertEqual(expected, archived)

    def test_run_budget_values_are_left_to_the_registered_policy(self):
        server = _server()
        pipeline = server.app.extensions["showcase_workspace_service"].star_pipeline
        pipeline.preset.update(
            max_model_calls=6,
            max_tool_calls=1,
            max_total_duration_seconds=300,
        )

        archived = validate_server_configuration(
            server, copy.deepcopy(STAR_REFERENCE_CONFIGURATION)
        )

        self.assertEqual(STAR_REFERENCE_CONFIGURATION, archived)

    def test_rejects_disabled_core_feature_and_tool_drift(self):
        disabled = copy.deepcopy(STAR_REFERENCE_CONFIGURATION["preset"])
        disabled["features"]["final_solution_review"] = False
        extra_tool = copy.deepcopy(STAR_REFERENCE_CONFIGURATION["registered_tools"])
        extra_tool.append("unexpected")

        for server in (_server(preset=disabled), _server(tools=extra_tool)):
            with self.subTest(server=server):
                with self.assertRaises(ValueError):
                    validate_server_configuration(
                        server, copy.deepcopy(STAR_REFERENCE_CONFIGURATION)
                    )

    def test_rejects_isolation_image_drift(self):
        with self.assertRaises(ValueError):
            validate_server_configuration(
                _server(image_id="sha256:" + "0" * 64),
                copy.deepcopy(STAR_REFERENCE_CONFIGURATION),
            )


if __name__ == "__main__":
    unittest.main()
