# MathAgent Faithful implement-spec 映射

状态：路线交接后的实施规格映射。本文不表示功能已经实现。

基准来源身份：`MathAgent_PRD_20261106.md` v0.2（2026-11-07），SHA-256 `666EAD9E6CB34D8AF72962A0E2F8BF13CE078848243E3A72A53524061C645622`；`MathAgent_Technical_Design_20261106.md`，SHA-256 `3711E42CE1AB0E6EA095747ECB00C29AEBF7D077D77C6E752A04A79CBFCDDC27`；《MathAgent 技术方案与总体架构设计报告》2026-11-05 修订版，原 PDF SHA-256 `370a37110d4104ff839daf3f08d933b004bc42d41868a7df15f6576cfa14091e`。文件名不作为修订日期的唯一依据。

决策依据：[确定 AND/OR 证明图与精准失效的迁移合同](https://github.com/RUSS0718/MathAgent/issues/139)、[确定多路线与 APRS 的收益、预算和比较规则](https://github.com/RUSS0718/MathAgent/issues/140)、[确定 Lean 适用范围与 L2/L3 发布标准](https://github.com/RUSS0718/MathAgent/issues/141)、[确定同源策略干预的隔离、比较与调度反馈](https://github.com/RUSS0718/MathAgent/issues/142)、[确定路线经验与形式化缓存的安全复用边界](https://github.com/RUSS0718/MathAgent/issues/143) 和 [冻结开发切片、发布门禁与路线交接](https://github.com/RUSS0718/MathAgent/issues/144)。

实现基线：PR 129 合并提交 `b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`。

## Problem Statement

PRD 第 13 节已经补齐技术报告中的功能要求，但这些要求仍需要映射到当前 Showcase 的公共入口、状态、事件、预算、验证、恢复和前端审阅接缝，才能进入 `implement-spec`。

当前仓库已经有 `POST /api/agent/jobs`、Job/Run 持久状态、SSE 事件、report、Evidence、候选答案、整题审查、配对实验和恢复基础。它还没有把三类关联图、CandidateRoute/APRS、同源动作干预、三层记忆、受限 Lean 闭环和证据驱动讲解组成一组可实施的产品合同。

本规格的目标是建立逐项可审查的映射。它不把现有代码、接口占位、离线结构测试或模型自报当成目标能力已经完成。

## Solution

沿用现有公共产品接缝：

```text
POST /api/agent/jobs
  → Job/Run 持久状态与事件账本
  → SSE 公开事件投影
  → report / Evidence 查询与导出
  → ChatWorkspace / RunReview / 实验审阅页
```

新增能力通过版本化的可选字段、事件和状态投影接入。Run 冻结 `schema_version`、`profile`、超时配置和 `policy_version`。旧 Run 保持旧语义，新能力默认关闭，官方 `user_agent.py`、`implementations/`、默认预算和官方评分路径不变。

Python Orchestrator、Rater、APRS、Specification Checker、MemoryManager 和 EffectEstimator 是内部控制组件，不要求实现成 LLM Agent。模型可以提出草稿、ProofAttempt、FailureHypothesis 或路线建议，但只有既有 Verifier/Controller、隔离工具和持久事务可以改变权威状态。

首版路线为串行主路线，主路线停滞后最多启用一条替代路线。完整并发 Population/APRS 保留为后续目标，不能由首版串行行为宣称已经覆盖。

### 现有接缝与明确缺口

| 现有来源 | 可复用能力 | 本规格仍需新增的合同 |
| --- | --- | --- |
| `showcase/flask_app.py`、`showcase/run_service.py`、`showcase/solver_harness/harness.py` | 公共 Job/Run 创建、查询、恢复和 SolverHarness 生命周期 | 新能力的显式 capability、版本化状态和兼容投影 |
| `showcase/solver_harness/storage.py`、`showcase/star_product_events.py` | SQLite 状态 CAS、状态/事件同事务提交、公开事件投影 | 三类图的实体、图版本、ID 关联和独立投影 |
| `showcase/solver_harness/candidates.py`、`best_effort.py` | AnswerCandidate 追加历史、有效性和硬预算下的纯候选选择 | CandidateRoute Population、路线谱系、Rater/APRS。现有答案候选不能冒充路线种群 |
| `showcase/solver_harness/paired.py`、`showcase/experiment_pair.py`、`experiment_pair_verification.py` | 独立 Run 配对、归档和独立复核 | 活动 Run 内同 checkpoint 的单动作双分支及其隔离/反馈合同 |
| `showcase/solver_harness/sessions.py`、`context_injection.py` | Run 内角色会话、作用域检查和当前状态视图 | Population Memory 与 Global Goal Cache 的跨 Run 适用性、复核和管理 |
| `showcase/solver_harness/verification.py`、`intern_port.py`、`star_result_semantics.py` | 结构化模型审查、受控工具证据和结果等级 | Lean Adapter、ProverBackend、Specification Checker 与内核级 L2 闭环 |
| `showcase/solver_harness/traceback.py`、`classified.py` | 计划/账本回退、依赖结果失效和救援 | Proposition/Inference 图上的 AND/OR 支撑计数及精确依赖闭包 |
| `showcase/solver_harness/final_binding.py`、`showcase/evidence.py` | 最终答案与整题审查绑定、报告和 Evidence 导出 | 逐段解释 claim refs、节点版本和 VerificationRecord 绑定 |
| `showcase/star_product_events.py`、ChatWorkspace、AgentTimeline、RunReview | 角色事件、时间线、Job 报告和审阅入口 | Proof、Route、Causal、Evidence 四个可展开的只读视图及深链 |

`showcase/graph.py` 存在，但它实现的是 LangGraph 执行调度器，不能当成 Proposition–Inference Proof Dependency Graph。现有 `/api/agent/jobs/<id>/report` 是运行报告查询，不等同于用户输入的 `/report` 表达模式；当前聊天组件也未发现 `/teach` 命令解析。

## User Stories

1. 作为数学任务用户，我希望从答案声明跳转到命题、推导、证据和来源 Run，以便知道答案依据什么。
2. 作为数学任务用户，我希望看到当前 `graph_version`、有效支持、冲突和失效原因，以便区分已验证内容与待重审内容。
3. 作为数学任务用户，我希望查看主路线、替代路线、父子谱系和路线切换原因，以便理解搜索过程。
4. 作为数学任务用户，我希望区分 CandidateRoute 和 AnswerCandidate，以便路线选择不会被误认为最终答案选择。
5. 作为数学任务用户，我希望看到 Rater/APRS 的公开评价维度、预算预留和停止原因，以便理解系统为什么继续或停止。
6. 作为数学任务用户，我希望失败假设明确标记为假设，而不是被显示成数学结论。
7. 作为研究人员，我希望从同一个 checkpoint 运行隔离的 control/variant 分支，以便比较单个求解动作。
8. 作为研究人员，我希望看到配对分母、unknown、未完成原因和不确定性，以便不把一次分支结果误读成稳定因果规律。
9. 作为用户，我希望 `/teach` 和 `/report` 的关键断言链接到 PropositionNode、InferenceNode 和 VerificationRecord，以便检查讲解来源。
10. 作为用户，我希望失效证据自动使相关讲解进入待重审状态，以便旧解释不会继续支撑当前答案。
11. 作为用户，我希望讲解新增的数学断言先进入验证流程，以便表达模式不会偷偷扩大答案结论。
12. 作为用户，我希望看到 Run Memory 中的 checkpoint、预算、证据和失效原因，以便恢复或结束任务。
13. 作为研究人员，我希望跨 Run 查看路线成功、失败和 unknown 观察，但不能把经验直接当成证明前提。
14. 作为用户，我希望形式化后端显示当前环境、验证等级和失败状态，以便区分 L0、L1、L2、L3 和 `LLM_REVIEWED`。
15. 作为用户，我希望形式化目标与原题条件不一致时拒绝 L3，但仍能读取普通答案和已有证据。
16. 作为用户，我希望局部失效只回退受影响的依赖闭包，以便独立有效结果继续可用。
17. 作为用户，我希望任务在进程重启后恢复同一 Run、预算和身份，以便不会重复接受或重复计账。
18. 作为用户，我希望资源耗尽时得到 Best-Effort 结果、未完成目标、验证等级、成本和来源身份，以便准确判断交付范围。
19. 作为评测人员，我希望固定题集、模型、Prompt、工具和预算运行 A–G 实验，以便比较策略机制。
20. 作为评委，我希望在系统视图中看到路线选择、干预过程、依赖关系和证据状态，同时看不到凭证、完整 Prompt 或隐藏推理。

## Implementation Decisions

### 公共接缝和状态边界

- 复用现有 Job 创建、Run 状态存储、事件追加、SSE 投影、report 和 Evidence 查询。
- 新状态使用增量版本字段。新字段缺失时，旧消费者按旧语义读取。
- 证明图、路线图和因果图使用独立实体与稳定 ID，通过引用关联，不使用一张无语义边表代替三类图。
- 每次合法图变更生成不可变 `graph_version`。状态只指向当前版本，历史版本保留审查。
- 所有新增事件必须经过同一 SQLite 事务写入状态和事件。非法图、非法引用、重复 ID、跨版本引用或版本冲突整次拒绝。
- 旧 Run 不自动生成证明图、路线图或因果图。启用证明图的新 Run 通过显式 `GraphBootstrap` 导入当前有效的非 `Conjecture` 账本记录。

### 最小实施切片

| 切片与依赖 | 入口和兼容 | 状态与产物 | 前端交互 | 失败行为 | 最小退出验收 |
| --- | --- | --- | --- | --- | --- |
| F1 图与 GraphBootstrap；映射 S07；前置 S03、S04 | 新 Run 的可选 capability；复用 SolverStateStore 和账本 | 不可变 `graph_version`、Proposition、Inference、ProofAttempt、`GraphBootstrap` 和未导入清单 | 查看命题、AND/OR 支撑、证据和失效 | 非法引用、循环、跨版本 ID 或无法映射账本记录不写入，不升级证据 | A/B/C、多个 OR 支持、精准撤销、循环/悬空拒绝、旧 Run 兼容 |
| F2 路线谱系与 APRS；映射 S08；前置 F1/S07 | Showcase 新 Run 显式启用；复用 planning/controller/best-effort，旧 Run 单路线 | CandidateRoute lineage、frontier、Rater 向量、Pareto 集、policy version、预算预留 | 查看主/替代路线、选择理由、成本和停止原因 | frontier 等价时拒绝重复路线；收尾预留不足时停止；不把 AnswerCandidate 当 Route | 主路线停滞才切换；最多一条替代路线；同一快照和 policy 下的评价、Pareto 集、预算裁决可 replay |
| F3 形式化后端；映射 S09；前置 F1/S07，可与 F2/S08 并行 | 显式形式化模式与受支持目标；复用 ToolRegistry 隔离边界 | ProofArtifact、Lean/Mathlib 环境、SpecificationRecord、后端 attempt lineage | 查看目标、环境、状态、等级和失败日志 | 不支持/不可用/timeout/error 保持 unknown 或对应失败；拒绝 sorryAx 和额外假设 | 固定环境的受限 L2 真实内核核验；L3 另过规格对应审查 |
| F4 受控干预；映射 S10；前置 F2/S08、F3/S09 | 显式实验入口；复用 campaign 和配对持久化 | FailureHypothesis、登记动作、冻结 checkpoint、control/variant、EffectEstimate | 查看假设、动作差异、两臂状态、结果与不确定性 | 源快照或配置不等、跨臂读写、unknown 插补均拒绝；父 Run 不自动采纳结果 | 单动作同源分支、对称父账本预算、完整 pair 分母和独立重审 |
| F5 三层记忆；映射 S10；前置 F2/S08、F3/S09 | 默认关闭的记忆管理入口；沿用用户/工作区隔离 | Run/Population/Goal Cache 记录、provenance、适用范围、复核、墓碑 | 查看来源、命中/拒绝原因、禁用、清理和跨域导入 | 失败/unknown 不成为证明或收益；失效缓存不直接复用；清理不删除权威账本 | 跨域拒绝、显式导入、版本变化 recheck、清理审计完整 |
| F6 证据驱动讲解；基础 `/teach`、`/report` 映射 S06，前置 S03、S05；图与 Lean 引用随 F1/F3 到位逐步启用 | 复用 final binding/Evidence；保留原答案和表达分离 | PresentationArtifact、段落 claim refs、验证等级、来源版本和新 ProofAttempt | 展开段落依据；切回原答案；查看待验证新断言 | 失效/不足证据触发重审；整理失败不影响原答案 | S06 先验收旧 Evidence/VerificationRecord 绑定；F1/F3 可用后验收图节点与形式化证据深链 |
| F7 统一系统视图；基础事件/UI 映射 S05，前置 S01、S03；Proof/Route/Causal/Evidence 视图随 F1–F6 逐步交付 | ChatWorkspace/RunReview 可选视图；复用公开事件白名单 | Proof、Route、Causal、Evidence 四类投影和深链 | 按义务、子智能体、时间线和证据层级切换 | 不完整或脱敏失败的事件不显示为成功状态 | 重连/刷新后身份一致；不泄漏 prompt/凭证；事件职责区分 |
| F8 研究评测；研究切片，覆盖 F1–F7，不对应新增 S 阶段 | 隔离实验配置入口；沿用 campaign/experiment runner；不支持的配置明确返回 `unsupported/not_run` | `faithful-A`–`faithful-G` manifest、完整分母、unknown、组别指标和导出报告 | 并列查看每组的机制差异、工程可运行性与数学效果 | 配置漂移、缺少样本身份或未完成分母时拒绝能力结论；不得静默降级成另一组 | A–G 逐组满足下方矩阵；固定控制变量、归档齐全；报告效果估计与不确定性 |

依赖按 #144 冻结：S01→S02→S03→S04；S05 在 S01、S03 后可与 S04 并行；S06 等 S03、S05；S07 等 S03、S04；S08 等 S07；S09 等 S07、可与 S08 并行；S10 等 S08、S09。F1–F8 是需求实现映射，不是新增总体阶段。S01–S06 的超时、上下文、义务、恢复和基础输出合同继续使用 #144 阶段门禁；F6 的图节点和 Lean 深链、F7 的完整图视图按各自数据生产者就绪后增量开放。

S08 首版只实现串行主路线与至多一条停滞后替代路线。完整并发 Population/APRS 是后续目标，必须在取得串行真实运行、规模和恢复证据后另行确定并发合同，不能由 F2 或 A–G 的串行结果宣称已实现。

### AC11–AC28 实施映射

#### Rater/APRS 的确定性合同

- **触发点：** 路线通过登记检查、出现新的已接受数学证据、当前动作结束或停滞、遇到失败/unknown、切换路线之前，以及搜索进入收尾阶段时重新评价。重复读取同一快照不重复派发模型请求。
- **输入：** 固定 `run_id`、`state_revision`、`graph_version`、`policy_version`、根义务状态、去重 `verified_gain`、独立证据质量、新颖性、可执行 frontier、路线 lineage、失败/unknown 观察、真实请求/token/工具/耗时/并发用量和父 Run 剩余资源。记忆命中只能作为带来源的辅助特征。
- **输出：** 每条路线的可复现向量、硬门槛结果、Pareto 集、固定字典序键、选择/淘汰理由、预算建议、收尾预留和停止原因；保存输入快照摘要与策略版本，供审计和 replay。
- **裁决顺序：** 先排除非法或前提已失效的路线，再按 Pareto 比较，继而按根义务进展、`verified_gain`、独立证据质量、新颖性、较低真实消耗作固定字典序裁决。按已确认的 S08 合同，当前运行时策略不使用 Elo，包括完全并列时；仍并列时以稳定 `route_id` 作技术性平局键。未来若要研究 Elo，必须作为独立、预登记的离线实验，不改变当前 Run 的裁决或数学状态。
- **预算：** 不设置人为费用上限。控制器按父 Run 实际剩余资源及 provider、账户、机器的真实约束运作，并先动态预留答案生成、整题审查和持久化资源；无法保障收尾时停止扩展路线。未知的 provider 上限保持 unknown，不填造数值。
- **状态边界：** Rater/APRS 只调度路线和分配资源；只有 Verifier/Controller 能原子接受数学证据。未知调用结果不触发自动新调用。离线校准生成新 `policy_version`，当前 Run 不在线改策略。

实现至少保留三类可序列化记录：

- `RaterInputSnapshot`：`run_id`、`state_revision`、`graph_version`、`route_id`、`frontier_digest`、根义务快照、去重 `verified_gain`、证据质量、新颖性、失败/unknown、实际资源、剩余资源、收尾预留和 `policy_version`。
- `RaterEvaluation`：各维度原始值与归一化值、方向、缺失值处理、硬门槛、支配关系、输入 hash 和评价版本。
- `APRSDecision`：候选路线集合、选中路线或停止动作、预算预留变化、裁决顺序、停止/切换原因、决策版本和输出 hash。

Rater 在同一状态提交事务内读取快照并写入评价。相同 `state_revision + graph_version + frontier_digest + policy_version` 幂等复用已有评价；旧评价返回后若状态版本已变化，Controller 拒绝其写入。路线状态至少区分 `created`、`eligible`、`active`、`stalled`、`completed`、`terminated` 和 `pruned`。`pruned` 路线不可直接重新激活，恢复必须创建新 lineage 并重新校验图版本、前沿和依赖。预算预留覆盖 provider 请求、输入/输出 token、工具调用、墙钟时间、并发槽位和持久化收尾；未知调用消耗保留，释放预留与路线裁决在同一事务中完成。

#### ProverBackend 选择合同

后端选择使用可审计规则，不依赖模型自评分。LLMProver 生成自然语言推导草稿或辅助引理；MathToolBackend 处理明确可计算的代数、枚举或数值目标；LeanTacticProver 只搜索已稳定 Lean Goal 的 tactic。Lean L2 仍须显式启用形式化模式、目标属于支持域、固定环境可用且资源允许。AlphaProof 只有在真实后端已部署并由当前配置启用时才可选。

仅当目标不受当前后端支持、得到可判定失败、验证覆盖不足且另一个已启用后端适用，或固定资源策略要求切换时才创建新 attempt。`unknown`、TIMEOUT、ERROR、provider 断流及环境不可用不能自动触发重试或伪造反例；用户显式重试或控制器已有明确非重复的新动作时，创建新 attempt 并链接原 lineage。切换保留每次 `ProofArtifact`、子目标、环境、状态和成本，不把任何后端产物自动升级为 L2/L3。

Backend Registry 至少保存后端 ID、支持目标类型白名单、可产生的最高验证等级、环境身份、输入/输出格式、确定性标记和不可用原因。每个目标先执行 L0 结构检查；普通模式不触发 L2/L3。MathToolBackend 的受控回执最高只能形成声明范围内的 L1，LLMProver 只能形成草稿或 `LLM_REVIEWED`，LeanTacticProver 通过隔离内核后才可产生指定目标的 L2。L3 还必须由 Specification Checker 审核原题→ProblemSpec、ProblemSpec→形式目标、形式目标→固定环境三层记录，并检查定义域、量词、假设、结论方向、等号条件和额外公理。前端交付分别显示“结构已检查”“指定范围已验证”“形式目标已验证”和“原题对应已审查”，不能用后端成功或编译成功替代更高等级。

#### FailureHypothesis 与 EffectEstimate

`FailureHypothesis` 至少记录假设 ID、来源 Checkpoint/`state_revision`、受影响根义务与命题、失败症状、诊断证据、候选 Proof-Action、优先级、反证条件及假设状态。原因分类固定包含方法不适配、引理结构不合理、拆解粒度不当、顺序低效和前提使用不充分；传输错误与 `unknown` 单独记录，不能冒充数学失败。动作按义务相关性、预期可验证进展、区分假设的能力、真实成本和对有效证据的风险，以固定策略排序。一个 pair 只允许执行一个登记动作差异。

`EffectEstimate` 绑定干预 ID、源 Checkpoint、两臂身份、预登记主指标、两臂结果、配对差异、可判定样本数、未完成分母、资源成本及预登记的不确定性区间算法。只有两臂均可判定时才计算配对差异；unknown 不插补。样本不足、缺失不对称或区间方法未预登记时只允许描述当前样本，不得称为因果结论或总体收益。被接受的配对观察只能进入版本化离线统计；APRS 使用这些统计必须经离线校准生成新 `policy_version`，不得在线更新当前 Run。

#### 图失效传播与路线停止

撤销一个证明支持后，Proposition 的状态由当前有效支持重新计算；同一命题仍有独立 OR 支持时保持有效，撤销最后一条支持才使其及 AND/OR 依赖闭包进入 `invalidated`。独立核验的反例才可标 `refuted`；有效支持与反例并存时标记 `conflict`，不作为下游前提。依赖变化使相关 CandidateRoute 标记为需重评并保留旧版本；Proof-Action 统计只标记为待复核，不反向改写数学命题。

Backward Planner 在根目标已满足、无可达 frontier、重复 frontier、达到已配置拆解边界、收尾预留不足、主/替代路线停滞或 Run 硬截止时停止扩展。停止原因写入路线事件；已有成果继续进入独立 AnswerCandidate 选择和 Best-Effort 交付。

| AC | 功能目标与触发条件 | 现有复用点 | 新增内部状态/事件 | 用户交互 | 失败行为与验收 |
| --- | --- | --- | --- | --- | --- |
| AC11 | 新 Run 启用证明图、路线图或干预记录时，三类图可独立查询并互链 | `storage.py`、`star_product_events.py`、`RunReview` | `graph_version`、`proposition_id`、`route_id`、`checkpoint_id`、`proof_attempt_id`、`intervention_id` | 从答案声明进入命题、路线和干预详情 | 图边界不可混写；独立查询、ID 互链、旧快照可审查 |
| AC12 | 新 Run 启用证明图时执行 `GraphBootstrap` | `verified_results_ledger`、`SolverStateStore` | `graph_bootstrap`、`not_imported_records`、来源等级和来源 ID | 查看导入清单和未导入原因 | 无法完整映射的记录不导入、不升级、不改变旧 Run；事务测试覆盖非法导入 |
| AC13 | Planner 创建、切换或淘汰路线时登记 Search Lineage | `planning.py`、`replan.py`、`candidates.py` | `CandidateRoute`、父子 lineage、frontier digest、变异/停止/淘汰原因 | 路线树、主路线、替代路线和切换原因 | 停滞后最多一条替代路线；相同 frontier 不重复；路线可恢复和可审查 |
| AC14 | 路线登记、有效证据提交、停滞和收尾前触发 Rater/APRS | `best_effort.py` 的确定性选择、`run_budget.py` | `rater_vector`、`pareto_set`、`policy_version`、预算预留和裁决理由 | 显示路线为何胜出或停止 | 非法路线先排除；Pareto/字典序可重放；收尾预留不足停止扩展；不把成本或 LLM 自评当验证收益 |
| AC15 | 路线搜索结束或根义务满足后选择答案 | `candidates.py`、`final_binding.py`、`best_effort.py` | 独立 `AnswerCandidate` 选择记录、当前图/义务/证据引用 | 分开显示路线选择和答案候选选择 | 路线不自动选答案；答案重新通过义务、证据和整题审查 |
| AC16 | 停滞、重复动作、明确验证失败或依赖失效时登记失败假设 | `meta.py`、`failure_records`、`traceback.py` | `FailureHypothesis`、原因分类、候选动作、优先级、反证条件、状态 | 显示“可能原因”，支持查看、暂停和登记实验建议 | 普通失败、传输错误和 unknown 不自动成为因果结论；缺结构化证据不得进入干预队列 |
| AC17 | 干预登记后从同一 checkpoint 分叉 control/variant | `paired.py`、`experiment_pair.py`、`run_budget.py` | `ProofAction`、冻结快照 hash、branch ID、随机种子和对称预留 | 显示两臂配置、隔离和启动顺序 | 只改变一个动作；父账本匹配；两臂独立写入；配置或 checkpoint 不匹配整对拒绝 |
| AC18 | 两臂完成或终止时生成配对结果 | `experiment_pair_verification.py`、campaign report | pair 状态、unknown/incomplete、`EffectEstimate`、反馈版本 | 显示差异、不确定性和未完成原因 | unknown 留在分母、不插补；父 Run 回原 checkpoint；统计不能在线改 policy |
| AC19 | `/teach` 或 `/report` 生成解释且有答案/图/验证记录 | `evidence.py`、`final_binding.py`、report API | 段落版本、claim refs、节点/记录/artifact refs、生成版本 | 段落展开依据、等级、来源路线和有效性 | 关键断言无来源则拒绝或标待验证；图/证据版本变化使讲解需重审 |
| AC20 | 讲解失效、超时、断流或新增数学断言 | `presentation` 结果边界、`final_binding.py` | `ExplanationClaim`、PresentationArtifact 状态和新 ProofAttempt | 可切回原答案；新增内容显示待验证 | 样式失败不覆盖原答案；新增断言未验证不能进入 Verified Claims 或提高答案等级 |
| AC21 | 跨 Run 查询路线经验或命中记忆 | `sessions.py`、Run 状态、campaign 归档 | Run/Population Memory 记录来源、状态、适用条件和注入结果 | 查看来源 Run、状态、注入/拒绝原因并关闭经验注入 | 成功、失败、unknown 都保留；失败/unknown 不进收益或证明前提；跨域默认隔离 |
| AC22 | 形式目标缓存命中、环境或依赖变化、用户禁用/清理 | `storage.py`、身份边界、验证结果 | Global Goal Cache key、recheck、stale/invalidated、墓碑事件 | 查看环境、等级、复核和清理记录 | 仅 L2+ 内核审计可写入；当前环境复核；L2 不升级 L3；清理不删权威账本 |
| AC23 | 目标进入验证或已知状态表明需切换到适用的替代后端 | `verification.py`、`intern_port.py`、`tool_policy.py`、result semantics | `ProofArtifact`、backend、attempt lineage、环境和状态 | 显示后端、选择/切换原因、等级和成本 | 自然语言推导草稿或辅助引理选 LLMProver；明确可计算的代数、枚举或数值目标选 MathToolBackend；已有 Lean Goal 的 tactic 搜索选 LeanTacticProver；AlphaProof 仅在后端实际可用且配置允许时启用。TIMEOUT/ERROR/unsupported/unavailable 不通过；unknown 不自动触发新调用；每次明确切换创建新 attempt 并保留 lineage |
| AC24 | 形式目标与原题 ProblemSpec 需要对应审查 | 现有最终绑定和验证范围 | 三层 `SpecificationRecord`、hash、assumption refs、review status | 显示“形式目标通过，原题对应待复核”或 L3 通过 | 定义域、量词、方向、额外假设不一致拒绝 L3；普通答案仍可交付 |
| AC25 | 命题、依赖、验证记录或规格版本失效，或恢复/回退 | `traceback.py`、`storage.py`、`run_checkpoints.py`、recovery | 依赖闭包、局部状态版本和恢复来源 | 显示回退目标、保留结果和原因 | A 失效只影响 A 及下游；不复活失效证据；恢复不重置预算、不重复接受 |
| AC26 | 硬截止、资源耗尽、路线停止或部分完成 | `best_effort.py`、`evidence.py`、`final_binding.py` | FinalArtifact、ProofStatus、Verified Claims、Unresolved Goals、成本和来源身份 | 显示已验证内容、未完成目标、验证等级、成本和路线身份 | 部分答案不能标完成；字段必须来自同一 Run 快照；无合格候选时明确未完成 |
| AC27 | 研究人员启用 A–G 实验入口 | `campaigns.py`、`campaign_store.py`、experiment runner/verification | 固定 manifest、数据与配置版本、随机种子、执行顺序、完整分母、unknown、逐组指标和报告 | 实验页按 A–G 并列展示机制差异、工程证据和数学能力证据 | 同模型/provider、题目版本、Prompt、工具/验证环境及资源条件；逐组指标、样本身份、失败和 unknown 可追溯；单次运行不能宣称能力提升；官方路径隔离 |
| AC28 | 用户打开系统视图或 Run 审阅页 | `star_product_events.py`、ChatWorkspace、AgentTimeline、RunReview | 四类只读投影：Proof、Route、Causal、Evidence | 可展开依赖、路线选择、干预、证据、缓存和失效状态 | 只展示持久化脱敏摘要；不泄露 Prompt、凭证或隐藏推理；模型提出、Verifier 接受、Controller 调度、研究观察分事件显示 |

### 验收合同

每个切片先通过离线工程合同，再单独记录真实工具、provider、Lean、自然题和数学效果证据。离线通过只说明机制可运行。

#### F1 图与 GraphBootstrap

- 失败用例：A/B 独立、C 依赖 A；撤销 A 后 B 保留；A 的最后有效支持撤销后 C 失效；悬空引用、循环、重复 ID、跨版本引用被整次拒绝。
- 验收产物：状态快照、事件序列、图版本、GraphBootstrap 映射和未导入清单。
- 最低证据：SQLite 事务测试、重启读取测试、旧 Run 兼容测试。

#### F2 路线谱系与 APRS

- 失败用例：同 frontier 重复创建、改名刷收益、无关引理刷收益、收尾预留不足仍扩展、主路线未停滞提前派发替代路线。
- 验收产物：路线树、Rater 向量、Pareto 集、policy version、预算账本和停止理由。
- 最低证据：确定性 replay；自然题和 provider 结果另行报告。

#### F3 形式化后端

- 失败用例：额外假设、错误目标、`sorryAx`、未登记公理、环境漂移、timeout、ERROR、部分通过。
- 验收产物：源码、日志、环境身份、证明项、三层 SpecificationRecord 和 attempt lineage。
- 最低证据：隔离 ProverBackend 的固定模板 L2；L3 必须增加独立对应审查。无可用 Lean 时状态为 `disabled` 或 `unknown`。

#### F4 受控干预

- 失败用例：control/variant checkpoint 不同、改变多个动作、跨臂读写、单臂 unknown 被计为失败、父 Run 吸收未经重审证据。
- 验收产物：pair manifest、随机顺序、两臂账本、未完成状态、EffectEstimate 和反馈版本。
- 最低证据：受控故障和同源双分支；单对结果只能作为本源状态观察。

#### F5 三层记忆

- 失败用例：失败经验变成证明前提、unknown 增加 verified_gain、跨用户自动命中、目标变化后继续使用旧形式证明、清理删除权威账本。
- 验收产物：三层记录、来源身份、recheck 结果、stale/invalidated 状态和墓碑事件。
- 最低证据：作用域隔离、版本失效、显式导入和用户管理测试。

#### F6 证据驱动讲解

- 失败用例：关键段落无来源、来源已失效仍显示当前结论、L2 显示为原题 L3、讲解新增断言直接进入已证账本、整理失败覆盖原答案。
- 验收产物：解释段落版本、claim refs、PresentationArtifact、验证等级和重审原因。
- 最低证据：绑定、失效和失败回退测试；讲解质量属于独立研究指标。

#### F7 系统视图

- 失败用例：SSE 重复或刷新后视图串 Run、未持久化的模型内容出现在视图、完整 Prompt/凭证泄漏、事件类型混淆。
- 验收产物：四类公开投影、深链、脱敏事件和浏览器截图/检查记录。
- 最低证据：前端 DTO、SSE 重连、浏览器多状态检查。

#### F8 研究评测

- 失败用例：配置漂移、随机顺序缺失、未完成 pair 被删除、unknown 被插补、实验入口改变官方调用、工程可运行性被写成能力提升。
- 验收产物：冻结 manifest、完整分母、运行归档、指标表和证据边界说明。
- 最低证据：离线 replay 和报告导出；provider-live 与数学效果需要独立批次。

| 组别 | 仅增加的机制 | 验收比较与最低报告指标 |
| --- | --- | --- |
| A | 统一 Intern-S2 适配的 Solver Harness 基线 | 独立答案正确性、根义务完成、有效验证证据数、请求/token/工具/时间、unknown 与失败。 |
| B | A + Proof Dependency Graph | 义务覆盖、有效支持、局部失效传播正确性、冲突/反例识别、恢复后的重复接受数。 |
| C | B + Backward Multi-route Planner | 有效验证进展、重复搜索比例、停滞出口、路线切换、frontier 覆盖及单位资源进展。 |
| D | C + Population/Rater/Pareto/APRS | 根义务完成、裁决 replay 一致性、Pareto/硬门槛结果、收尾预留遵守率、真实消耗及 AnswerCandidate 独立审查率。 |
| E | D + Adaptive Lean Verification | L2 目标与关键子目标通过率、完整形式化率、规格一致性、后端切换/失败状态及环境复核结果。 |
| F | E + Causal Diagnosis/Intervention | 完整 pair 数与登记分母、根义务和有效证据增量差异、单位资源进展、EffectEstimate、不确定性及 unknown/incomplete。 |
| G | 完整系统 + Memory + Explanation | 缓存复核率及 stale/invalidated 率、跨域拒绝率、claim provenance 完整率、解释逻辑一致性、清晰度/可学习性和原答案保留率。 |

#### A–G 实验执行合同

Faithful 消融使用 `faithful-A` 至 `faithful-G` 命名空间，与仓库既有架构实验的 A–D 命名分开。每组 manifest 至少包含实验组、父配置 hash、源码 SHA、启用能力、模型/provider、Prompt 版本、题集版本/hash、随机种子、执行顺序、重复次数、请求/token/工具/Lean/墙钟资源限制、停止规则和验证环境。每个样本保存 `sample_id`、配置 hash、完整状态、完成/unknown/incomplete/not_run/unavailable/invalid_config 状态和原因。

每组都固定题目与题目版本、模型/provider、Prompt、工具权限、验证环境和可比资源条件。A–G 是累积配置，每组与前一组对照；若某组所需能力未实现，实验结果为 `unsupported` 或 `not_run`，不能静默降级为另一组。现有配对 Runner 只能在 manifest 明确声明支持的干预组中复用，不能自动充当完整 A–G 执行器。

指标按以下合同计算：答案正确率的分子是独立评分为正确的完整样本，分母是已启动且有独立评分结果的样本，并另报未完成分母；完整证明成功率要求该样本全部根义务通过并完成整题审查；Lean 通过率以“进入支持域且 ProverBackend 实际执行”的形式化目标为分母，并另报 unsupported/unavailable；有效验证进展按当前图版本中新产生、去重且被 Verifier/Controller 接受的证据计数，并同时按请求、token 和墙钟归一化；路线搜索效率至少报告每个已接受有效证据对应的请求/token/时间、重复 frontier 比例和停滞后切换比例；解释质量使用预登记 rubric 和独立评审者，不能用生成长度或单次模型自评分数代替。

工程指标来自状态、事件、预算和恢复账本，包括状态机通过率、恢复成功率、配置一致性、事件完整性、unknown 保留率和资源计量完整率。数学指标来自官方评分回执、独立盲评、隔离内核回执或预登记的独立评审，包括答案正确率、根义务完成、独立验证进展、完整证明成功率、Lean 通过率、规格一致性和解释质量。仓库没有题集或答案库时，不能自行生成正确性分数；缺少独立评分来源时标为 `not_available`。

每组至少有一个最小失败场景：A 保留 provider unknown；B 撤销最后支撑并传播失效；C 拒绝重复 frontier；D 收尾预留不足时停止扩展；E `sorryAx` 或环境漂移拒绝 L2；F 单臂 unknown 保留为 incomplete；G 失效证据使解释进入待重审。工程证据和数学证据分栏导出。任一控制变量、样本身份或分母不匹配时结果标记为不可比较；单组工程门禁只证明机制可运行，不证明数学能力提升。

### 与 S01–S10 的映射

| S 切片 | 本规格承接 | 关键入口 | 退出证据 |
| --- | --- | --- | --- |
| S01 | 原有超时、错误、幂等和恢复 | Job 创建、transport、budget | 虚拟时钟和同 key 恢复 |
| S02 | 原有 ContextPack 和容量合同 | context injection、session | 出站 payload、摘要失败和来源追溯 |
| S03 | 义务、ProblemSpec、WorkUnit、FinalArtifact | initial state、planning、verification、finalize | 多要求题和收尾合同 |
| S04 | 停滞、回退、重规划 | controller、meta、replan | 有界停滞和重复动作出口 |
| S05 | F7 公开投影 | events、projection、ChatWorkspace、RunReview | SSE/浏览器和真实进度 |
| S06 | F6 讲解和独立输出绑定 | Composer/API、presentation、final binding | 原答案与样式分离、失败回退 |
| S07 | F1 证明图 | classified、traceback、storage、graph state | AND/OR、GraphBootstrap、精准失效 |
| S08 | F2 路线和 APRS | planning、controller、routes、APRS | 串行主/替代路线、收益去重和预算停止 |
| S09 | F3 形式化后端 | ToolRegistry、Lean Adapter、verification | L2 闭环；L3 对应审查独立记录 |
| S10 | F4、F5、F8 | paired、intervention、memory、experiment | 同源配对、记忆复核、固定评测 |

## Testing Decisions

测试只验证外部行为和公开产物。测试不能依赖模型隐藏推理，也不能用调用次数、输出长度或单次 LLM 评分代替数学验证。

- 状态与事件使用现有 `SolverStateStore`、CAS、事件账本和 SQLite 事务 seam。
- Job、SSE、report 和 Evidence 使用现有 Flask 公共接口 seam。
- 路线、图、记忆和干预优先在控制器的最高可观察 seam 测试，不复制第二套求解循环。
- 失败、恢复、unknown、超时和进程退出使用虚拟时钟、受控 provider、回放或故障注入。
- 前端使用现有 DTO/store、ChatWorkspace、AgentTimeline 和 RunReview seam，并用浏览器检查重连、刷新、长产物和视图隔离。
- F3 的 L2 只有隔离 ProverBackend 真实编译并通过内核检查后才能通过；普通模型复核不能代替。
- A–G 实验使用固定 manifest、同题同模型同工具同预算和完整分母。实验报告同时列工程证据与数学能力证据。
- 运行全仓合同时使用仓库规定的 `uv run` 入口。文档映射本身不触发 provider、Lean 或自然题实验。

## Out of Scope

- 修改官方 `user_agent.py`、`implementations/`、默认预算或官方评分路径。
- 在本规格中实现产品代码、真实付费 provider 实验、通用自动形式化或 AlphaProof 占位接入。
- 首版实现完整并发 Population/APRS。它保留为串行首版之后的独立目标。
- 让 Rater、APRS、MemoryManager、Specification Checker 或 EffectEstimator 成为 LLM Agent。
- 把离线测试、原型、单次配对、模型自评或接口存在写成数学能力提升。
- 把 `LLM_REVIEWED`、L1、L2 或局部工具回执自动升级为原题 L3。

## Further Notes

后续实施票按 F1–F8 拆分，但必须遵守 #144 已冻结的 S01–S10 依赖和阶段门禁。实施票应分别写明入口、开关、旧 Run 兼容、失败用例、离线门禁、真实隔离工具验收、自然 provider 验收和数学效果证据。

若固定环境、Lean、缓存、配对执行或自然 provider 在 2026-11-10 前不能稳定运行，交付应保留 `unavailable`、`not_verified` 或 `incomplete`，并附阻塞原因和原答案。该状态是可审查交付，不是能力完成声明。
