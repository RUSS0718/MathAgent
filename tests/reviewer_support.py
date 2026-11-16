"""Opt in technical HTTP tests using the production reviewer exchange."""
import secrets


def reviewer_client(app, client=None):
    """Return (client, csrf); call only in reviewer scenarios, never ordinary tests."""
    client = client or app.test_client()
    secret = app.config.get('SHOWCASE_REVIEWER_SECRET') or secrets.token_urlsafe(32)
    app.config['SHOWCASE_REVIEWER_SECRET'] = secret
    csrf = client.get('/api/check_auth').get_json()['csrf_token']
    response = client.post('/api/reviewer/grant', json={'secret': secret},
                           headers={'X-CSRF-Token': csrf})
    if response.status_code != 200:
        raise AssertionError(f'reviewer grant rejected: {response.status_code}')
    return client, csrf
