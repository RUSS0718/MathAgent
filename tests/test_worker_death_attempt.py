"""A worker killed inside fake HTTP cannot erase its committed reservation identity."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from showcase.flask_app import create_app


class WorkerDeathAttemptTest(unittest.TestCase):
    def test_real_process_death_retains_unresolved_public_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            script = r'''
import json, os, sys, time, uuid
from pathlib import Path
from unittest.mock import patch
from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.live_pipeline import LiveAgentPipeline
from showcase.tools import ToolRegistry
root = Path(sys.argv[1])
with patch.dict(os.environ, {'INTERN_API_KEY':'offline-only', 'INTERN_MODEL':'intern-s2'}):
    model = InternModelAdapter(InternChatClient(retry=1), max_tokens=256)
pipeline = LiveAgentPipeline(model, ToolRegistry(), execution_mode='fake')
app = create_app({'SHOWCASE_MODE':'live', 'SHOWCASE_DATA_DIR':str(root), 'SHOWCASE_LIVE_PIPELINE':pipeline, 'SHOWCASE_JOB_DELAY_SECONDS':1})
def killed_http(*args, **kwargs):
    os._exit(73)
patch('llm_client.requests.post', side_effect=killed_http).start()
browser = app.test_client()
csrf = browser.get('/api/check_auth').get_json()['csrf_token']
headers = {'X-CSRF-Token':csrf}
session = browser.post('/api/new_chat', headers=headers).get_json()['new_session_id']
job = browser.post('/api/agent/jobs', json={'message':'Compute 1+1.', 'session_id':session}, headers={**headers,'Idempotency-Key':str(uuid.uuid4())}).get_json()['job_id']
(root/'job.json').write_text(json.dumps(job))
time.sleep(20)
'''
            result = subprocess.run([sys.executable, '-c', script, directory], env={**os.environ, 'PYTHONUTF8': '1'}, timeout=30, capture_output=True)
            self.assertEqual(73, result.returncode, result.stderr.decode())
            job_id = json.loads((Path(directory) / 'job.json').read_text())
            app = create_app({'SHOWCASE_MODE': 'fake', 'SHOWCASE_DATA_DIR': directory, 'SHOWCASE_WORKER_ENABLED': False})
            try:
                browser = app.test_client()
                browser.get('/api/check_auth')
                report = browser.get(f'/api/agent/jobs/{job_id}/report').get_json()
                evidence = browser.get(f'/api/runs/{job_id}/evidence').get_json()
                self.assertEqual('failed', report['status'])
                for attempts in (report['report']['request_attempts'], evidence['request_attempts']):
                    self.assertEqual(1, len(attempts))
                    attempt = attempts[0]
                    self.assertTrue(attempt['attempt_id'])
                    self.assertTrue(attempt['logical_call_id'])
                    self.assertEqual('planner', attempt['role'])
                    self.assertEqual('intern-s2', attempt['requested_model'])
                    self.assertEqual(1, attempt['attempt_index'])
                    self.assertTrue(attempt['started_at_utc'])
                    self.assertEqual('reserved_dispatch_unconfirmed', attempt['dispatch_status'])
                    self.assertEqual('unknown', attempt['status'])
                    self.assertIsNone(attempt['usage']['total_tokens'])
            finally:
                app.extensions['showcase_workspace_service'].close()
                app.extensions['showcase_run_service'].close()
                app.extensions['loopback_store'].close()
