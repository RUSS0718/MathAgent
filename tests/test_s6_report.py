"""Public report review labels derive from structured checker observations."""
import unittest

from showcase.evidence import EvidencePackExporter


class WorkbenchReportTest(unittest.TestCase):
    def test_out_of_domain_is_explicit_without_claiming_final_proof(self):
        exporter = EvidencePackExporter()
        report = exporter.report({'run_id': 'run_fake', 'status': 'COMPLETED', 'stage': 'completed', 'final_response': '1'}, tool_results=[{'name': 'polynomial_check', 'status': 'success', 'value': {'candidate_status': 'unknown', 'coverage_status': 'unknown', 'candidates': [{'in_domain': False}]}}])
        self.assertEqual('out_of_domain', report['tool_summaries'][0]['domain_status'])
        self.assertEqual('unknown', report['checks']['status'])

    def test_unknown_without_domain_observation_is_not_called_out_of_domain(self):
        report = EvidencePackExporter().report({'stage': 'completed'}, tool_results=[{'name': 'polynomial_check', 'value': {'candidate_status': 'unknown'}}])
        self.assertEqual('unknown', report['tool_summaries'][0]['domain_status'])

class FactoryDatabaseTest(unittest.TestCase):
    def test_persistent_service_database_must_match_factory_database(self):
        import tempfile
        from pathlib import Path
        from showcase.flask_app import create_app
        from showcase.run_service import RunService
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            service = RunService(database_path=root / 'service.sqlite3')
            try:
                with self.assertRaisesRegex(ValueError, 'service_database_mismatch'):
                    create_app({'SHOWCASE_DATA_DIR': str(root / 'app')}, service=service)
            finally:
                service.close()

    def test_memory_service_with_pipeline_cannot_split_persistent_budget(self):
        import tempfile
        from showcase.flask_app import create_app
        from showcase.run_service import RunService
        with tempfile.TemporaryDirectory() as directory:
            service = RunService()
            try:
                with self.assertRaisesRegex(ValueError, 'service_database_mismatch'):
                    create_app({'SHOWCASE_DATA_DIR': directory, 'SHOWCASE_LIVE_PIPELINE': object()}, service=service)
            finally:
                service.close()