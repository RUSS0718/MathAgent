# 09: Trace-Back 归档、失效传播与救援

**What to build:** 从步骤 N 回退到合法 M 时，系统原子归档 M..N、失效依赖结果、保留可救援成果，并重建后续尝试。

**Blocked by:** #08

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] `M..N` 的报告、审查和辩论记录被归档而非删除。
- [ ] 依据被撤销前提的活动结果失效，下游依赖同步失效。
- [ ] 不依赖错误前提的成果进入救援引用并保留原证据等级。
- [ ] 新 Reasoner 尝试使用新会话身份。
- [ ] 缺失或非法 M 时不猜测目标，进入有记录的升级或终止。
- [ ] 支持 STAR AC-09、STAR AC-10、STAR AC-28、STAR AC-29 的归档、救援和账本隔离。
