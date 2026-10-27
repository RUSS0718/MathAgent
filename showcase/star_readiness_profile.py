"""Validate #97 execution modes before a provider request can be made."""

from urllib.parse import urlsplit


def validate_execution_profile(evidence_kind, manifest, client):
    """Require loopback for scripted runs and an authorized pinned client for live runs."""
    if evidence_kind == "scripted":
        try:
            parsed = urlsplit(client.api_base)
            valid = client.loopback_only is True and parsed.hostname == "127.0.0.1"
        except (AttributeError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError("star_readiness_loopback_client_invalid")
        if (manifest.get("execution_authorized") is not False
                or manifest.get("provider_mode") != "loopback_only"):
            raise ValueError("star_readiness_scripted_registration_invalid")
        return

    if evidence_kind != "live":
        raise ValueError("star_readiness_evidence_kind_invalid")
    if (manifest.get("execution_authorized") is not True
            or manifest.get("provider_mode") != "intern_s2_live"
            or manifest.get("status") != "authorized_live"):
        raise ValueError("star_readiness_live_authorization_required")
    try:
        valid = (
            client.loopback_only is False
            and client.provider_endpoint_only is True
            and client.api_base == manifest.get("provider_endpoint")
            and isinstance(client.authorization, str)
            and bool(client.authorization)
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("star_readiness_live_provider_invalid")
