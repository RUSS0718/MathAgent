"""Serve opt-in serial routes with the existing finite local HTTP provider."""
import json
import os
import tempfile
import threading
from copy import deepcopy
from http.server import ThreadingHTTPServer

from product_server import (
    InternChatClient,
    InternModelAdapter,
    Provider,
    RunBudgetLimits,
    counts,
    create_app,
    lock,
)

from tests.test_faithful_s03_job import REPLIES


class RouteProvider(Provider):
    """Use the S03 finite replies with S04's required controlled method identity."""
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        context = json.loads(body['messages'][-1]['content'])
        run_id = context['run_id']
        with lock:
            counts[run_id] += 1
            number = counts[run_id]
        replies = deepcopy(REPLIES)
        replies[1]['steps'][0]['method_id'] = 'computation'
        if number > len(replies):
            self.send_error(429)
            return
        payload = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(replies[number - 1])}}],
                   'model': 'intern-s2', 'usage': {'prompt_tokens': 7, 'completion_tokens': 3, 'total_tokens': 10}}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

if __name__ == '__main__':
    provider = ThreadingHTTPServer(('127.0.0.1', 8192), RouteProvider)
    threading.Thread(target=provider.serve_forever, daemon=True).start()
    os.environ['INTERN_API_KEY'] = 'local-route-fixture'
    os.environ['INTERN_API_BASE'] = 'http://127.0.0.1:8192/v1/chat/completions'
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({
            'TESTING': True, 'SHOWCASE_DATA_DIR': directory,
            'SHOWCASE_JOB_DELAY_SECONDS': 0, 'SHOWCASE_STAR_ENABLED': True,
            'SHOWCASE_STAR_EVIDENCE_KIND': 'fault_injection',
            'SHOWCASE_STAR_FEATURES': {'serial_routes': True, 'problem_spec': True,
                                      'proof_graph': True, 'progress_scheduling': True,
                                      'final_generation': True, 'final_solution_review': True},
            'SHOWCASE_STAR_BUDGET': RunBudgetLimits(max_model_calls=16, max_http_attempts=16),
            'SHOWCASE_STAR_ADAPTER': InternModelAdapter(InternChatClient(retry=1), max_tokens=256),
        })
        app.run(host='127.0.0.1', port=8195, threaded=True, use_reloader=False)
