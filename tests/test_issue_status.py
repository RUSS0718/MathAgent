"""Public CLI tests for credential-free GitHub issue status checks."""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts import check_issues


class _Response:
    """Provide the response methods used by the REST client."""

    def __init__(self, payload: object) -> None:
        self._payload = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        """Return the prepared JSON response body."""
        return self._payload


def _issue_payload(number: int, *, state: str = "open") -> dict[str, object]:
    """Build an independent public issue payload for the mocked REST response."""
    return {
        "number": number,
        "title": f"Issue {number}",
        "html_url": f"https://github.com/RUSS0718/MathAgent/issues/{number}",
        "state": state,
        "state_reason": None if state == "open" else "completed",
        "updated_at": "2026-11-02T00:00:00Z",
        "body": "must not be emitted",
    }


class IssueStatusCliTest(unittest.TestCase):
    """Verify the public CLI contract at its network boundary."""

    def _run(self, argv: list[str]) -> tuple[int, dict[str, object], str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = check_issues.main(argv)
        output = stdout.getvalue()
        return code, json.loads(output), output

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_success_is_json_and_each_get_has_unique_cache_buster(self, urlopen: Mock) -> None:
        """Return ordered issue summaries without bodies or authentication headers."""
        urlopen.side_effect = [
            _Response(_issue_payload(12)),
            _Response(_issue_payload(13, state="closed")),
        ]

        code, result, output = self._run(["--timeout", "3.5", "12", "13"])

        self.assertEqual(0, code)
        self.assertEqual(
            {
                "ok": True,
                "repo": "RUSS0718/MathAgent",
                "issues": [
                    {
                        "number": 12,
                        "title": "Issue 12",
                        "html_url": "https://github.com/RUSS0718/MathAgent/issues/12",
                        "state": "open",
                        "state_reason": None,
                        "updated_at": "2026-11-02T00:00:00Z",
                    },
                    {
                        "number": 13,
                        "title": "Issue 13",
                        "html_url": "https://github.com/RUSS0718/MathAgent/issues/13",
                        "state": "closed",
                        "state_reason": "completed",
                        "updated_at": "2026-11-02T00:00:00Z",
                    },
                ],
            },
            result,
        )
        self.assertNotIn("must not be emitted", output)
        self.assertNotIn("Authorization", output)
        self.assertEqual(2, urlopen.call_count)

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(3.5, urlopen.call_args_list[0].kwargs["timeout"])
        self.assertTrue(all(request.method == "GET" for request in requests))
        self.assertTrue(all(request.get_header("Authorization") is None for request in requests))
        cache_busters = [request.full_url.rsplit("_", 1)[1] for request in requests]
        self.assertEqual(2, len(set(cache_busters)))
        self.assertTrue(all("?_=" in request.full_url for request in requests))

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_invalid_input_is_json_nonzero_and_does_not_call_network(self, urlopen: Mock) -> None:
        """Reject invalid issue, repository, and timeout values before any GET."""
        for argv in (
            ["0"],
            ["--repo", "MathAgent", "1"],
            ["--timeout", "0", "1"],
        ):
            with self.subTest(argv=argv):
                code, result, _ = self._run(argv)
                self.assertNotEqual(0, code)
                self.assertFalse(result["ok"])
                self.assertEqual("usage", result["error"]["kind"])

        urlopen.assert_not_called()

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_http_error_is_json_and_nonzero(self, urlopen: Mock) -> None:
        """Report an HTTP failure without exposing a response body."""
        urlopen.side_effect = HTTPError(
            "https://api.github.com/repos/RUSS0718/MathAgent/issues/99",
            404,
            "Not Found",
            {},
            io.BytesIO(b'{"message":"secret response body"}'),
        )

        code, result, output = self._run(["99"])

        self.assertNotEqual(0, code)
        self.assertEqual({"ok": False, "error": {"kind": "http", "status": 404}}, result)
        self.assertNotIn("secret response body", output)

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_timeout_is_json_and_nonzero(self, urlopen: Mock) -> None:
        """Report a transport timeout distinctly from an HTTP response."""
        urlopen.side_effect = TimeoutError("timed out")

        code, result, _ = self._run(["1"])

        self.assertNotEqual(0, code)
        self.assertEqual({"ok": False, "error": {"kind": "timeout"}}, result)

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_malformed_json_is_json_and_nonzero(self, urlopen: Mock) -> None:
        """Reject a successful HTTP response that is not valid issue JSON."""
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b"not json"
        urlopen.return_value = response

        code, result, _ = self._run(["1"])

        self.assertNotEqual(0, code)
        self.assertEqual({"ok": False, "error": {"kind": "data"}}, result)

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_unicode_titles_survive_ascii_terminal_pipes(self, urlopen: Mock) -> None:
        """JSON escapes preserve titles across Windows terminal encodings."""
        payload = {**_issue_payload(1), "title": "修复检查点"}
        urlopen.return_value = _Response(payload)
        code, result, output = self._run(["1"])
        self.assertEqual(0, code)
        self.assertTrue(output.isascii())
        self.assertEqual("修复检查点", result["issues"][0]["title"])

    @patch.object(check_issues.urllib.request, "urlopen")
    def test_non_issue_payload_is_rejected(self, urlopen: Mock) -> None:
        """Reject unsupported states and GitHub pull request payloads."""
        payloads = (
            _issue_payload(1, state="pending"),
            {**_issue_payload(1), "pull_request": {"url": "https://api.github.com/pulls/1"}},
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                urlopen.return_value = _Response(payload)
                code, result, _ = self._run(["1"])
                self.assertNotEqual(0, code)
                self.assertEqual({"ok": False, "error": {"kind": "data"}}, result)


if __name__ == "__main__":
    unittest.main()
