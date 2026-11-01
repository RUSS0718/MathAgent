# CP-05 检查点公共 Job 验收与 #112 交接

**状态：** 受控 loopback / fault-injection 验收完成；provider-live 与数学能力结论仍为 `unknown`。

**日期：** 2026-11-01（Asia/Shanghai）

**范围：** Issue #120 / CP-05，源码冻结提交 `8e2246660e3cda867cb4fe0fa28a77eae390a60f`，源码树 `b36754128efbea1f32866fa7106d850a13bdf696`（分支 `fix/showcase-review-fixes`，基于集成 HEAD `047e8cd6522ab1a00dc49e2934ee73c8f36733a8`）。文档提交不作为源码冻结依据。只接入 Showcase 的显式 STAR 配置；官方 `user_agent.ReasoningAgent`、`implementations/`、默认预算和 baseline 没有改动。

## 验收合同

控制版与候选版使用同一个受控公共 Job、同一个单步 toy task 和同一组脚本化回复。控制版配置为 `final_generation=true`、`final_solution_review=true`，两个 checkpoint 和 `meta_guidance` 均关闭；候选版在此基础上显式打开 `planner_checkpoints=true`、`reasoner_checkpoints=true`、`meta_guidance=true`。流式配置不由 adapter 是否具有 `stream_complete` 推断，只有 `stream_activity=true` 时才选择流式调用和活动投影。

两套配置的规范化 JSON 指纹（UTF-8、键排序、紧凑分隔符后 SHA-256）为：控制版 `ab8942a128c8ccc5fc39e91e14b53c3ddc5777b8947d450d1b59ca83cac93527`，候选版 `19cffe90fe245695acc92779ca61289136a0b690a98e95c90a90b4ef42151256`。两次运行均为本地脚本 loopback，`thinking_mode` 为 `None`，不向 provider 请求发送 thinking 开关；transport 为受控 HTTP loopback/脚本响应，禁止真实 provider 请求。

运行时指纹与请求数据绑定：`prompt_fingerprint` 是最终传给 `InternModelPort` adapter 的完整 `messages` 的规范化 JSON SHA-256；`input_fingerprint` 是构造这些 messages 时实际采用的题目（包含 `original_problem` fallback）的规范化 JSON SHA-256；`schema_fingerprint` 是本次 request 的实际 `response_schema` 的规范化 JSON SHA-256；既有 `prompt_layers_fingerprint` 仍表示旧 prompt layer 投影。新增三类审计值只写入 invocation / Evidence，不进入默认 provider context；关闭 checkpoint 协议时，旧 `prompt_fingerprint` context 字段和原 messages 保持不变。CP-05 公共回归按每个 outbound role 重算 messages、input、schema，并覆盖 `final_generator` 的真实角色事件。

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
| CP-03：Planner 检查点 | `tests/test_solver_harness_planner_checkpoint.py`、`tests/test_cp05_public_job.py` 与 `tests/test_star_product_recovery.py::StarRecoveryTest.test_public_planner_checkpoint_process_recovery_and_duplicate_resume` | 覆盖 `YIELD → feedback → FINAL`、新调用身份、版本/空缺口/无进展/预算拒绝、进程退出、完成检查点复用和重复 resume 去重 |
| CP-04：Reasoner 检查点与 Meta | `tests/test_cp04_public_faults.py::CP04PublicFaultTest` 的六个公共 Job 用例：`test_yield_verifier_objection_reaches_next_reasoner_before_final_review`、`test_cancel_during_reasoner_checkpoint_does_not_reach_verifier`、`test_resume_rejects_old_revision_after_reasoner_checkpoint_unknown`、`test_traceback_with_reasoner_checkpoints_excludes_invalidated_results`、`test_approved_replan_decision_dispatches_new_plan_with_reasoner_checkpoints`、`test_process_reopen_reuses_reasoner_checkpoint_and_tool_receipt_once`；辅助机制证据见 `tests/test_solver_harness_reasoner_checkpoint.py`、`tests/test_star_product_traceback.py`、`tests/test_star_product_replan_decision.py`、`tests/test_star_product_recovery.py` | 六例直接通过公共 Job 验证局部 `YIELD → Verifier` 异议 → 下一 Reasoner、checkpoint 阶段取消、旧 revision 拒绝、合法 traceback 后排除失效成果、批准 replan 后真实新 Plan/Reasoner，以及进程重开后的完成 checkpoint 与真实 tool receipt 复用；恢复例同时核对原 deadline、累计 logical/HTTP/token 账、旧 call identity 和重复 resume。旧 harness/helper 测试只作补充，不能替代这六例；最终结果仍需 whole review 接受 |
| CP-05：集成与交接 | 本记录及 `tests/test_cp05_public_job.py` | 证明受控 loopback 工程闭环，不升级 provider-live 或能力结论 |

