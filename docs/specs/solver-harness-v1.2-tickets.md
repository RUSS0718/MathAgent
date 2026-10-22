# Solver Harness v1.2 Ticket 索引

**状态：** planned  
**依赖：** v1.1 的 SH-01..SH-05 全部关闭  
**权威范围：** [`showcase-solver-harness-v1.1-spec.md`](showcase-solver-harness-v1.1-spec.md) 与 STAR Core 实施规格

v1.1 关闭前，本文件只冻结延期项的归属、依赖和验收入口；不提前实现，也不创建 GitHub Issue。每个 ticket 在进入 v1.2 时必须补齐文件所有权、失败测试和退出命令。

| Ticket | 范围 | 依赖 | 验收入口 |
| --- | --- | --- | --- |
| SH-06 | 逐步执行、验证标签、Goal/Logic Gate | SH-05 | AC-05、STAR AC-06 |
| SH-07 | Challenge 连续会话与轮数上限 | SH-06 | AC-07、AC-08 |
| SH-08 | Meta 持久会话、动作路由与纯推理权限 | SH-07 | AC-11、AC-12、AC-24、AC-25 |
| SH-09 | Trace-Back、救援结果与失效传播 | SH-07、SH-08 | AC-09、AC-10、AC-28、AC-29 |
| SH-10 | Re-plan、禁止方向与后重规划探索 | SH-08、SH-09 | AC-11、AC-12、AC-26、AC-33 |
| SH-11 | 最终生成、整题 Verifier 与部分结果 | SH-06、SH-09 | AC-13、AC-30 |
| SH-12 | 七类 Skill、三层 Prompt 与按需加载 | SH-06 | AC-19、AC-31 |
| SH-13 | 工具沙箱、`easy-verify` 预检和错误恢复 | SH-06、SH-12 | STAR AC-06、AC-14、AC-27 |
| SH-14 | 流式部分输出、session 注册与重启恢复 | SH-07、SH-08 | AC-15、AC-22、AC-23、AC-32 |
| SH-15 | CandidateRegistry 与 Best-Effort Finalizer | SH-11 | AC-34、AC-35、AC-36、AC-37、AC-38、AC-39 |
| SH-16 | 证据等级、输出隔离与重放审计 | SH-15、SH-11 | AC-40、AC-41、AC-42、AC-43、AC-44 |
| SH-17 | 真实 Intern 适配、配对实验与发布门禁 | SH-13、SH-16 | v0.2 AC-06、AC-18、AC-20、AC-33 |

## v1.1 已覆盖验收

| AC | 对应 v1.1 用例 |
| --- | --- |
| AC-01 | AC-SH-01 |
| AC-02 | AC-SH-02 |
| AC-03 | AC-SH-03、AC-SH-04 |
| AC-04 | deferred；v1.1 只验证 Plan 交接，不验证非法计划修复 |
| AC-05 | AC-SH-01、AC-SH-02 的整题审查路由；逐步 Goal Gate 延期 |
| STAR AC-06 | deferred_to_v1.2 |
| AC-07 | deferred_to_v1.2 |
| AC-08 | deferred_to_v1.2 |
| AC-09 | deferred_to_v1.2 |
| AC-10 | deferred_to_v1.2 |
| AC-11 | deferred_to_v1.2 |
| AC-12 | deferred_to_v1.2 |
| AC-13 | 部分：AC-SH-02 的拒绝路径；完整重试延期 |
| AC-14 | deferred_to_v1.2 |
| AC-15 | AC-SH-05 |
| AC-16 | AC-SH-07 |
| AC-17 | AC-SH-08 |
| AC-18 | SH-01 官方 hash 检查；完整发布回归延期 |
| AC-19 | deferred_to_v1.2 |
| AC-20 | deferred_to_v1.2 |
| AC-21 | deferred_to_v1.2 |
| AC-22 | deferred_to_v1.2 |
| AC-23 | deferred_to_v1.2 |
| AC-24 | deferred_to_v1.2 |
| AC-25 | deferred_to_v1.2 |
| AC-26 | deferred_to_v1.2 |
| AC-27 | deferred_to_v1.2 |
| AC-28 | deferred_to_v1.2 |
| AC-29 | deferred_to_v1.2 |
| AC-30 | deferred_to_v1.2 |
| AC-31 | deferred_to_v1.2 |
| AC-32 | deferred_to_v1.2 |
| AC-33 | deferred_to_v1.2 |
| AC-34 | deferred_to_v1.2 |
| AC-35 | deferred_to_v1.2 |
| AC-36 | deferred_to_v1.2 |
| AC-37 | deferred_to_v1.2 |
| AC-38 | deferred_to_v1.2 |
| AC-39 | deferred_to_v1.2 |
| AC-40 | deferred_to_v1.2 |
| AC-41 | deferred_to_v1.2 |
| AC-42 | deferred_to_v1.2 |
| AC-43 | deferred_to_v1.2 |
| AC-44 | deferred_to_v1.2 |

## 退出规则

- 每个 ticket 必须先有失败测试或可执行验收用例；
- 未安装依赖或缺少凭证时保留跳过证据，不标为通过；
- 每个 ticket 关闭时更新 v1.1 验收记录的延期表；
- 只有 SH-01..SH-17 全部关闭，且 AC-01..AC-44 有实际结果，才能声明完整 STAR Core 工程合同完成；仍不得声明论文成绩复现。

