# F8 Faithful A–G 评测协议 v1

日期：2026-11-11。此协议先于 F8 实现评审与冻结。GitHub 实施票：[F8 #154](https://github.com/RUSS0718/MathAgent/issues/154)。变更指标、分母或状态语义时必须新建协议版本，不得覆盖既有批次。

状态：frozen，版本 faithful-f8-v1.1.1-engineering，冻结日期 2026-11-11。规范轴与规格轴最终定向复查均解除阻塞，允许按下方 v1.1.1 工程合同实现。本文前部 review_draft 内容保留为审查历史；冲突处以 v1.1.1 为准。冻结不代表实现或实验验收通过。

2026-11-11 用户明确授权替换审查安排：R1/R2 使用两个隔离子智能体，R3 在收到两份初审后裁决；不再以真人到位作为本轮工程开工门槛。此决定替代下文旧草案中的真人要求。自动数学审查单列为 model_assisted，不得冒充 independent_math 或真人 L3；provider-live、自然题求解、官方重评分依安排继续 not_run。本次冻结目标为 faithful-f8-v1.1.1-engineering；旧 review_draft 不覆盖、不改写既有实验结果。

## 分组

| 组 | 增量能力 | 必保留的失败或未知路径 |
| --- | --- | --- |
| A | S01–S06 Harness 与官方 88 分 baseline 对照 | provider unknown |
| B | F1 证明依赖图 | 支持撤销、精准失效、图版本 |
| C | F2 多路线 | 重复 frontier、路线终止与交付绑定 |
| D | Population/Rater/APRS | 收尾不足、unknown、独立路线比较 |
| E | F3 受限形式化 | sorryAx、环境漂移、L2/L3 区分 |
| F | F4 同源干预 | 单臂 unknown、配对身份与控制变量 |
| G | F5/F6 记忆与解释 | 缓存复核、证据失效、段落来源与等级 |

每组保留前序组对照栏；控制变量不成立时明确不可比较，不把 A–G 解释为无条件累加链。前置能力不可用时记录 unsupported 或 not_run，不静默跳组。

## 固定 manifest 与分母

每批冻结源码 SHA、配置及 hash、模型/provider、prompt 身份、题集 hash、种子、顺序与重复、能力开关、工具/验证环境、实际资源消耗和停止约束。未知上限标记 `unknown`，不得推测或虚构 provider 约束。

每组报告登记总样本数、完成数、失败数、unknown、incomplete、unsupported、not_run。主成功率保留登记分母；L2 目标覆盖、形式目标通过率与可判定条件率按下方明示分母分别计算。未完成样本保留身份，不删除、不插补、不由重跑覆盖。配置漂移、样本身份、控制变量或分母不符时标记 not_comparable。

## 指标

分别报告正确率、根义务覆盖、有效证据、路线效率、Lean/规格表现、L2/L3 核验通过率、配对差异与不确定性、缓存复核、解释 rubric、P50/P95 时延和成本。L2 表示形式目标核验；只有原题与规格对应达到要求时才记 L3。缺少独立数学评分来源时写 `not_available`。

F 组报告保留双臂、控制变量、配对身份和单臂 unknown；不能仅凭一次配对样本声称稳定因果增益。G 组解释评价需保留独立 rubric 与样本来源，不用实现测试通过数替代。

## L1、L2、L3 与官方评分

- **L1 表达回归**：固定 25 项表达/API 回归，完整报告成功、失败、跳过、源码 SHA 和分母；缺项不缩小分母。
- **L2 分组统计**：按登记样本和目标范围报告 L2/L3 的可判定数量、通过数、失败数及 unknown/incomplete/not_run；不可判定样本单列，不从总登记数中删除。L2 不计为 L3。
- **L3 人工抽查与自动检查**：预先记录抽样框、种子、分层、样本量、双人独立审查、分歧裁决、审查标准与记录字段。自动检查核对身份、来源版本、脱敏、分母和报告一致性；不代替人工数学判断。
- **官方端到端评分**：固定官方入口、88 分 baseline 源码/哈希、题目与评分流程；报告原始结果、差值及环境。Showcase 不改变官方路径和默认预算。

## 报告模板与证据包

报告按工程证据、真实工具、provider-live、自然题、独立数学判断分栏，并列 A–G 状态、baseline 对照、登记分母、各缺失状态、限制和来源。一次门禁或成功运行不能推出数学能力提升。

证据包包含 manifest、配置/题集 hash、运行身份、机器报告、核验及人工抽查记录、浏览器/API 证据、门禁源码 SHA/命令/摘要和失败记录。不得包含凭证、完整 prompt 或隐藏推理。

## 2026-11-11 技术评审修订（未冻结）

评审起点为 a0be0a3a7279a141304a1a64d4bc1842189955c9。本修订仍为 review_draft，不是实现许可。L3 题集、样本规模、两位人类审查者和分歧裁决安排待用户提供。协议冻结须记录版本、正文 SHA256、双轴审查结果与 #154 评论；冻结后的指标、分母、状态或抽样变更须发布新版本。

### 实际分组开关、能力与对照限制

开关来自 showcase/star_product_config.py、star_product_runtime.py、flask_app.py 与各生产者。配置只取受信服务端参数，不向 HTTP 开放任意配置。记录完整 applied config 与 hash，不能只记录增量。Faithful 命名与旧 campaigns A–D 隔离。

| 组 | 实际配置 | 对照与能力限制 |
| --- | --- | --- |
| A | SHOWCASE_STAR_ENABLED=True；SHOWCASE_STAR_FEATURES 显式启用 stream_activity、context_pack、problem_spec、progress_scheduling、final_generation、final_solution_review；提供 SHOWCASE_STAR_CONTEXT_CAPACITY，冻结实际 transport 和 SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION | S01–S06 工程证据可用，live 容量未确认。官方 ReasoningAgent 另列，不把 Harness A 当作官方基线。缺容量时相应运行 not_run。 |
| B | A 加 features.proof_graph=True，proof-graph-v1 | 对 A，来源为 F1/S07；保持 AND/OR、版本和精准失效语义。 |
| C | B 加 features.serial_routes=True，serial-aprs-v1；progress_scheduling 依赖必须进入 applied config | 对 B；串行路线不计为并发。 |
| D | SHOWCASE_STAR_POPULATION_ENABLED=True，由 population_config 构造 concurrent_routes=True、serial_routes=False、concurrent-aprs-v1 与 population-v1 | 对 C 是 policy 切换。#156 仅 engineering-preview，live 需 verified capacity、service_id、max_inflight、worker_slots、evidence_ref 和请求时限。preset 还改变 challenge 次数，须列全部差异；控制不成立则 not_comparable，不归因为并发。 |
| E | SHOWCASE_FORMAL_BACKEND 与 SHOWCASE_FORMAL_VERIFICATION_CONFIG；冻结 enabled、后端白名单、require_formal、目标、环境、公理、资源、timeout 和输出上限 | F3 受限目标。parent policy 必须明示；未经验证的 D+F3 组合 not_run，不能靠分别通过推定集成已通过。 |
| F | SHOWCASE_FAITHFUL_INTERVENTION_ENABLED=True；显式 planner_checkpoints 或 reasoner_checkpoints，复用父 checkpoint 和双臂账本 | NativeCheckpointExecutor.validate_checkpoint 要求 serial route，拒绝 population；完整 D→E→F 累加在当前源码 unsupported。F 串行专项独立保留 parent 及 control/intervention 两臂；与 E 的 parent 不同则前序比较 not_comparable。不新增并发干预能力。 |
| G | SHOWCASE_FAITHFUL_MEMORY_ENABLED 提供管理面，SHOWCASE_POPULATION_MEMORY_ENABLED 及显式同意控制注入，Goal Cache 须当前环境复核；SHOWCASE_PRESENTATION_ENABLED 启用 F6；F7 另需 SHOWCASE_F7_SYSTEM_VIEW_ENABLED | 管理开关不等于全部记忆已注入。冻结 scope、来源、同意与冷／暖缓存条件；parent 不同则 G/F 不作单因素比较。F7 仅读，f7-deeplink-v1 不变。 |

源码明确拒绝的组合为 unsupported；缺材料、环境、容量证据或未测试的组合为 not_run，均保留登记槽位。D 既不能因 #156 open 就记成完全没有实现，也不能用其受控工程证据充当真实服务容量或自然题效果。

### 登记单元、状态与统计

主键为 (batch_id, group, sample_id, repetition)。派发前登记全部 A–G 槽位；F 的 pair 及两臂共享父 checkpoint 身份。数学 verdict、执行状态、证据层级和可比较性独立记录。执行成功不能直接填数学 pass。

| execution_status | 含义 |
| --- | --- |
| completed | 所需执行已终止且交付已保存；独立请求可仍待结算，数学正确性另判 |
| failed | 有可定位记录的已知协议、执行或工具失败；不默认是数学错误 |
| unknown | 已发请求或工具结果无法证实，保留身份和预留，零自动重发 |
| incomplete | 已启动但所需交付未完成，例如取消、截止、收尾不足；未知结果不是主要停因 |
| unsupported | 固定源码、组合或目标域明确不支持，有能力与原因记录 |
| not_run | 已登记但尚未启动，或缺输入、环境、容量证据、授权或人工安排 |

六状态互斥、全部计入 N_registered，计数之和必须等于登记数。执行中的快照按 incomplete 记录并保留 running 事实。unknown 优先于其他未完成停因；数学交付和请求结算分开，已合法交付且有无关 unknown 请求时 execution_status 可为 completed，另记 settlement_status=unknown。主成功率使用登记分母，条件率另列可判定子集及其分母。

comparison_status 为 comparable、not_comparable 或 not_available。源码／配置漂移、题目身份、控制变量、顺序、重复或分母不符为 not_comparable；它不是第七种执行状态，不能消除失败和 unknown。晚到结算保留原终止快照并追加审计，不改写首次报告数学结论。显式重试另建身份并关联原记录，primary 分析只用预登记主运行，不挑最好重跑结果。

指标记录 numerator、denominator、eligible_count、missing_by_status、scope。正确率仅来自独立评分源；根义务覆盖按冻结根义务计数；有效证据按当前未失效且去重来源计数。路线效率须有对应收益与消耗，否则 not_available。P50/P95 使用 nearest-rank，即排序后 ceil(p*n) 的一基位置，另列 unknown／censored 数，不能把可观察子集当总体性能。缺失 usage／价格保持 null 与 unknown，不按零计成本。双臂差值只在可判定 pair 上描述，同时保留全部登记 pair 和缺失数；未冻结推断方法与功效时不输出显著性或稳定因果收益。

### manifest 最小合同

版本为 faithful-f8-manifest-v1。复用 experiment_manifest.canonical_json 的 UTF-8、排序键、紧凑分隔符与禁止 NaN 规则。内容 hash 为 SHA256，文件按原始字节、结构按规范 JSON。manifest 自身 hash 在旁置回执保存，不参与自身 hash。未知字段、重复键、重复登记主键拒绝。

| 字段组 | 必需内容 |
| --- | --- |
| identity | schema_version、protocol_version、protocol_sha256、batch_id、created_at、evidence_kind |
| source | 40 位源码 commit、源码清单 SHA256、干净状态、依赖锁 hash；BASELINE.json hash 与 11 文件逐项核对 |
| configuration | 每组 requested/applied config 和 hash、capability、policy/schema/profile/timeout 身份、parent 与允许差异 |
| model | provider、确切 model ID／可得快照、transport profile 指纹、thinking、temperature、输出上限、prompt 文件版本与 hash；不可得快照标 unknown |
| dataset | ID/version、字节 hash、逐题 input hash、来源、开发／独立划分；不含隐藏答案 |
| design | seed、题目及 group 顺序、重复、主运行身份、F 双臂顺序／checkpoint hash、L3 抽样框／分层／数量／审查安排 |
| environment | OS、Python／依赖版本、工具 image digest、Lean／库／公理／规格版本、网络和容器资源、证据引用 |
| resources | 服务／账户／机器已知硬限制及来源、run/phase/batch deadline、实际预算／收尾预留、停止条件；未知 provider 上限标 unknown |
| registrations | 全部 A–G sample/repetition 槽位、预登记目标 hash／scope、Run／pair 待绑定身份与能力缺失原因 |

实际耗时、usage 与工具成本写追加结果，不能修改冻结 manifest。停止条件覆盖 unknown、取消、硬截止、源码／配置漂移、账本或绑定缺陷。预算沿用已授权条件；旧 runner 的默认值不能冒充本批实测限制，也不能以新 Run 重置旧 deadline 或 unknown 预留。

### L1 固定 25 项清单与运行入口

固定选择器为 tests.test_faithful_f6_presentation（9 项）与 tests.test_s06_presentation（16 项），与 F6 表达／API 回归范围一致。以下 25 个 ID 为固定分母，新增测试另列。删除、不可加载、skip、expected failure 都不能缩小分母或计通过。

~~~text
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_persisted_graph_claim_exposes_proposition_and_inference_only_for_exact_public_excerpt
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_l2_evidence_has_a_versioned_target_reference_without_upgrading_original_answer
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_legacy_frozen_policy_keeps_its_original_renderer_and_no_new_delivery
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_no_eligible_best_effort_candidate_is_incomplete_even_with_old_success_and_answer
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_selected_candidate_uses_actual_public_projection_field_names
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_claim_without_current_review_cannot_complete_or_borrow_formal_reference
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_revalidation_revokes_delivery_claims_and_preserves_historical_artifact
tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_modes_and_failures_have_independent_sealed_artifacts_and_stable_output_requests
tests.test_faithful_f6_presentation.FaithfulF6OutputApiTest.test_renderer_timeout_connection_and_style_failure_preserve_original_without_solving
tests.test_s06_presentation.PresentationBindingTest.test_modes_have_separate_artifacts_and_never_replace_original_answer
tests.test_s06_presentation.PresentationBindingTest.test_rewritten_math_cannot_inherit_exact_text_review_even_with_valid_refs
tests.test_s06_presentation.PresentationBindingTest.test_missing_or_invented_claim_sources_remain_pending
tests.test_s06_presentation.PresentationBindingTest.test_current_evidence_change_marks_old_artifact_for_review_without_rewriting_it
tests.test_s06_presentation.PresentationBindingTest.test_public_snapshot_whitelists_sources_and_does_not_expose_private_proof
tests.test_s06_presentation.PresentationBindingTest.test_no_answer_stays_incomplete_in_all_modes
tests.test_s06_presentation.PublicPresentationApiTest.test_mode_is_frozen_and_idempotency_includes_it
tests.test_s06_presentation.PublicPresentationApiTest.test_explicit_outputs_keep_answer_and_persist_artifact
tests.test_s06_presentation.PublicPresentationApiTest.test_mode_mismatch_and_failed_presentation_keep_original_answer
tests.test_s06_presentation.PublicPresentationApiTest.test_old_job_without_mode_defaults_to_solve
tests.test_s06_presentation.PublicPresentationApiTest.test_default_off_capability_rejects_explicit_mode_without_freezing_it
tests.test_s06_presentation.PublicPresentationApiTest.test_non_object_presentation_body_is_bad_request
tests.test_s06_presentation.CurrentSolverPresentationTest.test_budget_stopped_real_candidate_is_partial_and_output_adds_no_model_call
tests.test_s06_presentation.CurrentSolverPresentationTest.test_public_artifact_saves_with_authoritative_graph_and_specification_versions
tests.test_s06_presentation.CurrentSolverPresentationTest.test_evidence_invalidation_marks_history_without_mutating_old_artifact
tests.test_s06_presentation.CurrentSolverPresentationTest.test_public_save_rejects_snapshot_when_solver_revision_races
~~~

实现验收时运行（现有入口，评审阶段不重跑 F7）：

~~~powershell
uv run python scripts/run_unittest_report.py --expect-count 25 --summary-json artifacts/<batch-id>/l1/summary.json --diagnostics artifacts/<batch-id>/l1/diagnostics.log tests.test_faithful_f6_presentation tests.test_s06_presentation
~~~

summary.json 保存 testsRun、failures/errors/skipped/expectedFailures/unexpectedSuccesses、elapsed、status、pid、start_time。配套记录必须保存固定 ID 清单、逐项状态、missing、源码 SHA、完整命令与机器报告 hash。现有入口不列全部成功 ID，不能只凭 testsRun=25 推定清单一致；F8 需对照固定 ID 并记录缺项。运行入口加载数量不符会拒绝执行，拒绝本身是失败证据，不能改选较小模块继续记通过。L1 表达回归不是形式化系统自身的 L1 等级。

### L2 形式目标与可判定分母

按 (group, policy, evidence_kind, target_scope, domain, environment_digest) 分组。target_scope 为 formal_target 或 original_problem，不能合并。sample/repetition 在派发前登记目标 ID/hash、规格版本与主核验身份；重试保留历史，不选择最好结果。

报告 N_registered、N_target_registered、N_decidable、N_pass、N_fail 和六状态计数。全登记主率为 N_pass/N_registered；另列形式目标子集率 N_pass/N_target_registered、可判定条件率 N_pass/N_decidable，以及目标覆盖 N_target_registered/N_registered。全部比率都标 scope 与分母名称，不能以子集率替换主率。分母为零时 value=null、status=not_available。decidable 仅含有实际可核验最终裁决的 pass/fail；工具 timeout、环境缺失、漂移和未执行不冒充已判数学错误。所有缺失保留在登记分母，不能因未生成目标而隐藏系统覆盖缺口；不适用形式化的样本明示 unsupported，而不是数学错误。

通过须有匹配目标、环境、公理审计与真实回执；sorryAx 或禁止公理拒绝通过。L2 只证形式目标；L3 还需原题与规格对应的独立证据。来源记录的 VERIFIED L3 与人工抽查的通过率分别展示，不互相替代或重复计数。

### L3 抽样及人工安排待确认

题集 hash、总样本数／每层数量、R1/R2 与裁决人尚未确定，用户正在安排。此项未冻结，整份协议继续 review_draft。准备清单位于 ignored artifacts/faithful-f8-inputs-20261111/准备清单.md，可在同目录安排.md 提供已有文件路径与安排；清单不是 manifest 或已完成评审。

待审规则：抽样框包含所有登记槽位及失败、unknown、不完整项，不限成功 L3。按 A–G、数学领域和声称等级／scope 分层，先固定层定义、各层 n、总 n、seed、短缺处置和适用范围。相同题跨组优先共同审查。具体规模依据题集及人力确定，不能事后重划层提高通过率。

计划确认后，各层按 SHA256(seed + ':' + sample_id + ':' + repetition) 字节序排序，sample_id/repetition 打破碰撞，取预登记数量，不替换无法判断项。若按运行状态分层，先冻结规则，结果封存后抽样，不能看人工判决后挑选。保存全部框 ID/hash、被抽 ID 与层，不只保存选中成功例。

R1/R2 初审互不可见，分别检查题意、定义域、量词、假设、规格方向、结论、证明完整性、引理依赖、工具支持范围、最终答案与讲解忠实性。各项判 pass/fail/unresolved，并记录理由及锚点。预登记人类裁决者处理分歧；未裁决保留 unresolved，不计通过。子代理的工程审查不能充当双人人工数学判断。

每份初审的总判定：全部适用必审项 pass 才为 pass；任何必审项 fail 则为 fail；无 fail 但任一必审项 unresolved 则为 unresolved。适用项由预登记 scope 决定，不能审查后改为不适用。两人总判定及逐项裁决相同才直接形成最终记录，任何分歧均进入裁决；裁决须给出逐争议项判决并依同规则汇总，未裁决不得投票取多数。每层以固定抽中数 n_h 为主分母，unresolved／未审保留；另列可判定条件率。不同抽样比例时仅报告分层率及各层 n_h/N_h；本版不汇总非等比例样本为总体数学通过率，不事后引入权重。原始汇总计数可列出，但标为样本描述，不外推抽样框。

记录字段：review_id、reviewer_alias、review_role、reviewed_at、frame_sha256、sample_id、group、repetition、run_id、output/artifact/paragraph ID（适用时）、answer_hash、target_hash、specification_version、source_revision、rubric_version、逐项 verdict、reason_code、evidence_refs。裁决另带两份初审 hash、争议点、最终 verdict、裁决者与日期。自动检查核对身份、来源、脱敏、完整性、分母和一致性，不生成缺失的人工数学 verdict。

### 官方重评分的实际缺口

BASELINE.json 指向独立源码 447a3a26b13141844bd1c529abd6f69d68db33a8；历史结果日期为 2026-10-11，correct/incorrect/invalid=88/12/0。2026-11-11 本次只读核验 11 文件 SHA256 全部匹配，未重新评分。入口为 user_agent.ReasoningAgent(client=...).solve(problem, metadata)。根入口、implementations、requirements.txt 和其中调用／token／时限常量字节保持稳定。

尚未核实官方题集 hash、评分脚本／平台可执行入口、标准答案受限位置、本批资源及环境。缺材料时 official_score.status=not_run、score_delta=null，baseline 仅引用历史结果。重评分另登记双方同题集、顺序／重复、metadata、环境和各自预算，不把 Harness 结果混进官方分数。

### 报告、证据包与最小示例

报告版本 faithful-f8-report-v1，必需字段为 batch_id、protocol_sha256、manifest_sha256、source_revision、evidence_layers、groups、l1、l2、l3、official_score、limitations。evidence_layers 必有 engineering、real_tool、provider_live、natural_problem、independent_math 五栏。每组必须有 parent、policy、capability_status、N_registered、六状态 counts、comparison_status/reasons、metrics、evidence_refs 与 limitations。

下例仅演示一个 not_run 槽位的统计，不代表登记了真实实验；完整报告必须含 A–G 全部组及上述必需字段。

~~~json
{"group":"faithful-A","N_registered":1,"counts":{"completed":0,"failed":0,"unknown":0,"incomplete":0,"unsupported":0,"not_run":1},"comparison_status":"not_available","metrics":{"accuracy":{"value":null,"status":"not_available","numerator":null,"denominator":1,"eligible_count":0}},"evidence_refs":[]}
~~~

包位于 artifacts/<batch-id>/，固定成员目录为 manifest.json、registration.json、configs/、records/、l1/、verification/、reviews/、api-browser/、failures/、gates/、report.json、report.md、integrity.json。未运行项须显式记 not_run 与原因；执行证据缺失时不能宣称验收。引用为包内相对路径与 hash，绑定 Run、来源版本和目标／答案／表达身份。受控 reason_code 与审定摘要替代任意模型文本。

integrity.json 列全部成员的相对路径、字节数、SHA256（自身除外）；先生成全部成员（含 report），再生成索引，最后以包外 export-receipt.json 保存索引 hash、protocol/manifest hash 与包身份。report 不含索引 hash，避免 report 与索引循环散列。拒绝绝对路径、穿越、软链接逃逸和未登记成员。公开包只含脱敏白名单投影，不直接压缩整个 artifacts。原题、隐藏答案、完整 prompt、raw／SQLite 与私密审查材料另存，不能混入可交付包。表达 rubric 待审为五项各 0–2：忠实于原答案、来源可追溯、推导覆盖、等级／限制准确、表达清晰；独立记录理由，未审查不填分。

### 实施接缝与退出条件（未解除开工门槛）

现有 campaigns/campaign_store 仅支持旧双臂配置和 Job 编排，不能直接当作 Faithful A–G。experiment_manifest/runner 可复用规范 JSON、hash、源身份与零派发预检，旧 model/retry/budget 限制不自动成为新协议。experiment_verification_reporting 的白名单未完整支持 F3 等级，不得把旧 formal unknown 当作 L2/L3。逐字段 schema 与最小显式 CLI 必须在冻结前确定，冻结后才实现；不添加求解、验证能力或 F7 写入口。

| 验收 | 公共入口／持久状态 | 必须可执行的断言与退出证据 |
| --- | --- | --- |
| F8-01 | 显式 Faithful CLI 注册／校验、冻结 manifest 回执 | schema/hash/源码/配置／题集一致；默认不启用；零模型／工具／F7 写请求；旧命名不变 |
| F8-02 | 组配置与完整登记表 | A–G 全保留，D 独立并发 policy，F 串行限制明示；缺失 unsupported/not_run，控制不成立 not_comparable |
| F8-03 | 只读 replay／导出与追加原结果 | 六状态与分母守恒；失败／unknown 不被重跑覆盖；漂移拒绝可比结论，单臂 unknown 保留 pair |
| F8-04 | 七组失败／unknown 工程证据 | 至少各一项：A provider unknown，B 最后支持撤销，C 重复 frontier，D 收尾不足，E sorryAx／漂移，F 单臂 unknown，G 解释依赖失效；映射真实生产者和来源，不冒充自然题失败率 |
| F8-05 | L1/L2/L3、独立评分和指标 | L1 固定 25 ID，L2 scope 分离；人工未审 not_run，自动核对不代判，缺评分源不输出正确率 |
| F8-06 | 脱敏报告及完整性索引 | 五类证据分栏、失败路径、机器报告、锚点完整；拒绝敏感字段和篡改，导出零额外调用 |
| F8-07 | 双轴审查、唯一冻结最终门禁 | 问题清零后冻结源码；42 skip 与实际报告逐项比对且不计通过；失败轮次保留，门禁期间零文件变动 |
| F8-08 | 验收记录、索引和 #154 | 公共入口／持久断言／证据逐项映射，源码 SHA／命令／机器报告／skip／复查／未验证范围齐全；冻结验收项全满足才关闭 |

冻结前剩余：L3 安排与计划、精确逐字段 schema／CLI 合同、协议双轴审查和问题修复。表格不表示功能已实现。F7 无故不重跑；F6 late-usage 若再现保留并诊断。长测试及 30 分钟本地静默检查遵循工程门禁和用户偏好，不用子代理持续轮询。

## v1.1.1 本轮冻结工程合同（替代上方待定安排）

### 登记与审查计划

本轮候选题集字节 SHA256 为 345b891e3c45f6a95a5b69107d294f7a2f61bd29843c5ba2a82b9c8cd4a0cd7f，14 个不同 ID，内部题面去重为 14 个。来源固定 commit 5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d；全部上游文件 SHA256 已匹配。题面是上游原文去尾部换行的投影，另计算 input_sha256，不把上游文件 hash 当模型输入 hash。领域与难度不作已校准声明，开发历史 unknown；只作为便利选取的试点，不称独立或代表性样本。参考解缺失不阻止登记，但禁止据此产生正确率。

登记 14 题 × 7 组 × 1 次=98 槽位；seed 固定为字符串 faithful-f8-pilot-20261111-v1，题目顺序按 ID 的 Unicode 码点升序，组顺序 A 至 G。唯一重复编号为 0。按 competition_id×answer_scope 划分五层（AIME2025/answer、HMMT2026/answer、Putnam2025/proof、IMO2025/proof、Apex2025/answer），领域未确认不用于抽样。每组选相同四题：AIME2025、HMMT2026、Putnam2025、IMO2025 各 1；各层按既定 SHA256(seed:sample_id:0) 排序取首项，共 28 槽。Apex 层抽取 0，明确未覆盖，不外推全框。没有候选的层不替补，保留 missing；不按运行结果改选。

R1/R2 继承当前模型，各自独立上下文，禁止互看初审，记录可确认模型身份；无法确认型号写 unknown。R3 在两份记录封存后核对分歧；它不是独立第三次采样。逐项审查和汇总规则沿用上文。无实际答案、目标或原题对应证据时 verdict=unresolved、reason=missing_artifact；不得为了填满 28 槽临时解题或凭题面评定系统答案。报告 model_assisted 单列，independent_math 保持 not_run。审查链路工程验收可以通过，数学通过数仍为 0；二者不能混称。

### 显式公共 CLI 与持久合同

入口为 uv run python -m showcase.faithful_eval，只有下列操作；不连接 provider，不创建求解 Job，不修改 F7 或旧 campaign API。需要真实求解时由既有 runner 另行生成公共证据，再按新实验合同登记，不在本切片新增执行器。

| 命令 | 输入与作用 | 成功与拒绝 |
| --- | --- | --- |
| register --manifest FILE --sha256 HASH --root DIR | 校验冻结 manifest、协议 hash、当前源码与 baseline；新建 DIR/batch_id/manifest.json、registration.json；98 槽默认 not_run，明确不支持的组合登记 unsupported | 只创建一次；目录已存在拒绝，不覆盖；源码非干净提交或身份不符拒绝 |
| record --batch DIR --record FILE | 导入白名单公共运行快照与指标，绑定 manifest 登记主键和来源；保存 records/<group>-<sample-hash>-<repetition>.json | 每槽只导入一次，旧文件不改写；失败或 unknown 也占槽。追加重试须独立批次，不以同槽覆盖 |
| replay --batch DIR | 校验所有登记、记录、hash、来源与分母，计算确定性报告并输出 JSON | 只读；无记录保留 not_run，漂移保留原执行状态并标 not_comparable；篡改非零退出 |
| export --batch DIR --output DIR | 重新只读校验，导出白名单证据包与 Markdown、integrity.json、包外回执 | 输出目录已存在拒绝；拒绝额外文件、软链接及 hash 不符，零模型／工具派发 |
| l1 --batch DIR | 使用本协议的 25 个精确测试 ID，复用 run_unittest_report.py 保存原始 summary/diagnostics 与源 SHA 侧录 | 只允许运行一次；25 项全部通过且无 skip/缺项才 pass；失败记录不覆盖 |
| review --batch DIR --review FILE | 外部子代理生成记录，由协调者导入 reviews/R1.json、R2.json、R3.json；导入、replay、export 均执行相同身份与hash校验 | 每角色只导入一次；R3须等两份初审，输入hash必须按R1/R2次序精确匹配；缺项、重复、缺artifact却pass或任意篡改均拒绝 |

reviews/ 为人工触发的子代理记录输入，replay 不发起代理。每份记录顶层为 schema_version=faithful-f8-review-v1、reviewer（R1/R2/R3）、model_id（可核实或 unknown）、manifest_sha256、entries。entries 每项含 group、sample_id、repetition、verdict（pass/fail/unresolved）、reason（受控标识）、snapshot_sha256（无答案为 null）。R1/R2 文件独立封存；R3 另有两个初审文件的 SHA256 列表 input_review_sha256，R1/R2 此字段为空列表。entry 集必须等于28抽中槽，缺一项拒绝，缺 artifact 只能 unresolved。R3 文件不能替代缺失初审或改变任何执行／数学等级；本轮没有答案，三份都必须全部 unresolved。导出附三份文件和 hash，报告仅标 model_assisted 审查链 complete，independent_math=not_run。

所有 JSON 拒绝重复键、NaN、未知字段、非法类型；对象以下列键集为准，必需键不得缺失。公共标识只允许字母数字及 ._:-/，路径字段不能由远端自由传入；sample_id 可含 /，落盘文件名用 ID hash。自由模型文本、题面、答案、prompt、凭证和隐藏推理不入公共登记与导出。hash 为小写 64 位 hex，revision 为小写 40 位 hex，整数不接受 bool，数值有限且非负。

例外必须明确：batch_id 为单段 [A-Za-z0-9][A-Za-z0-9_-]{0,79}，禁止点、斜线及目录穿越；注册解析后的批次路径必须位于 root 内。repetitions 为正整数，注册表完整生成 0..repetitions-1，本试点固定 1；seed 为非空字符串。resources.stop_rules 是无重复字符串数组，必须恰含 unknown、cancel、hard_limit、source_or_config_change、ledger_or_binding_defect；limits_status/tools_status 为 unknown/available/not_run。registration.json 顶层={schema_version,manifest_sha256,slots}，schema_version=faithful-f8-registration-v1；slot={group,sample_id,repetition,execution_status}，只可为 not_run 或 unsupported，依据组capability固定。replay无导入记录时继承登记状态，不把unsupported改not_run。

每个封存JSON旁置同名.sha256文本回执（原始文件字节hash）。replay/export核对manifest/registration、record、review、L1原始机器报告及诊断和侧录的全部回执，拒绝未登记文件；hash不是防恶意重签的密码学身份认证，只能证明包内一致性。协议文件hash不循环引用自身，在登记回执中保存；源码清单hash复用experiment_sources.source_identity，登记时写入本地source.json及其回执，replay当前源码变化单列not_comparable，不能回写旧身份。

manifest 顶层键：schema_version、protocol_version、protocol_sha256、batch_id、source_revision、baseline_sha256、dataset、model、prompt_sha256、seed、repetitions、environment、resources、groups。schema_version=faithful-f8-manifest-v1，protocol_version=faithful-f8-v1.1.1-engineering。dataset={sha256,samples}，每个 sample={id,input_sha256,source_sha256,source_ref,stratum,development_history,targets}，development_history=unknown/development/held_out；本试点全部 unknown。targets 恰含 A–G，值为 null 或 {target_sha256,scope,environment_sha256}，本试点全 null；model={provider,id,snapshot}，本轮无 provider 使用可登记 none/scripted/unknown，不将当前审查模型填成实际求解 provider。environment={identity_sha256,tools_status}，resources={identity_sha256,limits_status,stop_rules}，完整配置、环境和预算输入仅在本地私密冻结文件保存并以 hash 引用；public manifest 不携带原文。上述 hash 覆盖的实际文件在运行证据侧留存，缺文件不能升级真实实验为 executed。

groups 恰含 faithful-A 至 faithful-G，每项={parent,policy,capability_status,reason,config_sha256}。parent 为 null 或已登记组，禁止循环；policy 为实际 policy 身份，capability_status=available/unsupported，reason 为受控标识。可用不代表已执行。D 必须 concurrent-aprs-v1，C 必须 serial-aprs-v1；F 的本轮独立串行专项 policy 为 serial-intervention-v1，parent=faithful-C；对 E 的增量比较固定 not_comparable。E/G 的 parent 必须如实记录。注册表按清单笛卡尔积生成，禁止调用者传更小子集。组配置 hash 不同属于预登记干预差异，不能仅因此拒绝所有比较；实际 applied hash 必须与该组期望值一致。

record 键：schema_version、manifest_sha256、group、sample_id、repetition、execution_status、reason、run_id、source_revision、input_sha256、config_sha256、evidence_kind、snapshot_sha256、metrics、formal、pair。schema_version=faithful-f8-record-v1；execution_status 为六状态之一；evidence_kind=engineering/real_tool/provider_live/natural_problem。真实启动的 completed/failed/unknown/incomplete 必须有 run_id 及 snapshot hash。导入只表明材料已登记，不等于独立核验；证据层只能据有同源码、真实来源的验收报告升级，单条导入不把整个 layer 填 pass。config/input/source 与 manifest 不符保留记录并令 comparison_status=not_comparable，不能输出跨组提升。

metrics 固定键 accuracy、root_coverage、valid_evidence、route_efficiency、latency_ms、cost、cache_recheck、explanation_rubric。未观测用 null；本工程版本 accuracy 与 explanation_rubric 固定 null，独立／辅助判决另存，不接受模型自评分填正确率。可观测标量有限且非负；coverage 在 [0,1]。formal 为 null 或 {target_sha256,scope,grade,outcome,environment_sha256}，scope=formal_target/original_problem，grade=null/L2/L3，outcome=pass/fail/unknown/incomplete/unsupported/not_run；此为来源声明，不新增核验或提升等级；形式目标 scope 不能带 L3。F 的 pair 为 {id,checkpoint_sha256,control_status,intervention_status}，两臂状态六选一；其他组 pair=null。formal 目标分母包含已登记但缺失结果的槽位，目标／scope／环境须与 manifest targets 一致；未预登记目标导入拒绝。本试点 targets 全 null，后续目标实验须另登记批次，不改写本试点。

报告除上文统计外，每组额外明确前序比较与 parent 比较，未知指标记 not_available；F 单臂 unknown 保留完整 pair、可比较 pair 数另报。real_tool/provider_live/natural_problem/independent_math 未经独立来源验收均 not_run；模型辅助记录不得改变它们。L1 固定 ID 以本文件清单为唯一来源，清单 hash 随协议固定。工程见证由真实生产者合同测试产生，测试与原始机器报告保留，不将其虚构为竞赛题运行。

### 本轮退出范围

F8-01–08 为工程交付；L1 25 项必须实际通过，七组必要失败路径有生产者测试证据，98 槽登记、只读 replay／完整性导出、28 槽三代理辅助审查、双轴复查及最终唯一门禁均需实际执行。真人独立数学、真实 provider、自然题求解、官方重评分、广泛真实工具环境和数学效果明确 not_run，不因本轮工程通过关闭这些历史任务。若本轮工程全满足，可关闭 #154 的工程交付，保留 #130/#146/#156 和旧真实实验票状态；最终报告必须写明此范围由用户于 2026-11-11 明确修订，不能称原真人 L3 合同已满足。

冻结审查记录：Standards 解除路径隔离、精确schema/审查导入、登记状态继承三项；Spec 解除28槽审查导入与封存闭环。早期审查提出的循环散列、冻结时序、L2分母与分层汇总均已修复并复查。审查者继承当前所选模型，具体型号无法核实；仅审查协议，未运行测试。准备材料与源码核验见本地 artifacts/faithful-f8-inputs-20261111/ 和 artifacts/faithful-f8-protocol-review-20261111/，后续工程验收独立记录。

v1.1.1 实现前补充：baseline_sha256 绑定 BASELINE.json 原始字节；每题 source_sha256/source_ref 保留来源字节身份与不带查询串的固定来源引用（只接收可信本地映射的公开URL，不含题面）。这是schema补齐，无实验登记或实现启动；与v1.1共同接受原审查者定向复查。
