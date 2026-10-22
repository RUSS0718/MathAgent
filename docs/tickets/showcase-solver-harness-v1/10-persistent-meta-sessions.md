# 10: 持久 Meta 会话与结构化干预

**What to build:** 同一题的 Meta 跨计划保留历史并输出可校验决策；不同题不共享 Meta 上下文。

**Blocked by:** #08

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Meta 支持 `CONTINUE`、`TRACE_BACK`、`APPROVE_REPLAN`、`ABORT`。
- [ ] 同一题不同计划可读取先前失败与干预结果。
- [ ] 不同 Run 的 Meta 会话不交叉。
- [ ] timeout、code_issue、stuck 能产生具体可路由行动。
- [ ] Meta 无代码执行与权威状态写入权限。
- [ ] 支持 STAR AC-12、STAR AC-24、STAR AC-25 的持久会话、诊断和纯推理权限。
