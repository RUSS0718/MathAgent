# 12: 角色会话、最新投影与跨进程恢复

**What to build:** 每次角色调用前都注入最新授权状态，恢复后继续正确会话；不同题、不同计划尝试和不同步骤互不泄漏。

**Blocked by:** #07, #10

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Reasoner、Verifier、Meta 各有规定的会话范围。
- [ ] 新建或恢复会话均注入当前状态版本，不重复堆叠同一投影。
- [ ] Trace-Back/Re-plan 后使用新的 Reasoner 会话，旧历史仍可审计。
- [ ] 不同步骤的 Verifier 会话隔离；Meta 仅在同一 Run 内延续。
- [ ] 进程重建后能定位正确会话，身份或 hash 冲突时拒绝恢复。
- [ ] 支持 STAR AC-21、STAR AC-22、STAR AC-23 的会话与投影边界。
