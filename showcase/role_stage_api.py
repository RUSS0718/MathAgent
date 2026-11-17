"""Owner-authorized saved publications; never reconcile or dispatch work."""
import json

from .role_stage_results import plan_results


def read_role_results(service, user_id, job_id, role, source=None):
    with service.store._lock:
        job = service.store.get_job(job_id, user_id)
        row = service.store._connection.execute(
            'SELECT state_json FROM solver_states WHERE run_id=?', (job_id,)).fetchone()
        state = json.loads(row[0]) if row else {}
        return {'version': 'role-stage-v1', 'job_id': job_id, 'role': role,
                'status': job['status'], **plan_results(state, role, source)}
