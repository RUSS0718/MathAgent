"""Project-owned frozen answer rules; never loads developer skills."""
import hashlib

VERSION = "user-output-v1"
RULES = {
    "solve": "保留已有答案原文。明确部分完成与未验证边界，不新增数学结论。",
    "teach": "依据给定答案解释思路、关键推导、理解难点及尚未解决之处。不得补造证明、假设或验证结果。只输出教学正文。",
    "report": "按问题、假设、结论、验证范围、未完成目标组织报告。只使用提供的来源，不虚构验证，不把表达成功当作数学证明。只输出报告正文。",
}

def frozen_rule(mode):
    text = RULES[mode]
    return {"version": VERSION, "mode": mode, "text": text,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "max_output_tokens": 4096, "timeout_seconds": 120, "max_attempts": 1}
