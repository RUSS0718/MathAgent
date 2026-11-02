"""Read-only GitHub issue status checker with a credential-free JSON CLI.

This module owns only public REST GET requests for issue summaries. It does not
read credentials, mutate issues, or emit response bodies and other unneeded
issue fields.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import urllib.error
import urllib.request
import uuid
from typing import Any

DEFAULT_REPOSITORY = "RUSS0718/MathAgent"
GITHUB_API_ROOT = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
VALID_STATES = {"open", "closed"}


class UsageError(ValueError):
    """Represent an invalid command-line value or combination."""


class IssueCheckError(Exception):
    """Represent a safe, machine-readable failure during issue checking."""

    def __init__(self, kind: str, *, status: int | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.status = status


class _ArgumentParser(argparse.ArgumentParser):
    """Raise a controlled error so invalid input also produces JSON."""

    def error(self, message: str) -> None:
        """Convert argparse's human-oriented error into the CLI error contract."""
        raise UsageError(message)


def _positive_issue(value: str) -> int:
    """Parse a positive decimal GitHub issue number."""
    try:
        issue = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("issue numbers must be positive integers") from exc
    if issue <= 0:
        raise argparse.ArgumentTypeError("issue numbers must be positive integers")
    return issue


def _repository(value: str) -> str:
    """Validate an OWNER/REPO path before inserting it into the API URL."""
    if not REPOSITORY_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError("repository must use OWNER/REPO format")
    return value


def _positive_timeout(value: str) -> float:
    """Parse a finite timeout in seconds that is greater than zero."""
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive number")
    return timeout


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for one or more read-only issue checks."""
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPOSITORY,
        type=_repository,
        help=f"GitHub repository in OWNER/REPO form (default: {DEFAULT_REPOSITORY})",
    )
    parser.add_argument(
        "--timeout",
        default=10.0,
        type=_positive_timeout,
        help="HTTP timeout in seconds (default: 10)",
    )
    parser.add_argument("issues", metavar="ISSUE", nargs="+", type=_positive_issue)
    return parser


def _request_url(repository: str, issue: int) -> str:
    """Create a cache-busted URL for one public issue GET request."""
    return f"{GITHUB_API_ROOT}/repos/{repository}/issues/{issue}?_={uuid.uuid4().hex}"


def _read_issue(repository: str, issue: int, timeout: float) -> dict[str, Any]:
    """Fetch and validate one public issue, returning only status fields."""
    request = urllib.request.Request(
        _request_url(repository, issue),
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MathAgent-issue-status-checker",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise IssueCheckError("http", status=exc.code) from None
    except TimeoutError:
        raise IssueCheckError("timeout") from None
    except (urllib.error.URLError, OSError):
        raise IssueCheckError("network") from None
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        raise IssueCheckError("data") from None

    if not isinstance(payload, dict):
        raise IssueCheckError("data")
    state = payload.get("state")
    if (
        "pull_request" in payload
        or payload.get("number") != issue
        or not isinstance(payload.get("title"), str)
        or not isinstance(payload.get("html_url"), str)
        or not isinstance(state, str)
        or state not in VALID_STATES
        or not isinstance(payload.get("updated_at"), str)
    ):
        raise IssueCheckError("data")
    state_reason = payload.get("state_reason")
    if state_reason is not None and not isinstance(state_reason, str):
        raise IssueCheckError("data")
    return {
        "number": issue,
        "title": payload["title"],
        "html_url": payload["html_url"],
        "state": state,
        "state_reason": state_reason,
        "updated_at": payload["updated_at"],
    }


def _emit(result: dict[str, Any]) -> None:
    """Write one stable JSON object to stdout."""
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    """Run read-only issue checks and return zero only after every GET succeeds."""
    try:
        args = build_parser().parse_args(argv)
        issues = [_read_issue(args.repo, issue, args.timeout) for issue in args.issues]
    except UsageError:
        _emit({"ok": False, "error": {"kind": "usage"}})
        return 2
    except IssueCheckError as exc:
        error: dict[str, Any] = {"kind": exc.kind}
        if exc.status is not None:
            error["status"] = exc.status
        _emit({"ok": False, "error": error})
        return 1

    _emit({"ok": True, "repo": args.repo, "issues": issues})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
