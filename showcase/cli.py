"""CLI client for the v0.2 loopback workspace HTTP/SSE contract."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener


class CliError(RuntimeError):
    def __init__(self, code: str, status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


class ShowcaseClient:
    """Small stdlib-only client that mirrors the browser API calls."""

    def __init__(self, base_url: str, cookie_file: Path, timeout: float = 1_200.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_file = cookie_file
        self.timeout = timeout
        self.cookies = http.cookiejar.MozillaCookieJar(str(cookie_file))
        try:
            self.cookies.load(ignore_discard=True, ignore_expires=True)
        except FileNotFoundError:
            pass
        from urllib.request import HTTPCookieProcessor

        self.opener = build_opener(HTTPCookieProcessor(self.cookies))
        self.csrf_token = ""

    def bootstrap(self) -> dict[str, Any]:
        payload = self.request("GET", "/api/check_auth")
        self.csrf_token = str(payload.get("csrf_token", ""))
        if not self.csrf_token:
            raise CliError("csrf_token_missing")
        return payload

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
    ) -> Any:
        request_headers = {"Accept": "application/json", **(headers or {})}
        request_body = body
        if payload is not None:
            request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} and self.csrf_token:
            request_headers.setdefault("X-CSRF-Token", self.csrf_token)
        request = Request(
            self.base_url + path,
            data=request_body,
            headers=request_headers,
            method=method.upper(),
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except HTTPError as exc:
            raw = exc.read()
            status = exc.code
        except URLError as exc:
            raise CliError("network_error") from exc
        self._save_cookies()
        value = _decode_json(raw)
        if status < 200 or status >= 300:
            code = value.get("code", "request_failed") if isinstance(value, dict) else "request_failed"
            raise CliError(str(code), status)
        return value

    def idempotency_headers(self) -> dict[str, str]:
        return {"Idempotency-Key": str(uuid.uuid4())}

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        query = urlencode({"last_event_id": str(after)})
        request_headers = {"Accept": "text/event-stream"}
        if self.csrf_token:
            request_headers["X-CSRF-Token"] = self.csrf_token
        request = Request(
            f"{self.base_url}/api/agent/jobs/{job_id}/events?{query}",
            headers=request_headers,
            method="GET",
        )
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            value = _decode_json(exc.read())
            code = value.get("code", "events_failed") if isinstance(value, dict) else "events_failed"
            raise CliError(str(code), exc.code) from exc
        except URLError as exc:
            raise CliError("events_network_error") from exc
        self._save_cookies()
        return _parse_sse(raw)

    def _save_cookies(self) -> None:
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookies.save(ignore_discard=True, ignore_expires=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MathAgent v0.2 Showcase CLI (shared HTTP/SSE contract)")
    parser.add_argument("--base-url", default=os.getenv("SHOWCASE_BASE_URL", "http://127.0.0.1:8090"))
    parser.add_argument("--cookie-file", type=Path, default=Path("artifacts/showcase-v0.2/cli.cookies"))
    parser.add_argument("--timeout", type=float, default=1_200.0)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health")
    subparsers.add_parser("capabilities")
    subparsers.add_parser("logout")

    session = subparsers.add_parser("session")
    session_sub = session.add_subparsers(dest="action", required=True)
    session_sub.add_parser("list")
    session_sub.add_parser("create")
    load = session_sub.add_parser("load")
    load.add_argument("session_id")
    rename = session_sub.add_parser("rename")
    rename.add_argument("session_id")
    rename.add_argument("title")
    remove = session_sub.add_parser("delete")
    remove.add_argument("session_id")

    job = subparsers.add_parser("job")
    job_sub = job.add_subparsers(dest="action", required=True)
    submit = job_sub.add_parser("submit")
    submit.add_argument("--session-id", required=True)
    submit.add_argument("message")
    submit.add_argument("--verification-mode", choices=("auto", "required", "off"), default="auto")
    submit.add_argument("--file-id")
    for action in ("status", "events", "watch", "report", "cancel"):
        command = job_sub.add_parser(action)
        command.add_argument("job_id")
    resume = job_sub.add_parser("resume")
    resume.add_argument("job_id")
    resume.add_argument("answer")
    check = job_sub.add_parser("polynomial-check")
    check.add_argument("job_id")
    check.add_argument("payload", help="JSON object matching the polynomial_check schema")

    files = subparsers.add_parser("file")
    files_sub = files.add_subparsers(dest="action", required=True)
    files_sub.add_parser("list")
    upload = files_sub.add_parser("upload")
    upload.add_argument("path", type=Path)
    delete = files_sub.add_parser("delete")
    delete.add_argument("file_id")

    probe = subparsers.add_parser("probe", help="submit a problem and print the live node trace and report")
    probe.add_argument("problem", nargs="?", default="求解方程 x+1=2，并给出简要验证。")
    probe.add_argument("--session-id")
    probe.add_argument("--allow-non-live", action="store_true", help="allow a fake server (disabled by default)")
    return parser


def run(args: argparse.Namespace) -> int:
    client = ShowcaseClient(args.base_url, args.cookie_file, args.timeout)
    if args.command == "health":
        _print(client.request("GET", "/health"))
        return 0
    client.bootstrap()
    if args.command == "capabilities":
        _print(client.request("GET", "/api/capabilities"))
    elif args.command == "logout":
        _print(client.request("POST", "/api/logout", payload={}))
    elif args.command == "session":
        _run_session(client, args)
    elif args.command == "job":
        _run_job(client, args)
    elif args.command == "file":
        _run_file(client, args)
    elif args.command == "probe":
        _run_probe(client, args)
    else:  # pragma: no cover - argparse enforces the command set
        raise CliError("command_invalid")
    return 0


def _run_session(client: ShowcaseClient, args: argparse.Namespace) -> None:
    if args.action == "list":
        _print(client.request("GET", "/api/sessions"))
    elif args.action == "create":
        _print(client.request("POST", "/api/new_chat", payload={}))
    elif args.action == "load":
        _print(client.request("GET", f"/api/load_session?{urlencode({'session': args.session_id})}"))
    elif args.action == "rename":
        _print(client.request("POST", "/api/change_session", payload={"session_id": args.session_id, "title": args.title}))
    elif args.action == "delete":
        _print(client.request("POST", "/api/delete_session", payload={"session_id": args.session_id}))


def _run_job(client: ShowcaseClient, args: argparse.Namespace) -> None:
    if args.action == "submit":
        payload = {
            "session_id": args.session_id,
            "message": args.message,
            "verification_mode": args.verification_mode,
            "web_search_enabled": False,
        }
        if args.file_id:
            payload["input_user_file_id"] = args.file_id
        _print(client.request("POST", "/api/agent/jobs", payload=payload, headers=client.idempotency_headers()))
    elif args.action == "status":
        _print(client.request("GET", f"/api/agent/jobs/{args.job_id}"))
    elif args.action in {"events", "watch"}:
        events = client.events(args.job_id)
        for event in events:
            if event.get("event") != "heartbeat":
                _print(event)
    elif args.action == "report":
        _print(client.request("GET", f"/api/agent/jobs/{args.job_id}/report"))
    elif args.action == "cancel":
        _print(client.request("POST", f"/api/agent/jobs/{args.job_id}/cancel", payload={}, headers=client.idempotency_headers()))
    elif args.action == "resume":
        _print(client.request("POST", f"/api/agent/jobs/{args.job_id}/resume", payload={"answer": args.answer}, headers=client.idempotency_headers()))
    elif args.action == "polynomial-check":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as exc:
            raise CliError("polynomial_payload_invalid") from exc
        _print(client.request("POST", f"/api/agent/jobs/{args.job_id}/polynomial-check", payload=payload))


def _run_file(client: ShowcaseClient, args: argparse.Namespace) -> None:
    if args.action == "list":
        _print(client.request("GET", "/api/files"))
    elif args.action == "delete":
        _print(client.request("POST", "/api/delete_file", payload={"file_id": args.file_id}))
    elif args.action == "upload":
        content = args.path.read_bytes()
        boundary = f"----MathAgent{uuid.uuid4().hex}".encode()
        body = (
            b"--" + boundary + b"\r\n"
            + f'Content-Disposition: form-data; name="file"; filename="{args.path.name}"\r\n'.encode()
            + b"Content-Type: image/png\r\n\r\n" + content + b"\r\n--" + boundary + b"--\r\n"
        )
        _print(client.request("POST", "/api/upload_file", body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary.decode()}"}))


def _run_probe(client: ShowcaseClient, args: argparse.Namespace) -> None:
    capabilities = client.request("GET", "/api/capabilities")
    execution = capabilities.get("execution", {}) if isinstance(capabilities, dict) else {}
    if not args.allow_non_live and (execution.get("mode") != "live" or execution.get("status") != "configured"):
        raise CliError("live_mode_required")
    session_id = args.session_id
    if not session_id:
        session_id = client.request("POST", "/api/new_chat", payload={}).get("new_session_id")
    if not session_id:
        raise CliError("session_id_missing")
    accepted = client.request(
        "POST",
        "/api/agent/jobs",
        payload={"session_id": session_id, "message": args.problem, "verification_mode": "auto", "web_search_enabled": False},
        headers=client.idempotency_headers(),
    )
    _print({"phase": "accepted", **accepted})
    job_id = accepted.get("job_id")
    if not job_id:
        raise CliError("job_id_missing")
    for event in client.events(job_id):
        if event.get("event") != "heartbeat":
            _print(event)
    _print({"phase": "report", "report": client.request("GET", f"/api/agent/jobs/{job_id}/report")})


def _parse_sse(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in raw.split("\n\n"):
        if not block.strip():
            continue
        event_name = "message"
        event_id: int | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("id:"):
                try:
                    event_id = int(line[3:].strip())
                except ValueError:
                    event_id = None
            elif line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        try:
            data = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            data = {"raw": "\n".join(data_lines)}
        events.append({"id": event_id, "event": event_name, "data": data})
    return events


def _decode_json(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw": raw.decode("utf-8", errors="replace")}


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (CliError, OSError) as exc:
        code = exc.code if isinstance(exc, CliError) else type(exc).__name__
        print(json.dumps({"error": code}, ensure_ascii=False), file=sys.stderr)
        return 1


__all__ = ["CliError", "ShowcaseClient", "build_parser", "main"]
