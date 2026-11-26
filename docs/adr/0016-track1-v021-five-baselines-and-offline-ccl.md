# 0016. Track 1 v0.2.1 五基线矩阵与离线 CCL 归因边界

- **Status**: accepted

## Context

经 2025–2026 最近邻文献核验（`RSE`, `StepCo`, `Tether`, `Thinking Before Thinking`）及实验仓 10 题效用探针，如果在线继续运行双臂 Counterfactual Control 回放，会引入约 2 倍的测试时算力损耗；同时原有 4 条基线缺少与 `RSE` 同验证器的平面经验筛选基线及无打捞换路对照，无法精确解耦“依赖撤回 + 选择性打捞”的净收益。

## Decision

1. **取消推理期在线双臂 CCL**：测试时仅在线运行单臂 `{Continue, Pruned-Repair, Salvage-Switch}`，由 L1（有界 Python 断言）与 L2（隔离 Critic）混合核查门控结果；同 Checkpoint 双臂对照保留在实验仓作为论文 Analysis/Ablation 章节的离线受控归因实验。
2. **统一 5 条件对比矩阵（`CONDITIONS`）**：`track1_cli` 统一支持 `B1`（Critic 排序采样）、`B2`（StepCo 风格首错前前缀截取重推）、`B3`（`RSE + Same Verifier` 平面引理与负面教训筛选）、`B4`（`Switch without Salvage` 无打捞纯换路）与 `RiCL_v0.2`，五者共享相同的单 Run 预算账本与 L1/L2 核查器。

## Consequences

- 消除了在线推理约 50% 的对照臂浪费，使全成本 `Accuracy vs. Total Tokens` 曲线可直接正面对比 `RSE + Same Verifier` 与 `Switch without Salvage`。
- `B2`/`B3`/`B4` 的行为边界由离线单元测试固定守护；后续若扩展 L1 符号模板（Track 2），仍无需改动单题控制接口。
