"""Synchronous Run public report and checker binding acceptance."""
import tempfile
import unittest
from pathlib import Path

from test_graph_service import AgentSequence

from showcase.flask_app import create_app
from showcase.graph import AgentDecision, LangGraphExecutionLoop
from showcase.run_service import RunService
from showcase.tools import ToolRegistry


class SyncEvidenceContractTest(unittest.TestCase):
    def test_polynomial_candidates_do_not_establish_final_completeness(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = temporary.name
        database = Path(directory) / "runs.sqlite3"
        registry = ToolRegistry()
        registry.register_polynomial_check()
        loop = LangGraphExecutionLoop(AgentSequence([
            AgentDecision.tool("polynomial_check", {"schema_version": 1, "variable": "x", "coefficients": ["1", "-1"], "domain": {"kind": "real"}, "candidates": ["1"]}),
            AgentDecision.final("x=1"),
        ]), registry)
        service = RunService(execution_loop=loop, database_path=database)
        app = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": directory}, service=service, database_path=database)
        self.addCleanup(app.extensions["loopback_store"].close)
        self.addCleanup(service.close)
        self.addCleanup(app.extensions["showcase_workspace_service"].close)
        client = app.test_client()
        csrf = client.get("/api/check_auth").get_json()["csrf_token"]
        run = client.post("/api/runs", json={"problem": "x-1=0"}, headers={"X-CSRF-Token": csrf}).get_json()
        run_id = run["run_id"]
        check = client.get(f"/api/runs/{run_id}/evidence").get_json()["verification"]
        self.assertEqual("unknown", check["status"])
        self.assertEqual("polynomial_candidates", check["history"][0]["scope"])
        self.assertEqual("pass", check["history"][0]["candidate_status"])
        self.assertEqual("unknown", check["history"][0]["coverage_status"])
        self.assertEqual(check, run["result"]["verification"])
        events = client.get(f"/api/runs/{run_id}/events").get_json()["events"]
        self.assertEqual("unknown", next(item for item in events if item["type"] == "verification_completed")["status"])
