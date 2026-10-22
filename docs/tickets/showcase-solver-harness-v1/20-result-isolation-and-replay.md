# 20: 结果隔离与零调用重放

**What to build:** 内部审计元数据留在 Run/Evidence，正式适配器只输出允许字段；同一候选快照重放得到同一选择且零新增调用。

**Blocked by:** #18, #19

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 正式输出不泄漏 Best-Effort、冲突、未解决疑点或未知用量字段。
- [ ] 内部结果完整保留选择理由、排除集合、规则版本和终止原因。
- [ ] 同一快照重复执行选择得到相同候选和等级。
- [ ] 重放期间模型、工具和 Verifier 调用数均为零。
- [ ] 官方路径 schema 与默认预算保持不变。
- [ ] 支持 STAR AC-41、STAR AC-42 的正式输出隔离和零调用重放。
