# Solver Harness v1.2 任务索引

**状态：** planned

**依赖：** v1.1 的 SH-01..SH-05 全部关闭

**权威范围：** [Solver Harness v1.1 Spec](showcase-solver-harness-v1.1-spec.md) 与 STAR Core v1.2 合同

本文件只提供索引；每个 ticket 的可领取合同位于 `docs/tickets/showcase-solver-harness-v1/`，本地 `.scratch/showcase-solver-harness-v1/issues/` 为同一组文件的工作副本。v1.1 关闭前不实现 v1.2。

| Ticket | 交付结果 | Blocked by | 主验收 |
| --- | --- | --- | --- |
| SH-06 | 逐步 Reasoner 与可路由的结构化报告 | SH-05 | STAR AC-05、STAR AC-06 |
| SH-07 | 步骤级 Verifier 双 Gate 与非法裁决拒绝 | SH-06 | STAR AC-04、STAR AC-05 |
| SH-08 | 有状态 Challenge 与僵局升级 | SH-07 | STAR AC-07、STAR AC-08 |
| SH-09 | Trace-Back 归档、失效传播与救援 | SH-08 | STAR AC-09、STAR AC-10、STAR AC-28、STAR AC-29 |
| SH-10 | Meta 持久会话与四类决策 | SH-08 | STAR AC-11、STAR AC-12、STAR AC-24、STAR AC-25 |
| SH-11 | Re-plan 与后重规划受限再探索 | SH-09、SH-10 | STAR AC-11、STAR AC-12、STAR AC-26、STAR AC-33 |
| SH-12 | 四层会话、最新投影与跨进程隔离 | SH-07、SH-10 | STAR AC-21、STAR AC-22、STAR AC-23 |
| SH-13 | 七类 Skill、三层 Prompt 与运行时权限 | SH-07 | STAR AC-19、STAR AC-31 |
| SH-14 | 数学工具、执行证据与 `easy-verify` 预检 | SH-13 | STAR AC-06、STAR AC-14、STAR AC-27 |
| SH-15 | 最终生成与独立整题审查 | SH-09、SH-11 | STAR AC-13、STAR AC-30 |
| SH-16 | 流式中断、未知结果与恢复 | SH-12 | STAR AC-32、STAR AC-43 |
| SH-17 | 候选登记与失效传播 | SH-15 | STAR AC-34、STAR AC-35、STAR AC-36 |
| SH-18 | Best-Effort 预算兜底与确定性选择 | SH-17 | STAR AC-37、STAR AC-38、STAR AC-39 |
| SH-19 | 证据等级与内部账本 | SH-17 | STAR AC-40、STAR AC-44 |
| SH-20 | 结果隔离与零调用重放审计 | SH-18、SH-19 | STAR AC-41、STAR AC-42 |
| SH-21 | 真实 Intern 适配与 live 工具闭环 | SH-14、SH-16 | `v0.2 AC-06` |
| SH-22 | 配对实验与成本证据 | SH-15、SH-21 | STAR AC-20、STAR AC-33 |
| SH-23 | 官方边界与发布门禁 | SH-20、SH-22 | STAR AC-18 |

## 归属规则

- 每个 `SC-xxx` 和 `STAR AC-xx` 只在唯一主 ticket 中声明关闭；其他 ticket 只能引用。
- 依赖 ticket 未完成时，不创建会跳级的能力证据。
- live ticket 失败时保留失败记录，不把 fake/replay 改标为 live。
- v1.2 全部关闭仍不证明论文数值复现或数学正确率提升。

## 已由 v1.1 关闭的 STAR AC

| STAR AC | 主 ticket |
| --- | --- |
| STAR AC-01 | SH-05 |
| STAR AC-02 | SH-05 |
| STAR AC-03 | SH-04、SH-05 |
| STAR AC-15 | SH-02、SH-03 |
| STAR AC-16 | SH-04 |
| STAR AC-17 | SH-05 |

## SC 归属索引

| SC | 主 ticket |
| --- | --- |
| SC-001 | SH-01、SH-23 |
| SC-002 | SH-04、SH-07 |
| SC-003 | SH-04、SH-05 |
| SC-004 | SH-11 |
| SC-005 | SH-07 |
| SC-006 | SH-06 |
| SC-007 | SH-06、SH-14 |
| SC-008 | SH-07 |
| SC-009 | SH-08 |
| SC-010 | SH-09 |
| SC-011 | SH-10 |
| SC-012 | SH-11 |
| SC-013 | SH-15 |
| SC-014 | SH-13 |
| SC-015 | SH-12 |
| SC-016 | SH-02、SH-03 |
| SC-017 | SH-13、SH-14 |
| SC-018 | SH-04 |
| SC-019 | SH-21 |
| SC-020 | SH-07、SH-14 |
| SC-021 | SH-15、SH-20 |
| SC-022 | SH-05、SH-22 |
| SC-023 | SH-16、SH-22 |
| SC-024 | SH-23 |
| SC-025 | SH-01、SH-23 |
| SC-026 | SH-22 |
| SC-027 | SH-06、SH-19 |
| SC-028 | SH-12 |
| SC-029 | SH-12 |
| SC-030 | SH-12 |
| SC-031 | SH-10 |
| SC-032 | SH-10 |
| SC-033 | SH-11 |
| SC-034 | SH-14 |
| SC-035 | SH-09 |
| SC-036 | SH-15 |
| SC-037 | SH-13 |
| SC-038 | SH-16 |
| SC-039 | SH-17 |
| SC-040 | SH-18 |
| SC-041 | SH-19 |
| SC-042 | SH-20 |
| SC-043 | SH-16、SH-20 |
