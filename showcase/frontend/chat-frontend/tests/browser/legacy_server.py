"""Serve the three presentation templates for isolated browser tests only."""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
from presentation_pages import render_presentation_page  # noqa: E402


class Handler(BaseHTTPRequestHandler):
    """Read-only templates; tests intercept POST requests without model calls."""

    def do_GET(self):  # noqa: N802
        """Return only fixed, code-owned template names."""
        kind = self.path.strip("/")
        if kind not in {"demo", "showcase", "unbuilt"}:
            self.send_error(404)
            return
        body = render_presentation_page(kind).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        """Do not record form content."""


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 5177), Handler).serve_forever()
