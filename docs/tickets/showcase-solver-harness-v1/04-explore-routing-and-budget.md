# 04: 实现可离线复现的 Explore 路由与预算门禁

**What to build:** 开发者可用脚本模型跑出四种 Explore 评估，并在预算耗尽时得到零新增调用、可序列化的明确结果。

**Blocked by:** #03

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] `ScriptedModelPort` 能返回 SOLVED、PARTIALLY_SOLVED、NEED_PLAN、UNKNOWN。
- [ ] NEED_PLAN 和 UNKNOWN 不调用 Meta，直接进入 Plan。
- [ ] PARTIALLY_SOLVED 最多再探索一轮，随后进入 Plan。
- [ ] 模型调用前检查硬预算；耗尽后调用计数不增加。
- [ ] 预算耗尽返回合法状态和非编造文本。
- [ ] 支持 STAR AC-03 与 STAR AC-16 的 Explore 路由和预算边界。
- [ ] 测试不访问网络或真实凭证。
