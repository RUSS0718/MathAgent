# #96 流式用量问题：非流式主路径验收记录

日期：2026-10-27（Asia/Shanghai）。本轮目标调整为先让简单题和多步题都能走完适用的 Showcase 流程，为后续实验建立可复现工程基线。数学正确率不是本轮门槛；不发真实 provider 请求、不提高预算、不关闭整题审查、不修改官方入口。Issue #96 保持开放，流式只作可选入口。

#97 是独立的非流式验收，不以前述旧 E1/E2 通过为前置；原 E1/E2 结果保持不变。#95 仍正式受 #96 阻塞，付费执行暂停。

## 已确认边界

Issue 记录了两次真实流式运行：四次 HTTP 请求都正常结束，但没有 provider usage，保留的预留阻断了整题审查。现有证据不能证明流式接口不可用，也不能证明添加某个请求字段就能取得完整用量。Chat Completions、Messages 与当前流式适配器的真实 provider 兼容仍未通过本轮验证，因此它不作为本轮端到端门槛。

当前默认 `InternModelAdapter` 使用非流式 `chat_response`。客户端在解析 completion 结构前保留响应 usage；缺失字段继续为 unknown 并保留相应用量预留。超时后完整迟到响应结算到原 attempt；公开 attempt 投影也随原 attempt 更新。流式 `InternStreamAdapter` 仍是显式选择的可选实现，本轮不宣称其 provider 兼容或完整计量已验收。

## 本轮验收范围

- 简单题通过 Reference 快通道，完成最终生成、整题审查与最终文本绑定。
- 多步题通过 Reference 非快通道，覆盖计划、步骤处理、隔离工具回执、最终生成、整题审查与文本绑定。
- 故障恢复复用同一 Job、原预算 deadline 和已提交工具回执，不重复执行已完成工具。
- 重规划分支继续到完整最终审查，并核验 Report / Evidence 与最终交付使用相同绑定。
- provider usage 存在、响应结构畸形、超时后迟到成功和 usage 缺失分别验证；缺失 usage 不得结算为零。

这些均为离线脚本化 provider 或 loopback 证据，只证明在受控输入下工程流程可达，不证明真实 Intern provider readiness、难题数学正确率或普遍完成率。

## 验收结果

以下结果来自本轮当前工作树；固定本地隔离镜像由 `MATHAGENT_TEST_PYTHON_IMAGE` 指定。全仓及发布门禁均执行了完整测试套件，跳过项不会计为通过。

| 检查 | 命令 / 测试 | 结果 |
| --- | --- | --- |
| 非流式 usage、迟到结算与保留预留 | `tests.test_llm_late_settlement`、`tests.test_run_budget`、`tests.test_request_transport_late_callback` | **通过**，29 项通过 |
| 简单题与 Reference 工具流程 | `StarFullModeTest.test_reference_easy_problem_completes_fastpath_review_and_binding`、`test_reference_runs_same_public_job_with_real_tool_and_whole_review` | **通过**，2 项通过；使用固定本地隔离镜像 |
| 多步重规划闭环与审查绑定 | `StarReplanDecisionTest.test_reference_preset_rulings_cover_all_three_branches` | **通过**，三分支子场景完成且 Reference 成功分支绑定为 `same_artifact` |
| 完整 Reference 进程恢复 | `RobustRecoveryTest.test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding` | **通过**，同一 Job 恢复并完成最终审查及绑定 |
| 可选流式传输与断流账本回归 | `tests.test_star_product_streaming_recovery`、`tests.test_star_transport_policy`、`tests.test_request_transport_late_callback` | **通过**，35 项通过；仅脚本/loopback，不构成 provider 兼容验收 |
| Ruff 与差异空白检查 | 本轮涉及的 Python 文件；`git diff --check` | **通过** |
| 全仓离线合同 | `uv run --offline --frozen python -B scripts/check.py --offline` | **通过**，757 项测试通过；六个旁路故障注入探针和两个入口 `--help` 检查通过 |
| Showcase 发布门禁 | `uv run --offline --frozen python -B scripts/check_showcase_release.py` | **通过**，完整测试套件、发布证据合同、官方 baseline 哈希、导入边界及脱敏 replay 检查通过 |
| 源码差异与官方 baseline | `git diff --check`、定向 Ruff、发布检查及最终人工 diff review | **通过**；未改官方入口、`implementations/`、`BASELINE.json` 或发布边界文件 |

## Issue 状态

#96 保持开放。本轮已在 Issue 留言说明非流式端到端流程是当前工程基础、流式保持可选、本地修复尚未合并，以及离线证据不代表 provider-live 兼容或数学正确率。没有新增付费重试，没有修改原 RB08 E1/E2 结果。旧 E1/E2 readiness 提案中的阶段门不适用于独立 #97 验收；若另行启动旧提案所述 live readiness，仍须单独注册并复核依赖。

## 后续严格 Reference 门禁

先将 `MATHAGENT_TEST_PYTHON_IMAGE` 设为已验证的本地隔离镜像 ID，再运行 `uv run --offline --frozen python -B scripts/check_showcase_release.py --require-reference`。该选项要求简单题、Reference 多步工具和同 Job 恢复三项用例均通过；缺失、跳过或预期失败会使门禁失败。普通发布门禁也会打印每项 skip 原因。此严格门禁只覆盖这三项用例，不代表通过全组件矩阵；本轮历史发布门禁记录仍是未带 `--require-reference` 的结果。

## 后续恢复修复与严格门禁

2026-10-27，针对研究完成后进程退出的公共 Job 恢复用例，修复了替代计划版本再次递增和研究结果未传递的问题。恢复后的 Planner 沿用归档后的计划版本，并接收持久化研究结果、禁止方向和合法救援成果；已完成研究不重复派发。研究结果仍标记为 `unverified_exploration`。这一用例使用脚本化 provider，不证明真实模型会自然触发研究。

修复后的未提交工作树以固定本地镜像运行 `uv run --offline --frozen --no-sync python -B scripts/check_showcase_release.py --require-reference`，765 项测试通过，未显示跳过，结果为 `showcase_release=PASS`。本记录不改变上方历史门禁结果，也不代表完整组件矩阵或真实 provider 验收已通过。
