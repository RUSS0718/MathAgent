# SH16：调用中断与恢复合同

状态：已实现的离线工程合同；不构成真实模型可用性或数学能力证据。

入口是 `SolverHarness.solve/get_run`，通过 `features.stream_recovery: true` 显式启用，默认关闭。原有阶段名称不变，公开状态增加 `interrupted` 和 `recovered_pending_validation`。模型、Verifier、Meta 和最终生成均沿共享 dispatch 调用审计。

调用前持久化 run/problem/config、角色、会话、call_id、请求摘要与状态版本；不保存原题和完整组合 Prompt。流式端口返回可迭代对象：字符串或 `{type: text_delta, text: ...}` 为片段，`{result: <结构化结果>, usage: ...}` 为已完成结果。普通字典仍为同步完成结果。片段逐条脱敏落盘，工具错误和带 `partial_text` 属性的异常保留未完成内容，不能形成 ACCEPT。没有已知完成结果时，用量是 `null`，不能推断为零。

新实例读取旧实例留下的 dispatched/streaming 记录时，将其标记为 unknown_outcome。该状态表示恢复方无法证明外部请求完成，并不证明请求未执行。没有跨进程取消或提供方 exactly-once 保证。普通 solve 不重试；显式 `metadata.retry_call = {call_id: <旧ID>, new_call_id: <新ID>}` 才可发起新调用，且计入全局调用预算。必须重新传入同一道原题，通过问题哈希校验。复用同一重试决定不会再发出调用。

重试结果只进入审计记录，公开状态为 recovered_pending_validation；不直接写入已接受结论或最终答案，也不自动重新执行历史控制器路径。操作方应将恢复结果交回正常校验流程后再继续。终态 solve 幂等；终态 commit_event 只允许空补充事件、已有事件的原样重放、以及只改 calls 的 call_audit 补丁。迟到响应仅记录 ignored_late_response，不能覆写终态答案、阶段或账本。

验收使用 `uv run python -m unittest tests.test_solver_harness_streaming`：覆盖逐片段检查点、异常与工具错误、进程重建、显式新 ID 重试、Verifier/Meta 路径、完成幂等和迟到响应。另运行 Harness 与 Run 回归及 Ruff。未运行 live provider。
