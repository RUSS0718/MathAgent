# Solver Harness v1.1 实现规格

**状态：** accepted for `showcase-solver-harness-v1`

**日期：** 2026-10-22

**基线：** `develop@700f42317df35aab6ae3f7bcda5193a4c88e17d0`

**上游合同：** [STAR Core Agent 实施规格](../prd/STAR_CORE/STAR_Core_v1_2/STAR_CORE_SPEC_AGENT_v1_2.md)

**决策：** [ADR-0013](../adr/0013-solver-harness-boundary-and-shared-transaction.md)

## Problem Statement

`showcase` 已有稳定的产品 Run、Job、SSE、预算与 Evidence 合同，但 STAR Core 要求的新求解控制面还没有实现。当前 v1.1 文档只定义了范围和验收，没有可运行的 `SolverHarness`；此前把延期任务写成两张汇总表，无法逐项领取，且 v1.2 的若干任务跨度过大。

用户面对的具体问题是：无法在 Showcase 内启动一条可恢复、可审查的求解路径，也无法清楚区分 v1.1 的离线能力、v1.2 的目标能力和尚未验证的 live 数学能力。

## Solution

在现有 `showcase` 产品面内增加显式启用的 Solver Harness，不与官方 `user_agent.py` 路径合并。

v1.1 交付 S1 + S2：可恢复状态、revision 事务、Explore 两条可观察分支、最小整题审查、Plan 交接和预算耗尽时的合法结果。v1.2 在同一控制面上补齐 STAR Core 剩余机制与可关闭的 Best-Effort Finalization。

验收接缝统一为 `SolverHarness.solve()` 的公开结果与 `SolverHarness.get_run()` 的持久状态，测试使用临时 SQLite 和离线脚本端口。存储类、图节点和私有实现不作为验收接缝。

## User Stories

