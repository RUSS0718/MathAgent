"""Dispatch ownership and durable batch state; token authority remains S3."""
import json
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

from .star_diagnostic_registration import ROOT

def default_registry():
    common = subprocess.check_output(["git", "rev-parse", "--git-common-dir"],
                                     cwd=ROOT, text=True).strip()
    return (ROOT / common).resolve() / "star-diagnostic-102" / "consumption.sqlite3"


def claim(registry, manifest, archive, *, continuation=False):
    registry = Path(registry)
    registry.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(registry)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS consumed (id TEXT PRIMARY KEY, digest TEXT UNIQUE, archive TEXT, state TEXT)")
        db.execute("BEGIN IMMEDIATE")
        old = db.execute("SELECT digest,archive,state FROM consumed WHERE id=? OR digest=?",
                         (manifest["registration_id"], manifest["sha256"])).fetchone()
        if old and not (continuation and old == (manifest["sha256"], str(Path(archive).resolve()), "control_complete")):
            raise ValueError("diagnostic_registration_consumed")
        if db.execute("SELECT state FROM consumed WHERE state IN ('running','unknown','interrupted','archive_failed')").fetchone():
            raise ValueError("diagnostic_unresolved_batch_blocks_start")
        if continuation:
            if not old or manifest["phase"] != "P":
                raise ValueError("diagnostic_continuation_unavailable")
            db.execute("UPDATE consumed SET state='running' WHERE id=?", (manifest["registration_id"],))
        else:
            db.execute("INSERT INTO consumed VALUES (?,?,?,?)", (manifest["registration_id"],
                       manifest["sha256"], str(Path(archive).resolve()), "running"))
        db.commit()


def mark(registry, manifest, status):
    with closing(sqlite3.connect(registry)) as db:
        db.execute("UPDATE consumed SET state=? WHERE id=? AND digest=?",
                   (status, manifest["registration_id"], manifest["sha256"]))
        db.commit()


def initialize(db, manifest):
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE diagnostic_batch (manifest TEXT, status TEXT, last_event TEXT, last_event_at REAL);
        CREATE TABLE diagnostic_dispatch (position INTEGER PRIMARY KEY, run_id TEXT UNIQUE,
            attempt_id TEXT UNIQUE, deadline REAL, status TEXT, result_sha256 TEXT);
    """)
    db.execute("INSERT INTO diagnostic_batch VALUES (?, 'running', 'started', ?)",
               (json.dumps(manifest), time.time()))
    db.commit()


def status(db, value):
    db.execute("UPDATE diagnostic_batch SET status=?,last_event=?,last_event_at=?", (value, value, time.time()))
    db.commit()
