# 11: Re-plan 与后重规划受限再探索

**What to build:** Meta 批准换计划后，旧计划归档，禁止方向和可复用结果进入新计划；受预算限制时可执行非代码再探索。

**Blocked by:** #09, #10

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 换计划前保存旧计划、失败原因与版本。
- [ ] 新计划读取禁止方向和仍有效的复用结果。
- [ ] Re-plan 增加计划版本与 Reasoner 尝试序号。
- [ ] 允许的再探索任务受预算、次数和工具权限限制。
- [ ] 超预算时不启动再探索任务并记录准确终止原因。
- [ ] 支持 STAR AC-11、STAR AC-12、STAR AC-26 的 Re-plan 和受限再探索合同。
