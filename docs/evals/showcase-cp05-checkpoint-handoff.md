# CP-05 检查点公共 Job 验收与 #112 交接

**状态：** 受控 loopback / fault-injection 验收完成；provider-live 与数学能力结论仍为 `unknown`。

**日期：** 2026-11-01（Asia/Shanghai）

**范围：** Issue #120 / CP-05，基于集成 HEAD `a0541c9`，只接入 Showcase 的显式 STAR 配置。官方 `user_agent.ReasoningAgent`、`implementations/`、默认预算和 baseline 没有改动。

## 验收合同

候选配置同时显式打开 `planner_checkpoints`、`reasoner_checkpoints`、`meta_guidance`、`final_generation` 和 `final_solution_review`；控制配置关闭两个 checkpoint 开关。控制配置继续使用旧的 Explore → Plan → Reasoner → Verifier → Final 路径，关闭开关时不增加模型调用。

CP-05 的公共 Job 入口是 `POST /api/agent/jobs`，观察面是 Job、事件 SSE、报告和 Evidence。测试使用脚本化 loopback 响应，预算为 12 个逻辑模型调用、12 个 HTTP attempt、0 个工具调用；默认运行时与 token 上限仍由既有 `RunBudgetLimits` 计算。角色、轮次、状态和脱敏后的摘要可复核，原题、完整 prompt、隐藏答案、Meta 任务正文、完整 checkpoint ID 和个人信息不进入公共证据。

候选的非流式纵切顺序为：Explore 返回 `NEED_PLAN`；Planner 先交 `YIELD` 草案，再按反馈交合法 `FINAL` Plan；Reasoner 交局部成果；Verifier 审查并要求 Meta 的 `retry_different_method`；Reasoner 继续下一轮；Step Verifier 接受；Final Generator 生成最终文本；Whole Solution Verifier 完成最终审查。只有最终审查接受后 Job 才是 `succeeded`，checkpoint 局部成果不会直接成为最终答案。

## CP-01..CP-04 与 CP-05 证据映射

| 能力 | 受控证据 | 结论边界 |
| --- | --- | --- |
| CP-01：公共 Job、状态投影、脱敏 | `tests/test_cp05_public_job.py::CP05PublicJobTest.test_non_stream_checkpoint_job_covers_handoff_meta_and_final_review` | 证明公共入口可达、角色顺序和最终审查绑定；不证明数学正确率 |
| CP-02：流式活动与交接 | `tests/test_solver_harness_streaming_activity.py`、`tests/test_star_product_streaming_recovery.py` | 覆盖活动指标、片段持久化、交接和公共字段脱敏；文本正文不进入活动事件 |
| CP-03：Planner 检查点 | `tests/test_solver_harness_planner_checkpoint.py` 与 CP-05 公共 Job 测试 | 覆盖 `YIELD → feedback → FINAL`、新调用身份、版本和无进展终止 |
| CP-04：Reasoner 检查点与 Meta | `tests/test_solver_harness_reasoner_checkpoint.py` 与 CP-05 公共 Job 测试 | 覆盖局部成果、Verifier 审查、Meta 指导、下一轮及最终审查 |
| CP-05：集成与交接 | 本记录及 `tests/test_cp05_public_job.py` | 证明受控 loopback 工程闭环，不升级 provider-live 或能力结论 |

流式边界沿用已有公共 Job 证据：正常活动、调用完成、静默、无正文、缺 usage、断流、取消和迟到结果分别保持完成、空正文失败、usage 未知、unknown、canceled 或忽略迟到响应的原合同；断流和进程退出保留 unknown 与预留，不自动重发。恢复测试还核对已完成检查点、已接受成果和工具回执复用，不重复模型或工具调用，累计 logical / HTTP / tool / token 计数与原 deadline 不被重置。

## #112 实验交接

本交接保留 #112 的原批次身份、原始 `5/15` 标识、10 项 `not_run` 项、Planner `unknown` 身份、原 deadline 和预算预留。旧 raw、state、ledger 不改写；#112 仍按原登记保持 `unknown/not_run`，CP-05 的 loopback 结果不能替代或覆盖它。

交接只增加本 CP-05 的可复核脱敏记录：

- 控制版：checkpoint 开关关闭，旧公共合同和调用计数作为基线。
- 候选版：Planner / Reasoner checkpoint、Meta 指导和最终审查显式开启。
- 输入、角色、schema 版本和配置使用规范化摘要或指纹定位；公共文件不保存原题、完整 prompt 或敏感正文。
- 预算、checkpoint 轮数和停批规则沿用既有 Run 账本；`unknown`、`not_run`、迟到和取消分别保留原身份。
- 评分只记录工程可达性、事件/状态合同、恢复不重复和脱敏边界；不把 Demo 可运行、结构测试通过或 replay 一致误报为数学能力提升。

## loopback、replay 与 provider-live 边界

本次 CP-05 只使用本地脚本响应和故障注入，没有真实模型请求、没有新增付费探测。loopback 证据证明状态机、公共 Job、事件投影和预算/恢复合同可复核；replay 只重放已持久化状态与事件，不调用模型、Verifier 或工具，也不增加数学证据。

provider-live 仍是独立门槛：需要单独授权、独立批次身份、固定输入与 prompt/schema 指纹、真实 usage/finish reason、原 deadline、成本和失败处置记录。当前没有 provider-live 结果，不能据此关闭 #112、宣称能力提升或推断数学正确率。
