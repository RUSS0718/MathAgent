# CP-05 检查点公共 Job 验收与 #112 交接

**状态：** 受控 loopback / fault-injection 验收完成；provider-live 与数学能力结论仍为 `unknown`。

**日期：** 2026-11-01（Asia/Shanghai）

**范围：** Issue #120 / CP-05，最终冻结提交 `e0e67e4`（分支 `fix/showcase-cp05-implement-spec-closeout`，基于集成 HEAD `6972aaf`），只接入 Showcase 的显式 STAR 配置。官方 `user_agent.ReasoningAgent`、`implementations/`、默认预算和 baseline 没有改动。

## 验收合同

控制版与候选版使用同一个受控公共 Job、同一个单步 toy task 和同一组脚本化回复。控制版配置为 `final_generation=true`、`final_solution_review=true`，两个 checkpoint 和 `meta_guidance` 均关闭；候选版在此基础上显式打开 `planner_checkpoints=true`、`reasoner_checkpoints=true`、`meta_guidance=true`。流式配置不由 adapter 是否具有 `stream_complete` 推断，只有 `stream_activity=true` 时才选择流式调用和活动投影。

两套配置的规范化 JSON 指纹（UTF-8、键排序、紧凑分隔符后 SHA-256）为：控制版 `ab8942a128c8ccc5fc39e91e14b53c3ddc5777b8947d450d1b59ca83cac93527`，候选版 `19cffe90fe245695acc92779ca61289136a0b690a98e95c90a90b4ef42151256`。两次运行均为本地脚本 loopback，`thinking_mode` 为 `None`，不向 provider 请求发送 thinking 开关；transport 为受控 HTTP loopback/脚本响应，禁止真实 provider 请求。

协议与 Schema 指纹同样使用规范化 JSON SHA-256：`explore=89fbfab654098a2025a0b69375f8dc8a7d8000391507639243712ca85a3a1473`，`planner=47d696ba141a0df8916096620b35e322e402c59c41a80fca7b268a4c2ee2efee`，`reasoner=8836d710fac9532e05ef506e19a3da7fee87bb4a96b588396dd9842e83d986ef`，`step_verifier=f45df661a9c9ae45dee4ed363ed244c934a60b951d5cd4eeb2464b3fd2606eb7`，`final_generator=54ac692b082da9544bf9ee6ebc6c71cbf38396b8863aeb2e9d932de7f2cb6c10`，`whole_solution_verifier=edaea8b9ad088955e19001ef3b3bc6479028b604003ddf6dee7feeef56507aec8`；checkpoint protocol version 均为 `1`，Planner checkpoint Schema 指纹为 `ced41a67af4e3621e00be7239ed4ae73e1427def5d225c77669201ee3766d377`，Reasoner checkpoint Schema 指纹为 `8170e8838f48e6f5ddc5d00cbe6e2aa0f3297a90d3bf713579916aed85348f77`。

CP-05 的公共 Job 入口是 `POST /api/agent/jobs`，观察面是 Job、事件 SSE、报告和 Evidence。任务粒度为每次运行一个公开 toy task、一个 Plan、一个 step；控制版角色调用序列为 `explore → planner → reasoner → step_verifier → final_generator → whole_solution_verifier`，共 6 个 logical/HTTP 调用；候选版为 `explore → planner → planner → reasoner → meta → reasoner → step_verifier → final_generator → whole_solution_verifier`，共 9 个 logical/HTTP 调用。两版均为 0 个工具调用，测试预算上限为 12 个 logical/HTTP 调用，token 与运行时上限仍由既有 `RunBudgetLimits` 计算。角色、轮次、状态和脱敏后的摘要可复核，原题、完整 prompt、隐藏答案、Meta 任务正文、完整 checkpoint ID 和个人信息不进入公共证据。

候选版最多执行 2 个 Planner checkpoint round、2 个 Reasoner checkpoint round 和 1 次 Meta guidance；本次脚本路径实际使用 Planner `YIELD → FINAL`、Reasoner `YIELD → FINAL` 和 1 次 `retry_different_method`。控制版不创建 checkpoint。停批规则是：Job 到达 `succeeded`、`failed` 或 `canceled` 即停止；断流、未完成流、进程退出和未知远端结果进入 `needs_review`，不自动重发；取消或 deadline 后的迟到结果只允许按原 attempt 结算已知 usage，不得推进数学状态；预算、原 deadline 或协议硬失败均结束当前 Run，不换题、不扩预算。

独立评分只对可复核工程合同计分，不对数学答案或 provider-live 效果计分：角色序列和轮次 25%，logical/HTTP/tool/token 预算与原 deadline 20%，Job/Report/Evidence 最终字段一致性 25%，流式六类故障矩阵 20%，恢复不重复与脱敏边界 10%。每项以公共断言的 pass/fail 记录；任一硬预算、取消、deadline、unknown 或协议合同被错误改写，该项为 fail。控制版作为同题基线，候选版只报告合同差异和新增调用成本，不将差异解释为能力提升。

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
