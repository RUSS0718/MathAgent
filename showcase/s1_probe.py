"""Explicit one-attempt S1 gate, separate from the multi-role Demo pipeline."""

from __future__ import annotations

from .adapters import AdapterError, InternModelAdapter
from .request_attempts import capture_pipeline_attempts


class S1ProbePipeline:
    """Workspace-compatible G1 pipeline with a fixed one-request envelope."""

    def __init__(self):
        from llm_client import InternChatClient

        client = InternChatClient(timeout=120, retry=1, thinking_mode=True)
        client.model = "intern-s2"
        self.model = InternModelAdapter(client, model_id="intern-s2", max_tokens=256)

    @capture_pipeline_attempts
    def run(self, run_id, problem, *, verification_mode="off", emit=None):
        del problem, verification_mode
        try:
            self.model.complete(
                [{"role": "user", "content": "计算 1+1。只给出简短答案。"}],
                metadata={"run_id": run_id, "role": "g1"},
            )
            return {
                "status": "COMPLETED",
                "stage": "completed",
                "final_response": "G1 请求工程合同通过；本探测不评价数学能力。",
                "summary": "S1 G1 单次请求工程合同通过",
                "tool_results": [],
                "verification": {
                    "status": "unknown",
                    "findings": ["not_a_math_capability_evaluation"],
                },
            }
        except AdapterError as exc:
            return {
                "status": "FAILED",
                "stage": "failed",
                "final_response": None,
                "summary": "S1 G1 已消耗本次请求额度，live gate 阻塞",
                "error": {"category": exc.category},
                "tool_results": [],
                "verification": {"status": "unknown", "findings": ["live_gate_blocked"]},
            }
