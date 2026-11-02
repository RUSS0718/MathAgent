"""Byte-wire compatibility for the process-exit SSE fixture."""

import json
import sqlite3
import time
from contextlib import closing


class ByteStreamReply:
    """Frame old fixture lines as bytes and await the actual first audit commit."""

    status_code = 200

    def __init__(self, reply, folder, context, window):
        self.reply, self.folder = reply, folder
        self.call_id, self.window = context["call_id"], window

    def raise_for_status(self):
        self.reply.raise_for_status()

    def close(self):
        self.reply.close()

    def iter_content(self, chunk_size=1):
        for index, line in enumerate(self.reply.iter_lines()):
            yield (line + "\n\n").encode()
            if index == 0 and self.window == "stream_exit":
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    with closing(sqlite3.connect(self.folder / "showcase.sqlite3")) as db:
                        row = db.execute("SELECT state_json FROM solver_states").fetchone()
                    if row and json.loads(row[0]).get("calls", {}).get(
                        self.call_id, {}).get("partial_text"):
                        break
                    time.sleep(.01)
                else:
                    raise AssertionError("first SSE fragment never reached the persisted audit")
