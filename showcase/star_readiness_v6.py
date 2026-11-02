"""Single fresh multi-step sample envelope for Issue #97."""

V6_DRAFT_VERSION = "issue-97-nonstream-draft-v6"
V6_AUTHORIZATION_SCOPE = "issue-97-single-question-nonstream-batch-v6"
V6_PREVIOUS_DRAFT_SHA256 = "31e94716f82e0aaf9a52fe3f7df44df4a2316338811e78eab11e32df4aa355ab"
V6_QUESTION_SPECS = (
    (
        "multi-05",
        "https://www.imo-official.org/assets/documents/problems/2024/2024_eng.pdf#page=2",
        "public_multistep",
        "ef159e27e553a719f4cd411de7eef28ece951b3c1a332f8f9ddb56f4f64f64b4",
    ),
)
V6_MODEL = {
    "max_output_tokens": 8192, "name": "intern-s2", "request_timeout_seconds": 600,
    "retry": 3, "solver_mode": "star_reference", "temperature": 0.2,
    "thinking_mode": True, "verification_mode": "auto",
}
V6_RUN_LIMITS = ({
    "charged_tokens": 65536, "http_attempts": 16, "logical_calls": 12,
    "problem_tool_calls": 3, "wall_seconds": 3600,
},)
V6_ROUND_LIMITS = {
    "charged_tokens": 65536, "environment_preflights": 3, "http_attempts": 16,
    "logical_calls": 12, "problem_tool_calls": 3, "runs": 1,
    "tools_including_environment": 6, "wall_seconds": 3900,
}
