# STAR 架构健壮性与组件作用实验方案

状态：历史提案，未采纳、未注册为新 live 执行合同。日期：2026-10-27。范围承接 #70、#80、#87、#95、#96；不改变官方入口、默认预算、已归档实验或任何 Issue 状态。本提案不授权付费 live 请求，不得使用或挪用 RB08 额度；付费执行仍暂停。本方案只用于 RB08 / STAR Showcase readiness，不构成 `research-program-plan.md` 的 B-ready、G2、G3 或 G4，也不为 R1–R5 提供确认性统计证据。

当前 #97 是独立的非流式验收，不以前述旧 E1/E2 通过为前置。以下 E1/E2 readiness 注册条件及阶段 B–D 均保留为未采纳的历史方案，不是当前验收目标或 live 执行指令；原 E1/E2 结果只读保留，不重算、不覆盖。#95 仍正式受 #96 阻塞。

## 目标与结论边界

本轮目标是验证当前架构能否按合同贯通，不设正确率提升目标、MDE 或相对 Legacy 的胜负门槛。数学正确性可记录为旁证，但不影响本轮架构闭环判定。本方案把组件合同、Reference 运行闭环和未来相对效果比较分开，不能用同一类测试互相代替：

1. **组件是否按合同工作？** 用离线公共 Job、故障注入和最小旁路探针验证路由、验证、工具、计量、恢复和最终交付约束。该层证明机制行为，不证明模型会自然触发机制，也不证明数学能力提升。
2. **Reference 能否跑通端到端架构闭环？** 用固定公共题、真实 Intern、认证 Job、S3/S4 和真实自然 trace 检查调用、阶段协作、计量、预算及证据一致性。该层验证运行可达性，不把一次内部 ACCEPT 当成数学正确证明。
3. **架构或某个可选组件是否提升数学正确率？** 这属于未来独立问题，需要单独设计配对对照、样本量和资源预算；当前 RB08 的 E1/E2 没有 Legacy 对照，本轮也不注册这类效果检验。

“健壮”在本计划中是可审计的行为：失败与未知状态不混淆；账本不把缺失用量记作零；不突破调用、工具、token、deadline 和恢复合同；错误答案、拒绝、未决和正确交付分别保留；Report、Evidence、Job 和最终文本来源一致。不能仅凭一次通过、测试总数或模型的 ACCEPT 推断系统普遍可靠。

总体鲁棒性不作统计估计。阶段 A 只按预注册矩阵报告已执行场景的通过率 `passed / registered_and_executed`、失败点和 `not_covered`；该比率只描述注册场景，不能外推为目标题总体、模型总体或系统总体的通过概率。

Provider 侧流式适配器是可选传输入口，不是架构、E1 或 E2 的必要条件；`stream_recovery` 指持久 Job / Run 的恢复合同，仍是 `star_reference` 的必需配置，不等于必须使用 SSE。Messages API 示例展示流式 `output_tokens`，未承诺 `input_tokens`，也未列 `thinking_mode` 参数。缺少 `input_tokens` 时输入预留继续保留，该运行可判计量不完整，不能以零用量、额外预算或取消整题审查补救。模型列表对 `intern-s2` 的思考默认值不能单独证明 Messages endpoint 的思考行为；在真实提供方按独立预注册核验前，流式不得作为思考兼容已通过或完整计量已通过的证据。

## 当前已知边界

