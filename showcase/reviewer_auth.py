"""Session-specific reviewer permission and deny-by-default route classification."""
import re
import secrets
import sqlite3
from contextlib import closing

PERMISSION = 'reviewer.access'
PUBLIC_RULES = {
    '/health', '/', '/dashboard', '/dashboard/', '/dashboard-assets/<path:asset_path>',
    '/api/check_auth', '/api/logout', '/api/reviewer/grant', '/api/capabilities',
    '/api/files', '/api/upload_file', '/api/delete_file', '/api/sessions',
    '/api/new_chat', '/api/load_session', '/api/change_session', '/api/delete_session',
    '/api/agent/jobs', '/api/agent/jobs/active', '/api/agent/submissions/<submission_id>',
    '/api/agent/jobs/by-idempotency', '/api/agent/jobs/<job_id>',
    '/api/agent/jobs/<job_id>/answer', '/api/agent/jobs/<job_id>/events',
    '/api/agent/jobs/<job_id>/resume', '/api/agent/jobs/<job_id>/cancel',
    '/api/agent/jobs/<job_id>/clarifications/<request_id>',
    '/api/agent/jobs/<job_id>/clarifications/<request_id>/new-task',
    '/api/agent/jobs/<job_id>/revisions',
    '/api/agent/jobs/<job_id>/interventions/pause',
    '/api/agent/jobs/<job_id>/interventions/resume',
}


def technical_request(request):
    rule = str(request.url_rule) if request.url_rule else ''
    if rule == '/dashboard-assets/<path:asset_path>':
        asset = request.view_args.get('asset_path', '')
        return asset in {'system','campaigns','settings','run'} or asset.startswith(('run/','runs/','system/','campaigns/'))
    if rule == '/dashboard/<path:subpath>':
        subpath = request.view_args.get('subpath', '')
        return not (subpath in {'chat', 'workspace', 'reviewer'} or re.fullmatch(r'session/[A-Za-z0-9._-]{1,64}', subpath))
    return rule not in PUBLIC_RULES


class ReviewerGrants:
    def __init__(self, database_path):
        self.database_path = database_path
        with closing(sqlite3.connect(database_path)) as connection, connection:
            connection.execute('CREATE TABLE IF NOT EXISTS reviewer_session_grants ('
                               'session_id TEXT PRIMARY KEY REFERENCES auth_sessions(session_id))')

    def has(self, session):
        if session is None:
            return False
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            return connection.execute('SELECT 1 FROM reviewer_session_grants g JOIN auth_sessions s '
                                      'ON s.session_id=g.session_id WHERE s.session_id=? AND s.revoked_at IS NULL',
                                      (session.session_id,)).fetchone() is not None

    def grant(self, session, supplied, configured):
        if not isinstance(configured, str) or not configured or not isinstance(supplied, str):
            return False
        if not secrets.compare_digest(supplied.encode(), configured.encode()):
            return False
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute('INSERT OR IGNORE INTO reviewer_session_grants SELECT session_id '
                               'FROM auth_sessions WHERE session_id=? AND revoked_at IS NULL', (session.session_id,))
        return self.has(session)
