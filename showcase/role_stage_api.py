"""Owner-authorized saved publications; never reconcile or dispatch work."""
from .role_stage_results import plan_results
from .solver_harness.storage import read_owned_snapshot


def read_role_results(service, user_id, job_id, role, source=None):
    job, state = read_owned_snapshot(service.store, user_id, job_id)
    return {'version': 'role-stage-v1', 'job_id': job_id, 'role': role,
            'status': job['status'], **plan_results(state, role, source)}
