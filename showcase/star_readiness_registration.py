"""Frozen, non-dispatchable registration for the #97 nonstream readiness batch."""

import copy
import hashlib
import json
import re
from datetime import date

from .request_transport import INTERN_S2_LIVE_ENDPOINT

ADAPTER_VERSION = "issue-97-registration-adapter-v3"
V2_DRAFT_VERSION = "issue-97-nonstream-draft-v2"
V3_DRAFT_VERSION = "issue-97-nonstream-draft-v3"
V4_DRAFT_VERSION = "issue-97-nonstream-draft-v4"
DRAFT_VERSION = V4_DRAFT_VERSION
V2_QUESTION_SPECS = (
    (
        "simple-01",
        "https://projecteuler.net/problem=1",
        "simple_fastpath",
        "e84be303c2719dd77c917a0a6d75884a7c9abdd6f4c55e1069ff6af67a033cfb",
    ),
    (
        "multi-01",
        "https://projecteuler.net/problem=10",
        "public_multistep",
        "874c20406723e261e1f2dde0c5ab7f9ccb9e76957c48cb84718383151ccce5d6",
    ),
)
V3_QUESTION_SPECS = (
    (
        "simple-02",
        "https://projecteuler.net/problem=2",
        "simple_fastpath",
        "764d9d6e78508d59d2c66ea1d4358c25f6d01c559fe7e1090bd29c929330d042",
    ),
    (
        "multi-02",
        "https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf#page=2",
        "public_multistep",
        "f62ac6626ffa36647845b0e9d338191a9171899eed8615c033657c1ddc57e5b5",
    ),
)
V4_QUESTION_SPECS = (
    (
        "simple-03",
        "https://projecteuler.net/problem=6",
        "simple_fastpath",
        "1a85541f75ac9b29a651a77f6bc3793048f652870a9da54f879ccfed7ecb1035",
    ),
    (
        "multi-03",
        "https://www.imo-official.org/assets/documents/problems/2026/2026_eng.pdf#page=2",
        "public_multistep",
        "c8956a092a8c6b6004beed40bb1a6646e2a792299db5400dedd11bbd6912a086",
    ),
)
QUESTION_SPECS = V4_QUESTION_SPECS
V2_AUTHORIZATION_SCOPE = "issue-97-two-question-nonstream-batch"
V3_AUTHORIZATION_SCOPE = "issue-97-two-question-nonstream-batch-v3"
V4_AUTHORIZATION_SCOPE = "issue-97-two-question-nonstream-batch-v4"
V2_LIVE_MANIFEST_SHA256 = "0077b2884129f860169962cb31f9aa6e9da0a23e6440af1a5954b2c8c8c81bb0"
MODEL = {
    "max_output_tokens": 8192,
    "name": "intern-s2",
    "request_timeout_seconds": 180,
    "retry": 3,
    "solver_mode": "star_reference",
    "temperature": 0.2,
    "thinking_mode": True,
    "verification_mode": "auto",
}
STAR_REFERENCE_CONFIGURATION = {
    "isolation_image_id": "sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d",
    "preset": {
        "allowed_tools": ["polynomial_check", "python_math"],
        "features": {
            "final_generation": True, "final_solution_review": True,
            "local_code_tool": True, "meta_guidance": True, "persistent_sessions": True,
            "reexplore_after_replan": True, "skills": True, "star_routing": True,
            "stream_recovery": True,
        },
        "hint_mode": "none", "max_challenge_rounds": 5, "max_explore_rounds": 2,
        "max_final_solution_retries": 2, "max_replans": 3, "tool_timeout_seconds": 20,
    },
    "registered_tools": ["polynomial_check", "python_math"],
}
RUN_LIMITS = (
    {
        "charged_tokens": 32768,
        "http_attempts": 8,
        "logical_calls": 6,
        "problem_tool_calls": 1,
        "wall_seconds": 300,
    },
    {
        "charged_tokens": 65536,
        "http_attempts": 16,
        "logical_calls": 12,
        "problem_tool_calls": 3,
        "wall_seconds": 600,
    },
)
ROUND_LIMITS = {
    "charged_tokens": 98304,
    "environment_preflights": 3,
    "http_attempts": 24,
    "logical_calls": 18,
    "problem_tool_calls": 4,
    "runs": 2,
    "tools_including_environment": 7,
    "wall_seconds": 900,
}
STOP_ON = [
    "unknown_transport",
    "incomplete_or_unresolved_usage",
    "failure",
    "cancel",
    "hard_limit",
    "source_or_config_change",
    "ledger_or_binding_defect",
]

