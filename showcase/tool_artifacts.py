"""Immutable tool bytes with content integrity and explicit Run ownership."""

import hashlib
import json
import os
import re
import uuid
from pathlib import Path


class ToolArtifactError(ValueError):
    pass


class ToolArtifactStore:
    def __init__(self, root):
        self.root = Path(root)

    def put(self, run_id, call_id, kind, content, *, media_type="application/octet-stream"):
        self._run(run_id)
        self._call(call_id)
        if not isinstance(content, bytes):
            raise TypeError("artifact_bytes_required")
        digest = hashlib.sha256(content).hexdigest()
        ref = {"run_id": run_id, "call_id": call_id, "kind": kind, "sha256": digest,
               "size": len(content), "media_type": media_type}
        folder = self.root / run_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / digest
        if not target.exists():
            temporary = folder / (uuid.uuid4().hex + ".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, target)
        # A digest alone never grants another Run access.
        return ref

    def read(self, run_id, digest):
        self._run(run_id)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ToolArtifactError("artifact_ref_invalid")
        try:
            content = (self.root / run_id / digest).read_bytes()
        except OSError as exc:
            raise ToolArtifactError("artifact_not_found") from exc
        if hashlib.sha256(content).hexdigest() != digest:
            raise ToolArtifactError("artifact_integrity_failed")
        return content

    def verify(self, reference, *, run_id, call_id=None):
        if not isinstance(reference, dict) or reference.get("run_id") != run_id:
            raise ToolArtifactError("artifact_owner_mismatch")
        self._run(run_id)
        if call_id is not None and reference.get("call_id") != call_id:
            raise ToolArtifactError("artifact_call_mismatch")
        if call_id is not None:
            self._call(call_id)
        content = self.read(run_id, reference.get("sha256"))
        if len(content) != reference.get("size"):
            raise ToolArtifactError("artifact_size_mismatch")
        return content

    def receipt(self, run_id, call_id, outcome):
        encoded = json.dumps(outcome, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return self.put(run_id, call_id, "execution_receipt", encoded, media_type="application/json")

    @staticmethod
    def _run(run_id):
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
            raise ToolArtifactError("artifact_run_invalid")

    @staticmethod
    def _call(call_id):
        if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", call_id):
            raise ToolArtifactError("artifact_call_invalid")
