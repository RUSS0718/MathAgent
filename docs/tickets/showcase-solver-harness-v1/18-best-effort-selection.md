# 18: 硬预算下的 Best-Effort 确定性选择

**What to build:** 预算耗尽时只从已持久化、仍有效且完整的候选中选择答案，全程零新增模型、工具和 Verifier 调用。

**Blocked by:** #17

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 硬预算为零时模型、工具和 Verifier 调用均不增加。
- [ ] 选择先排除空白、不完整、被推翻、已失效和不合格候选。
- [ ] 按整题审查、独立证据、局部审查、未审查的固定顺序排序。
- [ ] 同级冲突记录 `candidate_conflict` 并用公开规则确定性决胜。
- [ ] 无合格候选时返回非空未解决说明，不伪造数值答案。
- [ ] 支持 STAR AC-37、STAR AC-38、STAR AC-39 的零调用、无候选和冲突边界。
