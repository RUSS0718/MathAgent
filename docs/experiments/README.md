# 实验开发入口

日期：2026-10-21。本目录的计划与 proposed 规格不代表能力完成。

1. [总计划](research-program-plan.md)：目标、分支、Matt Pocock 流程、setup、基线、预算、停止与归档。
2. [develop 审计](develop-inspection.md)：固定源码基线与待修缺口。
3. [Intern S2 合同](intern-s2-api-contract.md)：官方来源、待探测能力、计量与公开字段。
4. [本轮设置状态](setup-status.md)：实际运行的检查与尚未完成的事项。
5. [机器可读实验配置](../../experiments/campaign.json)：默认 offline，各研究策略关闭；不是在线调度器。
6. [研究近邻来源](research-prior-sources.md)：正式论文与预印本状态分开记录。
7. [审查与交接](review-and-handoff.md)：两条审查轴的发现、修复和下一切片。
8. [setup PR 正文草案](setup-pr-draft.md)：面向 develop 的可审查说明，尚未创建远端 PR。
9. [S5 同题配对 Runner](s5-paired-runner.md)：显式运行、公共 API、未知 / 失败保留和归档合同；不代表 live 或数学提升验收。
10. [STAR 架构健壮性与组件作用实验方案](star-architecture-robustness-plan.md)：历史提案，未采纳为当前执行合同；保留组件测试映射。
11. [#97 非流式两题登记草案](star-readiness-97-preregistration-draft.md)：独立样本、预算及停止条件；当前仍无真实调用授权。工程结果见[就绪核对记录](../evals/star-readiness-97-status.md)。

## 离线预检入口

```bash
uv sync --locked --all-groups
uv run python scripts/check_experiment_setup.py --offline
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
```

预检 stdout 为 JSON；成功退出码为 0，合同错误为 2。需要保存时添加 `--output artifacts/<run_id>/experiment-preflight.json`。检查固定模型、关闭开关、有限且类型正确的预算、五方向文档和指定提交的官方哈希；不读取凭证、不发出网络请求。输出中的 `planned_not_implemented=true` 表示在线调度与研究算法尚待开发。

需保留配置中的基线提交对象；浅克隆先在安装步骤补齐历史，预检自身不会联网补拉。质量 CI 的 checkout 已配置完整历史，支持 detached HEAD。

## 各方向开发前材料

| 方向 | PRD | 技术文档 | ADR |
| --- | --- | --- | --- |
| R1 | [PRD](../prd/research-r1-prd.md) | [技术合同](../specs/research-r1-technical-spec.md) | [ADR-0008](../adr/0008-r1-same-model-actions.md) |
| R2 | [PRD](../prd/research-r2-prd.md) | [技术合同](../specs/research-r2-technical-spec.md) | [ADR-0009](../adr/0009-r2-observable-plan-interventions.md) |
| R3 | [PRD](../prd/research-r3-prd.md) | [技术合同](../specs/research-r3-technical-spec.md) | [ADR-0010](../adr/0010-r3-typed-verification-unknown.md) |
| R4 | [PRD](../prd/research-r4-prd.md) | [技术合同](../specs/research-r4-technical-spec.md) | [ADR-0011](../adr/0011-r4-scoped-evidence-identity.md) |
| R5 | [PRD](../prd/research-r5-prd.md) | [技术合同](../specs/research-r5-technical-spec.md) | [ADR-0012](../adr/0012-r5-final-artifact-risk-target.md) |

共同决策为 [ADR-0007](../adr/0007-experiment-boundary-and-budget.md)。新增算法前先完成对应公共切片与风险验证；文档默认 proposed，接受状态依据实际评审记录更新。
