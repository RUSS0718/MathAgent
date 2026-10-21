# 实验开发入口

日期：2026-10-21。本目录的计划与 proposed 规格不代表能力完成。

1. [总计划](research-program-plan.md)：目标、分支、Matt Pocock 流程、setup、基线、预算、停止与归档。
2. [develop 审计](develop-inspection.md)：固定源码基线与待修缺口。
3. [Intern S2 合同](intern-s2-api-contract.md)：官方来源、待探测能力、计量与公开字段。
4. [本轮设置状态](setup-status.md)：实际运行的检查与尚未完成的事项。
5. [机器可读实验配置](../../experiments/campaign.json)：默认 offline，各研究策略关闭；不是在线调度器。

## 各方向开发前材料

| 方向 | PRD | 技术文档 | ADR |
| --- | --- | --- | --- |
| R1 | [PRD](../prd/research-r1-prd.md) | [技术合同](../specs/research-r1-technical-spec.md) | [ADR-0008](../adr/0008-r1-same-model-actions.md) |
| R2 | [PRD](../prd/research-r2-prd.md) | [技术合同](../specs/research-r2-technical-spec.md) | [ADR-0009](../adr/0009-r2-observable-plan-interventions.md) |
| R3 | [PRD](../prd/research-r3-prd.md) | [技术合同](../specs/research-r3-technical-spec.md) | [ADR-0010](../adr/0010-r3-typed-verification-unknown.md) |
| R4 | [PRD](../prd/research-r4-prd.md) | [技术合同](../specs/research-r4-technical-spec.md) | [ADR-0011](../adr/0011-r4-scoped-evidence-identity.md) |
| R5 | [PRD](../prd/research-r5-prd.md) | [技术合同](../specs/research-r5-technical-spec.md) | [ADR-0012](../adr/0012-r5-final-artifact-risk-target.md) |

共同决策为 [ADR-0007](../adr/0007-experiment-boundary-and-budget.md)。新增算法前先完成对应公共切片与风险验证；文档默认 proposed，接受状态依据实际评审记录更新。
