"""Keep only the public Job identity needed to audit each registered sample."""

from __future__ import annotations

from typing import Any

_IDENTITY_FIELDS = (
    "sample_id",
    "job_id",
    "session_id",
    "idempotency_key",
    "request_digest",
    "deadline_at",
)


def record_run_identity(
    status: dict[str, Any], intent: dict[str, Any], *, job_id: str | None = None
) -> bool:
    """Append or bind a sample's stable Job identity without copying request data."""
    records = status.setdefault("run_records", [])
    if not isinstance(records, list):
        return False
    identity = {
        "sample_id": intent.get("sample_id"),
        "job_id": job_id,
        "session_id": intent.get("session_id"),
        "idempotency_key": intent.get("idempotency_key"),
        "request_digest": intent.get("request_digest"),
        "deadline_at": intent.get("deadline_at"),
    }
    if any(value is None for key, value in identity.items() if key != "job_id"):
        return False

    existing = next(
        (record for record in records if record.get("sample_id") == identity["sample_id"]),
        None,
    )
    if existing is None:
        records.append(identity)
        return True
    if not isinstance(existing, dict):
        return False
    if any(existing.get(key) != identity[key] for key in _IDENTITY_FIELDS if key != "job_id"):
        return False
    if job_id is not None:
        if existing.get("job_id") not in {None, job_id}:
            return False
        existing["job_id"] = job_id
    return True