1. 作为产品使用者，我希望通过显式入口启动一次 Solver Run，以便与官方评测路径隔离。
2. 作为产品使用者，我希望得到可 JSON 序列化的结果，以便界面和实验工具消费。
3. 作为评审者，我希望结果明确区分 LLM 审查通过、未验证、预算耗尽和运行时失败，以免把部分结果当成完整证明。
4. 作为开发者，我希望 Explore 输出有四种稳定评估，以便预测下一阶段。
5. 作为开发者，我希望 `SOLVED` 必须先经过整题审查，以便不会由模型自报成功直接结束。
6. 作为开发者，我希望整题审查拒绝后保留探索发现并进入 Plan，以便不丢失已有工作。
7. 作为开发者，我希望 `NEED_PLAN` 和 `UNKNOWN` 确定性进入 Plan，以便路由可测试。
8. 作为开发者，我希望 `PARTIALLY_SOLVED` 最多再探索一轮后进入 Plan，以便循环有上限。
9. 作为开发者，我希望 v1.1 使用纯 Python 执行 S1、S2 使用 LangGraph 条件边，以便先固定业务状态再接图调度。
10. 作为开发者，我希望同一 Run 的快照与事件在进程重建后一致，以便可恢复。
11. 作为开发者，我希望基于过期 `state_revision` 的写入被拒绝，以便避免并发覆盖。
12. 作为开发者，我希望同一事件 ID 幂等提交，以便重启不重复接受步骤。
13. 作为开发者，我希望预算在模型和工具调用前检查，以便硬预算不会被越过。
14. 作为开发者，我希望预算耗尽时不新增调用，并返回合法、不编造的结果。
15. 作为开发者，我希望 `candidate_registry`、`best_effort_decision`、`finalization_reason` 始终存在且默认 `None`，以便 v1.2 可扩展而不改旧状态。
16. 作为开发者，我希望 Solver 状态与产品 Run 共用 SQLite 文件和事务边界，但使用独立表，以便不污染旧快照。
17. 作为开发者，我希望现有三个 Run 持久化、Run 快照和预算回归文件保持原样通过。
18. 作为开发者，我希望模型访问经过 `ModelPort`，以便测试不依赖网络。
19. 作为开发者，我希望 v1.2 再适配真实 Intern 模型，以便 v1.1 的验收不依赖凭证。
20. 作为开发者，我希望逐步 Reasoner 产出带验证标签的报告，以便验证器知道该计算还是证明。
21. 作为审查者，我希望 Verifier 同时检查 Goal Gate 和 Logic Gate，以便拒绝形式合格但目标错误的答案。
22. 作为审查者，我希望非法或不一致的 Verifier 裁决不被当作 `ACCEPT`。
23. 作为审查者，我希望 Challenge 在同一辩论会话中连续进行且有轮数上限。
24. 作为审查者，我希望达到 Challenge 上限时升级 Meta 而不是无限循环。
25. 作为开发者，我希望 Trace-Back 能归档步骤、失效下游结果并保留可救援结果。
26. 作为开发者，我希望非法 Trace-Back 目标被拒绝而不是猜测。
27. 作为开发者，我希望 Re-plan 保留旧计划、失败原因、禁止方向和可复用结果。
28. 作为开发者，我希望同一题的 Meta 历史跨计划保留，不同题严格隔离。
29. 作为开发者，我希望会话身份包含 Run、角色、计划尝试和步骤范围，以便恢复正确的历史。
30. 作为开发者，我希望四层记忆分别维护，以便 Reasoner、Verifier、Meta 和权威账本不互相污染。
31. 作为开发者，我希望每个角色调用前注入最新状态投影，以便恢复后不读旧结论。
32. 作为开发者，我希望 Meta 能把 timeout、code_issue 和 stuck 转成结构化行动。
33. 作为开发者，我希望纯推理模式真正移除代码工具权限，而不只是修改提示词。
34. 作为开发者，我希望重新规划后可执行受预算限制的非代码再探索。
35. 作为开发者，我希望 `easy-verify` 在送审前有真实执行证据，否则不得升级成 `verified`。
36. 作为开发者，我希望七个数学 Skill 只在触发时加载，并且能够观测加载结果。
37. 作为开发者，我希望最终生成使用新的整题 Verifier 会话，以便不依赖步骤审查的默认真理。
38. 作为开发者，我希望流式中断后保留部分输出但不把它当成完成。
39. 作为开发者，我希望候选从 Explore、Step 和 Finalize 持续登记且不可覆盖。
40. 作为开发者，我希望已推翻、已失效或依赖失效步骤的候选不能再被选择。
41. 作为开发者，我希望硬预算为零时 Best-Effort 选择不产生任何模型、工具或 Verifier 调用。
42. 作为开发者，我希望同等级候选冲突使用公开、确定性的平局规则。
43. 作为开发者，我希望没有合格候选时返回明确的未解决说明，而不是编造数值。
44. 作为开发者，我希望证据等级只描述证据充分性，不冒充概率或形式化证明。
45. 作为实验人员，我希望内部结果保留 Best-Effort 审计信息，而正式输出只写允许字段。
46. 作为实验人员，我希望同一快照的 Best-Effort 重放选择结果一致且零新增调用。
47. 作为实验人员，我希望未知结果的模型请求保留 `unknown_outcome`，不被误记为免费或成功。
48. 作为实验人员，我希望真实 Intern、配对实验和发布门禁有独立任务，不阻塞离线 v1.1。
49. 作为维护者，我希望每个 ticket 都能独立领取、验证并声明依赖，以便按依赖前沿推进。
50. 作为维护者，我希望 SC-001..SC-043 和 STAR AC-01..AC-44 各自有唯一工单归属和明确验收。

## Implementation Decisions

- Solver Harness 位于现有 Showcase 产品面，不新建 `harness_lab/` 或第二套顶层实验包。
- 产品版本为 v1.1；包版本保持 `0.1.0`，前端保持 `0.2.0`，Profile 保持 `showcase_mvp`。
- v1.1 范围是 S1 + S2；v1.2 完成 STAR 剩余合同和 Best-Effort 扩展。
- S1 使用纯 Python；S2 使用 LangGraph 条件边。LangGraph checkpoint 不是业务状态权威。
- Solver Run 与产品 Run 共用一个 SQLite 文件、连接和事务边界；状态与事件使用独立表。
- 新表在现有存储初始化时创建；Solver 专用读写和 revision 比较交换在 Solver Harness 子包内。
- 公开入口为 `SolverHarness.solve(problem, metadata)`；公开恢复读取为 `SolverHarness.get_run(run_id)`。
- 提交状态使用 `expected_revision` 比较交换；同一 Run 的 `event_id` 唯一；恢复校验题目与配置 hash。
- `ProblemState` 从第一版保留三个 Best-Effort 字段，默认 `None`。
- v1.1 模型只通过 `ScriptedModelPort` 使用；真实 `InternModelPort` 是 v1.2 独立切片，复用现有 Intern 适配器的传输、重试和用量语义。
- `ToolPolicy` 默认拒绝所有工具；v1.1 不执行生成代码。
- 预算至少覆盖模型调用、工具调用和总运行时，所有检查发生在派发前。
- v1.1 的 Plan 只证明交接与状态版本字段，不证明完整计划修复或逐步执行。
- v1.2 的逐步验证、Challenge、Trace-Back、Meta、Re-plan、Skills、工具、会话、流式恢复和 Best-Effort 分别按可观察行为拆分。
- STAR 编号统一写为 `STAR AC-xx`；`v0.2 AC-06` 单独保留，避免同名混淆。
- v1.1 继承 `engineering-preview`，不宣称真实 Intern 工具闭环、完整 STAR 或数学正确率提升。
- 验收只检查公开行为，不锁定私有类层级、SQL 细节、节点名称或内部调用顺序。

