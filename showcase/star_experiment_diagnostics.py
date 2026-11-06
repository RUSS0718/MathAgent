"""Fixed public categories for bounded experiment failure evidence."""

import re

_PUBLIC_CODES = frozenset({
    "star_prerequisites_unverified", "message_must_be_non_empty",
    "csrf_invalid", "auth_required", "solver_mode_invalid",
})
_FIXED_ERRORS = frozenset({
    "experiment_prerequisites_unverified", "experiment_preflight_evidence_invalid",
    "experiment_conditions_mismatch", "experiment_transport_mismatch",
    "experiment_public_read_failed", "scripted_provider_must_be_loopback",
})


def failure_diagnostic(exc):
    """Never archive arbitrary exception messages, URLs, prompts or credentials."""
    message = str(exc)
    if message in _FIXED_ERRORS:
        return {"code": message}
    match = re.fullmatch(
        r"experiment_public_admission_failed status=([45][0-9]{2}) code=([a-z_]{1,96})",
        message,
    )
    if match:
        status, code = match.groups()
        return {"code": "experiment_public_admission_failed", "status": int(status),
                "public_code": code if code in _PUBLIC_CODES else "unknown"}
    return {"code": "unclassified"}
