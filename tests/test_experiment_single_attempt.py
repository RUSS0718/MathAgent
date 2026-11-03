from __future__ import annotations

import tempfile
import unittest

from showcase.experiment_manifest import manifest_digest
from showcase.experiment_runner import preflight_manifest
from tests.test_showcase_experiment_execution import (
    _context,
    _context_for_run,
    _JobAdapter,
    _manifest,
)


def _provider_live_manifest():
    manifest = _manifest(
        {
            "revision": "a" * 40,
            "source_sha256": "b" * 64,
            "dirty_status": "clean",
            "dirty_paths": [],
        }
    )
    manifest["evidence_kind"] = "provider_live"
    manifest["authorization"]["execution_authorized"] = True
    return manifest


def _preflight(manifest):
    context = _context(manifest, _JobAdapter())
    return preflight_manifest(
        manifest,
        expected_sha256=manifest_digest(manifest),
        current_source=context["current_source"],
        trusted_model_config=context["trusted_model_config"],
        server_model_config=context["server_model_config"],
        sample_resolver=context["sample_resolver"],
        transport_adapter=context["transport_adapter"],
    )


class ExperimentSingleAttemptTest(unittest.TestCase):
    def test_provider_live_retry_one_passes_public_preflight(self):
        manifest = _provider_live_manifest()
        manifest["model"]["retry"] = 1

        result = _preflight(manifest)

        self.assertTrue(result["ready"], result["errors"])
        self.assertEqual("passed", result["checks"]["retry"])
        self.assertEqual(0, result["dispatch_count"])

    def test_provider_live_retry_one_dispatches_one_public_job(self):
        from showcase.experiment_execution import run_batch

        manifest = _provider_live_manifest()
        manifest["model"]["retry"] = 1
        adapter = _JobAdapter()
        run_id = "run-single-attempt"

        with tempfile.TemporaryDirectory() as temporary:
            result = run_batch(
                manifest,
                expected_sha256=manifest_digest(manifest),
                run_id=run_id,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, run_id),
            )

        self.assertEqual("completed", result["phase"])
        self.assertEqual(1, result["completed"])
        self.assertEqual(1, adapter.submissions)

    def test_unknown_dispatch_is_not_replayed_during_resume(self):
        from showcase.experiment_execution import resume_batch, run_batch

        manifest = _provider_live_manifest()
        manifest["model"]["retry"] = 1
        adapter = _JobAdapter(ambiguous=True)
        run_id = "run-single-attempt-unknown"
        digest = manifest_digest(manifest)
        factory_calls = []
        context = _context_for_run(manifest, adapter, run_id)
        context["job_adapter_factory"] = lambda: factory_calls.append(True) or adapter

        with tempfile.TemporaryDirectory() as temporary:
            first = run_batch(
                manifest,
                expected_sha256=digest,
                run_id=run_id,
                output_root=temporary,
                context=context,
            )
            resumed = resume_batch(
                run_id,
                expected_sha256=digest,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, run_id),
            )

        self.assertEqual("unknown_dispatch", first["stop_reason"])
        self.assertEqual("unknown_dispatch", resumed["stop_reason"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual([True], factory_calls)

    def test_retry_two_is_rejected_before_job_adapter_construction(self):
        from showcase.experiment_execution import run_batch

        manifest = _provider_live_manifest()
        manifest["model"]["retry"] = 2
        adapter = _JobAdapter()
        run_id = "run-retry-two"
        context = _context_for_run(manifest, adapter, run_id)
        factory_calls = []
        context["job_adapter_factory"] = lambda: factory_calls.append(True) or adapter

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "experiment_retry_unsupported"):
                run_batch(
                    manifest,
                    expected_sha256=manifest_digest(manifest),
                    run_id=run_id,
                    output_root=temporary,
                    context=context,
                )

        self.assertEqual([], factory_calls)
        self.assertEqual(0, adapter.submissions)

    def test_safe_resume_accepts_provider_live_retry_one_without_redispatch(self):
        from showcase.experiment_execution import resume_batch, run_batch

        manifest = _provider_live_manifest()
        manifest["model"]["retry"] = 1
        adapter = _JobAdapter([{"status": "running"}, {"status": "succeeded"}])
        run_id = "run-single-attempt-resume"
        digest = manifest_digest(manifest)

        with tempfile.TemporaryDirectory() as temporary:
            first = run_batch(
                manifest,
                expected_sha256=digest,
                run_id=run_id,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, run_id),
            )
            resumed = resume_batch(
                run_id,
                expected_sha256=digest,
                output_root=temporary,
                context=_context_for_run(manifest, adapter, run_id),
            )

        self.assertEqual("running", first["phase"])
        self.assertEqual("completed", resumed["phase"])
        self.assertEqual(1, adapter.submissions)
        self.assertEqual(1, resumed["completed"])


if __name__ == "__main__":
    unittest.main()
