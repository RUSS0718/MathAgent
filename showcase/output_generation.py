"""Durable, single-attempt terminal output generation, separate from solver budget."""
import copy
import hashlib
import json
import time

from .adapters import InternModelAdapter
from .presentation import build_presentation, failed_presentation, presentation_snapshot
from .redaction import redact_text
from .run_budget import RunBudgetLimits, bind_budget


def initialize_generation(store):
    with store._lock:
        store._connection.execute('''CREATE TABLE IF NOT EXISTS output_generations (
            job_id TEXT PRIMARY KEY, source TEXT NOT NULL, status TEXT NOT NULL,
            request_id TEXT NOT NULL, detail_json TEXT NOT NULL)''')
        # A previously dispatched request has an unknown outcome. Never replay it.
        store._connection.execute("UPDATE output_generations SET status='unknown' WHERE status='generating'")
        store._connection.commit()


def source_job(service, user_id, job_id):
    """Read source state without recovery/reconciliation or model dispatch."""
    job = service.store.get_job(job_id, user_id)
    from .star_product_modes import STAR_MODES
    if (job.get('result') or {}).get('solver_mode') in STAR_MODES:
        from .star_product_projection import current_solver
        with service.store._lock:
            job['result']['solver'] = current_solver(service.store._connection, job_id)
    return job


def generation_state(service, job_id):
    with service.store._lock:
        row = service.store._connection.execute(
            'SELECT * FROM output_generations WHERE job_id=?', (job_id,)).fetchone()
    return dict(row) if row else None


def _settle(service, job_id, status, detail):
    with service.store._lock:
        service.store._connection.execute(
            'UPDATE output_generations SET status=?,detail_json=? WHERE job_id=?',
            (status, json.dumps(detail, ensure_ascii=False), job_id))
        service.store._connection.commit()


def _seal(artifact, snapshot, request_id, cost, renderer):
    artifact['rule'] = snapshot['rule']
    artifact['renderer'] = renderer
    artifact['output_request'] = {'id': request_id, 'kind': 'presentation_only',
                                  'solver_resumed': False, **cost}
    payload = {k: v for k, v in artifact.items() if k != 'artifact'}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                       separators=(',', ':')).encode()).hexdigest()
    artifact['artifact'] = {'schema': artifact['schema_version'], 'sha256': digest,
                            'id': 'presentation:' + digest}
    return artifact


def generate_terminal(service, job_id):
    store = service.store
    with store._lock:
        row = store._connection.execute('SELECT user_id FROM workspace_jobs WHERE job_id=?', (job_id,)).fetchone()
    if row is None:
        return
    user_id = row[0]
    job = source_job(service, user_id, job_id)
    result = job.get('result') or {}
    rule = result.get('presentation_rule')
    if not rule or job['status'] not in {'succeeded', 'failed', 'canceled'}:
        return
    snapshot = presentation_snapshot(job)
    mode = result['presentation_mode']
    request_id = 'output:' + snapshot['fingerprint']
    cost = {'model_calls': 0, 'usage': None, 'max_output_tokens': 4096,
            'timeout_seconds': 120, 'max_attempts': 1}
    with store._lock:
        claimed = store._connection.execute(
            'INSERT OR IGNORE INTO output_generations VALUES(?,?,?,?,?)',
            (job_id, snapshot['fingerprint'], 'generating', request_id, json.dumps(cost))).rowcount
        store._connection.commit()
    if not claimed:
        return
    renderer = 'original-answer-rule-v1'
    try:
        if not snapshot['answer'] or job['status'] == 'canceled':
            raise ValueError('output_source_unavailable')
        if mode == 'solve':
            text = snapshot['answer']
        else:
            context = {'problem': redact_text(store.problem(job_id)),
                       'answer': snapshot['answer'], 'scope': snapshot['scope'],
                       'whole_review': snapshot['whole_review'],
                       'job_status': snapshot['job_status'],
                       'evidence_summary': {'sources': snapshot['sources'],
                                            'verified_claims': snapshot.get('verified_claims', []),
                                            'formal_verification': snapshot['formal_verification']}}
            context_text = json.dumps(context, ensure_ascii=False)
            if len(context_text.encode('utf-8')) > 65536:
                raise ValueError('output_context_capacity_exceeded')
            pipeline = service.star_pipeline if result.get('solver_mode') else service.pipeline
            adapter = getattr(pipeline, 'adapter', getattr(pipeline, 'model', None))
            if adapter is None:
                raise ValueError('output_model_unavailable')
            # Clone configuration, keeping the solver adapter and retry policy untouched.
            client = copy.copy(adapter._get_client())
            client.retry = 1  # repository client counts total attempts, not retries
            client.timeout = min(getattr(client, 'timeout', 120), 120)
            bounded = InternModelAdapter(client, model_id=adapter.model_id,
                                         max_tokens=4096, client_timeout=120, client_retry=1,
                                         thinking_mode=adapter.thinking_mode)
            budget = service.budget_ledger.ensure(request_id, RunBudgetLimits(
                max_model_calls=1, max_http_attempts=1, max_tool_calls=0,
                max_tokens=32768, max_runtime_seconds=120))
            cost['model_calls'] = 1
            renderer = 'bounded-model-output-v1'
            with bind_budget(budget):
                response = bounded.complete([
                    {'role': 'system', 'content': rule['text']},
                    {'role': 'user', 'content': context_text},
                ], metadata={'role': 'presentation', 'timeout_seconds': 120,
                             'phase_deadline_at': time.time() + 120, 'strict_completion': True})
            cost['usage'] = dict(response.usage) or None
            cost['model_id'] = response.model_id
            cost['returned_model'] = response.returned_model
            cost['role'] = 'presentation'
            cost['request_attempts'] = list(response.request_attempts)
            if (response.error_category or response.tool_requests or response.tool_request_error
                    or response.finish_reason == 'length' or not response.text.strip()):
                raise ValueError('output_protocol_invalid')
            text = response.text
        artifact = build_presentation(snapshot, mode, paragraphs=[
            {'text': text, 'kind': 'mathematical', 'claim_refs': []}])
    except Exception as exc:
        if hasattr(exc, 'request_attempts'):
            cost['request_attempts'] = list(exc.request_attempts)
        artifact = failed_presentation(snapshot, mode, getattr(exc, 'category', 'output_generation_failed'))
    output_budget = service.budget_ledger.snapshot(request_id)
    if output_budget is not None:
        cost['budget'] = output_budget
        cost['model_calls'] = output_budget['logical_calls']
    artifact = _seal(artifact, snapshot, request_id, cost, renderer)
    try:
        service.save_presentation(user_id=user_id, job_id=job_id, artifact=artifact)
    except Exception:
        _settle(service, job_id, 'stale', cost)
        return
    _settle(service, job_id, artifact['status'], cost)
