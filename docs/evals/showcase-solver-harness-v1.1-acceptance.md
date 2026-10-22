# Solver Harness v1.1 验收记录

**状态：** planned

**计划日期：** 2026-10-22

**对应规格：** [GitHub Issue #32](https://github.com/RUSS0718/MathAgent/issues/32)

本文件在实现切片完成前只记录验收骨架。每完成一个 ticket，追加命令、环境、结果和失败项；不得用计划或结构测试冒充已通过结果。

## 出口条件

- AC-SH-01 至 AC-SH-08 全部有可复核测试结果；
- `tests/test_run_persistence.py`、`tests/test_showcase_run.py`、`tests/test_run_budget.py` 未修改且通过；
- 官方冻结文件 hash 与 `BASELINE.json` 一致；
- SC-001..SC-043 每项都有唯一归属；
- 已知限制与 `engineering-preview` 状态写明；
- 没有把 fake、replay 或结构测试写成 live 数学能力证据；
- `v0.2 AC-06` 继续标记为 `unavailable`，不在 v1.1 声称工具闭环完成。

## 记录格式

| 日期 | Ticket | 命令 | 结果 | 已知差异 |
| --- | --- | --- | --- | --- |
| — | — | — | 尚未执行 | v1.1 实现未开始 |
