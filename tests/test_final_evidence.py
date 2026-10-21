"""Final artifact evidence contracts through the public Flask workspace."""
import unittest

from test_live_tool_workspace import (
    DeterministicHTTPProvider,
    LiveToolWorkspaceContractTest,
    ProviderResponse,
    _native_tool_response,
)

from showcase.tools import ToolRegistry


class FinalEvidenceContractTest(unittest.TestCase):
    _run_job = LiveToolWorkspaceContractTest._run_job

    def test_synthesis_rewrite_cannot_inherit_candidate_validation(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan"}),
            _native_tool_response("check_1", "polynomial_check", {
                "schema_version": 1, "variable": "x", "coefficients": ["1", "-1"],
                "domain": {"kind": "real"}, "candidates": ["1"],
            }),
            ProviderResponse({"content": "x=1"}),
            ProviderResponse({"content": "最终答案 x=2"}),
        ])
        result = self._run_job(provider, registry)
        check = result["evidence"]["verification"]
        self.assertEqual("unknown", check["status"])
        self.assertEqual("needs_review", check["acceptance"])
        self.assertEqual("pass", check["history"][0]["candidate_status"])
        self.assertEqual("unknown", check["history"][0]["coverage_status"])
        self.assertNotEqual(check["artifact"]["sha256"], check["history"][0]["artifact"]["sha256"])
        self.assertTrue(check["history"][0]["checker_version"])
        self.assertTrue(check["history"][0]["environment"])
        self.assertEqual(check, result["job_report"]["report"]["checks"])
        self.assertEqual(check, result["run_report"]["report"]["checks"])
        self.assertEqual(4, len(result["provider_requests"]))

    def test_same_candidate_identity_does_not_prove_complete_solution_set(self):
        registry = ToolRegistry()
        registry.register_polynomial_check()
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan"}),
            _native_tool_response("same", "polynomial_check", {
                "schema_version": 1, "variable": "x", "coefficients": ["1", "0", "-1"],
                "domain": {"kind": "real"}, "candidates": ["1"],
            }),
            ProviderResponse({"content": "x=1\r\n候选"}),
            ProviderResponse({"content": "x=1\n候选"}),
        ])
        result = self._run_job(provider, registry)
        check = result["evidence"]["verification"]
        self.assertEqual("same_artifact", check["binding"])
        self.assertEqual(check["artifact"], check["history"][0]["artifact"])
        self.assertEqual("unknown", check["status"])
        self.assertEqual("needs_review", check["acceptance"])
        self.assertEqual("pass", check["history"][0]["candidate_status"])
        self.assertEqual("unknown", check["history"][0]["coverage_status"])
        self.assertEqual("polynomial-check-v1", check["history"][0]["checker_version"])

    def test_shape_consistency_pass_cannot_accept_unsupported_final_claim(self):
        registry = ToolRegistry()
        registry.register("constant", lambda _: 1)
        provider = DeterministicHTTPProvider([
            ProviderResponse({"content": "Plan"}),
            _native_tool_response("shape", "constant", {}),
            ProviderResponse({"content": "x=1 或 x=999"}),
            ProviderResponse({"content": "x=1 或 x=999"}),
        ])
        result = self._run_job(provider, registry)
        check = result["evidence"]["verification"]
        self.assertEqual("pass", check["history"][0]["status"])
        self.assertEqual("shape_and_tool_consistency", check["history"][0]["scope"])
        self.assertEqual("unknown", check["status"])
        self.assertEqual("needs_review", check["acceptance"])
        self.assertEqual(check, result["job_report"]["report"]["checks"])


del LiveToolWorkspaceContractTest
