"""Regression for nested qualification consuming an outer module cleanup."""

import io
import unittest
from unittest.mock import patch

from showcase import star_experiment_server
from tests import test_star_experiment


class ExperimentImageLifetimeTest(unittest.TestCase):
    def test_nested_qualification_keeps_built_image_until_outer_module_teardown(self):
        original = star_experiment_server.CONTRACT_PYTHON_IMAGE_ID
        built = "sha256:" + "a" * 64
        self.addCleanup(setattr, star_experiment_server, "CONTRACT_PYTHON_IMAGE_ID", original)
        with patch.object(test_star_experiment, "ensure_star_experiment_image", return_value=built):
            test_star_experiment.setUpModule()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromName(
                "tests.test_star_experiment_registration.ExperimentRegistrationTest"
            )
            result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
            self.assertTrue(result.wasSuccessful())
            self.assertEqual(built, star_experiment_server.CONTRACT_PYTHON_IMAGE_ID)
        finally:
            teardown = getattr(test_star_experiment, "tearDownModule", None)
            if teardown is not None:
                teardown()
        self.assertEqual(original, star_experiment_server.CONTRACT_PYTHON_IMAGE_ID)

class ExperimentFailureDiagnosticTest(unittest.TestCase):
    def test_public_admission_category_is_fixed_and_private_messages_are_hidden(self):
        from showcase.star_experiment_diagnostics import failure_diagnostic

        self.assertEqual(
            {"code": "experiment_public_admission_failed", "status": 503,
             "public_code": "star_prerequisites_unverified"},
            failure_diagnostic(ValueError(
                "experiment_public_admission_failed status=503 code=star_prerequisites_unverified")),
        )
        for message in ("secret prompt and credential", "experiment_conditions_mismatch secret"):
            self.assertEqual({"code": "unclassified"}, failure_diagnostic(ValueError(message)))
        self.assertEqual("unknown", failure_diagnostic(ValueError(
            "experiment_public_admission_failed status=403 code=private_secret"))["public_code"])

    def test_coordinator_preserves_fixed_admission_diagnostic_in_result_and_archive(self):
        import json
        import tempfile
        import threading
        from pathlib import Path
        from unittest.mock import Mock

        from showcase.star_experiment import ExperimentCoordinator

        with tempfile.TemporaryDirectory() as folder:
            coordinator = object.__new__(ExperimentCoordinator)
            coordinator.path = Path(folder) / "round"
            coordinator.frozen = {"independent_oracles": {}, "schedule": []}
            coordinator.qualification = Mock(report={})
            coordinator.qualification.require.side_effect = ValueError(
                "experiment_public_admission_failed status=503 code=star_prerequisites_unverified")
            coordinator.evidence_kind = "scripted"
            coordinator._canceled = threading.Event()
            coordinator.manifest_sha256 = "fixture"
            result = coordinator.run(None)
            expected = {"code": "experiment_public_admission_failed", "status": 503,
                        "public_code": "star_prerequisites_unverified"}
            self.assertEqual("experiment_defect:ValueError", result["stop_reason"])
            self.assertEqual(expected, result["failure_diagnostic"])
            failure = json.loads((coordinator.path / "failure.json").read_text())
            self.assertEqual(expected, failure["diagnostic"])