- `docs/evals/star-rb08-release.md` 记录原 E1 执行 2/4 后停止、E2 为 0/6；真实流式请求正常结束但缺少用量，审查因预算预留未能派发。该批次及后续诊断复测都必须保持不可变，不能重命名为新实验或重算成通过。
- `showcase.star_experiment` 的当前注册合同固定 10 个 Run：E1 两题分别走非流式与流式，E2 三类公开题各重复两次；全轮硬上限为 96 logical calls、128 HTTP attempts、22 题目工具、524288 charged/reserved tokens、4800 秒。
- 完整 `star_reference` 需要 `CORE_FEATURES` 全部启用并通过隔离工具准入。关闭其核心项后，该运行不再是 Reference；不能把这种运行当作合法的 Reference 单组件消融。
- `showcase.solver_harness.PairedRunner` 当前只允许 `skills`、`reexplore_after_replan`、`candidate_registry`、`best_effort` 四个单因素配对项；现有 `Campaign` 也不覆盖 `legacy` 对完整 `star_reference` 的整体架构比较。两者都不能直接承担该整体对照。
- 因此，要让流式真正可选，必须使用**新版本注册合同**：旧失败批次与旧版本条件保持原样，并将 proposed 新条件、理由和哈希单独登记。未更新并验证 Runner 合同前，不得口头把旧四样本 E1 改读成非流式 E1。
- GitHub 工单依赖也是任何 `#95` live 注册的前置核验，不能由技术方案自动解除。截至 2026-10-27，只读核验显示 [#96](https://github.com/RUSS0718/MathAgent/issues/96) 仍为 Open，且是正式 blocking [#95](https://github.com/RUSS0718/MathAgent/issues/95)；#95 正文中的 `Blocked by #94` 已过期，因为 [#94](https://github.com/RUSS0718/MathAgent/issues/94) 于 2026-10-26 关闭。[#87](https://github.com/RUSS0718/MathAgent/issues/87) 仍 Open，8 个子 Issue 中 7 个完成，未完成的子票是 #95；[#80](https://github.com/RUSS0718/MathAgent/issues/80) 未被 #95/#96 直接阻塞，但 ALIGN-AC-18 的真实自然非快通道完整闭环仍未通过。独立 #97 非流式验收不解除 #95/#96 依赖；付费执行仍暂停。本提案本身不授权付费请求、远端写入或关闭 Issue。

计量、执行与任务结局必须分开编码：`transport_status=known|unknown`、`task_status=completed|rejected|incomplete|canceled`、`usage_status=complete|incomplete|unresolved`。只有完整终态响应但字段缺失时，传输仍可为 known、usage 为 incomplete；这既不是网络 unknown，也不等于数学错误。可能仍在途或断流未完成的响应记 transport unknown、usage unresolved；只有完整交付满足最终审查与文本绑定才记 task completed。

## 阶段 A：非流式主路径与端到端流程

本轮先用本机 loopback、脚本 provider 和隔离工具验收，不连接真实 provider。流式传输不是本轮 Reference readiness 的前置条件；持久 Job/Run 恢复合同仍需覆盖。验收矩阵至少包括：

- 简单题经过 Reference 快通道，完成最终生成、整题审查和 S4 同文本绑定。
- 多步题经过 Plan、Reasoner、步骤审查、隔离工具回执消费、最终生成、整题审查和 S4 绑定；另覆盖独立 ReplanDecision 分支。
- 在工具回执或模型调用后的进程退出点恢复同一 Job；不得重复执行已提交工具，且原 deadline、账本与最终来源绑定保持一致。
- 非流式完整响应的真实 usage 结算；畸形 completion 仍结算已收到的 usage；完整迟到响应回填同一 attempt 与公开账本投影。
- usage 缺失、部分响应或网络未知时保留相应用量预留、停止后续 dispatch，不得记为零消耗或自动重发未知请求。

每项只复用与当前源码身份匹配的测试；源码 SHA、dirty 状态、命令、实际退出码、skip 和测试 ID 均入记录。离线矩阵证明受控响应下的工程行为，不证明 provider live readiness、数学正确率或普遍完成率。以后若单独验收流式，再为 SSE 完整响应、末尾 usage、断流与迟到结算建独立矩阵，不阻塞本轮非流式闭环。

## 阶段 A：零付费组件合同与故障矩阵

每个机制至少有一项正向公共 Job、一个拒绝/故障反例，以及适用时一项恢复断言。用例须观察 Job、Run、S3、工具回执和 Evidence 的实际结果；测试 skip、xfail 或断言崩溃不算覆盖。阶段 A 的运行清单须逐条登记每个 SC/AC 对应的机制、配置项、正向场景、故障场景、不变量、证据和结论类型；未登记或已登记但未执行的 SC/AC 均记 `not_covered`，不得用同组或相邻用例补算。可复用现有用例及旁路探针，新增测试只补确实没有的接缝。

| 组件组 | 必测情形 | 主要证据 / 现有代码入口 |
| --- | --- | --- |
| 路由与阶段协作 | Explore 快通道；合法 Plan 到步骤审查；CHALLENGE 后 CONTINUE；Guidance 触发独立 ReplanDecision；回退、重规划和旧裁决消费 | Job 阶段、公开 timeline、事件/动作身份、调用账本；`showcase/solver_harness/controller.py`、`planning.py`、`replan.py`；`tests/test_star_product_guidance_consumption.py`、`test_star_product_continue_identity.py`、`test_star_product_replan_decision.py` |
| Role Skills、候选与零调用收尾 | 角色 Skill 在正确上下文生效且跨 Run 隔离；候选版本及来源完整；预算耗尽后 Best-Effort 只从已有合格候选选择且不增加模型/工具调用；replay 重算一致 | 出站上下文指纹、调用/工具增量为零、候选状态与选择来源；`skills.py`、`candidates.py`、`best_effort.py`、`replay.py`；`tests/test_star_product_skill_context.py`、`test_star_product_best_effort.py`、`test_star_result_history.py` |
| 独立审查与分类账本 | Verifier 自主请求受控计算；成功/损坏/伪造回执；已证局部成果与未证整体猜想共存；无效依赖不复活 | Verifier 裁决、回执校验、分类账本来源与依赖；`verification.py`、`classified.py`；`tests/test_star_product_verifier_compute.py`、`test_star_product_classified_outcomes.py` |
| 隔离工具 | 正常执行、域外/超时/预算不足、无输出、expected-output match/mismatch、隔离准入失败 | S3 工具次数、容器回执/退出状态、报告分类；`star_product_runtime.py`、`tool_precheck.py`、`tools.py`；对应 RB02/RB06 Docker 用例 |
| 整题审查、证明与 S4 绑定 | 最终生成携带有效证明正文；审查对象确为交付候选；改写、缺来源、伪造或历史 ACCEPT 不能继承绑定 | `final_response`、whole-review source、proof-delivered、S4 哈希及状态一致；`finalize.py`、`final_binding.py`；`tests/test_star_product_final_proof.py` 及来源门禁 |
| 预算、传输与协议 | HTTP/JSON/schema 失败和网络 unknown 分开；收到增量后断流；正常结束无 usage；迟到 usage 只结算原 attempt；输入用量缺失保留输入预留 | request attempts、known usage / reserved / charged / unresolved 分栏、停止状态和是否重发；`run_budget.py`、`adapters.py`；`tests/test_star_transport_policy.py`、`test_star_product_streaming_recovery.py`、`test_star_product_protocol_failure.py` |
| 持久会话与调用恢复 | 各恢复窗口重启；完成动作复用原身份，未决动作不自动重发；原 deadline 和账本不重置 | Job/Run 终态、恢复源、动作/attempt ID、重新派发数、原 deadline；`sessions.py`、`calls.py`、`stream_recovery` feature 及 RB06/RB07 用例 |
| 产品投影与脱敏 | Job、Report、Evidence、SSE 对状态和绑定一致；公开结果不带凭证、prompt、隐藏推理正文或 partial text | 公共 API 产物与敏感字段断言；RB04 公共 Job / 浏览器用例 |

离线阶段的出口条件：项目离线合同、相关完整测试、完整模式隔离门禁和差异审查通过；所有跳过单独归因。除逐组件合同外，必须有一条完整 `star_reference` 公共 Job 路径，实际经过 Plan、Reasoner、步骤审查、最终生成、整题审查和 S4 绑定；若该验收包含计算分支，还须核对隔离工具请求、真实回执与后续消费。现有 `star_limited` 的三调用快通道不能替代这条完整路径。失败回到拥有该机制的最小切片。输出为组件矩阵、版本/测试身份、故障分类和未覆盖项；不生成“live 能力通过”结论。

### 按配置项逐一映射

阶段 A 的组件组矩阵还须在运行清单中展开为逐项记录。`star_reference` 的九个配置项都必须有正常路径、故障反例、可观测结果和结论类型；同组测试不能替代逐项覆盖。具体测试 ID 与提交 hash 写入离线报告。

| 配置项 | `star_reference` 基线 | 离线作用证据 | live 消融边界 |
| --- | --- | --- | --- |
| `star_routing` | 必需 | 合法/非法阶段路由、裁决消费及停止位置 | 不关闭；按真实 trace 报触发覆盖 |
| `persistent_sessions` | 必需 | 重启恢复、身份复用、原 deadline 与 ledger 保留 | 不关闭；故障注入验证恢复合同 |
| `stream_recovery` | 必需；readiness 不要求实际走 SSE | Job/Run 进程退出恢复、动作身份复用、原 deadline/账本保持及已完成工具不重放 | SSE 作为可选传输；未单独验收时不进 live |
| `final_generation` | 必需 | 最终候选身份、有效证明正文与交付产物一致 | 只做合同必要性探针，不关闭做 live 消融 |
| `final_solution_review` | 必需 | 审查对象、拒绝/修复与最终文本绑定 | 不关闭整题审查或 S4 |
| `local_code_tool` | 必需 | 白名单、隔离、超时/预算拒绝及真实回执消费 | 不绕过隔离；只做安全故障注入 |
| `meta_guidance` | 必需 | guidance 触发、独立 replan 决策及无触发控制 | 可列为 reference-derived 单因素候选 |
| `reexplore_after_replan` | 必需 | 重规划后探索、旧裁决失效与新动作身份 | 可列为 reference-derived 单因素候选 |
| `skills` | 必需 | 正确角色上下文、跨 Run 隔离与不泄漏 | 可列为 reference-derived 单因素候选 |

阶段 A 必须记录以下既有行为测试的实际运行状态。三个配置准入测试是所有项的共同前置；`skip`、`xfail` 或未执行都记为 `not_covered`。表内的测试 ID 是可复用的离线证据，不声称自然 live 触发。

| 配置项 | 正向行为 | 拒绝 / 故障行为 | 恢复 / 账本行为 | 本轮缺口或条件 |
| --- | --- | --- | --- | --- |
| `star_routing` | `StarRoutingTest.test_star_solved_polishes_same_explore_session_before_fresh_review`；`StarPlanningTest.test_need_plan_and_accepted_step_expose_actual_gate_decision` | `StarRoutingTest.test_star_invalid_initial_plan_repairs_once_then_terminates`；`StarPlanningTest.test_invalid_dependency_is_repaired_with_the_actual_invalid_plan` | `StarContinueIdentityTest.test_process_exit_after_meta_continue_resumes_with_new_action_identity` | `StarReplanDecisionTest.test_reference_preset_rulings_cover_all_three_branches` 受隔离镜像条件限制，未运行时不得计覆盖。 |
| `persistent_sessions` | `SessionsTest.test_challenge_restores_distinct_role_histories`；`SessionsTest.test_recreation_continues_meta_history_and_completed_run_is_idempotent` | `SessionsTest.test_restored_identity_conflict_is_rejected_before_model_call` | `StarRecoveryTest.test_process_exit_after_session_exchange_does_not_repeat_acceptance`；`StarAlignChainRecoveryTest.test_chain_resume_crosses_every_new_persistent_boundary` | 恢复链集成用例不代表每个持久化边界均有独立故障用例。 |
| `stream_recovery`（持久 Job/Run 恢复） | `RobustRecoveryTest.test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding`；`StarRecoveryTest.test_process_exit_after_tool_receipt_does_not_repeat_tool` | `StarFullModeTest.test_full_unknown_call_requires_new_identity_and_preserves_shared_deadline` | `StarRecoveryTest.test_process_exit_after_verifier_tool_receipt_reuses_the_computation`；`StarAlignChainRecoveryTest.test_chain_resume_crosses_every_new_persistent_boundary` | 这里的 feature 名指持久状态恢复合同，不要求 provider 使用 SSE；隔离镜像条件及 skip 必须单列。 |
| 可选 SSE 传输 | `StarStreamingRecoveryTest.test_streamed_job_persists_each_delta_before_next_fragment_and_publishes_counts_only`；`StarTransportPolicyTest.test_late_complete_usage_settles_the_original_unknown_reservation` | `StarStreamingRecoveryTest.test_mid_stream_timeout_keeps_unknown_reservation_and_requires_explicit_retry`；`StarTransportPolicyTest.test_abrupt_eof_without_done_is_unknown_and_never_retried` | `StarStreamingRecoveryTest.test_process_exit_mid_stream_keeps_unknown_and_requires_explicit_new_identity` | 当前没有真实 provider 完整 usage / thinking 兼容证据；不属于本轮 Reference 主路径门槛。 |
| `final_generation` | `FinalizeTest.test_explore_plan_step_final_runs_without_supplied_plan`；`StarFinalProofTest.test_valid_proof_bodies_reach_final_generation_and_whole_review` | `FinalizeTest.test_budget_before_final_generation_dispatches_nothing_extra`；`FinalizeTest.test_failed_final_verifier_preserves_candidate_as_unverified` | `StarAlignChainRecoveryTest.test_chain_resume_crosses_every_new_persistent_boundary` | 已覆盖候选、预算拒绝与生成后恢复。 |
| `final_solution_review` | `StarFinalBindingTest.test_explore_review_binds_delivery_and_preserves_versions`；`StarFinalBindingTest.test_reject_retries_are_bounded_and_actual_accepted_version_is_bound` | `StarFinalBindingTest.test_repeated_reject_exhausts_without_reviewed_delivery`；`StarFinalBindingTest.test_delivery_rewrite_cannot_inherit_whole_review`；`StarFinalBindingTest.test_forged_review_reference_cannot_replace_actual_review` | `StarFinalBindingTest.test_cross_connection_append_keeps_original_whole_review_and_answer` | 整题审查与 S4 不得在 live 或架构验收中关闭。 |
| `local_code_tool` | `StarProductPythonTest.test_public_job_runs_registered_python_once_and_keeps_verified_artifacts`；`StarFullModeTest.test_reference_runs_same_public_job_with_real_tool_and_whole_review` | `StarProductPythonTest.test_public_job_policy_denial_never_dispatches_python`；`StarToolTest.test_tool_hard_limit_stops_next_claim_and_verifier`；`StarFullModeTest.test_runtime_isolation_failure_after_startup_rejects_without_model_or_job` | `StarRecoveryTest.test_process_exit_after_tool_receipt_does_not_repeat_tool`；`StarRecoveryTest.test_process_exit_after_verifier_tool_receipt_reuses_the_computation` | 完整 Reference + 隔离工具正例依赖配置镜像；被跳过时记 `not_covered`。 |
| `meta_guidance` | `StarGuidanceTest.test_blocked_step_guidance_changes_next_actual_task_and_pure_reasoning`；`StarGuidanceTest.test_replan_guidance_goes_through_the_independent_replan_decision` | `StarGuidanceTest.test_unknown_remote_timeout_stays_needs_review_without_meta_retry`；`StarGuidanceConsumptionTest.test_bypassing_the_consumption_gate_reproduces_stale_preemption` | `StarGuidanceConsumptionTest.test_recovery_after_guidance_decision_applies_it_exactly_once`；`StarGuidanceConsumptionTest.test_recovery_after_meta_ruling_applies_it_exactly_once` | `StarGuidanceConsumptionTest.test_reference_preset_second_traceback_consumes_only_the_new_meta_ruling` 受隔离镜像条件限制。 |
| `reexplore_after_replan` | `StarGuidanceTest.test_multiple_research_tasks_are_bounded_and_used_by_replacement_plan`；`StarGuidanceTest.test_guidance_replan_research_does_not_reuse_stale_meta_directions` | `StarResearchBudgetTest.test_cancel_research_keeps_late_usage_without_further_planner`；`StarResearchBudgetTest.test_meta_and_threaded_research_share_one_cumulative_job_ledger` | **缺少对齐用例**：现有 `StarReplanDecisionTest.test_recovery_after_replan_guidance_rules_exactly_once` 未验证恢复后的研究结果、新 Explore 动作及其消费关系。 | 补齐该恢复消费接缝前，对完整恢复链记 `not_covered`。 |
| `skills` | `SkillsTest.test_explore_loads_only_triggered_protocol_at_current_revision`；`SkillsTest.test_report_and_verifier_requests_load_both_review_protocols` | `SkillsTest.test_disabled_keeps_original_request`；`StarGuidanceTest.test_skills_disabled_does_not_change_challenge_context` | `StarSkillContextTest.test_role_history_and_current_projection_are_isolated_between_public_runs` | **缺少对齐用例**：没有专门验证恢复后正确重载角色 Skill ID / 版本的测试。 |

共同配置准入测试：`StarFullModeTest.test_reference_preset_is_exactly_nine_core_features_and_registry_inactive`、`StarFullModeTest.test_each_core_feature_missing_or_disabled_rejects_before_enqueue`、`StarFullModeTest.test_full_options_and_disabled_review_reject_before_model`。完整模式受隔离镜像门控的用例即使定义存在，只要运行结果为 skip 仍记为 `not_covered`。

本轮矩阵审阅发现两项具体覆盖缺口，阶段 A 需各补一个恢复合同后才能声称覆盖对应行为：`skills` 在进程恢复后应按当前角色重载并核对 Skill ID/版本，且跨 Run 不泄漏；`reexplore_after_replan` 在重规划后恢复时应确认旧方向失效、研究结果不重复派发、新 Explore 动作使用新身份并只消费一次。其他新测试只在矩阵项缺少正向/反例/账本断言时增加，避免重复已存在的合同。

Verifier、自主受控计算、分类账本、unknown 栅栏、整题审查、S3/S4、最终来源绑定和脱敏是独立合同，不是可随意关闭的消融开关；核心安全组件只做旁路故障注入的 `contract_necessity` 证据，该结论不证明自然触发或数学收益，也不进入 live 数学消融。任何 live arm 都不得关闭整题审查、S3 或 S4。阶段 A 对这些合同做正向与旁路故障探针。标记为 `contract_necessity` 的证据必须冻结一个具体故障场景，并在合同开启、受控旁路、恢复合同三个条件下用相同输入、初始状态、随机种子和执行顺序运行。注册时逐项写明预期观察量及应保持的不变量。合同开启时公共验收必须 pass 且不变量成立；旁路时对应公共验收必须 red，并观察到预登记的不变量违例；恢复合同后同一验收必须再次 pass。登记故障场景、旁路点、预期观察量、不变量、公共验收 ID、源码身份和三次结果。结论只适用于该冻结故障场景和该合同，不外推到其他故障或整体系统效果。`candidate_registry` 和 `best_effort` 不属于当前 `star_reference` 基线，只在各自启用的其他模式中验证，不能把其结果称为 Reference 组件贡献。

## 历史提案阶段 B：有界 Reference 真实验收

先定义并实现新的 **`RB08-v2 Reference-readiness`** 注册版本；它是一个新验收批次，不得称作或补算原 E1。新 schedule 必须在 manifest 中为每个 Run 显式记录 `stage`、`question_id`、`repeat_id`、`transport` 与 limits，四个 E1 位置固定 `transport=nonstream`，两个短题各 `repeat_id=1,2`；四项 E1 全部通过后才派发 E2 三类题各两次，记录独立 repeat ID。manifest 同时固定 `original_E1_counted=false`、`ROB-AC-20=not_covered`，并引用原始失败批次 hash。当前注册器固定旧传输 schedule，故必须先实现该版本校验、执行顺序、停止行为和归档 hash 的离线测试；没有这项 runner 合同及新 manifest hash 时不得发真实请求。Provider 侧 Messages SSE 流式继续作为可选传输入口，不进入 E1/E2 核心 readiness；`stream_recovery` 的持久化恢复合同仍须满足。若之后单独检验流式，只能用独立注册、同一 Messages endpoint 的非流式对照和完整的 thinking/usage 准入条件，且失败不改变非流式 readiness 的定义。
所有新实验 manifest（包括 `RB08-v2`、C 和 D）还须钉住 `architecture_spec_version`、Reference config（`reference_config`），并为各 arm 固定源码 SHA；逐 Run 记录实际 `applied_config` 和 provider 返回的模型/版本字段。provider 未返回的模型/版本字段记为 `unavailable`，其他缺失字段也不得推测或伪造。若 provider 未返回模型版本，两臂仍须使用同一预登记时间窗；若返回 service ID，则记录并要求两臂一致，未返回则记 `unavailable`。结论限于该时间窗和已确认的 service ID，不声称固定权重快照或权重级复现。实际模型/版本与注册值不一致时记为条件漂移，按停止规则处理。

E1 的三调用顺序用于验证同一 Job 的完整交付闭环（模型调用、计量、整题审查、最终文本身份与 S4 绑定），通常对应快通道；它不能证明 Plan、Reasoner、步骤审查或隔离工具自然发生。完整 Reference 的非快通道架构路径由离线公共 Job 合同覆盖，并由 E2 的真实自然 trace 门单独核验。两种闭环分别记录，不互相补算。

新批次最多仍为 **10 个 Run**：E1 两个短题各两次独立非流式 Run，共 4 个（两题×重复，不是四个题族统计样本）；四项均通过后，E2 三类公开题各两次独立非流式 Run，共 6 个。复用现有 E1/E2 per-Run 与整轮硬上限，不提高任何字段。每个 Run 都先按下面的固定条件判定，再按阶段门判定。

- **E1 每 Run 架构闭环条件：** 不超过 `6 logical calls / 8 HTTP attempts / 1` 个题目工具、`32,768 charged/reserved tokens` 和 `300 秒`；已知 provider input 与 output usage 合计不超过 **8,192 tokens**；包含预检的交付耗时不超过 120 秒；按预登记三调用顺序实际完成同一 Job 的三次调用；不使用题目工具；`transport_status=known`、`usage_status=complete`、`task_status=completed`；整题审查对最终候选给出合法终态，最终交付文本与被审查候选的身份和来源一致，S4 绑定有效。外部数学正确性与解释质量只记录，不作为本轮通过条件；内部审查的 ACCEPT 也不单独作为数学正确性证明。任一架构闭环、计量或硬预算条件失败，该 Run 记 `run_fail`。
- **E2 每 Run 架构闭环条件：** 不超过 `12 logical calls / 16 HTTP attempts / 3` 个题目工具、`65,536 charged/reserved tokens` 和 `600 秒`；`transport_status=known`、`usage_status=complete`、`task_status=completed`；整题审查对最终候选给出合法终态；最终交付文本与被审查候选的身份和来源一致且 S4 绑定有效。独立数学正确性与解释质量只记录，不作为本轮通过条件。自然快通道可以满足该 Run 的交付闭环条件，但不满足下面的自然非快通道闭环门。
- **立即停止条件：** 任一 E1 或 E2 Run 出现 `transport_status=unknown`、`usage_status=incomplete|unresolved`、产品/协议/配置/来源缺陷、取消、预算或 deadline 硬限，立即停止本批次，不换题、不重试、不提高预算；该批次的阶段 B 总门为 `fail`。数学评分为错、拒答或未触及硬限的数学未完成单独记入 `mathematics_status`，不把它改写成架构通过证据，也不单独触发资源重试。

**E2 自然非快通道闭环门**定义为：六个 E2 Run 中至少有一个同时满足 `run_pass=true` 和以下完整事件链，且每个事件都来自该 Run 的真实自然 trace：合法 Plan → Reasoner 步骤 → 自然提出且在白名单内的受控计算 → 隔离实际回执被消费 → 整题审查 → S4 绑定最终交付。快通道、脚本触发、故障注入和 replay 都不计入该门；没有这样的 Run 时记 `natural_nonfast_gate=false`，即使普通数学结果通过也不能补算。

**阶段 B 阶段门：** 四个 E1 Run 全部达到架构闭环条件且没有立即停止条件后，才派发 E2。阶段 B 总门为：四个 E1 Run 全部 `architecture_run_pass`，三个 E2 题类各自的两次重复中至少有一次 `architecture_run_pass`，`natural_nonfast_gate=true`，且全批次没有账本/manifest/源码身份/模型条件/最终绑定缺陷。满足时记 `B_total_pass`，表示该有限样本中端到端架构按合同跑通；不表示答案正确率或普遍可靠性。否则记 `B_total_fail`，只归档已执行结果和失败点。数学结果单列 `mathematics_status`，不参与此门。

流式只保留为既有适配器的离线合同覆盖或日后的单独预注册传输实验；不混入此轮 10 个 Run，也不决定非流式 E1/E2 通过与否。若后续注册该实验，先核实 endpoint 的思考模式行为及 provider usage 字段；只有该题每次调用均能对账完整输入/输出用量时才进入完整计量比较。缺输入用量时只报告传输已完成、计量不完整并保留预留，不拿预留/估算当实耗。剩余 Run 额度不自动使用。

E2 要求至少一次**真实自然**的完整非快通道闭环：合法 Plan → Reasoner 步骤 → 自然提出且在白名单内的受控计算 → 隔离实际回执被消费 → 整题审查 → S4 绑定最终交付。没有自然触发时记 `not_covered`，受控/脚本场景不能补算为 live。该项对应 #80 AC-18/#70 的实际核心缺口。

此版本化变更把当前 E1 的流式/非流式传输对照从新 readiness 批次中移除，改为同题非流式重复。它不满足原注册 E1，不满足 #87 原 ROB-AC-20，也不关闭或改写 #95/#87/#80/#70。旧 manifest 与结果只读保留；新结果单独报告 readiness，并逐项给出它对各 Issue AC 的覆盖映射。

阶段 B 只回答 Reference 是否按门槛完成这些固定架构闭环。它没有 baseline arm；报告逐 Run 的 `architecture_run_pass`、架构事件链、数学状态、调用/工具/token/预留/时延及失败点，不声称架构相对收益、普遍正确率、p95 或因果组件贡献。

## 历史提案阶段 C：整体架构相对基线的配对效果

在阶段 B 的 `B_total_pass` 完成且账号额度、计量与运行成本已复核后，另立实验批次和硬预算；不挪用或覆盖 RB08/#95 旧额度。本提案只规划一个探索性的 C pilot，不注册或执行 C confirm。新增离线注册与执行合同，验证认证公共 Job 能以相同题文和冻结条件运行 `legacy` baseline 与完整 `star_reference`，并分别归档。现有 `PairedRunner` 和 `Campaign` 都不支持该整体比较，必须先实现并通过新的 runner 离线注册、随机顺序、同题配对、停止与归档测试；在此之前不得派发 live。

阶段 C 和每个阶段 D pilot 都必须在前一阶段门通过、真实资源核准后，分别以独立 manifest 登记单 Run 与批次硬上限，覆盖 logical calls、HTTP attempts、已知 input/output tokens、charged/reserved tokens、题目工具和 wall-clock。只有费率与计量可核验时才登记金额，否则金额记为 `null`。注册器缺少任一必需上限时拒绝注册；执行器达到上限或没有下一 Run 的完整预算时停止派发，超限时硬停止。C pilot 的拟议规模为 12 个题族、最多 24 个双臂 Run；每个入选 D 因素的拟议规模为 12 个新题族、最多 24 个配对 Run。这些规模不是当前派发授权；本提案不提供全计划累计 Run 或资源预算，也不注册任何 C/D live 批次。各批次均不得使用或挪用 RB08 额度，也不得提高 RB08-v2 已冻结的单 Run 或整轮上限。本提案不授权付费请求；任何付费 live 执行仍须另行取得明确授权。

两臂使用同一 Intern 模型标识、temperature、思考设定、题目输入、响应截止和**相同每题总资源上限**；请求/工具差异作为结果记录。对照固定命名为 `showcase-legacy@<pinned_commit>`，精确绑定既有 Showcase `legacy` mode 的提交 SHA、配置、请求路径和验证行为；注册前填入 SHA，禁止把它与研究计划中的 `B-direct` 或官方 `B-official` 混称。整体包比较中，Reference 的角色协作、Verifier、工具、S3、S4 等保留为 treatment 的组成部分，不能为“条件一致”而从 Reference 删除。运行前冻结两臂共用的盲态外部数学正确性+交付完整性 rubric、题目数学义务和 `undecided` 判定规则。每份交付由 **2 名互不沟通的盲评者**按同一清单独立评分；系统为每份交付生成随机 ID，分别打乱呈现顺序，并移除 arm 标签、Run/请求/时间/配置等运行元数据。随机 ID 与 arm 的映射由不参与评分的注册管理员保管，评分和裁决锁定前不可查。输出文本可能暴露架构特征，因此每名评审者在评分锁定后、揭盲前，还须记录是否猜测 arm 及其猜测；不得据此改分或排除样本。任何主终点分歧交由第 **3 名盲评者**在盲态下按冻结义务和 rubric 独立裁决。评分与裁决全部锁定后才揭盲和比较结果；第三人仍无法裁定时标为 `undecided`，在 intention-to-treat 主分析中计为未达成。评估侧复核不替 Legacy 补造 STAR 的内部 Verifier、S4 或来源/文本绑定；这些只列为 STAR 的过程/合同指标，不作为 Legacy 成功判据。相同输入、模型、每题硬限和外部评分是公平约束，架构内部机制保留为待比较的处理差异。若某题类无法在相同隔离/工具边界下比较，应预先划为单独 strata 或排除出该比较，不得事后混算。

先冻结抽样框、公开题源及其版本/日期/hash、纳入排除条件、抽样方法和随机种子。按固定规则去除重复题；同一来源题目的改写、换数值或其他同源变体合并为一个问题族，每族按预登记规则只抽取一道题。对每道候选题，由不知道 arm 分配且只查看题目属性的预评审，在任何分配或运行前按以下顺序裁定分层：第一，若题目可在预登记的短计算义务内完成且不自然需要隔离计算，归入**简单计算层**；第二，仅对未归入第一层且自然需要白名单隔离计算的题目，归入**自然适用隔离计算层**；第三，其余符合纳入条件的题目归入**一般证明/多步推理层**。前一层命中后不得进入后一层；没有任何一层且不符合纳入条件的候选题在随机化前排除；运行后不得改层。C pilot 冻结 12 个独立问题族，每层各 4 题；每个问题族在两臂各运行一次，组内先后顺序随机，题族是统计单位。C pilot 可记录 `skills`、`meta_guidance`、`reexplore_after_replan` 的自然触发和可核验 trace 作为阶段 D 的准入观察，但不把这些观察改作 D 效应估计。所有已分配题族都保留在 intention-to-treat 主分析；实际隔离工具是否触发只作过程指标，绝不据此筛选主分析。结论限定于这 12 个冻结题族及其抽样框，不外推为目标题总体的普遍效应。

主要终点为两臂共用的“盲态外部数学正确性+交付完整性” rubric。对每个问题族 `i`，记录 Reference 的 `Y_Ri` 和 legacy 的 `Y_Li`，只有该臂在同一盲态 rubric 下数学正确且交付完整时取 `1`；错误、拒绝、已知未完成、取消、undecided 或已知缺失交付取 `0`，并保留原始状态原因。`transport_status=unknown` 按停止规则处理，不直接记作数学失败。单臂内部 Verifier、S4 或来源/文本绑定失败，记录为该臂过程/合同指标；只有在其导致该臂未交付或按共用 rubric 判为交付不完整时，才据此使该臂主终点为 `0`，且不自动判整批无效。此类内部指标不嵌入两臂共享 rubric，也不作为 Legacy 成功判据；产品自身端到端完成率另列为次指标。所有已随机分配题族都进入 intention-to-treat（ITT）；不因实际工具触发、曝光状态、评审分歧或另一臂结果而删除、替换或重跑题族。共同实验完整性事件（如盲评揭盲或配对分配被破坏、共用账本不可核对、跨臂安全隔离失效），或停止规则所致的未完成配对，才使整批不估效。

阶段 C 与 D 共用停止规则：一般数学错误、拒绝或未触及硬限的已知未完成以 `0` 计，完成该题族的配对并保留原 attempt，不替换、不重跑。`unknown`、共同账本不可核、跨臂来源/安全隔离失效、答案泄漏、独立盲评不可用、任何硬限或模型条件漂移时，停止新增派发并结算原 attempt；单臂内部 Verifier、S4 或来源绑定失败按主终点和过程指标规则处理，不自动使整批无效。若因此留下未完成配对，或共同实验完整性不变量失效，则整批不估效，不取已完成子集。

每个问题族的配对结局按 `11`、`10`、`01`、`00` 记录，其中 `10` 表示 Reference 成功而 legacy 失败，`01` 表示 legacy 成功而 Reference 失败。令 `Y` 仅表示上述两臂共用盲态外部 rubric 的通过与否，`D_si=Y_Rsi−Y_Lsi`，则第 `s` 层的点估计为 `Δ_s=mean(D_si)=(n10_s−n01_s)/n_s`，不一致率点估计为 `q_s=(n10_s+n01_s)/n_s`。三个互斥层等权的宏平均点估计固定为 `Δ_macro=(Δ_simple+Δ_tool+Δ_proof)/3`。C pilot 每层只有 `n_s=4`，只报告配对四格表和这些点估计，不计算或解读标准误、样本方差、置信区间或其他精度指标；例如某层出现 `SE=0` 也不表示精度已知。

C pilot 只报告三层配对四格表、`q_s`、`Δ_s` 和 `Δ_macro`，所有结果标记为 `exploratory/descriptive`。不报告显著性、置信区间、标准误、alpha 或功效结论，也不以 pilot 结果证明架构优越或决定确认检验。`Δ_macro>0` 仅表示这 12 个冻结题族的观察到的正确且完整交付比例较高；`Δ_macro<0` 表示较低；`Δ_macro=0` 表示未观察到宏平均差异。上述统计量只描述本 pilot 的题族、分层和运行条件，不代表目标题总体效应或确认性因果结论。

本提案不注册确认性 C 检验，也不把 pilot 作为确认性通过门。C pilot 的小样本描述统计不构成确认性结论；任何确认检验均须另行注册，不属于本提案。

## 历史提案阶段 D：单个组件的边际作用

阶段 D 只能在阶段 C pilot 完成且整批可估后启动；D 使用与 C 不同的题族，并单独登记预算。C pilot 中记录到的组件自然触发只用于候选筛选：只有某因素在 12 个 Reference Run 中至少 **4 个不同题族**出现完整、可核验的自然触发且无安全不变量违例，才可另行登记该因素的 D pilot；否则记 `not_estimable/no_natural_exposure`，不开展该因素的 D pilot。这个覆盖筛选不估计组件效应，也不作为样本量估计。每个入选因素各自预注册一个新的 12 题族 exploratory pilot，每层 4 题；每题族做一次完整 Reference control 与一次单因素消融 variant 的配对 Run，随机组内执行顺序。候选因素的自然触发链须在注册时写明事件、因果顺序和可核验 trace 字段；“配置已开启”或 scripted/fault-injection 触发不算自然触发。`meta_guidance` 至少记录 Guidance、独立 ReplanDecision、被采纳的新计划及其新动作身份；`reexplore_after_replan` 至少记录已生效的重规划、旧动作/裁决失效、新 Explore 动作身份及后续消费关系；`skills` 至少记录 Skill ID/版本、接收角色、注入上下文摘要及后续模型动作对该上下文的引用。Trace 必须以 Job/Run 和事件/动作 ID 连起顺序、来源、结果和实际 applied config，并可从归档的公开事件与受控证据复核，不含凭证、完整 prompt 或隐藏推理正文。

若要估计 Reference 策略组件的 live 边际作用，先实现并离线验证专用 runner：control 为冻结的完整 `star_reference`；variant 明确命名 `star_reference_ablation/<feature>`，只改变一个策略配置项，并保留整题审查、S3/S4、隔离、unknown 栅栏、相同模型/协议、同题同预算和外部评分。仅在受信任的离线注册与实验 runner 中允许该 variant，不新增可由普通 HTTP 用户设置的 feature 开关。每个题族随机 arm 顺序；记录实际 applied config、组件是否触发、Job/Run/attempt/tool/usage 三状态、停止原因和独立盲评。D 与 C 共用上述盲态外部数学正确性+交付完整性 rubric 作为主要终点，方向固定为 `完整 Reference − 单因素消融 variant`；未触发该因素的题族仍保留在 ITT。暴露子集只作机制诊断，不作为主效应估计、筛选或替换样本。候选限于 `skills`、`reexplore_after_replan`、`meta_guidance` 等不会绕过上述安全合同的策略项；variant 要明确标记为 reference-derived，不再称完整 Reference。整题审查、S3/S4、隔离和来源/预算安全不变量不得关闭做 live ablation。`candidate_registry`、`best_effort` 不在 Reference 基线中，应在各自产品模式单独评估。

每个因素的 D pilot 最多 24 Run，只报告三层配对四格表、ITT 风险差和该因素实际曝光覆盖，均标记为 `exploratory/descriptive`；不据此宣称组件有效或有害，也不作确认性因果结论。不能把 C pilot 或其他因素的 D pilot 合并为该因素的样本量依据；不同因素之间也不共享题族。当前提案不注册 D confirm，确认性消融另行注册。

核心安全组件以旁路故障注入评估 `contract_necessity`，不推断 live 数学收益，也不量化所有组件的数学贡献；`live_marginal_effect` 只适用于 `skills`、`meta_guidance`、`reexplore_after_replan` 等可选策略项；阶段 C 整体对比标 `system_level_effect`。三类证据不可互换，也不做一次性全因子排列。

## 归档、报告与下一步

每批固定题文来源/hash、盲评义务、模型/条件、源码提交和 dirty 状态、配置与 manifest hash、预算/停止规则、每 Job 的调用/attempt/工具/证据引用、原始失败及三个独立状态字段。原始题、答案、完整 prompt 和 raw 继续留在忽略的 artifact 或受控仓外存储；Git 只保留脱敏汇总、代码和注册合同。报告明确标记 `scripted`、`fault_injection`、`live`、`replay`，不混为同一种证据。

阶段 A 的首轮执行记录（2026-10-27）：非流式用量/迟到结算聚焦回归、简单题 Reference 快通道、多步隔离工具及整题审查、重规划、回执提交后的同一 Job 进程恢复已覆盖；随后全仓离线合同（757 项测试）、Showcase 发布门禁、差异与官方 baseline 审查均通过。范围决定与证据边界已留言至 #96，#96/#95/#87/#80 均保持开放。本轮没有发送真实 provider 请求、提高预算或改变官方入口；工程可达性不作为数学正确率提升证据。阶段 A 的逐组件完整矩阵仍需按本提案后续逐项注册和补证，不能由本轮代表性闭环替代。旧提案中的 E1→E2 顺序仅适用于该历史 readiness 方案，不构成独立 #97 非流式验收的前置；架构配对效果与组件消融仍是独立的可选实验。
