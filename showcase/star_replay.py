"""Read-only saved-batch replay. No model, Registry or runtime is constructed."""

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from .solver_harness.storage import SolverPersistenceError, SolverStateStore
from .star_acceptance import RUNNER_VERSION, evaluate_delivery


def replay_saved_batch(batch, *, original_runner_version):
    """Verify historical export hashes and return a separate, prompt-free report.

    The old manifest does not attest SQLite: its current hash is recorded and
    its selected review is cross-checked against the attested public exports.
    Hashes establish consistency with supplied inputs, not archive authenticity.
    The caller owns writing the returned report outside the original archive.
    """
    batch = Path(batch).resolve()
    result = dict(
        runner_version=RUNNER_VERSION,
        original_runner_version=original_runner_version,
        external_dispatches=0,
        integrity="failed",
        input_hashes={},
        selection=dict(review_bound=False, proof_delivered=False, nonfastpath=False),
        limitations=[
            "LLM review is not formal or independent mathematical verification.",
            "Legacy manifest does not attest the SQLite snapshot.",
            "Historical registration eligibility is not reassessed.",
        ],
    )

    def read(name):
        path = (batch / name).resolve()
        if not path.is_relative_to(batch):
            raise ValueError("unsafe_archive_path")
        data = path.read_bytes()
        result["input_hashes"][name] = hashlib.sha256(data).hexdigest()
        return data

    try:
        manifest = json.loads(read("hashes.json"))
        for name, digest in manifest.items():
            if hashlib.sha256(read(name)).hexdigest() != digest:
                raise ValueError("archive_hash_mismatch")
        required = {
            "job.json",
            "report.json",
            "evidence.json",
            "role-contexts.json",
            "acceptance.json",
        }
        if not required.issubset(manifest):
            raise ValueError("archive_manifest_incomplete")
        job, report, evidence, contexts, old = (
            json.loads(read(name))
            for name in [
                "job.json",
                "report.json",
                "evidence.json",
                "role-contexts.json",
                "acceptance.json",
            ]
        )
        database = batch / "data/showcase.sqlite3"
        read("data/showcase.sqlite3")
        # immutable avoids WAL/shm creation in the original archive. Refuse a
        # pending WAL because immutable would silently ignore its newer state.
        if Path(str(database) + "-wal").exists():
            raise ValueError("archive_has_pending_wal")
        with closing(
            sqlite3.connect(database.as_uri() + "?mode=ro&immutable=1", uri=True)
        ) as connection:
            connection.row_factory = sqlite3.Row
            run = SolverStateStore(connection).get_run(job["job_id"])
        if not run:
            raise ValueError("solver_snapshot_missing")
        records = run["state"].get("whole_solution_reviews", [])
        public = report.get("checks", {})
        history = public.get("history", [])
        if (
            not records
            or len(records) != len(history)
            or public != evidence.get("verification")
            or report.get("answer") != job.get("result", {}).get("final_response")
            or any(
                record.get(key) != item.get(key)
                for record, item in zip(records, history)
                for key in ["artifact", "source", "proof_sources"]
            )
            or public.get("source") != records[-1].get("source")
        ):
            raise ValueError("public_snapshot_source_mismatch")
        result.update(
            integrity="verified",
            original_proof_delivered=old.get("proof_delivered"),
            selection=evaluate_delivery(job, run, contexts),
        )
        result["difference_reason"] = (
            "Resolve delivered review call and candidate lineage instead of first role occurrence."
            if old.get("proof_delivered") != result["selection"]["proof_delivered"]
            else "No change to proof delivery finding."
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        sqlite3.Error,
        SolverPersistenceError,
    ) as exc:
        result["reason"] = (
            type(exc).__name__
            + ":"
            + (
                str(exc)
                if str(exc)
                in {
                    "unsafe_archive_path",
                    "archive_hash_mismatch",
                    "archive_manifest_incomplete",
                    "archive_has_pending_wal",
                    "solver_snapshot_missing",
                    "public_snapshot_source_mismatch",
                }
                else "missing_or_invalid_archive_evidence"
            )
        )
    return result
