"""SQLite LangGraph checkpoints and pending writes for product Run threads."""

from __future__ import annotations

import sqlite3
import threading

from langgraph.checkpoint.base import WRITES_IDX_MAP, BaseCheckpointSaver, CheckpointTuple


class RunCheckpointSaver(BaseCheckpointSaver):
    """Store LangGraph's serialized checkpoint without exposing it in reports."""

    def __init__(self, database_path=":memory:"):
        super().__init__()
        self.connection = sqlite3.connect(str(database_path), check_same_thread=False)
        self.lock = threading.RLock()
        self.connection.execute("PRAGMA busy_timeout = 5000")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS run_graph_checkpoints (
                thread TEXT, namespace TEXT, id TEXT, parent TEXT,
                checkpoint_type TEXT, checkpoint BLOB, metadata_type TEXT, metadata BLOB,
                PRIMARY KEY(thread,namespace,id)
            );
            CREATE TABLE IF NOT EXISTS run_graph_writes (
                thread TEXT, namespace TEXT, checkpoint_id TEXT, task TEXT, idx INTEGER,
                channel TEXT, value_type TEXT, value BLOB,
                PRIMARY KEY(thread,namespace,checkpoint_id,task,idx)
            );
        """)

    def get_tuple(self, config):
        values = config["configurable"]
        thread, namespace = values["thread_id"], values.get("checkpoint_ns", "")
        query = "SELECT * FROM run_graph_checkpoints WHERE thread=? AND namespace=?"
        params = [thread, namespace]
        if values.get("checkpoint_id"):
            query += " AND id=?"
            params.append(values["checkpoint_id"])
        query += " ORDER BY id DESC LIMIT 1"
        with self.lock:
            row = self.connection.execute(query, params).fetchone()
            if row is None:
                return None
            writes = self.connection.execute(
                "SELECT task,channel,value_type,value FROM run_graph_writes "
                "WHERE thread=? AND namespace=? AND checkpoint_id=? ORDER BY task,idx",
                (thread, namespace, row[2]),
            ).fetchall()

        def cfg(checkpoint_id):
            return {
                "configurable": {
                    "thread_id": thread,
                    "checkpoint_ns": namespace,
                    "checkpoint_id": checkpoint_id,
                }
            }

        return CheckpointTuple(
            config=cfg(row[2]),
            checkpoint=self.serde.loads_typed((row[4], row[5])),
            metadata=self.serde.loads_typed((row[6], row[7])),
            parent_config=cfg(row[3]) if row[3] else None,
            pending_writes=[
                (task, channel, self.serde.loads_typed((kind, value)))
                for task, channel, kind, value in writes
            ],
        )

    def put(self, config, checkpoint, metadata, new_versions):
        values = config["configurable"]
        kind, data = self.serde.dumps_typed(checkpoint)
        metadata_kind, metadata_data = self.serde.dumps_typed(metadata)
        thread, namespace = values["thread_id"], values.get("checkpoint_ns", "")
        with self.lock, self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO run_graph_checkpoints VALUES (?,?,?,?,?,?,?,?)",
                (
                    thread,
                    namespace,
                    checkpoint["id"],
                    values.get("checkpoint_id"),
                    kind,
                    data,
                    metadata_kind,
                    metadata_data,
                ),
            )
        return {
            "configurable": {
                "thread_id": thread,
                "checkpoint_ns": namespace,
                "checkpoint_id": checkpoint["id"],
            }
        }

    def put_writes(self, config, writes, task_id, task_path=""):
        values = config["configurable"]
        with self.lock, self.connection:
            for index, (channel, value) in enumerate(writes):
                kind, data = self.serde.dumps_typed(value)
                self.connection.execute(
                    "INSERT OR REPLACE INTO run_graph_writes VALUES (?,?,?,?,?,?,?,?)",
                    (
                        values["thread_id"],
                        values.get("checkpoint_ns", ""),
                        values["checkpoint_id"],
                        task_id,
                        WRITES_IDX_MAP.get(channel, index),
                        channel,
                        kind,
                        data,
                    ),
                )

    def is_interrupted(self, run_id):
        checkpoint = self.get_tuple({"configurable": {"thread_id": run_id}})
        return checkpoint is not None and any(
            channel == "__interrupt__" for _, channel, _ in checkpoint.pending_writes
        )

    def close(self):
        self.connection.close()
