"""Hint provenance is public; the private hint affects the actual planner."""

import json
import unittest

from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from tests.star_product_support import ACCEPT, StarJobFixture
from tests.test_star_product_planning import FEATURES, STEP
from tests.test_star_product_tools import NEED_PLAN, PLAN, VERDICT


class StarHintTest(StarJobFixture, unittest.TestCase):
    def test_meta_hint_has_separate_provenance_and_reaches_planner(self):
        self.open_star([{"hint": "Try addition"}, NEED_PLAN, PLAN, STEP, VERDICT,
                        {"final_response": "2"}, ACCEPT], SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_HINT_MODE="meta_auto",
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        self.assertEqual("preplan_hint", self.outbound[0]["action"])
        planner = next(r for r in self.outbound if r["role"] == "planner")
        self.assertEqual("Try addition", planner["preplan_hint"])
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn('"hint_source":"meta"', stream.replace(" ", ""))
        self.assertNotIn("Try addition", stream)

    def test_invalid_hints_reject_without_job_or_dispatch(self):
        self.open_star([])
        for hint in (False, [], " ", "x" * 2001):
            with self.subTest(hint=hint):
                response = self.client.post("/api/agent/jobs", json={
                    "session_id": self.session, "message": "1+1", "solver_mode": "star_limited", "solver_hint": hint,
                }, headers=self.headers())
                self.assertEqual(400, response.status_code)
        legacy_hint = self.client.post("/api/agent/jobs", json={
            "session_id": self.session, "message": "1+1", "solver_hint": "use addition",
        }, headers=self.headers())
        self.assertEqual(400, legacy_hint.status_code)
        self.assertEqual("solver_hint_invalid", legacy_hint.get_json()["code"])
        self.assertEqual([], self.outbound)
        self.assertEqual([], self.client.get("/api/agent/jobs/active").get_json()["jobs"])

    def test_user_hint_is_not_directly_projected_and_reaches_planner(self):
        hint = "Use the special addition hint"
        self.open_star([NEED_PLAN, PLAN, STEP, VERDICT, {"final_response": "2"}, ACCEPT],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        headers = self.headers()
        body = {"session_id": self.session, "message": "1+1", "solver_mode": "star_limited", "solver_hint": hint}
        response = self.client.post("/api/agent/jobs", json=body, headers=headers)
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        planner = next(r for r in self.outbound if r["role"] == "planner")
        self.assertEqual(hint, planner.get("preplan_hint"))
        self.assertEqual(409, self.client.post("/api/agent/jobs", json={**body, "solver_hint": "different"}, headers=headers).status_code)
        public_responses = [
            self.client.get(f"/api/agent/jobs/{job_id}"),
            self.client.get(f"/api/agent/jobs/{job_id}/events"),
            self.client.get(f"/api/agent/jobs/{job_id}/report"),
            self.client.get(f"/api/runs/{job_id}"),
            self.client.get(f"/api/runs/{job_id}/events"),
            self.client.get(f"/api/runs/{job_id}/report"),
            self.client.get(f"/api/runs/{job_id}/evidence"),
            self.client.get(f"/api/load_session?session={self.session}"),
        ]
        outbound_count = len(self.outbound)
        for response in public_responses:
            with self.subTest(path=response.request.path):
                self.assertEqual(200, response.status_code)
                self.assertNotIn(hint, response.get_data(as_text=True))
        self.assertEqual(outbound_count, len(self.outbound))
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn('"hint_source":"user"', stream.replace(" ", ""))

        other = self.app.test_client()
        for path in (f"/api/agent/jobs/{job_id}", f"/api/agent/jobs/{job_id}/events",
                     f"/api/agent/jobs/{job_id}/report", f"/api/load_session?session={self.session}"):
            with self.subTest(owner="unauthenticated", path=path):
                self.assertEqual(401, other.get(path).status_code)

    def test_private_hint_used_as_step_id_is_pseudonymized_in_public_outputs(self):
        # The model echoes the private hint as its internal step ID.
        hint = "PRIVATE HINT TEXT"
        plan = {**PLAN, "steps": [{**PLAN["steps"][0], "step_id": hint}]}
        self.open_star([NEED_PLAN, plan, STEP, VERDICT, {"final_response": "2"}, ACCEPT],
                       SHOWCASE_STAR_FEATURES=FEATURES,
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        response = self.client.post("/api/agent/jobs", json={
            "session_id": self.session, "message": "1+1", "solver_mode": "star_limited",
            "solver_hint": hint,
        }, headers=self.headers())
        self.assertEqual(202, response.status_code)
        job_id = response.get_json()["job_id"]
        self.assertEqual("succeeded", self.terminal(job_id)["status"])
        planner = next(request for request in self.outbound if request["role"] == "planner")
        reasoner = next(request for request in self.outbound if request["role"] == "reasoner")
        self.assertEqual(hint, planner["preplan_hint"])
        self.assertEqual(hint, reasoner["step"]["step_id"])

        public_responses = [
            self.client.get(f"/api/agent/jobs/{job_id}"),
            self.client.get(f"/api/agent/jobs/{job_id}/events"),
            self.client.get(f"/api/agent/jobs/{job_id}/report"),
            self.client.get(f"/api/runs/{job_id}"),
            self.client.get(f"/api/runs/{job_id}/events"),
            self.client.get(f"/api/runs/{job_id}/report"),
            self.client.get(f"/api/runs/{job_id}/evidence"),
        ]
        for public in public_responses:
            with self.subTest(path=public.request.path):
                self.assertEqual(200, public.status_code)
                self.assertNotIn(hint, public.get_data(as_text=True))
        stream = self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
        self.assertIn('"step_id":"步骤 1"', stream)
        self.assertNotIn(hint, stream)
        events_before = [json.loads(line[6:]) for line in stream.splitlines()
                         if line.startswith("data: ") and '"solver_event_id"' in line]
        attempts_before = self.client.get(f"/api/agent/jobs/{job_id}").get_json()["result"]["request_attempts"]

        reopened = create_app({"TESTING": True, "SHOWCASE_DATA_DIR": self.data_dir})
        try:
            second = reopened.test_client()
            second.get("/api/check_auth")
            job_again = second.get(f"/api/agent/jobs/{job_id}")
            events_again = second.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True)
            self.assertNotIn(hint, job_again.get_data(as_text=True))
            self.assertNotIn(hint, events_again)
            self.assertEqual(
                [event["solver_event_id"] for event in events_before],
                [json.loads(line[6:])["solver_event_id"] for line in events_again.splitlines()
                 if line.startswith("data: ") and '"solver_event_id"' in line],
            )
            attempts_again = job_again.get_json()["result"]["request_attempts"]
            self.assertEqual(
                sorted((item["attempt_id"], item["solver_call_id"]) for item in attempts_before),
                sorted((item["attempt_id"], item["solver_call_id"]) for item in attempts_again),
            )
        finally:
            reopened.extensions["showcase_workspace_service"].close()
            reopened.extensions["showcase_run_service"].close()
            reopened.extensions["loopback_store"].close()

    def test_meta_hint_is_bounded_before_it_reaches_the_planner(self):
        oversized = "x" * 2001
        self.open_star([{"hint": oversized}], SHOWCASE_STAR_HINT_MODE="meta_auto",
                       SHOWCASE_STAR_BUDGET=RunBudgetLimits(max_model_calls=8, max_http_attempts=8))
        job_id = self.create_job()
        job = self.terminal(job_id)
        self.assertEqual("failed", job["status"])
        self.assertEqual(["meta"], [request["role"] for request in self.outbound])
        self.assertNotIn(oversized, self.client.get(f"/api/agent/jobs/{job_id}/events").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
