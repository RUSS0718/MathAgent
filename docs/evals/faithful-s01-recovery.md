# Faithful S01 恢复与终态验收

日期：2026-11-07（Asia/Shanghai）。策略：`faithful-stream-v1`。适配器：`InternStreamAdapter`。

本记录覆盖受控 HTTP、公共 Job、SQLite 持久化和真实子进程退出。provider 请求由脚本化 loopback transport 提供，不代表真实 provider 可用性、SLA 或数学能力。本分支基于并合并了 `mathagent-faithful` 集成 tip `96991db`，并保留独立验证者提交的浏览器材料。

## 验收结果

- 同一 `Idempotency-Key` 重放创建请求时，HTTP 返回原 Job 与冻结策略。只执行原来的三个 provider 请求，不新增 Job 或预算预留。
- 专用 worker 在 SSE 中途执行 `os._exit`。新进程重开 Job 后保留 unknown 调用；普通 resume 返回 409 且不发请求。显式新调用 ID 恢复时，旧 unknown、预留 tokens、原 deadline 和答案绑定均保留。
- 在 `os._exit` 前已持久化的完成回执会被恢复路径复用。恢复不重复执行已完成的 Explore 或 step verifier 请求。
- 完整但 schema 无效的流被列为 `protocol_failed`，保留 finish reason 与 provider usage，不进入 unknown 列表；普通 resume 不重发。
- 取消中的完整迟到流只结算原请求用量，不推进 solver 或改写答案。恢复后成功 Job 收到迟到完成回执时，状态、答案、solver 快照和交付绑定不变。
- 冻结策略下，完整远端流在 EOF 后的本地汇总超过 deadline 时记为 `local_processing_failed`，公开 finish reason 和 usage；数学步骤不提交，普通 resume 被拒。
- 未完成流的事件 parser 超时仍归为 unknown。旧 Run 未冻结流策略时，EOF 汇总超时仍保留旧 unknown 分类；无处理失败的 recovery DTO 不增加 `processing_failures`，且保持既有字段集合。

## 执行证据

新增验收通过：

```powershell
uv run --frozen python -m unittest tests.test_faithful_s01_recovery
# Ran 6 tests in 24.468s — OK

uv run --frozen python -m unittest tests.test_faithful_s01_processing
# Ran 3 tests in 14.050s — OK
```

复用的旧策略与终态回归通过：

```powershell
uv run --frozen python -m unittest tests.test_star_product_streaming_recovery.StarStreamingRecoveryTest.test_mid_stream_timeout_keeps_unknown_reservation_and_requires_explicit_retry tests.test_star_product_streaming_recovery.StarStreamingRecoveryTest.test_schema_invalid_complete_stream_is_not_normalized_and_never_shows_probability tests.test_star_product_streaming_recovery.StarStreamingRecoveryTest.test_process_exit_mid_stream_keeps_unknown_and_requires_explicit_new_identity
# Ran 3 tests in 14.571s — OK

uv run --frozen python -m unittest tests.test_star_job_parse_deadline_98.JobParseDeadlineTest.test_blocked_stream_event_finishes_job_before_late_parser_release tests.test_star_job_parse_deadline_98.JobParseDeadlineTest.test_late_stream_assembly_does_not_publish_after_terminal_job tests.test_star_product_control.StarControlTest.test_late_usage_settles_after_cancel_without_next_role_or_math_progress tests.test_star_product_recovery.StarRecoveryTest.test_cancel_during_explicit_retry_preserves_late_unknown_and_stops_math tests.test_star_product_recovery.StarRecoveryTest.test_process_exit_after_recorded_verifier_response_reuses_it
# Ran 5 tests in 14.446s — OK
```

`ruff check` 通过，`git diff --check` 通过。没有运行全仓长测或真实 provider 请求。

## 边界

本轮未运行集成树中的浏览器 spec；浏览器证据单独保存在 [`faithful-s01-browser.md`](faithful-s01-browser.md)，不与本记录的后端跨进程证据合并表述。provider-live、自然题数学效果、真实服务容量与费用仍未验收。该离线切片只关闭这里列出的后端恢复、分类和终态组合，不单独宣告整个 S01 退出。
