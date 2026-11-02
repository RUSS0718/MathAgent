"""Verify retained SQLite evidence when a public Job archive is incomplete."""

import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from showcase import star_readiness_registration as readiness_registration
from showcase.star_acceptance import evaluate_delivery
from showcase.star_experiment_archive import ExperimentArchive
from showcase.star_experiment_server import ExperimentServer
from showcase.star_readiness_configuration import validate_server_configuration
from showcase.star_readiness_coordinator import StarReadinessCoordinator
from tests.star_experiment_support import LoopbackProvider
from tests.test_star_readiness_coordinator import QUESTION_SPECS, SOURCE, frozen_manifest


class StarReadinessArchiveRetentionTest(unittest.TestCase):
    """Check Job and usage ledger retention after local archive failure."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.enterContext(patch("showcase.star_readiness_coordinator.ARTIFACTS",
                                self.folder / "artifacts"))
        self.enterContext(patch(
            "showcase.star_readiness_coordinator.current_source_identity", return_value=SOURCE
        ))
        self.enterContext(patch(
            "showcase.star_readiness_registration.QUESTION_SPECS", QUESTION_SPECS
        ))
        self.enterContext(patch(
            "showcase.star_readiness_registration.V4_QUESTION_SPECS", QUESTION_SPECS
        ))
        self.manifest = frozen_manifest()

    @unittest.skipUnless(
        os.environ.get("RUN_STAR_READINESS_DOCKER_INTEGRATION") == "1",
        "requires a Docker-enabled environment; set RUN_STAR_READINESS_DOCKER_INTEGRATION=1",
    )
    def test_delivery_archive_failure_retains_terminal_job_and_sqlite_budget_ledger(self):
        """Keep terminal Job and S3 ledger data available if delivery archival fails."""
        provider = LoopbackProvider()
        self.addCleanup(provider.close)
        original_respond = provider.respond

        def respond(context):
            serialized = json.dumps(context, ensure_ascii=False)
            question_id = "multi-01" if "2 + 3" in serialized else "simple-01"
            provider.run_keys.setdefault(context["run_id"], question_id)
            answer = "5" if question_id == "multi-01" else "4"
            role = context["role"]
            if role == "explore":
                if question_id == "multi-01":
                    return {"assessment": "NEED_PLAN", "worked": [], "failed": [], "candidates": []}
                return {"assessment": "SOLVED", "worked": [], "failed": [], "candidates": [],
                        "solution_candidate": answer}
            if role == "explore_polish":
                return {"solution_candidate": answer}
            if role == "planner":
                return {"version": 1, "steps": [{"step_id": "derive", "title": "Compute",
                        "objective": "Derive the registered result"}]}
            if role == "reasoner":
                claim = {"statement": answer, "label": "easy-verify"}
                if question_id == "multi-01":
                    claim["tool_request"] = {
                        "tool": "python_math",
                        "arguments": {"code": "print(2 + 3)\n"},
                        "scope": "finite_computation",
                        "expected_output": "5\n",
                    }
                return {"argument": f"A direct derivation gives {answer}.",
                        "claims": [claim], "blocked": False}
            if role == "step_verifier":
                return {"goal_gate": "YES", "logic_gate": "PASS", "verdict": "ACCEPT",
                        "objection": ""}
            if role == "final_generator":
                return {"final_response": f"Final answer: {answer}"}
            if role == "whole_solution_verifier":
                return {"verdict": "ACCEPT", "reason": "The registered result is supported"}
            return original_respond(context)

        provider.respond = respond
        adapter = provider.adapters()["nonstream"]
        adapter._get_client().loopback_only = True
        coordinator = StarReadinessCoordinator(
            self.folder / "delivery-archive-failure",
            adapters={"nonstream": adapter},
            manifest=self.manifest,
            manifest_sha256=readiness_registration.digest(self.manifest),
        )
        runtime_paths = []

        def create_server(*args, **kwargs):
            runtime_paths.append(Path(args[0]).parent)
            return ExperimentServer(*args, **kwargs)

        original_put = ExperimentArchive.put
        archive_puts = []
        job_posts = []
        original_post = ExperimentServer.post

        def record_job_post(server, path, payload, **kwargs):
            if path == "/api/agent/jobs":
                job_posts.append(payload)
            return original_post(server, path, payload, **kwargs)

        def fail_delivery_archive(archive, name, value):
            archive_puts.append(name)
            if name == "delivery-00.json":
                self.assertTrue((archive.path / "run-00.json").is_file())
                raise OSError("fixture_delivery_archive_failed")
            return original_put(archive, name, value)

        with (
            patch("showcase.star_readiness_coordinator.ExperimentServer",
                  side_effect=create_server),
            patch("showcase.star_readiness_coordinator.validate_server_configuration",
                  validate_server_configuration),
            patch("showcase.star_readiness_coordinator.evaluate_delivery", evaluate_delivery),
            patch.object(ExperimentServer, "post", record_job_post),
            patch.object(ExperimentArchive, "put", fail_delivery_archive),
        ):
            result = coordinator.run()

        self.assertEqual(1, len(runtime_paths))
        runtime = runtime_paths[0]
        self.assertTrue(runtime.is_dir(), f"recorded runtime was removed: {runtime}")
        self.assertEqual("retained", result["runtime_storage_cleanup"], result)
        self.assertEqual(runtime.relative_to(self.folder / "artifacts").as_posix(),
                         result["runtime_storage_path"])
        self.assertEqual("failure", result["stop_reason"], result)
        self.assertEqual("OSError", result["failure_type"], result)
        self.assertLess(archive_puts.index("run-00.json"), archive_puts.index("delivery-00.json"))
        self.assertEqual(1, len(job_posts))
        self.assertEqual(1, result["executed_runs"])
        self.assertFalse(result["usage"]["usage_complete"])
        self.assertFalse((coordinator.path / "intent-01.json").exists())
        self.assertTrue((coordinator.path / "run-00.json").is_file())

        self.assertEqual(1, len(result["uncollected"]))
        job_id = result["uncollected"][0]["job_id"]
        self.assertEqual([{"index": 0, "job_id": job_id}], result["uncollected"])
        database = runtime / "nonstream" / "showcase.sqlite3"
        self.assertTrue(database.is_file())
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
            job = connection.execute(
                "SELECT job_id,status FROM workspace_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            ledger_row = connection.execute(
                "SELECT ledger_json FROM run_budgets WHERE run_id=?", (job_id,)
            ).fetchone()

        self.assertEqual((job_id, "succeeded"), job)
        self.assertIsNotNone(ledger_row)
        self.assertEqual(
            {"reason": "job_archive_incomplete", "run_ids": [job_id]},
            json.loads((runtime / "retention.json").read_text(encoding="utf-8")),
        )
        actions = json.loads(ledger_row[0])["actions"]
        logical_actions = [action for action in actions if action["kind"] == "logical"]
        http_actions = [action for action in actions if action["kind"] == "http"]
        self.assertTrue(logical_actions)
        self.assertTrue(http_actions)
        self.assertTrue(all(action["status"] == "success" for action in http_actions))
        self.assertTrue(all(action["usage"]["total_tokens"] == 10 for action in http_actions))
        self.assertTrue(all(
            action["public_attempt"]["dispatch_status"] == "transport_observed"
            for action in http_actions
        ))


if __name__ == "__main__":
    unittest.main()