流式边界沿用已有公共 Job 证据：正常活动、调用完成、静默、无正文、缺 usage、断流、取消和迟到结果分别保持完成、空正文失败、usage 未知、unknown、canceled 或忽略迟到响应的原合同；断流和进程退出保留 unknown 与预留，不自动重发。活动投影保留固定字段集合；未观测的时间点、计数、usage 状态和终态统一公开为 `unavailable`，不把缺失观测误报为成功。恢复测试还核对已完成检查点、已接受成果和工具回执复用，不重复模型或工具调用，累计 logical / HTTP / tool / token 计数与原 deadline 不被重置。

## #112 实验交接

本交接保留 #112 的原批次身份、原始 `5/15` 标识、10 项 `not_run` 项、Planner `unknown` 身份、`deadline=unknown` 的原登记和预算预留。旧 raw、state、ledger 不改写；#112 仍按原登记保持 `unknown/not_run`，CP-05 的 loopback 结果不能替代或覆盖它。

交接只增加本 CP-05 的可复核脱敏记录：

- 控制版：checkpoint 开关关闭，旧公共合同和调用计数作为基线。
- 候选版：Planner / Reasoner checkpoint、Meta 指导和最终审查显式开启。
- 输入、角色、schema 版本和配置使用规范化摘要或指纹定位；公共文件不保存原题、完整 prompt 或敏感正文。
- 预算、checkpoint 轮数和停批规则沿用既有 Run 账本；`unknown`、`not_run`、迟到和取消分别保留原身份。
- 评分只记录工程可达性、事件/状态合同、恢复不重复和脱敏边界；不把 Demo 可运行、结构测试通过或 replay 一致误报为数学能力提升。

## loopback、replay 与 provider-live 边界

本次 CP-05 只使用本地脚本响应和故障注入，没有真实模型请求、没有新增付费探测。loopback 证据证明状态机、公共 Job、事件投影和预算/恢复合同可复核；replay 只重放已持久化状态与事件，不调用模型、Verifier 或工具，也不增加数学证据。

provider-live 仍是独立门槛：需要单独授权、独立批次身份、固定输入与 prompt/schema 指纹、真实 usage/finish reason、原 deadline、成本和失败处置记录。当前没有 provider-live 结果，不能据此关闭 #112、宣称能力提升或推断数学正确率。

## 本次修复验证边界

本修复 worker 未启动全量测试；父线程保存的历史全量结果为 `1030 tests, errors=1, skipped=42`，唯一错误是 deadline 竞态用例的分类不稳定，单独诊断和重跑均通过，不能写成全量通过。新增 CP04 公共验收单独运行命令 `uv run python -m unittest tests.test_cp04_public_faults`，结果为 `6 tests, 0 errors, 0 skipped`。与既有 Reasoner/traceback/replan/recovery 聚焦模块联合运行结果为 `53 tests, 0 errors, skipped=1`；唯一 skip 是未设置已验证 Docker reference image 的参考预置测试。其余 CP-05、共享事务与非阻塞 settlement、deadline、流式矩阵、实际指纹、关闭协议和 Reference loader 检查属于父线程既有聚焦证据；本记录不把跳过视为通过。Docker 参考验收仍由最终门禁按 `MATHAGENT_TEST_PYTHON_IMAGE` 和 `--require-reference` 单独执行。