## Testing Decisions

好测试的标准是：从公共入口发起完整行为，断言可观察结果与持久状态；不直接调用私有 helper，不依赖网络、真实凭证、真实时钟或固定机器路径。

- 主接缝是 `SolverHarness.solve()` 与 `SolverHarness.get_run()`。产品 Run 回归继续通过 `RunService` 的现有接缝。
- v1.1 使用临时 SQLite、`ScriptedModelPort`、`ScriptedVerifierPort` 和可控预算；每次用新 Harness 实例模拟进程重建。
- AC-SH-01..08 分别覆盖 Explore 审查接受、拒绝进 Plan、确定性 Plan 路由、部分解决上限、恢复、revision 冲突、预算耗尽和扩展字段默认值。
- revision 冲突通过两个读取同一快照的调用方竞争提交来验证；只断言后写者被拒绝且先写者状态未丢。
- 预算耗尽通过调用计数断言“零新增调用”，并断言返回结果仍可 JSON 序列化。
- v1.1 额外运行三个既有回归文件、仓库离线检查和 baseline hash 检查；这三份文件不改。
- v1.2 每一项 STAR AC 具体落在一个 ticket；跨 ticket 的 AC 只在唯一主 ticket 声明关闭，其他 ticket 只引用。
- 逐步验证使用声明式脚本回复覆盖 Goal/Logic 不一致、解析失败和边界 M。
- Challenge 测试同一辩论内的上下文连续性、轮数上限和升级行为。
- Trace-Back 和 Re-plan 使用跨步骤、跨计划的脚本状态断言归档、失效和救援。
- Best-Effort 使用固定候选快照验证零调用、确定性排序、冲突、无候选和证据等级；重放两次结果必须一致。
- 真实 Intern 与 live 证据只由显式 live ticket 执行，CI 继续默认离线。
- 现有可参考先例包括 `tests/test_showcase_run.py`、`tests/test_run_persistence.py`、`tests/test_run_budget.py`、Workspace Job 合同测试和 campaign 报告测试。

## Out of Scope

- 修改 `user_agent.py`、`implementations/`、`BASELINE.json`、官方默认预算或官方输出合同。
- 在 v1.1 交付完整 Meta、逐步双 Gate、Challenge、Trace-Back、Re-plan、四层记忆、代码沙箱、七类 Skill 或 Best-Effort 候选选择。
- 将 v1.1 的 fake/replay 结果表述为真实 Intern 能力或数学正确率提升。
- 让 Solver 状态写入 `runs.snapshot_json` 或改变现有 Profile 字符串。
- 以 Lean、定理证明器或完整解集证明作为 LLM 审查的替代。
- 在 v1.1 引入真实网络、真实时钟依赖或跨题共享的知识库。
- 提前创建空的七个 Skill 文件或为未实现能力伪造调用记录。

## Further Notes

- 权威需求仍是 STAR Core 三份文档；本 spec 负责 Showcase 内的范围和验收归属，不重写上游数学协议。
- 实施顺序应以无阻塞 ticket 的前沿推进；v1.1 收口后才进入 v1.2。
- GitHub 是已配置 tracker，标签使用 `enhancement` 与 `ready-for-agent`；依赖写在每个 ticket 的 `Blocked by`，除非平台原生依赖可用。
- v1.1/v1.2 的一票一文件合同位于 `docs/tickets/showcase-solver-harness-v1/`；`.scratch/showcase-solver-harness-v1/issues/` 是本地工作副本。GitHub 发布状态仍为未发布。

## 验收与需求归属

