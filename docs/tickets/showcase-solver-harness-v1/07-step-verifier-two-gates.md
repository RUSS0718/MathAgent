# 07: 实现步骤级双 Gate 与严格裁决

**What to build:** Verifier 对目标完成度和逻辑证据分别裁决，只有双 Gate 通过且明确 `ACCEPT` 才能推进步骤。

**Blocked by:** #06

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Goal Gate 为 NO 时即使 Logic Gate 为 PASS，也不能接受。
- [ ] Logic Gate 非 PASS 时不能接受。
- [ ] 非法、模糊或解析失败的裁决绝不降级为 `ACCEPT`。
- [ ] `trace_back_to` 缺失或越界时拒绝该裁决。
- [ ] 接受的结果记录类别、来源、证据等级和依赖。
- [ ] 支持 STAR AC-04、STAR AC-05 的非法计划、双 Gate 和严格裁决。
