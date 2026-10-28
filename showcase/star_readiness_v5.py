"""Proposed v5 sample and increased wall-clock envelope for Issue #97."""

V5_DRAFT_VERSION = "issue-97-nonstream-draft-v5"
V5_AUTHORIZATION_SCOPE = "issue-97-two-question-nonstream-batch-v5"
V5_PREVIOUS_DRAFT_SHA256 = "244178f1c57529cb372d9117bbb8ce47de91f135f1ae0aa9dee6784386a51fb8"

V5_QUESTION_SPECS = (
    (
        "simple-05",
        "https://projecteuler.net/problem=5",
        "simple_fastpath",
        "66e13c3935ec292ac66513bfbf76dc554e6e1e93c77f6ccbf1334ab98ce0f5e2",
    ),
    (
        "multi-04",
        "https://www.imo-official.org/assets/documents/problems/2025/2025_eng.pdf#page=2",
        "public_multistep",
        "db91a829df2f5ad0fc777006698bd95fd3c363946cb025956a6203d81d738e38",
    ),
)

V5_MODEL = {
    "max_output_tokens": 8192,
    "name": "intern-s2",
    "request_timeout_seconds": 600,
    "retry": 3,
    "solver_mode": "star_reference",
    "temperature": 0.2,
    "thinking_mode": True,
    "verification_mode": "auto",
}
V5_RUN_LIMITS = (
    {
        "charged_tokens": 32768,
        "http_attempts": 8,
        "logical_calls": 6,
        "problem_tool_calls": 1,
        "wall_seconds": 900,
    },
    {
        "charged_tokens": 65536,
        "http_attempts": 16,
        "logical_calls": 12,
        "problem_tool_calls": 3,
        "wall_seconds": 3600,
    },
)
V5_ROUND_LIMITS = {
    "charged_tokens": 98304,
    "environment_preflights": 3,
    "http_attempts": 24,
    "logical_calls": 18,
    "problem_tool_calls": 4,
    "runs": 2,
    "tools_including_environment": 7,
    "wall_seconds": 4800,
}
