# 17: 候选登记、来源与失效传播

**What to build:** Explore、Step 和 Finalize 的完整答案都能追加为带来源的候选；反例、回退和重规划会准确取消其选择资格。

**Blocked by:** #15

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 完整候选拥有唯一 ID、来源阶段、计划版本、事件引用和证据引用。
- [ ] 新候选不覆盖旧版本；历史候选仍可审计。
- [ ] 已推翻候选不能进入最终选择。
- [ ] 依赖被 Trace-Back 撤销的候选自动失效。
- [ ] 候选状态区分草稿、可选取、已审查、已推翻和已失效。
- [ ] 支持 STAR AC-34、STAR AC-35、STAR AC-36 的登记、推翻和失效传播。
