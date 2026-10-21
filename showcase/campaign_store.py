"""Durable batch intents and content addressed local archives."""

import json
import os
import sqlite3
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .campaign_contract import digest, encoded
from .workspace import WorkspaceError


class CampaignStore:
    def __init__(self, database_path, archive_root):
        self.database_path = str(database_path)
        self.archive_root = Path(archive_root)
        self.lock = threading.RLock()
        with self.connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS campaigns (campaign_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, idempotency_key TEXT NOT NULL, input_hash TEXT NOT NULL, document TEXT NOT NULL, UNIQUE(user_id,idempotency_key))"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.database_path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def claim(self, user_id, key, config, source):
        input_hash = digest(config)
        with self.lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT input_hash,document FROM campaigns WHERE user_id=? AND idempotency_key=?",
                (user_id, key),
            ).fetchone()
            if existing:
                if existing[0] != input_hash:
                    raise WorkspaceError("idempotency_conflict", status=409)
                return json.loads(existing[1]), True
            campaign_id = "campaign_" + uuid.uuid4().hex
            common_hash = digest(config["common"])
            document = {
                "schema_version": 1,
                "campaign_id": campaign_id,
                "common": config["common"],
                "common_hash": common_hash,
                "config_hash": input_hash,
                "source": source,
                "strategies": config["strategies"],
                "status": "incomplete",
                "pairs": [],
            }
            document["mode"] = "fake"
            document["config_archive"] = {
                "path": f"{campaign_id}/config-{input_hash}.json",
                "sha256": input_hash,
            }
            for problem in config["problems"]:
                document["pairs"].append(
                    {
                        "pair_id": problem["id"],
                        "problem_hash": digest(problem["problem"]),
                        "common_hash": common_hash,
                        "arms": {
                            arm: {
                                "status": "incomplete",
                                "job_id": None,
                                "idempotency_key": str(uuid.uuid4()),
                                "cost": None,
                                "quality": {"status": "unknown"},
                                "usage": {
                                    "http_attempts": None,
                                    "provider_known": None,
                                    "provider_unknown_fields": None,
                                    "unknown_attempts": None,
                                },
                                "strategy_status": "not_started",
                            }
                            for arm in ("baseline", "candidate")
                        },
                    }
                )
            connection.execute(
                "INSERT INTO campaigns VALUES (?,?,?,?,?)",
                (campaign_id, user_id, key, input_hash, encoded(document).decode()),
            )
        self.archive(campaign_id, "config", config)
        return document, False

    def get(self, campaign_id, user_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT document FROM campaigns WHERE campaign_id=? AND user_id=?",
                (campaign_id, user_id),
            ).fetchone()
        if not row:
            raise WorkspaceError("campaign_not_found", status=404)
        return json.loads(row[0])

    def save(self, document, user_id):
        with self.connect() as connection:
            connection.execute(
                "UPDATE campaigns SET document=? WHERE campaign_id=? AND user_id=?",
                (encoded(document).decode(), document["campaign_id"], user_id),
            )

    def list(self, user_id, offset, limit):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT document FROM campaigns WHERE user_id=? ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def archive(self, campaign_id, kind, value):
        payload = encoded(value)
        content_hash = digest(value)
        directory = self.archive_root / campaign_id
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{kind}-{content_hash}.json"
        target = directory / name
        if not target.exists() or target.read_bytes() != payload:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    dir=directory, prefix=".archive-", delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        return {"path": f"{campaign_id}/{name}", "sha256": content_hash}
