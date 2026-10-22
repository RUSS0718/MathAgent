# 19: 证据等级与内部账本

**What to build:** 内部结果用 `high`、`medium`、`low`、`rejected` 描述证据充分性，并附理由、证据引用和未解决疑点。

**Blocked by:** #17

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 等级依据结构化证据生成，不依据模型自报置信度。
- [ ] 未校准时默认不输出数值概率。
- [ ] 理由代码、证据引用和未解决疑点可追溯。
- [ ] 局部 LLM 接受、计算成功或投票不能提升为形式化证明。
- [ ] 已推翻候选保持 `rejected`，不参与选择。
- [ ] 支持 STAR AC-40、STAR AC-44 的证据充分性与等级守恒。
