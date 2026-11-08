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
S03_PROBLEM = 'S03 browser root obligations'
S05_LATENCY_PROBLEM = 'S05 browser event latency'
S05_LONG_ARTIFACT_PROBLEM = 'S05 browser long public answer'
S05_TRACEBACK_HISTORY_PROBLEM = 'S05 browser traceback history: prove 1+1=2'
S05_REPLAN_HISTORY_PROBLEM = 'S05 browser replan history: prove 1+1=2'
S05_LONG_ARTIFACT = '公开推导段落。' * 500
S05_HISTORY_CLAIM = {'statement': '1+1=2', 'label': 'hard-verify'}
S05_TRACEBACK_REPLIES = [
    NEED_PLAN,
    {'version': 1, 'steps': [{
        'step_id': 'history-step', 'title': 'Prove equality', 'objective': 'Prove 1+1=2',
        'obligation_ids': ['root:s03'], 'auxiliary_goal_ids': [],
    }]},
    report('first attempt', claims=[S05_HISTORY_CLAIM]),
    {**TRACE, 'trace_back_to': 1},
    report('retried attempt', claims=[S05_HISTORY_CLAIM]),
    {'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT', 'objection': '',
     'obligation_evidence': [{
         'obligation_id': 'root:s03', 'evidence_category': 'universal_proof',
         'claim_indexes': [0],
     }]},
    {'final_response': '2'}, ACCEPT,
]
S05_REPLAN_REPLIES = [
    NEED_PLAN,
    {'version': 1, 'steps': [{
        'step_id': 'history-step', 'title': 'Prove equality', 'objective': 'Prove 1+1=2',
        'obligation_ids': ['root:s03'], 'auxiliary_goal_ids': [],
    }]},
    report('first attempt', claims=[S05_HISTORY_CLAIM]),
    PROPOSE,
    {**META_ABORT, 'decision': 'APPROVE_REPLAN',
     'reason_summary': 'Use a fresh plan for this browser fixture',
     'forbidden_directions': ['repeat prior plan'], 'reusable_results': []},
    {'version': 2, 'steps': [{
        'step_id': 'fresh-history-step', 'title': 'Fresh proof', 'objective': 'Prove 1+1=2',
        'obligation_ids': ['root:s03'], 'auxiliary_goal_ids': [],
    }]},
    report('replanned attempt', claims=[S05_HISTORY_CLAIM]),
    {'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT', 'objection': '',
     'obligation_evidence': [{
         'obligation_id': 'root:s03', 'evidence_category': 'universal_proof',
         'claim_indexes': [0],
     }]},
    {'final_response': '2'}, ACCEPT,
]
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
        spec_enabled = context.get('problem_spec_version') == 1
        run_id = context['run_id']
        with lock:
            counts[run_id] += 1
            number = counts[run_id]
        if problem == S05_LATENCY_PROBLEM:
            time.sleep(.25)
        if problem == 'unknown' and number == 1:
            self.close_connection = True
            return
        if problem in {'cancel', 'timeout'}:
            time.sleep(2)
        role = context['role']
        if role == 'explore':
            reply = {'assessment': 'NEED_PLAN', 'worked': [], 'failed': [], 'candidates': []} if problem in {'plan', 'tool', S03_PROBLEM, S05_LATENCY_PROBLEM, S05_LONG_ARTIFACT_PROBLEM, S05_TRACEBACK_HISTORY_PROBLEM, S05_REPLAN_HISTORY_PROBLEM} else {'assessment': 'SOLVED', 'worked': [], 'failed': [], 'candidates': [], 'solution_candidate': '2'}
        elif role == 'planner':
            reply = ({'version': 1, 'steps': [{
                'step_id': 's03-work', 'title': 'Prove the value', 'objective': 'Prove the statement',
                **({'obligation_ids': ['root:s03'], 'auxiliary_goal_ids': []} if spec_enabled else {}),
            }]} if problem in {S03_PROBLEM, S05_LATENCY_PROBLEM, S05_LONG_ARTIFACT_PROBLEM, S05_TRACEBACK_HISTORY_PROBLEM, S05_REPLAN_HISTORY_PROBLEM} else
                {'version': 1, 'steps': [{'step_id': 'PRIVATE HINT TEXT', 'title': 'Add', 'objective': 'Add'}]})
        elif role == 'reasoner':
            reply = ({'argument': 'The identity follows by integer addition.',
                      'claims': [{'statement': '1+1 equals 2 by the definition of addition.',
                                  'label': 'hard-verify'}],
                      'blocked': False} if problem in {S03_PROBLEM, S05_LATENCY_PROBLEM, S05_LONG_ARTIFACT_PROBLEM, S05_TRACEBACK_HISTORY_PROBLEM, S05_REPLAN_HISTORY_PROBLEM} else
                {'argument': 'PRIVATE PROOF TEXT', 'claims': [], 'blocked': False})
        elif role == 'step_verifier':
            reply = ({'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT', 'objection': '',
                      'obligation_evidence': [{'obligation_id': 'root:s03',
                                               'evidence_category': 'universal_proof',
                                               'claim_indexes': [0]}]}
                     if problem in {S03_PROBLEM, S05_LATENCY_PROBLEM, S05_LONG_ARTIFACT_PROBLEM, S05_TRACEBACK_HISTORY_PROBLEM, S05_REPLAN_HISTORY_PROBLEM} else
                     {'goal_gate': 'YES', 'logic_gate': 'PASS', 'verdict': 'ACCEPT', 'objection': ''})
        elif role == 'final_generator':
            reply = {'final_response': S05_LONG_ARTIFACT if problem == S05_LONG_ARTIFACT_PROBLEM else '2'}
        elif role == 'explore_polish':
            reply = {'solution_candidate': '1+1=2'}
        elif role == 'whole_solution_verifier':
            reply = {'verdict': 'ACCEPT', 'reason': 'Addition'}
        elif role == 'meta' and problem in {'replan', S05_REPLAN_HISTORY_PROBLEM}:
            reply = {}
        else:
            self.send_error(400)
            return
        if problem == 'trace':
            reply = trace_replies[number - 1]
        if problem == 'replan':
            reply = replan_replies[number - 1]
        if problem == S05_TRACEBACK_HISTORY_PROBLEM:
            reply = S05_TRACEBACK_REPLIES[number - 1]
        if problem == S05_REPLAN_HISTORY_PROBLEM:
            reply = S05_REPLAN_REPLIES[number - 1]
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
        spec_app = create_app({'TESTING': True,
            'SHOWCASE_DATA_DIR': str(Path(directory) / '8095'),
            'SHOWCASE_JOB_DELAY_SECONDS': 0, 'SHOWCASE_STAR_ENABLED': True,
            'SHOWCASE_STAR_EVIDENCE_KIND': 'fault_injection',
            'SHOWCASE_STAR_FEATURES': {
                'problem_spec': True, 'final_generation': True, 'final_solution_review': True,
            },
            'SHOWCASE_STAR_BUDGET': RunBudgetLimits(
                max_model_calls=28, max_http_attempts=28, max_tool_calls=0,
            ),
            'SHOWCASE_STAR_ADAPTER': InternModelAdapter(
                InternChatClient(retry=1), max_tokens=256,
            )})
        @spec_app.get('/__test__/jobs/<job_id>/persisted-event-times')
        def persisted_event_times(job_id):
            service = spec_app.extensions['showcase_workspace_service']
            with service.store._lock:
                rows = service.store._connection.execute(
                    'SELECT event_id,event_type,created_at FROM workspace_events WHERE job_id=? ORDER BY event_id',
                    (job_id,),
                ).fetchall()
            return spec_app.response_class(json.dumps([{
                'id': int(row['event_id']), 'event': row['event_type'],
                'created_at': row['created_at'],
            } for row in rows]), mimetype='application/json')
        threading.Thread(target=spec_app.run, kwargs={'host': '127.0.0.1', 'port': 8095,
            'threaded': True, 'use_reloader': False}, daemon=True).start()
        app.run(host='127.0.0.1', port=8091, threaded=True, use_reloader=False)
