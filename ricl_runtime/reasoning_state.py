"""Run-local, content-addressed evidence with explicit dependency invalidation."""

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace

from .identity import stable_id
from .port import ToolCall, ToolReceipt


@dataclass(frozen=True)
class Evidence:
    """A verified result or successful controlled-tool receipt."""

    evidence_id: str
    result_id: str | None
    content: str
    scope: str
    source: str
    depends_on_all: tuple[str, ...] = ()
    depends_on_any: tuple[str, ...] = ()
    valid: bool = True


class SharedReasoningState:
    """Store reusable evidence and invalidate only conclusions that depend on it."""

    def __init__(self) -> None:
        self._evidence: dict[str, Evidence] = {}

    def add_verified_result(
        self,
        content: str,
        *,
        scope: str = "",
        depends_on_all: Iterable[str] = (),
        depends_on_any: Iterable[str] = (),
    ) -> Evidence:
        """Add a result already confirmed by an independent verifier."""

        all_ids = tuple(dict.fromkeys(depends_on_all))
        any_ids = tuple(dict.fromkeys(depends_on_any))
        for evidence_id in (*all_ids, *any_ids):
            if not self.is_valid(evidence_id):
                raise ValueError(f"dependency is missing or invalid: {evidence_id}")

        result_id = stable_id("result", {"content": content, "scope": scope})
        evidence_id = stable_id(
            "evidence",
            {
                "result_id": result_id,
                "scope": scope,
                "source": "independent_verifier",
                "depends_on_all": all_ids,
                "depends_on_any": any_ids,
            },
        )
        existing = self._evidence.get(evidence_id)
        if existing is not None:
            return existing
        evidence = Evidence(
            evidence_id=evidence_id,
            result_id=result_id,
            content=content,
            scope=scope,
            source="independent_verifier",
            depends_on_all=all_ids,
            depends_on_any=any_ids,
        )
        self._evidence[evidence_id] = evidence
        return evidence

    def add_tool_receipt(
        self,
        receipt: ToolReceipt,
        *,
        invocation_id: str,
        call: ToolCall,
    ) -> Evidence:
        """Accept only a successful receipt correlated to the controlled invocation."""

        if (
            not isinstance(receipt, ToolReceipt)
            or not receipt.success
            or receipt.invocation_id != invocation_id
            or receipt.tool_name != call.tool_name
            or not receipt.receipt_id
            or not receipt.tool_name
            or not isinstance(receipt.output, str)
        ):
            raise ValueError("tool receipt does not prove a successful controlled invocation")

        evidence_id = stable_id(
            "evidence",
            {"receipt_id": receipt.receipt_id, "tool_name": receipt.tool_name, "output": receipt.output},
        )
        existing = self._evidence.get(evidence_id)
        if existing is not None:
            return existing
        evidence = Evidence(
            evidence_id=evidence_id,
            result_id=None,
            content=receipt.output,
            scope=f"controlled tool: {receipt.tool_name}",
            source="controlled_tool",
        )
        self._evidence[evidence_id] = evidence
        return evidence

    def is_valid(self, evidence_id: str) -> bool:
        """Return whether an evidence item exists and remains valid."""

        evidence = self._evidence.get(evidence_id)
        return evidence is not None and evidence.valid

    def valid_evidence(self) -> tuple[Evidence, ...]:
        """Return current valid evidence in insertion order."""

        return tuple(evidence for evidence in self._evidence.values() if evidence.valid)

    def invalidate(self, evidence_id: str) -> tuple[str, ...]:
        """Invalidate one item and its broken AND/OR dependants."""

        if evidence_id not in self._evidence:
            raise ValueError(f"unknown evidence: {evidence_id}")
        if not self._evidence[evidence_id].valid:
            return ()

        invalidated = [evidence_id]
        self._evidence[evidence_id] = replace(self._evidence[evidence_id], valid=False)
        changed = True
        while changed:
            changed = False
            for candidate_id, candidate in tuple(self._evidence.items()):
                if not candidate.valid:
                    continue
                required_lost = any(not self.is_valid(dep) for dep in candidate.depends_on_all)
                alternatives_lost = bool(candidate.depends_on_any) and not any(
                    self.is_valid(dep) for dep in candidate.depends_on_any
                )
                if required_lost or alternatives_lost:
                    self._evidence[candidate_id] = replace(candidate, valid=False)
                    invalidated.append(candidate_id)
                    changed = True
        return tuple(invalidated)

    def public_snapshot(self) -> list[dict[str, object]]:
        """Return evidence metadata without storing its text in the run record."""

        return [
            {
                "evidence_id": evidence.evidence_id,
                "result_id": evidence.result_id,
                "scope": evidence.scope,
                "source": evidence.source,
                "depends_on_all": list(evidence.depends_on_all),
                "depends_on_any": list(evidence.depends_on_any),
                "valid": evidence.valid,
                "content_sha256": hashlib.sha256(evidence.content.encode("utf-8")).hexdigest(),
            }
            for evidence in self._evidence.values()
        ]