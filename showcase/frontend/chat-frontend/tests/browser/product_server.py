"""Browser integration server: real product API and finite local HTTP provider."""
import json
import os
import sys
import tempfile
import threading
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from llm_client import InternChatClient
from showcase.adapters import InternModelAdapter
from showcase.flask_app import create_app
from showcase.run_budget import RunBudgetLimits
from showcase.tools import ToolRegistry
from tests.star_product_support import ACCEPT
from tests.test_star_product_challenge import META_ABORT
from tests.test_star_product_private_receipt import STEP as TOOL_STEP
from tests.test_star_product_tools import NEED_PLAN, VERDICT
from tests.test_star_product_traceback import PLAN, PROPOSE, TRACE, report

counts = defaultdict(int)
lock = threading.Lock()
trace_replies = [
    NEED_PLAN, PLAN, report("safe reviewed fact"), VERDICT,
    report("old wrong fact"), VERDICT, report("old dependent fact"), VERDICT,
    report("private rejected proof"), TRACE,
    report("new route"), VERDICT, report("new dependent"), VERDICT,
    report("new completion"), VERDICT, {"final_response": "2"}, ACCEPT,
]
replan_replies = [*trace_replies[:10], report("private failed argument"), PROPOSE,
    {**META_ABORT, "decision": "APPROVE_REPLAN", "reason_summary": "Old route failed",
     "forbidden_directions": ["old route"], "reusable_results": ["safe reviewed fact"]},
    {"version": 2, "steps": [{"step_id": "fresh", "title": "Fresh", "objective": "New route"}]},
    report("fresh proof"), VERDICT, {"final_response": "2"}, ACCEPT]

class Provider(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(dict(counts)).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        context = json.loads(body['messages'][-1]['content'])
        problem = context['original_problem']
        run_id = context['run_id']
        with lock:
            counts[run_id] += 1
            number = counts[run_id]
        if problem == 'unknown' and number == 1:
            self.close_connection = True
            return
        if problem in {'cancel', 'timeout'}:
            time.sleep(2)
        role = context['role']
        if role == 'explore':
            reply = {'assessment': 'NEED_PLAN', 'worked': [], 'failed': [], 'candidates': []} if problem in {'plan', 'tool'} else {'assessment': 'SOLVED', 'worked': [], 'failed': [], 'candidates': [], 'solution_candidate': '2'}
        elif role == 'planner':
            reply = {'version': 1, 'steps': [{'step_id': 'PRIVATE HINT TEXT', 'title': 'Add', 'objective': 'Add'}]}
        elif role == 'reasoner':
            reply = {'argument': 'PRIVATE PROOF TEXT', 'claims': [], 'blocked': False}
        elif role == 'step_verifier':
            reply = {'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT', 'objection': ''}
        elif role == 'final_generator':
            reply = {'final_response': '2'}
        elif role == 'explore_polish':
            reply = {'solution_candidate': '1+1=2'}
        elif role == 'whole_solution_verifier':
            reply = {'verdict': 'ACCEPT', 'reason': 'Addition'}
        elif role == 'meta' and problem == 'replan':
            reply = {}
        else:
            self.send_error(400)
            return
        if problem == 'trace':
            reply = trace_replies[number - 1]
        if problem == 'replan':
            reply = replan_replies[number - 1]
        if problem == 'tool' and role == 'reasoner':
            reply = TOOL_STEP
        if number > 28:
            self.send_error(429)
            return
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(reply)}}], 'model': 'intern-s2', 'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        try:
            self.wfile.write(json.dumps(payload).encode())
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
            pass  # Cancellation/deadline deliberately close the provider connection.

if __name__ == '__main__':
    provider = ThreadingHTTPServer(('127.0.0.1', 8092), Provider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    os.environ['INTERN_API_KEY'] = 'local-browser-fixture'
    os.environ['INTERN_API_BASE'] = 'http://127.0.0.1:8092/v1/chat/completions'
    registry = ToolRegistry()
    registry.register_polynomial_check()
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': directory,
            'SHOWCASE_JOB_DELAY_SECONDS': 0, 'SHOWCASE_STAR_ENABLED': True,
            'SHOWCASE_STAR_EVIDENCE_KIND': 'fault_injection',
            'SHOWCASE_STAR_FEATURES': {'final_generation': True, 'final_solution_review': True, 'local_code_tool': True},
            'SHOWCASE_STAR_REGISTRY': registry,
            'SHOWCASE_STAR_BUDGET': RunBudgetLimits(max_model_calls=28, max_http_attempts=28, max_tool_calls=2),
            'SHOWCASE_STAR_ADAPTER': InternModelAdapter(InternChatClient(retry=1), max_tokens=256)})
        for port, limit in ((8093, RunBudgetLimits(max_model_calls=1, max_http_attempts=1, max_tool_calls=0)),
                            (8094, RunBudgetLimits(max_runtime_seconds=.5))):
            other = create_app({'TESTING': True, 'SHOWCASE_DATA_DIR': str(Path(directory) / str(port)),
                'SHOWCASE_JOB_DELAY_SECONDS': 0, 'SHOWCASE_STAR_ENABLED': True,
                'SHOWCASE_STAR_EVIDENCE_KIND': 'fault_injection', 'SHOWCASE_STAR_BUDGET': limit,
                'SHOWCASE_STAR_ADAPTER': InternModelAdapter(InternChatClient(retry=1), max_tokens=256)})
            threading.Thread(target=other.run, kwargs={'host': '127.0.0.1', 'port': port,
                'threaded': True, 'use_reloader': False}, daemon=True).start()
        app.run(host='127.0.0.1', port=8091, threaded=True, use_reloader=False)
