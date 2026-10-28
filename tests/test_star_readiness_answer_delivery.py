"""Offline acceptance cases for the optional public answer output."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import run_star_readiness_97 as cli
from showcase.star_readiness_answer_delivery import AnswerOutput
from showcase.star_readiness_coordinator import StarReadinessCoordinator
from showcase.star_readiness_registration import digest
from tests import test_star_readiness_coordinator as support


class AnswerDeliveryTest(unittest.TestCase):
    def test_paths_outside_artifacts_or_inside_archive_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            archive = artifacts / "archive"
            for path in (root / "outside.jsonl", archive / "answers.jsonl", archive):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    AnswerOutput(path, artifacts=artifacts, archive=archive)
                self.assertFalse(path.exists())

    def test_answer_directory_cannot_be_the_current_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "issue-97-answers"
            with self.assertRaises(ValueError):
                with AnswerOutput(archive / "answers.jsonl", artifacts=root, archive=archive):
                    pass
            self.assertFalse(archive.exists())

    def test_historical_archive_is_not_an_answer_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old_archive = root / "old-archive"
            old_archive.mkdir()
            (old_archive / "registration.json").write_text("{}", encoding="utf-8")
            answer = old_archive / "answers.jsonl"
            with self.assertRaises(ValueError):
                with AnswerOutput(answer, artifacts=root, archive=root / "new-archive"):
                    pass
            self.assertFalse(answer.exists())

    def test_dedicated_answer_directory_cannot_itself_be_an_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            answer_dir = root / "issue-97-answers"
            answer_dir.mkdir()
            answer = answer_dir / "answers.jsonl"
            for marker in ("registration.json", "result.json", "hashes.json"):
                marker_path = answer_dir / marker
                marker_path.write_text("{}", encoding="utf-8")
                with self.subTest(marker=marker), self.assertRaises(ValueError):
                    with AnswerOutput(answer, artifacts=root, archive=root / "new-archive"):
                        pass
                self.assertFalse(answer.exists())
                marker_path.unlink()

    def test_nested_or_arbitrary_answer_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for answer in (root / "answers.jsonl",
                           root / "issue-97-answers" / "nested" / "answers.jsonl"):
                with self.subTest(answer=answer), self.assertRaises(ValueError):
                    with AnswerOutput(answer, artifacts=root, archive=root / "new-archive"):
                        pass
                self.assertFalse(answer.exists())

    def test_cli_rejects_existing_output_before_building_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            output = root / "issue-97-answers" / "answers.jsonl"
            output.parent.mkdir()
            output.write_text("keep", encoding="utf-8")
            args = cli.build_parser().parse_args([
                "run-live", "--manifest", str(manifest), "--manifest-sha256", digest({}),
                "--archive", str(root / "archive"), "--answer-output", str(output),
                "--execute-live",
            ])
            with patch.object(cli, "ARTIFACTS", root), patch.object(cli, "_build_adapter") as build:
                with self.assertRaises(ValueError):
                    cli._run(args)
                build.assert_not_called()
            self.assertEqual("keep", output.read_text(encoding="utf-8"))

    def test_cli_rejects_historical_archive_before_building_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            old_archive = root / "old-archive"
            old_archive.mkdir()
            (old_archive / "registration.json").write_text("{}", encoding="utf-8")
            output = old_archive / "answer.jsonl"
            args = cli.build_parser().parse_args([
                "run-live", "--manifest", str(manifest), "--manifest-sha256", digest({}),
                "--archive", str(root / "new-archive"), "--answer-output", str(output),
                "--execute-live",
            ])
            with patch.object(cli, "ARTIFACTS", root), patch.object(cli, "_build_adapter") as build:
                with self.assertRaises(ValueError):
                    cli._run(args)
                build.assert_not_called()
            self.assertFalse(output.exists())

    def test_only_nonempty_public_answers_are_written_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "issue-97-answers" / "answers.jsonl"
            with AnswerOutput(path, artifacts=root, archive=root / "archive") as sink:
                sink("simple-01", "job-1", "  ")
                sink("simple-01", "job-1", None)
                sink("simple-01", "job-1", "答案 4\n")
            self.assertEqual(
                [{"question_id": "simple-01", "job_id": "job-1", "final_response": "答案 4\n"}],
                [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()],
            )
            with self.assertRaises(ValueError):
                AnswerOutput(path, artifacts=root, archive=root / "archive")


class CoordinatorAnswerDeliveryTest(unittest.TestCase):
    def setUp(self):
        support.StarReadinessCoordinatorTest.setUp(self)

    def test_output_failure_stops_without_another_dispatch_or_leaking_error_text(self):
        coordinator = StarReadinessCoordinator(
            self.coordinator.path, adapters=self.coordinator.adapters,
            manifest=self.manifest, manifest_sha256=self.coordinator.manifest_sha256,
            answer_sink=Mock(side_effect=OSError("private answer and credential")),
        )
        result = coordinator.run()
        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual(1, len(support.ScriptedServer.instances[0].dispatched))
        self.assertEqual("OSError", result["failure_type"])
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertEqual(1, result["usage"]["http_attempts"])
        self.assertEqual(["job-1"], support.ScriptedServer.instances[0].provenance_calls)
        self.assertEqual(1, self.delivery_mock.call_count)
        self.assertTrue((coordinator.path / "run-00.json").is_file())
        self.assertTrue((coordinator.path / "delivery-00.json").is_file())
        self.assertEqual("retained", result["runtime_storage_cleanup"])
        runtime = self.folder / "artifacts" / result["runtime_storage_path"]
        retention = json.loads((runtime / "retention.json").read_text(encoding="utf-8"))
        self.assertEqual("answer_delivery_failed", retention["reason"])
        for artifact in coordinator.path.glob("*.json"):
            self.assertNotIn("private answer and credential", artifact.read_text(encoding="utf-8"))

    def test_output_failure_preserves_unknown_usage_and_stops(self):
        support.ScriptedServer.scenario = "unknown"
        coordinator = StarReadinessCoordinator(
            self.coordinator.path, adapters=self.coordinator.adapters,
            manifest=self.manifest, manifest_sha256=self.coordinator.manifest_sha256,
            answer_sink=Mock(side_effect=OSError("private")),
        )
        result = coordinator.run()
        self.assertEqual("failure", result["stop_reason"])
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertEqual(8192, result["usage"]["reserved_tokens"])
        self.assertTrue((coordinator.path / "run-00.json").is_file())
        self.assertTrue((coordinator.path / "delivery-00.json").is_file())
        self.assertEqual(1, len(support.ScriptedServer.instances[0].dispatched))

    def test_output_failure_after_recovered_dispatch_keeps_evidence(self):
        support.ScriptedServer.scenario = "dispatch_response_lost"
        coordinator = StarReadinessCoordinator(
            self.coordinator.path, adapters=self.coordinator.adapters,
            manifest=self.manifest, manifest_sha256=self.coordinator.manifest_sha256,
            answer_sink=Mock(side_effect=OSError("private")),
        )
        result = coordinator.run()
        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual(17, result["usage"]["charged_tokens"])
        self.assertEqual([], result["unresolved_dispatches"])
        self.assertEqual("retained", result["runtime_storage_cleanup"])
        self.assertTrue((coordinator.path / "delivery-00.json").is_file())
        self.assertEqual(1, len(support.ScriptedServer.instances[0].dispatched))

    def test_failed_terminal_job_still_saves_public_answer(self):
        support.ScriptedServer.scenario = "failed"
        path = self.folder / "artifacts" / "issue-97-answers" / "failed.jsonl"
        with AnswerOutput(path, artifacts=self.folder / "artifacts", archive=self.coordinator.path) as sink:
            coordinator = StarReadinessCoordinator(
                self.coordinator.path, adapters=self.coordinator.adapters,
                manifest=self.manifest, manifest_sha256=self.coordinator.manifest_sha256,
                answer_sink=sink,
            )
            result = coordinator.run()
        self.assertEqual("failure", result["stop_reason"])
        self.assertEqual(1, len(support.ScriptedServer.instances[0].dispatched))
        self.assertEqual("fixture answer", json.loads(path.read_text(encoding="utf-8"))["final_response"])
        for artifact in coordinator.path.glob("*.json"):
            self.assertNotIn("fixture answer", artifact.read_text(encoding="utf-8"))

    def test_collect_delivers_before_cleanup_and_archive_stays_sanitized(self):
        path = self.folder / "artifacts" / "issue-97-answers" / "answers.jsonl"
        with AnswerOutput(path, artifacts=self.folder / "artifacts", archive=self.coordinator.path) as output:
            sink = Mock(side_effect=output)
            coordinator = StarReadinessCoordinator(
                self.coordinator.path, adapters=self.coordinator.adapters,
                manifest=self.manifest, manifest_sha256=self.coordinator.manifest_sha256,
                answer_sink=sink,
            )
            def cleanup(*args, **kwargs):
                self.assertEqual(2, sink.call_count)
                self.assertEqual(2, len(path.read_text(encoding="utf-8").splitlines()))
                return support.cleanup_runtime_storage(*args, **kwargs)
            with patch("showcase.star_readiness_coordinator.cleanup_runtime_storage", side_effect=cleanup):
                result = coordinator.run()
        self.assertEqual("completed", result["stop_reason"])
        answers = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["simple-01", "multi-01"], [item["question_id"] for item in answers])
        self.assertEqual(["fixture answer"] * 2, [item["final_response"] for item in answers])
        for artifact in coordinator.path.glob("*.json"):
            text = artifact.read_text(encoding="utf-8")
            self.assertNotIn("fixture answer", text)
            self.assertNotIn("Compute 2 + 2.", text)


if __name__ == "__main__":
    unittest.main()
