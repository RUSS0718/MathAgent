# 03: 拒绝过期 revision 并幂等提交事件

**What to build:** 两个基于同一快照的提交者竞争时，只有 revision 匹配的一方可以推进状态，重复事件不会重复生效。

**Blocked by:** #02

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] `expected_revision` 不匹配时提交被拒绝，更新后的状态不被覆盖。
- [ ] 同一 Run 重复提交相同 `event_id` 不增加事件或 revision。
- [ ] 成功提交按同一事务写入事件与下一 revision。
- [ ] 状态与事件读取保持一致，不暴露半提交结果。
- [ ] 三个既有回归文件原样通过。
- [ ] 支持 STAR AC-15 的幂等恢复边界。
