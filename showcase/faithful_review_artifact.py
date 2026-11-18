"""Answer availability guard for model-assisted F8 artifact reviews."""

from hashlib import sha256

EMPTY_ANSWER_SHA256 = sha256(b"").hexdigest()


def validate_answer_verdict(identity: dict, verdict: str) -> None:
    """A Run ID and a digest of empty bytes do not establish an answer."""
    missing = not identity.get("run_id") or identity.get("answer_sha256") in {
        None, "", EMPTY_ANSWER_SHA256,
    }
    if missing and verdict != "unresolved":
        raise ValueError("missing_answer_requires_unresolved")