### v1.1 验收

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| AC-SH-01 | Explore SOLVED，整题审查 ACCEPT | 不进入 Plan；`status=completed_llm_reviewed`；`final_response` 非空 |
| AC-SH-02 | Explore SOLVED，整题审查 REJECT | 进入 Plan；保留 Explore findings；不得标为通过 |
| AC-SH-03 | Explore NEED_PLAN / UNKNOWN | 确定性进入 Plan，且不调用 Meta |
| AC-SH-04 | Explore PARTIALLY_SOLVED | 再探索或进入 Plan；总探索轮数不超过 2 |
| AC-SH-05 | 进程重建 | 同一 `run_id` 的状态、事件和 revision 一致 |
| AC-SH-06 | 过期 revision | 拒绝写入且不覆盖更新状态；相同 `event_id` 幂等 |
| AC-SH-07 | 预算耗尽 | 零新增模型/工具/Verifier 调用；返回可 JSON 序列化状态 |
| AC-SH-08 | 扩展未启用 | 三个扩展字段均为 `None`，且无额外调用 |

v1.1 的出口要求：AC-SH-01..08 有实际测试结果；三个既有回归文件未修改且通过；SC-001..SC-043 均有唯一归属；验收记录明确 `engineering-preview`。v1.1 不宣称完整 STAR、真实 Intern 工具闭环或数学正确率提升。

### STAR AC 主归属

| STAR AC | 主 ticket | 说明 |
| --- | --- | --- |
| STAR AC-01 | SH-05 | Explore SOLVED 后整题接受 |
| STAR AC-02 | SH-05 | Explore SOLVED 被拒后交接 Plan |
| STAR AC-03 | SH-04、SH-05 | 四种 Explore 路由；不调用 Meta |
| STAR AC-04 | SH-07 | 计划结构与非法计划边界 |
| STAR AC-05 | SH-07 | 双 Gate 与非法裁决 |
| STAR AC-06 | SH-06 | 标签级证据边界；执行证据在 SH-14 |
| STAR AC-07 | SH-08 | Challenge 连续会话 |
| STAR AC-08 | SH-08 | Challenge 上限与升级 |
| STAR AC-09 | SH-09 | Trace-Back 归档与救援 |
| STAR AC-10 | SH-09 | 非法 Trace-Back 目标 |
| STAR AC-11 | SH-11 | Re-plan 版本与禁止方向 |
| STAR AC-12 | SH-10、SH-11 | Meta 跨计划持久化；不同题隔离 |
| STAR AC-13 | SH-15 | 最终审查拒绝与有界重试 |
| STAR AC-14 | SH-14 | 超时、网络和受限重试分类 |
| STAR AC-15 | SH-02、SH-03 | 重启恢复与幂等提交 |
| STAR AC-16 | SH-04 | 预算耗尽后零新增调用 |
| STAR AC-17 | SH-05 | 扩展关闭时无额外调用或字段值 |
| STAR AC-18 | SH-23 | 官方冻结文件与默认预算回归 |
| STAR AC-19 | SH-13 | 权限隔离与脱敏拒绝审计 |
| STAR AC-20 | SH-22 | 配对实验与版本/用量来源 |
| STAR AC-21 | SH-12 | 四层记忆边界 |
| STAR AC-22 | SH-12 | 新建/恢复会话的最新状态注入 |
| STAR AC-23 | SH-12 | 会话注册与跨进程隔离 |
| STAR AC-24 | SH-10 | Meta 诊断与结构化行动 |
| STAR AC-25 | SH-10 | 纯推理时真实移除工具权限 |
| STAR AC-26 | SH-11 | 后重规划受限再探索 |
| STAR AC-27 | SH-14 | `easy-verify` 预检回执 |
| STAR AC-28 | SH-09 | 正负账本与失效联动 |
| STAR AC-29 | SH-09 | 猜测与失效结论不得作为事实 |
| STAR AC-30 | SH-15 | Verifier 与 Meta 意见来源分离 |
| STAR AC-31 | SH-13 | 三层 Prompt 与可观察 Skill |
| STAR AC-32 | SH-16 | 流式中断与不重复提交 |
| STAR AC-33 | SH-22 | 受限 Profile 与跳过原因 |
| STAR AC-34 | SH-17 | 候选持续登记 |
| STAR AC-35 | SH-17 | 已推翻候选不可选 |
| STAR AC-36 | SH-17 | Trace-Back 失效传播 |
| STAR AC-37 | SH-18 | 硬预算零调用兜底 |
| STAR AC-38 | SH-18 | 无合格候选的未解决说明 |
| STAR AC-39 | SH-18 | 同级冲突与确定性平局 |
| STAR AC-40 | SH-19 | 不输出未校准数值置信度 |
| STAR AC-41 | SH-20 | 正式输出与内部证据隔离 |
| STAR AC-42 | SH-20 | 完全重放零调用 |
| STAR AC-43 | SH-16 | 在途请求 `unknown_outcome` |
| STAR AC-44 | SH-19 | 证据等级守恒 |

