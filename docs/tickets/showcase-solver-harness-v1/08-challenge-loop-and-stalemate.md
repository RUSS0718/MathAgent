# 08: 连续 Challenge 与僵局升级

**What to build:** 一次 Challenge 让 Reasoner 回应具体异议、Verifier 在同一会话复检；达到上限时升级 Meta，不无限循环。

**Blocked by:** #07

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] 同一步 Challenge 双方保留连续辩论历史。
- [ ] 三轮后接受时只接受一次并保留全部轮次。
- [ ] 达到最大轮数仍无结论时进入 `STALEMATE` 并升级 Meta。
- [ ] 新步骤建立新的 Verifier 会话，不复用上一步历史。
- [ ] Challenge 进行期间不产生新步骤的接受结果。
- [ ] 支持 STAR AC-07、STAR AC-08 的连续辩论、上限和升级。
