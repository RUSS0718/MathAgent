from __future__ import annotations

import subprocess
import sys
import unittest


class ShowcaseCliContractTest(unittest.TestCase):
    def test_explicit_secret_grants_only_opted_in_cli_over_http(self):
        import os
        import tempfile
        import threading
        from pathlib import Path
        from unittest.mock import patch

        from werkzeug.serving import make_server

        from showcase.cli import CliError, ShowcaseClient
        from showcase.flask_app import create_app

        with tempfile.TemporaryDirectory() as directory:
            app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory,
                              'SHOWCASE_WORKER_ENABLED': False,
                              'SHOWCASE_REVIEWER_SECRET': 'local-cli-fixture'})
            server = make_server('127.0.0.1', 0, app)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                origin = f'http://127.0.0.1:{server.server_port}'
                with patch.dict(os.environ, {'SHOWCASE_CLIENT_REVIEWER_SECRET': ''}):
                    ordinary = ShowcaseClient(origin, Path(directory) / 'ordinary.cookies')
                    ordinary.bootstrap()
                    with self.assertRaises(CliError) as denied:
                        ordinary.request('GET', '/api/agent/jobs/missing/report')
                    self.assertEqual(403, denied.exception.status)
                with patch.dict(os.environ, {'SHOWCASE_CLIENT_REVIEWER_SECRET': 'local-cli-fixture'}):
                    trusted = ShowcaseClient(origin, Path(directory) / 'trusted.cookies')
                    trusted.bootstrap()
                    self.assertIn('solver_modes', trusted.request('GET', '/api/capabilities'))
                self.assertNotIn('solver_modes', ordinary.request('GET', '/api/capabilities'))
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
                for key in ('showcase_workspace_service', 'showcase_run_service', 'loopback_store'):
                    app.extensions[key].close()

    def test_help_exposes_frontend_contract_commands(self) -> None:
        result = subprocess.run(
            [sys.executable, "showcase_cli.py", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode)
        for command in ("capabilities", "session", "job", "probe"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
