# SP-08 安全恢复与未知重试合同

状态：公共故障注入验收通过；责任 #64，SP-AC-13/14；基点 `8f6f4f8`，已同步 SP-10 集成 `6027068`。实际证据见 [验收记录](../evals/star-product-sp08.md)。

## 接缝与验收

用户已在 #56/#64 确认接缝：认证 Job 创建、同一 Job resume/cancel、Run、SSE、报告、Evidence；可控 HTTP 提供方只注入回复和故障，不替换产品调度。

1. 第二步接受后退出，重开应用，同一 Job resume 执行第三步；原账本、题目、模式、deadline 不变，接受/出站/计费不重复。
2. 回复已审计而状态尚未推进时退出，恢复复用原回复，只推进一次数学状态。
3. unknown 默认 needs_review；普通 resume 拒绝。显式 retry_call 使用公开旧 ID 和新 ID，保留旧 unknown 及预留，不重置 deadline。
4. resume 与取消在现有控制事务中竞争；读 SSE/导出零出站。错误身份、重复 retry、非 unknown、终态和 deadline 旁路拒绝。
5. 工具回执已持久化、步骤报告尚未提交时复用回执；工具执行中退出且没有回执时拒绝续算，保留 unknown，不能自动重放工具。
6. 最终候选生成上限按同一 `plan_version` / `attempt_index` 的持久候选记录累计；恢复不能重置 `max_final_solution_retries`。已经生成的待审候选仍可显式新身份重试审查，即使生成额度已经用尽；审查拒绝后没有剩余额度则确定性终止。

实现顺序：公共失败用例 → 最小恢复实现 → 公共 unknown 重试用例 → 最小人工决策接线 → 故障反例及相关回归。

范围仅限显式 STAR sidecar；官方冻结路径不变。故障注入不作为 live 或数学能力证据。
