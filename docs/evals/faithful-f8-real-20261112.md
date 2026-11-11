# F8 真实题集执行记录

日期：2026-11-12；状态：in_progress。接续 [真实合同v1](../engineering/faithful-f8-real-protocol-20261111.md)、[v1.2格式恢复](../engineering/faithful-f8-real-recovery-20261112.md)及[新源码接续v1.3](../engineering/faithful-f8-real-source-continuation-20261112.md)，执行入口为#157。官方重评分unavailable，真人L3 not_run，usage缺失observe_only。

## R19源码门禁

非法Meta已完成决定未退出阶段导致18次无进展Meta派发；原B/AIMEI5失败保留，修复提交`d3ccd9f`。门禁及文档冻结源码`543177955392beb514bae2c26bf1c26b49986d9f`，两轴审查均解除。

命令：`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-f8-r19-20261112-01`。门禁6/6通过，1683.094秒；1916项、0 failure/error、42 skip，source_changed=false；发布27、前端52单测/类型/构建通过，audit 0。42 skip的ID与原因同上一F8/F6/F7链，均不计通过；`artifacts/faithful-f8-real-20261111/source-gate-skip-comparison.json`逐项留证。旧Lean timeout、SQLite锁及late-usage间歇根因未确认，本次成功不宣称修复。

## 首次结果与接续

98槽总登记、70个A/B/C/D/G必需主槽、14个E原题目标域不支持及条件F不变。题集/独立参考事前封存；不是独立留出题集。所有已派发槽保留首次结果，不删除、插补或重派。精确有理数9题与证明5题分栏；正式28槽辅助审查尚未执行。

实际固定Lean专项2/2为受控目标L2，不是原题通过；两Job真实并行开发探测仅确认观测容量2，不保证SLA，不替代D自然题并发。原G/AIMEI1正确且实际注入1条，不能推断记忆收益。

| 批次 | 首次主槽数 | 处置与来源 |
| --- | --- | --- |
| execution/d/continuation/recovery/verdict | 7 | 原v1/v1.1/v1.2，1完成正确、6失败/取消；R19旧产品失败保留 |
| source-execution-01 | 4 | 3个已知模型失败，B/I10 progress_action_blocked触发glue分类缺口 |
| progress-execution-01 | 3 | C/G I10 schema失败；A/I15本地unsupported not_executed回执分类缺口 |
| precheck-execution-01 | 2 | B/I15已知失败；C/I15两次planner YIELD达既有上限 |
| checkpoint-execution-01 | 2 | G/I15复用原C同源码session；A/HMMT1 polynomial schema拒绝投影需精确分类 |
| schema-execution-01 | 1 | B/HMMT1本地事件身份冲突，F8-R20产品缺陷，停止新派发 |

glue分类补充均用原封存Job红绿及拒绝反例、两轴审查，保留原失败；不改产品、prompt或预算，不把未执行/拒绝回执计工具通过。manifest父链及各result/job hash逐项核对。各批具体manifest/hash、归因与审查见ignored `artifacts/faithful-f8-real-20261111/`及#157评论。旧工程试点98 not_run不改写。

## R20修复与第二次源码冻结条件

Run `run_ea0fab0d6197be919b4b5d12ea7764f5`共11HTTP全部已知完成，产品在Verifier计算续审→claim目标修复→重复计算请求时，两个不同call_id的预留事件共用compute-1后缀，出现SolverEventConflictError。单进程精确复现证据为`artifacts/faithful-f8-r20-fix-20261112/red-exact.json/log`；不归为数学失败。最小修复只给续审预留事件附确定性call身份摘要，不改请求、调用身份、预算、工具去重或恢复授权。单项绿与42项计算/反例聚焦回归通过、0 skip，fast及Ruff通过；源码门禁待运行。

新源码接续沿用v1.3要求：旧19首次槽全部保留，只接续51未派发主槽；另封manifest并绑定新源码及其唯一成功门禁，原绝对deadline不延长。按源码分层，跨版本not_comparable；不能把本轮修复后结果作为旧失败的替代。新glue审查、门禁、51槽首次终态、适用F、28槽辅助审查及最终包仍未完成；本记录不构成#157关闭依据。
