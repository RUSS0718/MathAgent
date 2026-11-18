"""Versioned product rules for opt-in streamed model calls."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Mapping
from dataclasses import dataclass

STREAM_TIMEOUT_POLICY_VERSION = "faithful-stream-v1"


@dataclass(frozen=True)
class StreamTimeoutPolicy:
    """The accepted idle and soft-warning rules, without provider timeout claims."""

    policy_version: str = STREAM_TIMEOUT_POLICY_VERSION
    soft_prompt_seconds: int = 1200
    effective_idle_seconds: int = 30

    def __post_init__(self) -> None:
        if (
            self.policy_version != STREAM_TIMEOUT_POLICY_VERSION
            or self.soft_prompt_seconds != 1200
            or self.effective_idle_seconds != 30
        ):
            raise ValueError("stream_timeout_policy_unsupported")

    def snapshot(self) -> dict[str, int | str]:
        """Return the immutable, serializable policy persisted with a Run."""

        return {
            "policy_version": self.policy_version,
            "soft_prompt_seconds": self.soft_prompt_seconds,
            "effective_idle_seconds": self.effective_idle_seconds,
        }

    @classmethod
    def from_snapshot(cls, value: Mapping[str, object]) -> StreamTimeoutPolicy:
        """Validate a persisted policy instead of silently upgrading its meaning."""

        if set(value) != {"policy_version", "soft_prompt_seconds", "effective_idle_seconds"}:
            raise ValueError("stream_timeout_policy_invalid")
        if (
            type(value.get("soft_prompt_seconds")) is not int
            or type(value.get("effective_idle_seconds")) is not int
        ):
            raise ValueError("stream_timeout_policy_invalid")
        return cls(
            policy_version=value.get("policy_version"),
            soft_prompt_seconds=value["soft_prompt_seconds"],
            effective_idle_seconds=value["effective_idle_seconds"],
        )


def policy_for_version(version: str | None) -> dict[str, int | str] | None:
    """Resolve an explicitly enabled server version; ``None`` keeps legacy runs."""

    if version is None:
        return None
    return StreamTimeoutPolicy(policy_version=version).snapshot()


def validate_snapshot(value: Mapping[str, object] | None) -> dict[str, int | str] | None:
    """Return a validated copy suitable for durable Job and Run state."""

    if value is None:
        return None
    return StreamTimeoutPolicy.from_snapshot(value).snapshot()


class StreamCallLifecycle:
    """Track effective stream deltas separately from wire heartbeats."""

    def __init__(self, policy: Mapping[str, object], started_at: float, run_deadline: float):
        self.policy = StreamTimeoutPolicy.from_snapshot(policy)
        self.started_at = started_at
        self.run_deadline = run_deadline
        self._last_effective_at: float | None = None
        self._seen_event_ids: set[tuple[str, str]] = set()
        self._soft_prompt_sent = False
        self._complete = False
        self._lock = threading.Lock()

    def deadline(self) -> float:
        """Return the active stream idle deadline, bounded by the original Run deadline."""

        with self._lock:
            if self._complete or self._last_effective_at is None:
                return self.run_deadline
            idle_deadline = self._last_effective_at + self.policy.effective_idle_seconds
            return min(self.run_deadline, idle_deadline)

    def record_event_id(self, event_id: str | None, event_data: str) -> bool:
        """Deduplicate an explicit ID only when its payload also repeats."""

        if not event_id:
            return False
        identity = (event_id, hashlib.sha256(event_data.encode("utf-8")).hexdigest())
        with self._lock:
            if identity in self._seen_event_ids:
                return True
            self._seen_event_ids.add(identity)
        return False

    def record_delta(
        self,
        *,
        content: str | None,
        reasoning: str | None,
        now: float,
    ) -> bool:
        """Advance idle after a non-empty delta; identical payloads remain distinct."""

        if not ((isinstance(content, str) and content) or (isinstance(reasoning, str) and reasoning)):
            return False
        with self._lock:
            self._last_effective_at = now
        return True

    def soft_prompt_due(self, now: float) -> bool:
        """Return true once when the soft-warning age is reached."""

        with self._lock:
            if self._soft_prompt_sent or now < self.started_at + self.policy.soft_prompt_seconds:
                return False
            self._soft_prompt_sent = True
            return True

    def complete(self) -> None:
        """Stop applying effective-idle expiry after the provider stream completes."""

        with self._lock:
            self._complete = True


def call_policy_evidence(
    policy: Mapping[str, object], *, endpoint: str
) -> dict[str, object]:
    """Build the opt-in attempt evidence without retaining a raw endpoint or SLA claim."""

    return {
        "policy_version": StreamTimeoutPolicy.from_snapshot(policy).policy_version,
        "provider": "unknown",
        "endpoint_sha256": hashlib.sha256(endpoint.encode("utf-8")).hexdigest(),
        "provider_timeout_limit": {
            "status": "unknown",
            "seconds": None,
            "source": None,
            "version": None,
            "date": None,
        },
    }
