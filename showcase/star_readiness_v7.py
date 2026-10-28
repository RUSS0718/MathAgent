"""Answer-completion envelope for the next Issue #97 registration draft."""

V7_DRAFT_VERSION = "issue-97-nonstream-draft-v7"
V7_ADAPTER_VERSION = "issue-97-registration-adapter-v4"
V7_AUTHORIZATION_SCOPE = "issue-97-single-question-nonstream-batch-v7"
V7_PREVIOUS_DRAFT_SHA256 = "eb2324ac3f74a9f55e9c879f5f6716d021212f0b3ee1b8d0cf3529b9b1ae3423"

V7_QUESTION_SPECS = (
    (
        "multi-05",
        "https://www.imo-official.org/assets/documents/problems/2024/2024_eng.pdf#page=2",
        "public_multistep",
        "ef159e27e553a719f4cd411de7eef28ece951b3c1a332f8f9ddb56f4f64f64b4",
    ),
)
V7_MODEL = {
    "max_output_tokens": 16384,
    "name": "intern-s2",
    "request_timeout_seconds": 900,
    "retry": 3,
    "solver_mode": "star_reference",
    "temperature": 0.2,
    "thinking_mode": True,
    "verification_mode": "auto",
}
V7_RUN_LIMITS = ({
    "charged_tokens": 524288,
    "http_attempts": 72,
    "logical_calls": 24,
    "problem_tool_calls": 8,
    "wall_seconds": 7200,
},)
V7_ROUND_LIMITS = {
    "charged_tokens": 524288,
    "environment_preflights": 3,
    "http_attempts": 72,
    "logical_calls": 24,
    "problem_tool_calls": 8,
    "runs": 1,
    "tools_including_environment": 11,
    "wall_seconds": 7500,
}
