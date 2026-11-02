"""Executable E0/E3 qualification; saved reports alone cannot authorize live."""

import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from .star_experiment_archive import source_identity
from .star_experiment_registration import digest, registration
from .star_replay import replay_saved_batch

_EXECUTED = object()


def qualify(saved_batch, *, original_runner_version, manifest, manifest_sha256, evidence_kind="live"):
    """RB08 calls this before constructing a paid-provider coordinator.

    Scripted qualification runs a focused real public regression; live requires
    the complete RB06 matrix including real Docker/process and mutation checks.
    Both actually replay the supplied hash-checked archive with zero dispatch.
    """
    registration(manifest, expected_sha256=manifest_sha256)
    if evidence_kind not in {"live", "scripted"}:
        raise ValueError("experiment_evidence_kind_invalid")
    replay = replay_saved_batch(saved_batch, original_runner_version=original_runner_version)
    from tests.rb06_e3 import CASES

    cases = [*CASES, "tests.test_star_acceptance", "tests.test_star_result_history",
             "tests.test_star_experiment_registration", "tests.test_star_experiment"] if evidence_kind == "live" else [
        "tests.test_star_rb03_obligations.ProofObligationJobTest."
        "test_complete_explore_preserves_explanation_in_three_real_requests"]
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromNames(cases))
    mutations, mutation_log = None, io.StringIO()
    if evidence_kind == "live" and result.wasSuccessful() and not result.skipped:
        from tests.rb06_mutations import main
        with redirect_stdout(mutation_log):
            main()  # Crashes and wrong failures raise; never converted into PASS.
        mutations = 5
    report = dict(registration_sha256=manifest_sha256, evidence_kind=evidence_kind, source=source_identity(), replay=replay,
                  tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  skips=len(result.skipped), expected_failures=len(result.expectedFailures),
                  unexpected_successes=len(result.unexpectedSuccesses), mutations=mutations,
                  log=output.getvalue(), mutation_log=mutation_log.getvalue())
    valid = (replay["integrity"] == "verified" and replay["external_dispatches"] == 0
             and replay["selection"]["review_bound"] and result.testsRun > 0
             and result.wasSuccessful() and not result.skipped and not result.expectedFailures)
    if evidence_kind == "live":
        original_job = json.loads((Path(saved_batch) / "job.json").read_text(encoding="utf-8"))
        valid = (valid and mutations == 5 and replay["selection"]["proof_delivered"]
                 and original_job.get("job_id") == "run_e21ce7d7cc6fe22863896d4d21254d98")
    return Qualification(report, valid, _authority=_EXECUTED)


class Qualification:
    """In-process result of actual qualification, checked again before dispatch."""

    def __init__(self, report, valid, *, _authority=None):
        if _authority is not _EXECUTED:
            raise ValueError("qualification_requires_executed_gates")
        self.report, self.valid = report, valid
        self.identity = digest(report)

    def require(self, evidence_kind, manifest_sha256):
        if (self.report.get("registration_sha256") != manifest_sha256 or not self.valid or digest(self.report) != self.identity
                or self.report["source"] != source_identity()
                or self.report["evidence_kind"] != evidence_kind):
            raise ValueError("experiment_prerequisites_unverified")
