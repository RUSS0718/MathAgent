# 05: 完成整题审查与 v1.1 收口

**What to build:** Explore 声称解出时，整题审查可以接受候选或拒绝并交接 Plan；v1.1 的延期项都有唯一 ticket、依赖和验收入口。

**Blocked by:** #03, #04

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Explore SOLVED 且审查 ACCEPT 时结束为 `completed_llm_reviewed`，不进入 Plan。
- [ ] 审查 REJECT 时保留探索发现并进入 Plan，不标为已审查通过。
- [ ] 两条 Explore 分支都有独立断言，不使用单路径假测试。
- [ ] 支持 STAR AC-01、STAR AC-02、STAR AC-17 的 Explore 与扩展关闭边界。
- [ ] AC-SH-01..08 全部有实际结果。
- [ ] SC-001..SC-043 各有唯一 v1.1/v1.2 归属。
- [ ] 验收记录写明 `engineering-preview`、`v0.2 AC-06` 延期和未证明项。