_DRAFT_KEYS = {
    "budget_status",
    "dirty_status",
    "enforcement",
    "evidence_types",
    "execution_authorized",
    "model",
    "original_batch",
    "previous_draft_sha256",
    "question_encoding",
    "questions",
    "round_limits",
    "runner_qualification",
    "schedule",
    "source_identity",
    "status",
    "stop_on",
    "version",
}
_MANIFEST_KEYS = {
    "authorization_date",
    "authorization_scope",
    "reference_configuration",
    "adapter_version",
    "draft_sha256",
    "draft_version",
    "execution_authorized",
    "model",
    "provider_mode",
    "provider_endpoint",
    "questions",
    "round_limits",
    "schedule",
    "schema_version",
    "source_identity",
    "status",
    "stop_on",
}
_SOURCE_KEYS = {"revision", "source_sha256", "dirty_status"}
_HASH_RE = re.compile(r"[0-9a-f]{64}\Z")


def digest(value):
    """Return the canonical JSON SHA256 used to freeze a registration."""
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def adapt_draft(draft, *, current_source):
    """Adapt a compatible v2, v3, or v4 draft into a non-dispatchable manifest."""
    record = _json_copy(draft)
    _validate_draft(record)
    source = _validate_source(current_source)
    manifest = {
        "adapter_version": ADAPTER_VERSION,
        "authorization_date": None,
        "authorization_scope": None,
        "draft_sha256": digest(record),
        "draft_version": record["version"],
        "execution_authorized": False,
        "model": copy.deepcopy(MODEL),
        "provider_mode": "loopback_only",
        "provider_endpoint": None,
        "reference_configuration": copy.deepcopy(STAR_REFERENCE_CONFIGURATION),
        "questions": [
            {
                "id": item["id"],
                "source": item["source"],
                "text": item["text"],
                "text_sha256": item["prompt_sha256"],
                "type": item["type"],
            }
            for item in record["questions"]
        ],
        "round_limits": copy.deepcopy(ROUND_LIMITS),
        "schedule": copy.deepcopy(record["schedule"]),
        "schema_version": 2,
        "source_identity": source,
        "status": "draft_not_dispatchable",
        "stop_on": copy.deepcopy(STOP_ON),
    }
    _validate_manifest(manifest)
    return manifest


def authorize_live_registration(
    manifest,
    *,
    expected_sha256,
    current_source,
    explicit_authorization,
    authorization_date,
):
    """Authorize an unapproved v3 or v4 loopback manifest; keep v2 read-only."""
    if explicit_authorization is not True:
        raise ValueError("star_readiness_live_authorization_required")
    if not isinstance(authorization_date, str):
        raise ValueError("star_readiness_live_authorization_invalid")
    try:
        if date.fromisoformat(authorization_date).isoformat() != authorization_date:
            raise ValueError
    except ValueError:
        raise ValueError("star_readiness_live_authorization_invalid") from None
    record = registration(
        manifest,
        expected_sha256=expected_sha256,
        current_source=current_source,
    )
    if record["draft_version"] not in (V3_DRAFT_VERSION, V4_DRAFT_VERSION):
        raise ValueError("star_readiness_live_draft_version_invalid")
    if record["execution_authorized"] is not False or record["provider_mode"] != "loopback_only":
        raise ValueError("star_readiness_live_authorization_invalid")
    record.update(
        authorization_date=authorization_date,
        authorization_scope=_authorization_scope_for_draft_version(record["draft_version"]),
        execution_authorized=True,
        provider_endpoint=INTERN_S2_LIVE_ENDPOINT,
        provider_mode="intern_s2_live",
        status="authorized_live",
    )
    _validate_manifest(record)
    return record


def registration(manifest, *, expected_sha256, current_source):
    """Verify the frozen hash, exact envelope, and unchanged caller source identity."""
    record = _json_copy(manifest)
    if not isinstance(expected_sha256, str) or not _HASH_RE.fullmatch(expected_sha256):
        raise ValueError("star_readiness_registration_invalid")
    if digest(record) != expected_sha256:
        raise ValueError("star_readiness_registration_identity_mismatch")
    _validate_manifest(record)
    if _validate_source(current_source) != record["source_identity"]:
        raise ValueError("star_readiness_source_identity_mismatch")
    return record


