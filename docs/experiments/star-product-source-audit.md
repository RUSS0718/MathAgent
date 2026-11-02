# SP-01 固定来源与产品验收映射

状态：首次审计完成；产品集成待实现，不能据此关闭 SP-AC-22。日期：2026-10-23。

本表的 SC/AC 编号来自本项目 STAR Core 合同，**不是原论文自带编号**。原论文和源码用于独立核对机制；本地测试仅为历史工程证据，不能反向定义上游。

## 固定输入

- 论文：[arXiv:2605.19338v1](https://arxiv.org/html/2605.19338v1)，§3、附录 A/B/C/D。
- 上游：[Julius-Woo/STAR-PolyaMath 固定 commit](https://github.com/Julius-Woo/STAR-PolyaMath/tree/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d)，SHA `5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d`。本地 clone 的 HEAD 已核对，原始 clone 仅存 ignored artifacts。
- 本地实现基点：`606d874fcee11bc161d68aa001cd706de63afbe2`；集成分支 `showcase-star-product`。之前的独立 Solver 工程证据见 [v1.2 发布记录](../evals/showcase-solver-v1.2-release.md)。
- 产品合同：[spec #56](https://github.com/RUSS0718/MathAgent/issues/56)；状态权威：[ADR-0014](../adr/0014-star-product-state-and-recovery.md)。
- 全表状态 `H`：有本地 Harness/基础设施线索，但尚未从同一公共 Job 验收完整 STAR；`X`：项目新增合同。两者都不是产品通过。未来责任为唯一最终 ticket，SP-13 另做独立上游复核。

## 逐项 SC 来源与责任

公共接缝统一为 `POST /api/agent/jobs` → Job/Run/SSE/report/Evidence；不得以直接 Harness 调用代替。文件列是基点的实际文件，不是假定未来文件存在。

| SC | 合同行为 | 论文定位 | 固定上游路径 | 实际本地路径 | AC | 最终责任 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SC-001 | 隔离实验入口和官方合同 | B.1 | `src/runner.py` | `showcase/flask_app.py` | AC-18 | SP-13 #69 | H |
| SC-002 | 确定性状态机 | 3.1, B.1 | `src/orchestrator_mixins/orchestrator_solve.py` | `showcase/solver_harness/controller.py` | AC-04, AC-08 | SP-04 #60 | H |
| SC-003 | Exploration 与提前成功路径 | 3.2 | `src/orchestrator_mixins/orchestrator_exploration.py` | `showcase/solver_harness/star_routing.py` | AC-01..03 | SP-04 #60 | H |
| SC-004 | 可选预计划 Meta 与用户 Hint | 3.3 | `src/orchestrator_mixins/orchestrator_planning.py` | `showcase/solver_harness/star_routing.py` | AC-03, AC-20 | SP-04 #60 | H |
| SC-005 | 计划生成、结构验证、版本化 | 3.3 | `src/orchestrator_mixins/orchestrator_planning.py` | `showcase/solver_harness/planning.py` | AC-04, AC-11 | SP-04 #60 | H |
| SC-006 | 逐步 Reasoner | 3.4 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/step.py` | AC-05, AC-07 | SP-04 #60 | H |
| SC-007 | 三类验证标签和证据 | 3.4 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/verification.py` | AC-06 | SP-04 #60 | H |
| SC-008 | 两 Gate 与四类 Verifier 裁决 | 3.4 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/verification.py` | AC-05, AC-10 | SP-04 #60 | H |
| SC-009 | 有界且连续的 Challenge | 3.4 | `src/orchestrator_mixins/orchestrator_challenge.py` | `showcase/solver_harness/challenge.py` | AC-07..08 | SP-05 #61 | H |
| SC-010 | Trace-Back、归档、救援结论 | 3.4, B.5 | `src/state.py` | `showcase/solver_harness/traceback.py` | AC-09..10 | SP-06 #62 | H |
| SC-011 | 持久化 Meta 裁决 | 3.4 | `src/orchestrator_mixins/orchestrator_failure.py` | `showcase/solver_harness/meta.py` | AC-11..12 | SP-06 #62 | H |
| SC-012 | Re-plan 与 forbidden directions | 3.4, B.5 | `src/state.py` | `showcase/solver_harness/replan.py` | AC-11..12 | SP-06 #62 | H |
| SC-013 | 最终生成及整题审查 | 3.5 | `src/orchestrator_mixins/orchestrator_solve.py` | `showcase/solver_harness/finalize.py` | AC-01, AC-13 | SP-10 #66 | H |
| SC-014 | 七种按需 Skill | B.2 | `.github/skills/` | `showcase/solver_harness/skills.py` | AC-05, AC-19 | SP-07 #63 | H |
| SC-015 | 角色会话和状态视图 | 3.1, B.3 | `src/agent_runner.py` | `showcase/solver_harness/sessions.py` | AC-07, AC-12 | SP-07 #63 | H |
| SC-016 | 快照、事件与可靠恢复 | B.5 | `src/state.py` | `showcase/solver_harness/storage.py` | AC-09, AC-15 | SP-08 #64 | H |
| SC-017 | 本地工具及权限 | B.4 | `src/agent_runner.py` | `showcase/solver_harness/tool_ports.py` | AC-06, AC-19 | SP-09 #65 | H |
| SC-018 | 预算、循环与超时 | A | `src/config.py` | `showcase/run_budget.py` | AC-08, AC-16 | SP-03 #59 | H |
| SC-019 | 模型适配与真实用量 | 3.1, A | `src/agent_runner.py` | `showcase/solver_harness/intern_port.py` | AC-16, AC-20 | SP-03 #59 | H |
| SC-020 | 错误分类与有界恢复 | 3.4, B.1 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/calls.py` | AC-10, AC-14 | SP-07 #63 | H |
| SC-021 | 输出 JSON 合同 | 3.5; 项目输出适配 | `src/orchestrator_mixins/orchestrator_solve.py` | `showcase/solver_harness/result.py` | AC-13, AC-16 | SP-10 #66 | H |
| SC-022 | Feature Flags 和 Profile | A; 项目模式合同 | `src/config.py` | `showcase/solver_harness/harness_config.py` | AC-17 | SP-02 #58 | H |
| SC-023 | 脱敏 Trace 与事件审计 | B.5; 项目脱敏适配 | `src/state.py` | `showcase/workspace.py` | AC-15, AC-20 | SP-12 #68 | H |
| SC-024 | 33 个端到端验收用例 | 项目验收，不是上游编号 | `无上游 SC/AC 编号` | `tests/test_solver_release.py` | AC-01..33 | SP-13 #69 | X |
| SC-025 | 分阶段提交及发布边界 | 项目发布边界 | `无官方比赛入口合同` | `BASELINE.json` | AC-18 | SP-13 #69 | X |
| SC-026 | 配对实验与成本统计 | 4.3, D | `src/agent_runner.py` | `showcase/solver_harness/paired.py` | AC-20 | SP-13 #69 | H |
| SC-027 | 接受结论不等于形式化定理 | 3.4; 项目证据加强 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/verification.py` | AC-06, AC-13 | SP-10 #66 | H |
| SC-028 | 四层记忆与正负账本契约 | B.3, B.5 | `src/state.py` | `showcase/solver_harness/sessions.py` | AC-21, AC-28, AC-29 | SP-07 #63 | H |
| SC-029 | sessionStart/resume 状态注入与视图新鲜度 | B.3 | `src/hooks/inject_problem_context.py` | `showcase/solver_harness/context_injection.py` | AC-22, AC-28 | SP-07 #63 | H |
| SC-030 | Session ID 注册/隔离与跨进程重建 | B.3 | `src/agent_runner.py` | `showcase/solver_harness/sessions.py` | AC-23 | SP-07 #63 | H |
| SC-031 | Meta 诊断与行动指令协议 | 3.4, C.3 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/meta.py` | AC-24 | SP-07 #63 | H |
| SC-032 | Meta 强制纯推理和运行时工具禁用 | 3.4, C.3 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/tool_policy.py` | AC-25 | SP-07 #63 | H |
| SC-033 | 后重规划的 Meta 协调再探索/子任务 | B.4 | `src/orchestrator_mixins/orchestrator_exploration.py` | `showcase/solver_harness/research.py` | AC-26, AC-33 | SP-07 #63 | H |
| SC-034 | `easy-verify` 自动预检和证据回执 | 3.4 | `src/orchestrator_mixins/orchestrator_execution.py` | `showcase/solver_harness/tool_precheck.py` | AC-27 | SP-09 #65 | H |
| SC-035 | 正负账本同步及可救援证据与猜想隔离 | B.5 | `src/state.py` | `showcase/solver_harness/traceback.py` | AC-28, AC-29 | SP-06 #62 | H |
| SC-036 | 整题审核角色差异的显式合同 | 3.5, C.2 | `src/orchestrator_mixins/orchestrator_solve.py` | `showcase/solver_harness/finalize.py` | AC-30 | SP-10 #66 | H |
| SC-037 | 三层 Prompt/Skill/状态组合和权限 | B.2, B.3, C | `src/hooks/inject_problem_context.py` | `showcase/solver_harness/prompts.py` | AC-31 | SP-07 #63 | H |
| SC-038 | 流式部分输出、Meta 恢复和幂等记账 | B.1; 项目原子恢复加强 | `src/agent_runner.py` | `showcase/solver_harness/calls.py` | AC-32, AC-33 | SP-08 #64 | H |
| SC-039 | 候选登记、溯源与依赖失效 | 项目 Best-Effort 扩展 | `无原生候选登记合同` | `showcase/solver_harness/candidates.py` | AC-34..36 | SP-11 #67 | X |
| SC-040 | 预算耗尽时无模型调用的最佳候选选择 | 项目 Best-Effort 扩展 | `无零调用选择合同` | `showcase/solver_harness/best_effort.py` | AC-37..39 | SP-11 #67 | X |
| SC-041 | 定性证据等级与可追溯理由 | 项目 Best-Effort 扩展 | `无本项目定性等级合同` | `showcase/solver_harness/confidence.py` | AC-39..40, AC-44 | SP-11 #67 | X |
| SC-042 | 比赛输出隔离和内部结构化结果 | 项目 Best-Effort 扩展 | `无本项目官方隔离合同` | `showcase/solver_harness/result.py` | AC-38, AC-41 | SP-11 #67 | X |
| SC-043 | 候选回放、计费与在途请求审计 | 项目 Best-Effort 扩展 | `无零调用回放合同` | `showcase/solver_harness/replay.py` | AC-42..43 | SP-11 #67 | X |

## 逐项 AC 到产品验收

场景及预期由 STAR Core 合同逐行保留；源机制回指上表 SC。每项基点状态均为待公共产品验收，不沿用旧矩阵的 covered 作为产品通过。

| AC | 触发场景 | 需观察的用户结果 | 来源 SC | 实际本地路径 | 最终责任 |
| --- | --- | --- | --- | --- | --- |
| AC-01 | Explore=SOLVED，整题 Accept | 同一 Explore 会话中润色；完成；Planner 调用数为 0 | SC-003 | `showcase/solver_harness/star_routing.py` | SP-04 #60 |
| AC-02 | Explore=SOLVED，整题 Reject | 进入 Plan；保留发现；不得标通过 | SC-003 | `showcase/solver_harness/star_routing.py` | SP-04 #60 |
| AC-03 | Explore=PARTIALLY_SOLVED | Meta 决定重试或规划；轮数不超上限 | SC-003 | `showcase/solver_harness/star_routing.py` | SP-04 #60 |
| AC-04 | Plan 非法编号或循环 | 修复有界；无效计划不执行 | SC-005 | `showcase/solver_harness/planning.py` | SP-04 #60 |
| AC-05 | Goal=NO, Logic=PASS, verdict=ACCEPT | 判为无效裁决，禁止推进 | SC-008 | `showcase/solver_harness/verification.py` | SP-04 #60 |
| AC-06 | easy-verify 无执行证据 | 不写成 verified 或 formally_proved | SC-007 | `showcase/solver_harness/verification.py` | SP-04 #60 |
| AC-07 | 第三轮 Challenge 接受 | 双方保留三轮辩论；仅接受一次 | SC-009 | `showcase/solver_harness/challenge.py` | SP-05 #61 |
| AC-08 | 达到最大 Challenge 次数 | 升级 Meta；无死循环 | SC-009 | `showcase/solver_harness/challenge.py` | SP-05 #61 |
| AC-09 | 第 N 步 Traceback 至 M | 归档 M..N、下游成果失效、保留可救援成果 | SC-010 | `showcase/solver_harness/traceback.py` | SP-06 #62 |
| AC-10 | TRACE_BACK 缺失/越界 M | 禁止猜测；有记录的升级或终止 | SC-010 | `showcase/solver_harness/traceback.py` | SP-06 #62 |
| AC-11 | APPROVE_REPLAN | 老版本留档；新版本生成；禁止方向带入 | SC-012 | `showcase/solver_harness/replan.py` | SP-06 #62 |
| AC-12 | 同题多 Plan 与不同题 | 同题 Meta 历史延续；不同题会话隔离 | SC-015 | `showcase/solver_harness/sessions.py` | SP-07 #63 |
| AC-13 | 整题校验不通过 | 有界重试；最终状态不伪称 verified | SC-013 | `showcase/solver_harness/finalize.py` | SP-10 #66 |
| AC-14 | 模型/工具超时、网络异常 | 正确分类；部分结果保存；重试受限 | SC-020 | `showcase/solver_harness/calls.py` | SP-07 #63 |
| AC-15 | 在归档与快照间强制中断 | 恢复不重复接受、不丢归档、不重复记账 | SC-016 | `showcase/solver_harness/storage.py` | SP-08 #64 |
| AC-16 | 预算不足 | 不再派发；结果 JSON 合法；标明预算终止 | SC-018 | `showcase/run_budget.py` | SP-03 #59 |
| AC-17 | 所有功能关闭 | 无额外工具与模型调用；单次路径可测试 | SC-022 | `showcase/solver_harness/harness_config.py` | SP-02 #58 |
| AC-18 | 比赛默认入口回归 | 文件与调用合同保持；`final_response` 非空且 JSON 可序列化 | SC-001 | `showcase/flask_app.py` | SP-13 #69 |
| AC-19 | Meta 请求直接执行代码或跨题读取 | 访问被拒；审计保留脱敏拒绝事件 | SC-017 | `showcase/solver_harness/tool_ports.py` | SP-09 #65 |
| AC-20 | 相同配置的配对运行 | 可导出模型/题目/版本/预算/用量来源与失败分类 | SC-026 | `showcase/solver_harness/paired.py` | SP-13 #69 |
| AC-21 | 跨计划四层记忆的独立性 | Meta 历史与账本持续；Reasoner/Verifier 只在规定会话窗口保存 | SC-028 | `showcase/solver_harness/sessions.py` | SP-07 #63 |
| AC-22 | 会话新建和 resume 后状态变更 | 最新角色投影被注入且不跨题；旧状态不会覆盖最新 | SC-029 | `showcase/solver_harness/context_injection.py` | SP-07 #63 |
| AC-23 | 同名题不同 run 与进程重启 | 不会复用错误 session；真实 resume 或本地重构可验证 | SC-030 | `showcase/solver_harness/sessions.py` | SP-07 #63 |
| AC-24 | timeout/code_issue/stuck 三种诊断 | 结构化输出具体动作与任务；动作经控制器核验 | SC-031 | `showcase/solver_harness/meta.py` | SP-07 #63 |
| AC-25 | Meta 下达纯推理指令后模型想执行 Python | 工具被运行时白名单拒绝；模式改变留痕 | SC-032 | `showcase/solver_harness/tool_policy.py` | SP-07 #63 |
| AC-26 | Replan 后探索含多个研究子任务 | 研究委派与汇总进入新计划；所有子任务计费、非代码 | SC-033 | `showcase/solver_harness/research.py` | SP-07 #63 |
| AC-27 | easy-verify 存在 Python 代码片段 | 有真实沙箱回执后再送审；异常无法冒充 verified | SC-034 | `showcase/solver_harness/tool_precheck.py` | SP-09 #65 |
| AC-28 | Replan 同时产生禁用路线和救援结论 | 新会话均可见且旧记录未丢；原错结论不可用 | SC-035 | `showcase/solver_harness/traceback.py` | SP-06 #62 |
| AC-29 | Conjecture/失效结论出现于账本 | 不提升到已证事实，不能当作活动引理 | SC-035 | `showcase/solver_harness/traceback.py` | SP-06 #62 |
| AC-30 | Verifier/Meta 整题意见矛盾或调用失败 | 来源分别标识；未获 Verifier 审查不得标整题验证通过 | SC-036 | `showcase/solver_harness/finalize.py` | SP-10 #66 |
| AC-31 | 三层 Prompt 的触发和工具权限 | 记录激活 Skill；注入视图版本；禁止越权工具 | SC-037 | `showcase/solver_harness/prompts.py` | SP-07 #63 |
| AC-32 | 流式半途超时与重启 | 片段持久化但不解析为终态；调用不重复提交 | SC-038 | `showcase/solver_harness/calls.py` | SP-08 #64 |
| AC-33 | 关闭扩展或比赛预算中断 | 未授权子任务/预检不启动；输出准确 Profile 与跳过原因 | SC-033 | `showcase/solver_harness/research.py` | SP-07 #63 |
| AC-34 | Explore、Step、Final 三阶段提交完整候选 | 候选版本完整、来源可追溯 | SC-039 | `showcase/solver_harness/candidates.py` | SP-11 #67 |
| AC-35 | 最新候选被确证错误 | 不进入可选集合 | SC-039 | `showcase/solver_harness/candidates.py` | SP-11 #67 |
| AC-36 | 回退时撤销依赖的步骤 | 所有受影响候选失效 | SC-039 | `showcase/solver_harness/candidates.py` | SP-11 #67 |
| AC-37 | 模型调用额度为零，账本已有合格答案 | 不发模型或工具请求，仍能交付候选 | SC-040 | `showcase/solver_harness/best_effort.py` | SP-11 #67 |
| AC-38 | 模型额度为零，账本无合格答案 | 明确未完成，非空但不编造数学答案 | SC-040 | `showcase/solver_harness/best_effort.py` | SP-11 #67 |
| AC-39 | 两个同等级候选互相矛盾 | 记录冲突，稳定平局处理，证据等级不高估 | SC-040 | `showcase/solver_harness/best_effort.py` | SP-11 #67 |
| AC-40 | 尝试返回未经校准的数字 0.95 | 合同拒绝或剥离数字，只保留可追溯定性证据 | SC-041 | `showcase/solver_harness/confidence.py` | SP-11 #67 |
| AC-41 | 运行官方入口的回归 | `user_agent.py` 及默认模型调用和输出结构不变 | SC-042 | `showcase/solver_harness/result.py` | SP-11 #67 |
| AC-42 | 对同一完成的 Snapshot 执行两次重放 | 选择一致；额外模型和工具调用数为 0 | SC-043 | `showcase/solver_harness/replay.py` | SP-11 #67 |
| AC-43 | 预算到期时模型调用仍未返回 | 记录 `unknown_outcome`；不可假设未扣费，不重复提交结果 | SC-043 | `showcase/solver_harness/replay.py` | SP-11 #67 |
| AC-44 | 工具完成一个局部算术检查 | 不得宣称整题已形式化证明 | SC-041 | `showcase/solver_harness/confidence.py` | SP-11 #67 |

## 已确认差异与约束

| 分类 | 原来源观察 | 本项目合同与处理 |
| --- | --- | --- |
| 一致的核心设计 | 论文 §3 与源码 solve/exploration/execution/challenge/failure 有探索、双 Gate、质询、回退、重规划 | 保留机制，不以旧 helper 测试代替产品路径证据 |
| 有意平台适配 | 原 `agent_runner.py` 调 Copilot CLI，使用可恢复会话及工作目录文件 | Intern S2/API、共享 SQLite、LangGraph、Workbench；由 SP-02/03/07/08 验收真实动作和身份 |
| 有意加强 | 上游代码执行经过 CLI/工作目录及 URL deny；不是本项目要求的 Docker OS 限制 | SP-09 使用经验证的隔离环境、硬输出上限、内容可核验产物；不可用则拒绝完整模式 |
| 论文/源码与严格验收冲突 | `orchestrator_solve.py:481–487` 在整题 Verifier 调用失败时仍接受 solution；§3.5 要求最终审核 | 不复制失效开放行为。SP-10 必须在失败/拒绝时标明未审查或未通过，不标 verified |
| 原标签与证据范围差异 | 论文 §3.4 将执行 Python 结果视为 grounded；上游 easy-verify 以代码回执支持审查 | 仅支持实际检查的 claim/scope；不能升级整题形式化证明（SC-027/AC-44） |
| 恢复要求加强 | 上游 state.json 与 PROBLEM_STATE.md 是分开写入的文件；文件存在不能证明原子接受/记账 | ADR-0014 跨状态提交合同由 SP-08 验证；当前公共 Job 尚无 STAR 接受步骤，风险门槛 blocked |
| 项目新增 | SC-039..043、AC-34..44 是 Best-Effort 项目扩展 | 单独模式、零调用终止选择、候选不可变历史；不得归功于原 STAR |
| 当前缺口 | 公共 worker 仍调用旧 `live_graph.py` planner→solver→verifier→synthesizer | SP-02..12 实际接入；只有全部产品验收及 SP-13 独立复核后才能声明完整 |

## 默认配置核对

固定上游 `src/config.py` 的三个角色均为 `gpt-5.5` / `xhigh`，而本项目固定 Intern S2；不能使用本项目模型结果声称复现论文成绩。上游读取时的 README 未列不同的默认模型。

| 上游字段/默认值 | 基点实际本地执行路径 | 产品处理/责任 |
| --- | --- | --- |
| REASONER_TIMEOUT=1800 / VERIFIER_TIMEOUT=1200 / META_STRATEGIST_TIMEOUT=600 | `showcase/adapters.py`、`showcase/server.py` provider timeout；Harness 不持有共享 deadline 权威 | 显式受限预算，S3 deadline 拥有总时限，SP-03 |
| CODE_EXECUTION_TIMEOUT=600 / SESSION_RESUME_TIMEOUT=600 | `showcase/solver_harness/tool_ports.py`、`calls.py` | Docker 硬超时/新请求身份，SP-08/09 |
| MAX_CHALLENGE_ROUNDS=5 / MIN_CHALLENGE_ROUNDS=1 | `challenge.py`，max_challenge_rounds 默认5 | 产品配置必须传到实际调度；SP-05 |
| MAX_CONSECUTIVE_TIMEOUTS=3 / MAX_CODE_RETRIES=3 / MAX_TIMEOUT_RETRIES=8 / AGENT_MAX_RETRIES=5 | `llm_client.py` 的 HTTP retry 与 Harness `calls.py` 是不同层 | 映射每层 attempt，均过同一 S3，不复制重试倍增；SP-03/07 |
| MAX_SOLUTION_RETRIES=2 | `finalize.py` 的 max_final_solution_retries | 有界新审核；SP-10 |
| MAX_STEP1_FAILURES=3 / MAX_REPLANS=3 | `meta.py`、`replan.py` | 显式配置并从 Job 验收次数；SP-06 |
| ENABLE_EXPLORATION=True / MAX_EXPLORATION_ROUNDS=2 / EXPLORATION_BUDGET_MIN=15（soft） | `star_routing.py` | 参考模式强制核心；soft 提示不能冒充硬时限；SP-02/04 |
| MAX_STEPS=20 / MAX_TRACE_BACKS=5 / MAX_TOTAL_DURATION=3600 | `plan.py`、`traceback.py`、`budget.py`；Harness 默认 model_calls=2，duration=3600，tool_calls=8 | 旧受限配置不是完整参考；与 S3 单一账本对齐；SP-02/03/06 |
| EXCLUDED_TOOLS=(web_search,web_fetch) / DENIED_URLS=(*) | `tool_policy.py` / Registry | 非代码研究委派与 Docker network=none 均须硬约束；SP-07/09 |

基点的 `showcase/solver_harness/intern_evidence.py:CONFIG` 仅开启 stream_recovery、persistent_sessions、local_code_tool、final_generation、final_solution_review，工具限 polynomial_check，模型6次/工具2次/180秒；这是受限历史 probe，不是 star_reference。`harness_config._normalize_config` 仅 JSON 标准化，没有全核心依赖校验。默认功能关闭不新增官方调用。

## 退出与证据追踪

执行报告和风险退出条件见 [SP-01 风险报告](star-product-risk-sp01.md)。逐项最终状态仍由责任 ticket 的公共验收写回，不能把本表路径定位或历史测试映射计作产品完成。SP-13 应重新读固定论文和 commit，并核对新增动作证据，而不是只检查这些表格行存在。