### SC 主归属

| SC | 主 ticket | 说明 |
| --- | --- | --- |
| SC-001 | SH-01、SH-23 | 实验入口隔离与发布边界 |
| SC-002 | SH-04、SH-07 | 确定性 Explore/Plan 与步骤路由 |
| SC-003 | SH-04、SH-05 | Explore 四类评估与提前成功 |
| SC-004 | SH-11 | 预计划 Meta 与用户 Hint |
| SC-005 | SH-07 | 计划结构与版本边界 |
| SC-006 | SH-06 | 逐步 Reasoner |
| SC-007 | SH-06、SH-14 | 三类标签与执行证据 |
| SC-008 | SH-07 | 双 Gate 与四类裁决 |
| SC-009 | SH-08 | 有界连续 Challenge |
| SC-010 | SH-09 | Trace-Back 与救援 |
| SC-011 | SH-10 | Meta 持久裁决 |
| SC-012 | SH-11 | Re-plan 与禁止方向 |
| SC-013 | SH-15 | 最终生成与整题审查 |
| SC-014 | SH-13 | 七类按需 Skill |
| SC-015 | SH-12 | 角色会话与状态视图 |
| SC-016 | SH-02、SH-03 | 状态、事件与恢复 |
| SC-017 | SH-13、SH-14 | 工具权限与受控执行 |
| SC-018 | SH-04 | 预算、循环和超时门禁 |
| SC-019 | SH-21 | 模型适配与真实用量 |
| SC-020 | SH-07、SH-14 | 错误分类与有界恢复 |
| SC-021 | SH-15、SH-20 | 内部结果与正式输出 |
| SC-022 | SH-05、SH-22 | Feature Flags 与 Profile |
| SC-023 | SH-16、SH-22 | 脱敏 Trace 与审计 |
| SC-024 | SH-23 | 全部验收用例 |
| SC-025 | SH-01、SH-23 | 分阶段提交与发布边界 |
| SC-026 | SH-22 | 配对实验与成本统计 |
| SC-027 | SH-06、SH-19 | 审查不等于形式化证明 |
| SC-028 | SH-12 | 四层记忆与正负账本 |
| SC-029 | SH-12 | 会话启动/恢复注入 |
| SC-030 | SH-12 | Session 注册与隔离 |
| SC-031 | SH-10 | Meta 诊断与行动 |
| SC-032 | SH-10 | 纯推理权限 |
| SC-033 | SH-11 | 后重规划再探索 |
| SC-034 | SH-14 | `easy-verify` 预检 |
| SC-035 | SH-09 | 救援与禁止路线同步 |
| SC-036 | SH-15 | 整题审查角色差异 |
| SC-037 | SH-13 | 三层 Prompt、Skill 与权限 |
| SC-038 | SH-16 | 流式部分输出与幂等恢复 |
| SC-039 | SH-17 | 候选登记与失效 |
| SC-040 | SH-18 | 预算门控与兜底选择 |
| SC-041 | SH-19 | 证据等级与理由 |
| SC-042 | SH-20 | 正式输出与内部元数据隔离 |
| SC-043 | SH-20、SH-16 | 重放、计费与在途审计 |

多 ticket 条目表示一个合同被拆成不可跳级的前后切片；关闭声明只在最后一个依赖完成的 ticket 中生效。

## Ticket 索引

| Ticket | 交付结果 | Blocked by | 主验收 |
| --- | --- | --- | --- |
| SH-01 / #01 | 冻结基线并建立文档入口 | — | AC-18 前置 |
| SH-02 / #02 | Solver 状态、事件和跨实例恢复 | #01 | AC-15 |
| SH-03 / #03 | revision 冲突与幂等提交 | #02 | AC-15 |
| SH-04 / #04 | Explore 路由与预算门禁 | #03 | AC-03、AC-16 |
| SH-05 / #05 | 整题审查与 v1.1 收口 | #03、#04 | AC-01、AC-02、AC-17 |

一票一文件位于 `docs/tickets/showcase-solver-harness-v1/`，编号 01..05 对应本表；`.scratch` 目录是本地工作副本。