def _json_copy(value):
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, UnicodeEncodeError):
        raise ValueError("star_readiness_registration_invalid") from None


def _validate_draft(record):
    if not isinstance(record, dict) or set(record) != _DRAFT_KEYS:
        raise ValueError("star_readiness_registration_invalid")
    question_specs = _question_specs_for_draft_version(record["version"])
    if (
        record["status"] != "draft_not_dispatchable"
        or record["budget_status"] != "proposed_unapproved"
        or record["enforcement"] != "not_implemented"
        or record["runner_qualification"] != "not_implemented"
        or record["original_batch"] != "unchanged_not_counted"
        or record["question_encoding"] != "UTF-8 exact text with LF separators, no trailing newline"
        or type(record["execution_authorized"]) is not bool
        or record["execution_authorized"] is not False
        or type(record["dirty_status"]) is not bool
        or record["evidence_types"] != ["scripted", "fault_injection", "live", "replay"]
        or not isinstance(record["previous_draft_sha256"], str)
        or not _HASH_RE.fullmatch(record["previous_draft_sha256"])
    ):
        raise ValueError("star_readiness_registration_invalid")
    _validate_historical_source(record["source_identity"])
    _validate_model(record["model"])
    _validate_questions(record["questions"], draft=True, question_specs=question_specs)
    _validate_schedule(record["schedule"], question_specs=question_specs)
    _validate_round_limits(record["round_limits"])
    if record["stop_on"] != STOP_ON:
        raise ValueError("star_readiness_registration_invalid")


def _validate_manifest(record):
    # Validate the original loopback envelope without changing its frozen hash.
    if (
        isinstance(record, dict)
        and set(record) == _MANIFEST_KEYS - {
            "authorization_date", "authorization_scope", "provider_endpoint",
        }
        and type(record["schema_version"]) is int
        and record["schema_version"] == 1
        and record["adapter_version"] == "issue-97-registration-adapter-v2"
        and record["draft_version"] == V2_DRAFT_VERSION
        and record["provider_mode"] == "loopback_only"
    ):
        record = {
            **record, "schema_version": 2, "adapter_version": ADAPTER_VERSION,
            "authorization_date": None, "authorization_scope": None, "provider_endpoint": None,
        }
    if (
        not isinstance(record, dict)
        or set(record) != _MANIFEST_KEYS
        or type(record["schema_version"]) is not int
        or record["schema_version"] != 2
        or record["adapter_version"] != ADAPTER_VERSION
        or not isinstance(record["draft_sha256"], str)
        or not _HASH_RE.fullmatch(record["draft_sha256"])
        or record["stop_on"] != STOP_ON
    ):
        raise ValueError("star_readiness_registration_invalid")
    question_specs = _question_specs_for_draft_version(record["draft_version"])
    loopback = (
        record["status"] == "draft_not_dispatchable"
        and record["execution_authorized"] is False
        and record["provider_mode"] == "loopback_only"
        and record["provider_endpoint"] is None
        and record["authorization_date"] is None
        and record["authorization_scope"] is None
    )
    live = (
        record["status"] == "authorized_live"
        and record["execution_authorized"] is True
        and record["provider_mode"] == "intern_s2_live"
        and record["provider_endpoint"] == INTERN_S2_LIVE_ENDPOINT
        and record["authorization_scope"]
        == _authorization_scope_for_draft_version(record["draft_version"])
        and isinstance(record["authorization_date"], str)
    )
    if not loopback and not live:
        raise ValueError("star_readiness_registration_invalid")
    if live:
        # Only the consumed historical v2 envelope may retain its live identity.
        # Rebinding its source or date must not create a fresh consumption key.
        if record["draft_version"] == V2_DRAFT_VERSION and digest(record) != V2_LIVE_MANIFEST_SHA256:
            raise ValueError("star_readiness_live_draft_version_invalid")
        try:
            if date.fromisoformat(record["authorization_date"]).isoformat() != record["authorization_date"]:
                raise ValueError
        except ValueError:
            raise ValueError("star_readiness_registration_invalid") from None
    _validate_model(record["model"])
    _validate_source(record["source_identity"])
    if record["reference_configuration"] != STAR_REFERENCE_CONFIGURATION:
        raise ValueError("star_readiness_configuration_invalid")
    if any(value is not True for value in
           record["reference_configuration"]["preset"]["features"].values()):
        raise ValueError("star_readiness_configuration_invalid")
    _validate_questions(record["questions"], draft=False, question_specs=question_specs)
    _validate_schedule(record["schedule"], question_specs=question_specs)
    _validate_round_limits(record["round_limits"])


