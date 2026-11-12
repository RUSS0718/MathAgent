"""One corrective solver turn after a known local Python source rejection."""

from __future__ import annotations

import json

SOURCE_REJECTIONS = frozenset({
    "call_not_allowed", "syntax_error", "syntax_not_allowed", "import_not_allowed",
    "name_not_allowed", "attribute_not_allowed",
})


def repair_messages(messages, request, record):
    """Keep the rejected call paired with its receipt and preserve conversation history."""
    receipt = {
        "tool_call_id": request.tool_call_id, "name": request.name,
        "status": "rejected", "error_category": record["error_category"],
        "value": None,
        "instruction": "代码未执行。仅有一次纠正机会：使用 sp.diff(expr, x) 等模块顶层调用，"
        "禁止表达式方法、危险导入和动态执行；也可直接给出答案并说明缺少工具证据。",
    }
    if request.protocol == "native":
        exchange = [
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": request.tool_call_id, "type": "function", "function": {
                    "name": request.name, "arguments": json.dumps(request.arguments, ensure_ascii=False),
                },
            }]},
            {"role": "tool", "tool_call_id": request.tool_call_id, "name": request.name,
             "content": json.dumps(receipt, ensure_ascii=False)},
        ]
    else:
        exchange = [
            {"role": "assistant", "content": request.assistant_content},
            {"role": "user", "content": json.dumps({"tool_result": receipt}, ensure_ascii=False)},
        ]
    return list(messages) + exchange
