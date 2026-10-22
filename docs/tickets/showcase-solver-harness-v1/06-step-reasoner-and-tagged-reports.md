# 06: 产出带验证标签的逐步 Reasoner 报告

**What to build:** 开发者可从合法计划执行一个步骤，得到包含目标、论证、非平凡断言标签、证据引用和受阻状态的报告。

**Blocked by:** #05

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 每条非平凡断言恰好使用 `verified`、`easy-verify` 或 `hard-verify` 之一。
- [ ] `verified` 必须带实际执行证据引用。
- [ ] 缺少执行证据的 `easy-verify` 不会被报告为 `verified`。
- [ ] 报告可被后续 Verifier 读取并关联到对应步骤。
- [ ] 支持 STAR AC-06 与 SC-006、SC-027 的标签级证据边界。
