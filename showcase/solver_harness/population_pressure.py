"""Detect provider rate limiting from the shared Run budget ledger."""

import json

RATE_LIMIT_REASON = "provider_rate_limited_current_epoch"


def pressure_reason(connection, state):
    """Return a pause reason for a current-epoch HTTP 429, otherwise ``None``.

    The caller should stop new exploration while this reason is present. The
    reason is epoch-scoped: an explicit owner takeover makes earlier actions
    historical, while this read-only check leaves unknown actions and holds intact.
    """
    run_id = state.get("run_id")
    population = state.get("population", {})
    owner = population.get("owner")
    actions = population.get("actions", {})
    if (not isinstance(run_id, str) or not isinstance(owner, dict)
            or type(owner.get("epoch")) is not int or not isinstance(actions, dict)):
        return None

    row = connection.execute(
        "SELECT ledger_json FROM run_budgets WHERE run_id=?", (run_id,)
    ).fetchone()
    if row is None:
        return None
    ledger = json.loads(row[0])
    if not isinstance(ledger, dict) or not isinstance(ledger.get("actions"), list):
        return None

    current_epoch = owner["epoch"]
    for attempt in ledger["actions"]:
        if not isinstance(attempt, dict) or attempt.get("kind") != "http":
            continue
        public_attempt = attempt.get("public_attempt")
        if (not isinstance(public_attempt, dict)
                or public_attempt.get("http_status") != 429):
            continue
        action = actions.get(attempt.get("population_action_id"))
        if (isinstance(action, dict) and action.get("owner") == owner
                and action.get("epoch") == current_epoch):
            return RATE_LIMIT_REASON
    return None