def _validate_model(value):
    if not isinstance(value, dict) or set(value) != set(MODEL):
        raise ValueError("star_readiness_registration_invalid")
    if (
        any(type(value[key]) is not int for key in
            ("max_output_tokens", "request_timeout_seconds", "retry"))
        or type(value["temperature"]) is not float
        or type(value["thinking_mode"]) is not bool
        or value != MODEL
    ):
        raise ValueError("star_readiness_registration_invalid")


def _validate_questions(value, *, draft, question_specs=None):
    question_specs = QUESTION_SPECS if question_specs is None else question_specs
    if not isinstance(value, list) or len(value) != len(question_specs):
        raise ValueError("star_readiness_registration_invalid")
    expected_keys = {"id", "prompt_sha256", "source", "text", "type"} if draft else {
        "id", "source", "text", "text_sha256", "type"
    }
    hash_key = "prompt_sha256" if draft else "text_sha256"
    for item, (question_id, source, question_type, expected_hash) in zip(value, question_specs):
        if (
            not isinstance(item, dict)
            or set(item) != expected_keys
            or item["id"] != question_id
            or item["source"] != source
            or item["type"] != question_type
            or not isinstance(item["text"], str)
            or not item["text"].strip()
            or not isinstance(item[hash_key], str)
            or not _HASH_RE.fullmatch(item[hash_key])
            or item[hash_key] != expected_hash
            or hashlib.sha256(item["text"].encode("utf-8")).hexdigest() != item[hash_key]
        ):
            raise ValueError("star_readiness_registration_invalid")


def _validate_schedule(value, *, question_specs=None):
    question_specs = QUESTION_SPECS if question_specs is None else question_specs
    if not isinstance(value, list) or len(value) != len(question_specs):
        raise ValueError("star_readiness_registration_invalid")
    for item, (question_id, _, _, _), limits in zip(value, question_specs, RUN_LIMITS):
        if (
            not isinstance(item, dict)
            or set(item) != {"attempts", "limits", "question", "transport"}
            or type(item["attempts"]) is not int
            or item["attempts"] != 1
            or item["question"] != question_id
            or item["transport"] != "nonstream"
            or not _exact_int_mapping(item["limits"], limits)
        ):
            raise ValueError("star_readiness_registration_invalid")


def _validate_round_limits(value):
    if not _exact_int_mapping(value, ROUND_LIMITS):
        raise ValueError("star_readiness_registration_invalid")


def _exact_int_mapping(value, expected):
    return (
        isinstance(value, dict)
        and set(value) == set(expected)
        and all(type(item) is int for item in value.values())
        and value == expected
    )


def _question_specs_for_draft_version(version):
    if version == V2_DRAFT_VERSION:
        return V2_QUESTION_SPECS
    if version == V3_DRAFT_VERSION:
        return V3_QUESTION_SPECS
    if version == V4_DRAFT_VERSION:
        return V4_QUESTION_SPECS
    raise ValueError("star_readiness_registration_invalid")


def _authorization_scope_for_draft_version(version):
    if version == V2_DRAFT_VERSION:
        return V2_AUTHORIZATION_SCOPE
    if version == V3_DRAFT_VERSION:
        return V3_AUTHORIZATION_SCOPE
    if version == V4_DRAFT_VERSION:
        return V4_AUTHORIZATION_SCOPE
    raise ValueError("star_readiness_registration_invalid")


def _validate_source(value):
    if (
        not isinstance(value, dict)
        or set(value) != _SOURCE_KEYS
        or not isinstance(value["revision"], str)
        or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["revision"])
        or not isinstance(value["source_sha256"], str)
        or not _HASH_RE.fullmatch(value["source_sha256"])
        or type(value["dirty_status"]) is not bool
    ):
        raise ValueError("star_readiness_source_identity_invalid")
    return copy.deepcopy(value)


def _validate_historical_source(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"revision", "source_sha256"}
        or not isinstance(value["revision"], str)
        or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value["revision"])
        or not isinstance(value["source_sha256"], str)
        or not _HASH_RE.fullmatch(value["source_sha256"])
    ):
        raise ValueError("star_readiness_registration_invalid")
