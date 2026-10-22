# 13: 七类 Skill、三层 Prompt 与权限组合

**What to build:** 角色调用按“角色定义、触发 Skill、最新状态投影”组合上下文，并能观测实际加载了哪些 Skill 与工具权限。

**Blocked by:** #07

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 七个 Skill 各有触发条件、输入、输出和权限说明。
- [ ] 未触发的 Skill 不进入上下文。
- [ ] 每次调用可观察到激活的 Skill 和状态投影版本。
- [ ] 工具权限来自运行时白名单，不只写在 Prompt 中。
- [ ] 支持 STAR AC-19：Meta 无 Shell/代码执行权限，跨题读取被拒且留下脱敏审计。
- [ ] 支持 STAR AC-31 的三层 Prompt 与可观察 Skill 组合。
