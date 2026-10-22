# 22: 配对实验与成本证据

**What to build:** 实验者能对相同题目、模型版本、工具权限和预算运行配对比较，并保留失败、unknown 和真实成本来源。

**Blocked by:** #15, #21

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 配对双方只有允许的实验策略不同。
- [ ] 报告保留双方结果、调用、耗时、失败和 unknown。
- [ ] Token 或费用未知时写 null/unknown，不用字符数替代。
- [ ] 无扩展的受限运行标记准确 Profile 和跳过原因。
- [ ] 工程比较不声明数学正确率提升。
- [ ] 支持 STAR AC-20、STAR AC-33 的配对、未知用量和受限 Profile 证据。
