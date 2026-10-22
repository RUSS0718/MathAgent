# STAR Core：编码 Agent 可执行实施规格

> spec_id: STAR-CORE-PRD　spec_version: 1.2-best-effort　date: 2026-10-22  
> status: SPEC_ONLY_NOT_IMPLEMENTED  
> human_prd: [`STAR_CORE_PRD_HUMAN_v1_2.md`](STAR_CORE_PRD_HUMAN_v1_2.md)  
> deployment_scope: MathAgent 独立实验侧车。禁止未经独立验收修改官方 `user_agent.py` 路径。

> 审计修订：v1.1 与人类版共享 SC-001..SC-043、AC-01..AC-44。新增范围的完整来源矩阵见 [`STAR_CORE_COMPONENT_AUDIT.md`](STAR_CORE_COMPONENT_AUDIT_v1_1.md)。本文件是待执行合同，不意味着已经实现。  
> 本轮对论文与官方主要源码路径进行了交叉审阅，但未锁定远程 commit 做逐函数覆盖和实际端到端复现；不得宣称已证明 STAR 无遗漏。

## 0. 执行合同

### 0.1 目标

实现完整的 **STAR-inspired Core**：确定性状态机管理 Reasoner、Verifier、Meta-Strategist，支持探索提前解题、正式规划、按步推理、分级验证、连续 Challenge、定点 Trace-Back、Meta 裁定的 Re-plan、跨尝试持久化、整题审查、可恢复状态与审计日志。

**定义**：这里的“完整”指本文列出的行为协议完整实现。不得声称复现 STAR 原论文成绩、Copilot CLI 的所有内部能力或数学形式化正确性。

### 0.2 指令优先级与来源

1. 遵守本地仓库当前的 `AGENTS.md`、正式比赛要求及安全规则。
2. 以 `STAR_CORE_PRD_HUMAN_v1_2.md` 与本文件共享的 `SC-001..SC-038` 为验收合同。
3. 阅读 STAR 论文及固定 commit 的官方源码，并在实现说明中标记 `[论文]`、`[官方代码]` 与 `[本项目]`。
4. 两份 PRD 不一致时，**停止该需求的实现**，在实施日志中记录冲突。不要猜测用户偏好。其他无冲突的切片可以继续。
5. 用户的本次任务是**提供规格**。不要把本文件视为已实施结果。

### 0.3 范围

**MUST implement**：`SC-001` 至 `SC-038` 中的完整 STAR Core 功能与验收。`SC-039` 至 `SC-043` 是本项目 Best-Effort 扩展，独立开关和单独验收；不得将扩展误称为 STAR 原生机制。

**MUST NOT implement in this phase**：Danus 全量 Fact Graph、SHEAF Lean 依赖图、OSVerify 的二次错误验证、Moonshine 猜想生命周期、PackingStar 专用搜索、完整 Lean MCP、模型训练、双向搜索树交汇。未来扩展必须走单独 feature flag。

**MUST preserve**：当前官方 `user_agent.ReasoningAgent`、`implementations/`、默认请求预算及既有评测 Runner 的行为，除非用户给出新的集成决策并提供独立回归证据。

### 0.4 工作方式

执行每一切片：**先读取仓库及现有实现 → 写失败测试 → 实现最小完整纵切 → 执行聚焦测试 → 执行相关全量测试 → 审查 diff → 记录验收**。不以“代码已写”代替验收。未安装某项依赖时保留跳过证据，不得把跳过标记为通过。

## 1. 需求索引与所有权

| ID | 要求 | 推荐模块 | 核心验收 |
| --- | --- | --- | --- |
| SC-001 | 隔离实验入口和官方合同 | `api.py`, `cli.py` | AC-18 |
| SC-002 | 确定性状态机 | `orchestrator.py` | AC-04, AC-08 |
| SC-003 | Exploration 与提前成功路径 | `phases/explore.py` | AC-01..03 |
| SC-004 | 可选预计划 Meta 与用户 Hint | `phases/preplan.py` | AC-03, AC-20 |
| SC-005 | 计划生成、结构验证、版本化 | `phases/plan.py` | AC-04, AC-11 |
| SC-006 | 逐步 Reasoner | `phases/step.py` | AC-05, AC-07 |
| SC-007 | 三类验证标签和证据 | `evidence.py` | AC-06 |
| SC-008 | 两 Gate 与四类 Verifier 裁决 | `phases/verify.py` | AC-05, AC-10 |
| SC-009 | 有界且连续的 Challenge | `phases/challenge.py` | AC-07..08 |
| SC-010 | Trace-Back、归档、救援结论 | `phases/traceback.py` | AC-09..10 |
| SC-011 | 持久化 Meta 裁决 | `phases/meta.py` | AC-11..12 |
| SC-012 | Re-plan 与 forbidden directions | `phases/replan.py` | AC-11..12 |
| SC-013 | 最终生成及整题审查 | `phases/finalize.py` | AC-01, AC-13 |
| SC-014 | 七种按需 Skill | `skills/` | AC-05, AC-19 |
| SC-015 | 角色会话和状态视图 | `sessions.py`, `views.py` | AC-07, AC-12 |
| SC-016 | 快照、事件与可靠恢复 | `state.py`, `storage.py` | AC-09, AC-15 |
| SC-017 | 本地工具及权限 | `tools.py`, `sandbox.py` | AC-06, AC-19 |
| SC-018 | 预算、循环与超时 | `budget.py`, `config.py` | AC-08, AC-16 |
| SC-019 | 模型适配与真实用量 | `model_adapter.py` | AC-16, AC-20 |
| SC-020 | 错误分类与有界恢复 | `errors.py` | AC-10, AC-14 |
| SC-021 | 输出 JSON 合同 | `api.py`, `result.py` | AC-13, AC-16 |
| SC-022 | Feature Flags 和 Profile | `config.py` | AC-17 |
| SC-023 | 脱敏 Trace 与事件审计 | `telemetry.py` | AC-15, AC-20 |
| SC-024 | 33 个端到端验收用例 | `tests/` | AC-01..33 |
| SC-025 | 分阶段提交及发布边界 | repo 检查、文档 | AC-18 |
| SC-026 | 配对实验与成本统计 | 实验适配器 | AC-20 |
| SC-027 | 接受结论不等于形式化定理 | `evidence.py`, `result.py` | AC-06, AC-13 |
| SC-028 | 四层记忆与正负账本契约 | `memory.py`, `state.py` | AC-21, AC-28, AC-29 |
| SC-029 | sessionStart/resume 状态注入与视图新鲜度 | `context_injection.py` | AC-22, AC-28 |
| SC-030 | Session ID 注册/隔离与跨进程重建 | `sessions.py` | AC-23 |
| SC-031 | Meta 诊断与行动指令协议 | `phases/meta.py`, `meta_actions.py` | AC-24 |
| SC-032 | Meta 强制纯推理和运行时工具禁用 | `tools.py`, `phases/step.py` | AC-25 |
| SC-033 | 后重规划的 Meta 协调再探索/子任务 | `phases/reexplore.py` | AC-26, AC-33 |
| SC-034 | `easy-verify` 自动预检和证据回执 | `phases/verify.py`, `sandbox.py` | AC-27 |
| SC-035 | 正负账本同步及可救援证据与猜想隔离 | `memory.py`, `phases/traceback.py`, `phases/replan.py` | AC-28, AC-29 |
| SC-036 | 整题审核角色差异的显式合同 | `phases/finalize.py` | AC-30 |
| SC-037 | 三层 Prompt/Skill/状态组合和权限 | `prompts.py`, `skills/`, `context_injection.py` | AC-31 |
| SC-038 | 流式部分输出、Meta 恢复和幂等记账 | `agent_runner.py`, `storage.py` | AC-32, AC-33 |
| SC-039 | 候选登记、溯源与依赖失效 | `candidates.py` | AC-34..36 |
| SC-040 | 预算耗尽时无模型调用的最佳候选选择 | `best_effort.py`, `budget.py` | AC-37..39 |
| SC-041 | 定性证据等级与可追溯理由 | `confidence.py`, `evidence.py` | AC-39..40, AC-44 |
| SC-042 | 比赛输出隔离和内部结构化结果 | `result.py`, `official_adapter.py` | AC-38, AC-41 |
| SC-043 | 候选回放、计费与在途请求审计 | `storage.py`, `telemetry.py` | AC-42..43 |

以上文件路径是**建议模块归属**，不是断言现有仓库已有这些文件。实际创建之前检查已有 `harness_lab/` 与测试目录，避免重名或覆盖。

## 2. 初始化仓库与保持官方边界（SC-001, SC-025）

1. 读取 `AGENTS.md`、`docs/README.md`、`BASELINE.json`、已有 `harness_lab`、评测 Runner 和现有测试。
2. 保存官方边界文件的 SHA-256。必须至少包括 `user_agent.py`、`implementations/` 下当前文件、官方配置和预算入口。
3. 记录 STAR 官方仓库固定 commit。不要仅以可漂移的 `main` 作为复现来源。
4. 将所有新增代码放入显式导入的实验包。允许扩展现有 `harness_lab`，但先测试已有功能；不得直接替换上一版公开对外合同。
5. 运行一次原生离线回归并存档结果。只有在隔离边界成立后，才允许实现具体阶段。
6. 将运行产物放到被 Git 忽略的 `artifacts/<run_id>/`。默认不持久化 API 密钥、完整原始 Prompt、隐藏标准答案或跨题私密上下文。

Exit gate：官方入口文件 hash 未改变；原始测试结果已记录；本地可显式运行实验包且不自动调用模型。

## 3. 构建单一可信的状态与事件模型（SC-002, SC-016, SC-023, SC-027）

### 3.1 内部枚举

```yaml
RunPhase:
  - SETUP
  - PREPLAN
  - EXPLORE
  - EXPLORE_REVIEW
  - PLAN
  - STEP_EXECUTE
  - STEP_VERIFY
  - CHALLENGE
  - TRACE_BACK
  - META_DECIDE
  - REPLAN
  - POST_REPLAN_REEXPLORE
  - CODE_PRECHECK
  - META_GUIDANCE
  - FINAL_GENERATE
  - FINAL_VERIFY
  - TERMINAL
StepStatus:
  - PENDING
  - IN_PROGRESS
  - VERIFYING
  - CHALLENGING
  - ACCEPTED
  - INVALIDATED
  - ARCHIVED
RunStatus:
  - running
  - completed_llm_reviewed
  - completed_unverified
  - partial_budget_exhausted
  - partial_aborted
  - failed_runtime
VerifierVerdict:
  - ACCEPT
  - CHALLENGE
  - TRACE_BACK
  - PROPOSE_REPLAN
MetaDecision:
  - CONTINUE
  - TRACE_BACK
  - APPROVE_REPLAN
  - ABORT
```

### 3.2 `ProblemState` 必需字段

```yaml
ProblemState:
  schema_version: string
  run_id: string
  problem_hash: string
  config_hash: string
  phase: RunPhase
  status: RunStatus
  plan_version: integer
  attempt_index: integer
  current_step: integer | null
  steps: map[step_id, StepRecord]
  exploration_findings: list[ExplorationRound]
  accepted_results: list[AcceptedResult]
  failure_records: list[FailureRecord]
  verified_results_ledger: list[EvidenceRecord]
  confirmed_failures_ledger: list[FailureRecord]
  meta_interventions: list[MetaIntervention]
  reexploration_tasks: list[DelegatedResearchTask]
  session_registry: map[SessionKey, SessionRecord]
  run_salt: string
  state_revision: integer
  tool_policy: ToolPolicy
  partial_transcript_refs: list[ArtifactRef]
  session_refs: RoleSessionRefs
  counters: RunCounters
  budget: BudgetSnapshot
  usage: UsageSummary
  artifact_refs: map[string, string]
  created_at: iso8601
  updated_at: iso8601
```

每个 `StepRecord` 含 `step_id`、`objective`、`plan_version`、`status`、`report_ref`、`review_ref`、`challenge_rounds`、`dependencies` 与失效记录。`FailureRecord` 含失败种类、计划版本、源步骤、提出者、原因、禁止方向、救援结果和时间戳。`AcceptedResult` 含陈述、类别、证据标签、报告来源、审查来源、依赖和是否仍有效。

### 3.3 不变式

```text
INV-01: Only Orchestrator writes ProblemState and state snapshots.
INV-02: No ACCEPT without valid Verifier verdict and two passing gates.
INV-03: A challenged step never advances until it is accepted or rerouted.
INV-04: Rollback invalidates all active results dependent on archived steps.
INV-05: Replan changes plan_version and Reasoner attempt_index.
INV-06: Meta never solves a proof or executes code; only post-replan restricted delegation may be authorized.
INV-07: Every model/tool call checks budget before dispatch.
INV-08: Every cycle has a finite round/attempt/time bound.
INV-09: LLM-reviewed claims never receive formally_proved status.
INV-10: A resumed run must match problem_hash and config_hash.
INV-11: Unknown/malformed verdict never becomes ACCEPT.
INV-12: Official MathAgent entry remains unchanged by default.
INV-13: Each role invocation injects the latest authorized projection; stale snapshot cannot silently win.
INV-14: Rescued results need dependency checks; invalidated results never enter active prompts as facts.
INV-15: pure_reasoning=true removes executable tools from runtime permissions.
INV-16: A conjecture in a reviewed ledger is not a proved theorem.
INV-17: Model partial text does not imply successful call or proof acceptance.
INV-18: Provider session ID and role scope are validated on every resume.
```

### 3.4 持久化协议

- **MUST** 持有 `state.json` 机器快照和追加式 `events.jsonl`；`PROBLEM_STATE.md` 从状态确定性渲染。[本项目] 适配不同于上游 Markdown canonical layer。
- **MUST** 在状态改变后持久化，先记录唯一事件 ID，再原子更新快照。记录旧阶段、新阶段、事件触发者和所引用裁决。
- **MUST** 用事件 ID 和调用 ID 防止重启后的重复状态提交。模型供应商不支持幂等时，记录 `unknown_outcome` 并显式决定是否重试。
- **MUST** 在回退时同时归档步骤报告、审查记录和辩论记录；不得通过覆盖文件丢掉历史。
- **MUST** 区分活动已接受结论、已失效结论、受限证据、猜测和最终答案。
- **SHOULD** 用文件锁或独占 run ownership 防止同一 Run 被两个进程并发修改。

Exit gate：AC-09、AC-15 的纯 Python 测试通过；模拟中断能保持一致状态。

## 4. 实现角色适配器、会话与视图（SC-015, SC-019）

### 4.1 `ModelAdapter` 合同

```python
class ModelAdapter(Protocol):
    def invoke(self, request: ModelRequest) -> ModelResult: ...
```

`ModelRequest` 至少包含：`run_id`、`role`、`session_key`、`messages`、`model_id`、`reasoning_effort`、`timeout_seconds`、`call_id`、`allowed_tools`。`ModelResult` 至少包含：`text`、`structured_output`、`finish_reason`、`provider_request_id`、`usage`、`latency_seconds`、`error`。

**MUST** 区分逻辑模型调用和底层 HTTP 尝试数。供应商不提供 Token 统计时写 `null`；禁止填 `0` 或用字符估算后伪称真实用量。

### 4.2 会话键与重置规则

```text
reason-<run_id>-a<attempt_index>   # 同一尝试跨步骤复用
verify-<run_id>-step<NN>-a<K>      # 同一步挑战中复用
verify-<run_id>-final-<attempt>    # 整题审查每次新建
meta-<run_id>                     # 整题生命周期持续
explore-<run_id>-r<round>         # 每轮探索新建
```

**MUST** 在 Trace-Back、Re-plan 后创建新的 Reasoner 尝试会话。**MUST** 在不同步骤建立新的 Verifier 会话。**MUST** 在同一步的辩论轮次之间保留 Reasoner、Verifier 对话上下文。**MUST** 持续维护同题 Meta 历史，并隔离不同题目。

无服务器端会话支持时，在本地安全恢复对话；不要每轮从零开始。若必须压缩历史，保留裁决、异议、已经承认的缺陷和用户题目，并记录摘要来源。

### 4.3 三个状态视图

```yaml
reasoner_view: [problem, active_plan, current_step, accepted_results_with_evidence, relevant_failures, tool_state]
verifier_view: [problem, stated_objective, current_report, accessible_accepted_results, verification_tags, in_step_debate]
meta_view: [plan_version, progress, failure_records, repeated_objections, attempts, replan_count, remaining_budget, strategy_history]
```

每次调用前生成一个不可变快照。视图只可读，不能被角色写回。Reasoner 不负责决定自己已验证；Meta 不获得代码执行工具；只有后重规划受控研究子任务委派是允许的调度权限。

Exit gate：AC-07、AC-12、AC-19 通过。

## 5. 实现五阶段完整控制流（SC-003..SC-013）

### 5.1 Exploration（SC-003）

```yaml
ExploreRound:
  assessment: SOLVED | PARTIALLY_SOLVED | NEED_PLAN | UNKNOWN
  worked: [string]
  failed: [string]
  candidates: [string]
  partial_results: [EvidenceRecord]
  solution_candidate: string | null
```

**Route rules**：

```text
IF assessment == SOLVED:
    polish candidate in the SAME explore session -> fresh whole-solution Verifier
    IF ACCEPT: TERMINAL completed_llm_reviewed
    ELSE: archive round -> PLAN, preserve findings
ELIF assessment == PARTIALLY_SOLVED:
    Meta assesses whether to retry exploration or plan
    IF retry and round < max_rounds and budget_ok: next exploration round
    ELSE: PLAN
ELSE:
    archive round -> PLAN
```

**MUST** 记录探索失败及其类型。新一轮探索读取之前轮次的结构化结果，而非自动继承全部过期会话。默认参考上限 `MAX_EXPLORATION_ROUNDS=2`。

### 5.2 Preplan 与 Planning（SC-004, SC-005）

支持 `hint_mode = none | meta_auto | user_hint`。`user_hint` 保存来源元数据；不得被冒充自动生成。预提示失败是有记录的非致命事件，可在预算允许时继续规划。

`Plan` 包含 `version`、`steps`、`created_from_exploration_ids`、`forbidden_directions_ref`。每个步骤必须有 `step_id`、`title`、`objective` 和可选 `depends_on`。通常 6 至 10 步，硬上限 20 步。

结构校验包括：非空目标、合法编号、步骤数量、唯一 ID、合法依赖、无前向循环和计划格式。**不要**由程序假装判断步骤的数学正确性。非法计划只做有界修复；失败生成 `PARSE_ERROR` 或 `PLAN_INVALID` 状态。

### 5.3 Step 执行与验证标签（SC-006, SC-007, SC-027）

`StepReport` 必须含 `step_id`、`objective`、`argument`、`claims`、`tool_evidence_refs`、`blocked`。每条非平凡 claim 有且仅有一种标签：`verified`、`easy-verify` 或 `hard-verify`。

```yaml
verified:
  meaning: executed computation with captured input/code/output
  not_equivalent_to: formal_proof

easy-verify:
  meaning: independently checkable computation not yet run
  verifier_action: run or independently recalculate

hard-verify:
  meaning: mathematical claim requiring proof review
  verifier_action: review assumptions and full inference chain
```

**MUST** 将程序执行证据与数学证明文本关联。**MUST NOT** 在缺少执行证据时把 `easy-verify` 升为 `verified`。

### 5.4 Verifier 两 Gate 和四个裁决（SC-008）

```json
{
  "goal_gate": "YES",
  "logic_gate": "PASS",
  "verdict": "ACCEPT",
  "trace_back_to": null,
  "objections": [],
  "accepted_results": []
}
```

枚举：`goal_gate ∈ {YES, PARTIAL, NO}`，`logic_gate ∈ {PASS, FAIL, UNCERTAIN}`，`verdict ∈ {ACCEPT, CHALLENGE, TRACE_BACK, PROPOSE_REPLAN}`。

**MUST reject** `ACCEPT` if `goal_gate != YES` or `logic_gate != PASS`。**MUST validate** `1 <= trace_back_to <= current_step` for `TRACE_BACK`。`accepted_results` 至少标记类别、陈述、来源、证据级别和依赖。

若 Agent 返回 STAR 原版 Markdown 标题（例如 `## Verdict`, `## TRACE_BACK_TO`），用专用解析器转换成此内部类型。仅按结构化区块解读裁决；禁止全文关键词匹配。无效结果可以有限次格式修复，但始终不能静默 `ACCEPT`。

### 5.5 Challenge（SC-009）

入口：Verifier 返回 `CHALLENGE`。每轮顺序固定：

1. Reasoner 使用本步当前辩论历史回应具体异议；可以修订，也可以举证。
2. Verifier 在本步原会话中重新检查 Goal Gate 与 Logic Gate。
3. Orchestrator 解析裁决并记录轮数、文本引用和预算。
4. `ACCEPT` 进入下一步；`TRACE_BACK` 回退；`PROPOSE_REPLAN` 升级 Meta；再次 `CHALLENGE` 且未达到上限则继续。

达到上限返回 `STALEMATE` 并升级 Meta；禁止自动接受或死循环。参考每步最多 5 轮。

### 5.6 Trace-Back（SC-010）

输入：当前步 `N` 和合法目标步 `M`。操作必须**整体提交**：

1. 将 `M..N` 的步骤报告、审查结果、辩论记录移到带版本的 archive。
2. 失效这些步骤带来的活动成果，以及明确依赖其上的下游成果。
3. 为不依赖错误前提的成果创建 `rescued_results` 引用，保留原证据级别。
4. 创建 `FailureRecord(kind=trace_back)`，记录触发者与原因。
5. 重置当前步骤为 M，增加 attempt_index，生成新 Reasoner 会话键。
6. 保存事件、快照和角色状态视图，再进入 `STEP_EXECUTE`。

若不能判断结果是否依赖错误步骤，采用保守撤销，而不是乐观保留。若 `M` 不合法，返回 `PARSE_ERROR` 或升级 Meta，禁止猜测。

### 5.7 Meta 与 Re-plan（SC-011, SC-012）

Meta 在同题所有计划版本之间持续存在；输入进度、失败与资源摘要；输出：

```json
{
  "decision": "APPROVE_REPLAN",
  "reason_summary": "...",
  "plan_summary": "...",
  "forbidden_directions": ["..."],
  "reusable_results": ["..."],
  "trace_back_to": null
}
```

路由：

```text
CONTINUE       -> 当前路线下一合法动作
TRACE_BACK M   -> 验证 M -> Trace-Back
APPROVE_REPLAN -> 验证 replan_count < MAX_REPLANS -> 存档旧计划 -> 新计划版本
ABORT          -> 部分结果 + partial_aborted
```

Meta 触发源包括 `PROPOSE_REPLAN`、`plan-blocked`、Challenge stalemate、连续超时和可配置的 Step 1 反复失败。新计划要读取 `forbidden_directions`、已验证可复用结果及先前失败摘要；这些提示不等于严格数学定理。

参考 Re-plan 最多 3 次。计划替换后允许按配置受限重新探索；无预算则终止并记录准确状态。

### 5.8 Final generation 和整题检查（SC-013）

全部当前计划步骤经 Verifier `ACCEPT` 后，Reasoner 合成完整答案。**MUST** 使用新 Verifier 会话检查原题一致性、完整性、跨步骤逻辑、最终答案格式。

整题拒绝：在 `MAX_SOLUTION_RETRIES=2` 参考上限和预算内修改后重审。审查服务失败但仍返回候选答案：`completed_unverified`。所有步骤审查通过并不自动让最后重写的答案取得 `completed_llm_reviewed`。

探索快通道也必须遵守同一整题接受条件。失败路径返回 `partial_solution` 和清楚的不完整状态。

## 6. 状态机的实现规则（SC-002, SC-020）

### 6.1 转移表

| 当前阶段 | 输入事件 | 允许目标 | 不允许的行为 |
| --- | --- | --- | --- |
| SETUP | input_ok | PREPLAN 或 EXPLORE 或 PLAN | 在输入验证前调用模型 |
| EXPLORE | SOLVED | FINAL_VERIFY | 未审查直接 COMPLETE |
| EXPLORE | PARTIALLY_SOLVED | EXPLORE_REVIEW | 无界继续探索 |
| EXPLORE | NEED_PLAN/UNKNOWN | PLAN | 直接标完成 |
| PLAN | valid_plan | STEP_EXECUTE | 不校验结构 |
| PLAN | invalid_plan | bounded PLAN retry 或 TERMINAL | 无限修复 |
| STEP_EXECUTE | step_report | STEP_VERIFY | 未产出证据直接 ACCEPT |
| STEP_VERIFY | ACCEPT | 下步或 FINAL_GENERATE | 两 Gate 未通过时推进 |
| STEP_VERIFY | CHALLENGE | CHALLENGE | 丢弃辩论历史 |
| STEP_VERIFY | TRACE_BACK | TRACE_BACK | 无 M 回退 |
| STEP_VERIFY | PROPOSE_REPLAN | META_DECIDE | 未经 Meta 直接换计划 |
| CHALLENGE | ACCEPT | 下步或 FINAL_GENERATE | 缺失证据仍接受 |
| CHALLENGE | STALEMATE | META_DECIDE | 无上限辩论 |
| META_DECIDE | CONTINUE | STEP_EXECUTE 或 CHALLENGE | 违反预算 |
| META_DECIDE | TRACE_BACK | TRACE_BACK | 非法 M |
| META_DECIDE | APPROVE_REPLAN | REPLAN | 越过最大换计划次数 |
| META_DECIDE | ABORT | TERMINAL | 宣称已解决 |
| REPLAN | plan_archived | 可选 EXPLORE 或 PLAN | 覆盖历史 |
| FINAL_GENERATE | candidate | FINAL_VERIFY | 跳过独立检查却标已验证 |
| FINAL_VERIFY | ACCEPT | TERMINAL | 非 `ACCEPT` 状态标已通过 |
| FINAL_VERIFY | reject | 有界 FINAL_GENERATE retry 或 TERMINAL | 无界修复 |
| ANY | budget_exhausted | TERMINAL | 超额调用 |

### 6.2 错误策略

```yaml
errors:
  MODEL_TIMEOUT: preserve partial output; allow bounded meta-guided recovery
  NETWORK_ERROR: bounded retry with separate physical-attempt accounting
  TOOL_ERROR: retain stderr/status; never mark computation verified
  PARSE_ERROR: bounded structured repair; never coerce to accept
  MATHEMATICAL_REJECTION: challenge, traceback, or meta decision
```

**MUST** 区分模型返回了一个错误数学结论，与 API 没有返回有效内容。**MUST** 对每次失败保留原因、尝试次数和最终状态。**MUST** 避免重试过程把同一次供应商请求当作两次不同证据。

## 7. Skills、Prompt 与工具（SC-014, SC-017）

### 7.1 按需 Skill

必须各自可检查地实现：

| Skill ID | 触发条件 | 最小内容 |
| --- | --- | --- |
| `exploration-protocol` | 启用探索时 | 四种评估、例子、失败、候选、预算 |
| `verifier-review-protocol` | 验证任意步骤与整题时 | 两 Gate、异议、四裁决、结果块 |
| `verification-tag-protocol` | 生成或审查非平凡断言时 | 三种标签的使用和证据范围 |
| `meta-intervention-protocol` | 策略介入、僵局、超时 | 四种决策及原因字段 |
| `math-solving-strategies` | Meta 选择适用数学方法时 | 常见归纳、反证、不变量、极值、构造等方法及使用范围 |
| `construct-counterexamples` | 怀疑猜想或中间命题错误时 | 小例子、边界情形、反例验证 |
| `code-issue-resolution` | 代码超时、执行错误或输出不符时 | 分类、恢复动作、有限重试 |

Skill 是项目内部按需加载的操作协议，不是必需注册的 ChatGPT Skill。根据上游源文件独立编写时，记录来源及许可；不要声称自行撰写的 Prompt 与官方文本逐字节一致。

### 7.2 最小角色 Prompt 合同

```text
Reasoner:
- 输入原题、当前目标、已接受事实、相关失败、工具权限。
- 探索时交付四类 assessment 和发现记录。
- 规划时交付合法、有编号的步骤及目标。
- 执行时交付有明确验证标签的步骤报告。
- Challenge 时只回应当前异议并更新步骤报告。
- 不修改 Orchestrator 的权威状态。

Verifier:
- 先检查 Goal Gate，再检查 Logic Gate。
- 按验证标签决定计算审查或证明审查。
- 恰好返回一个结构化 verdict；Trace-Back 必须给合法 M。
- 输出异议和可保留的结果及证据引用。
- 不访问其他问题空间，不修改权威状态。

Meta-Strategist:
- 输入跨尝试进度、失败历史与预算，不接管证明工作。
- 处理僵局、计划阻塞、超时与策略切换。
- 输出 CONTINUE、TRACE_BACK、APPROVE_REPLAN 或 ABORT。
- APPROVE_REPLAN 时给出失败原因、禁止方向和可复用结果。
- 不直接运行代码或修改权威文件；只在后重规划探索时可请求受限的研究任务委派。
```

### 7.3 工具权限

**MUST** 关闭网络搜索、任意外部 HTTP 和跨题文件访问。Reasoner 和 Verifier 仅可执行审核过的本地计算工具，并保存代码、输入、输出、退出码和超时状态。Meta 无直接代码执行权限；如启用后重规划协同探索，Orchestrator 可向 Meta 暴露白名单内的 `delegate_research_task`，不得暴露 Shell 或文件写入。以沙箱执行不可信生成代码，避免把宿主机 Shell 直接暴露为无限制工具。

如果比赛不允许代码工具，在受限 Profile 关闭并记录环境差异。不能既关闭工具，又报告“与原 STAR 计算验证同等条件”。

## 8. 配置和预算（SC-018, SC-022）

### 8.1 参考配置

```yaml
profile: star_reference
features:
  exploration: true
  preplan_meta: false
  planning: true
  step_verifier: true
  challenge: true
  traceback: true
  meta_strategy: true
  reexplore_after_replan: true
  final_solution_review: true
  verification_tags: true
  local_code_tool: true
  persistent_sessions: true
  memory_ledgers: true
  role_state_injection: true
  meta_guided_recovery: true
  pure_reasoning_fallback: true
  code_precheck: true
  post_replan_delegation: true
reference_limits:
  max_exploration_rounds: 2
  max_challenge_rounds_per_step: 5
  max_replans: 3
  max_steps: 20
  max_tracebacks: 5
  max_final_solution_retries: 2
  reasoner_step_timeout_seconds: 1800
  verifier_timeout_seconds: 1200
  meta_timeout_seconds: 600
  code_timeout_seconds: 600
```

参考配置以本次看到的上游代码为起点。另有下列**源码默认值**需要纳入 `reference_config`，并与论文、README 分开注明来源：

```yaml
upstream_code_defaults_as_observed:
  exploration_budget_min_soft: 15
  min_challenge_rounds: 1
  max_consecutive_timeouts: 3
  max_code_retries: 3
  max_timeout_retries: 8
  agent_max_retries: 5
  max_step1_failures: 3
  session_resume_timeout_seconds: 600
  max_total_duration_seconds: 3600
  default_models_from_config_py: [gpt-5.5, gpt-5.5, gpt-5.5]
  default_model_from_readme_table: claude-opus-4.7
```

**MUST** 锁定具体 commit、核对这些配置在运行路径中的生效情况，并记录 README 与 `config.py` 的默认模型不一致。**MUST NOT** 把源码中的 3600 秒或模型 ID 误写为比赛官方上限，或声称自动再现论文全部运行条件。

`competition_constrained`：从比赛运行时读取模型调用、时间和输出限制；在每次调用前扣减可用资源。当预算不足以完成一个完整 STAR 循环时，输出 `partial_budget_exhausted` 或不经最终审查的明确状态，**不得以相同 Profile 名称对外宣称完整 STAR 复现**。

### 8.2 开关依赖校验

```text
challenge=true            REQUIRES step_verifier=true
traceback=true            REQUIRES step_verifier=true
reexplore_after_replan     REQUIRES meta_strategy=true
post_replan_delegation    REQUIRES reexplore_after_replan=true
pure_reasoning_fallback   REQUIRES meta_strategy=true
code_precheck             REQUIRES verification_tags=true AND step_verifier=true
memory_ledgers            REQUIRED in star_reference; disable only for ablation
role_state_injection      REQUIRED in star_reference; disable only for ablation
replan-capable execution  REQUIRES meta_strategy=true
verification_tags=true    SHOULD have step_verifier or explicit evidence validator
final_solution_review=false -> cannot report completed_llm_reviewed
planning=false            -> mark as ablation/single-shot, not star_reference
```

所有实验新功能默认关闭，只有显式创建 Profile 才能调用。新增每个开关都需提供“关闭不调用”和“打开改变唯一行为”的测试。

## 9. 对外 API、计量和可重复实验（SC-019, SC-021, SC-023, SC-026）

### 9.1 入口合同

```python
class ResearchHarness:
    def solve(self, problem: str, metadata: dict | None = None) -> dict: ...
```

返回字段：`run_id`、`final_response`（非空字符串）、`status`、`verification_level`、`trace`（脱敏）、`usage` 和 `experiment`。无完全证明时允许返回清楚标识的部分成果，但不得伪造通过验证。官方 `ReasoningAgent` 的单独结果适配器必须严格遵守比赛 JSON 合同。

### 9.2 用量与审计

```yaml
usage:
  logical_model_calls: int
  physical_attempts: int | null
  input_tokens: int | null
  output_tokens: int | null
  cached_tokens: int | null
  tool_calls: int
  wall_seconds: float
  usage_source: provider | unavailable
experiment:
  profile: string
  model_id: string
  config_hash: string
  code_commit: string
  dataset_version: string | null
  tokenizer_or_provider_version: string | null
```

**MUST** 将每次状态转移及其裁决 ID 加入脱敏事件 Trace。不得在演示 Trace 中包含密钥、完整 Prompt、隐藏答案或其他 Run 的内容。详细原始模型输出只能按明确的本地 Debug 策略保存，不能默认进入 Git 提交。

### 9.3 配对实验边界

同一实验对保持模型、模型版本、推理参数、题目数据、工具权限、总预算和评分器版本一致。无法获得真实 Token 用量的运行应在 Token 维度标为 `unknown`，不允许用输出字符数代替。报告 `pass@budget`、总调用数、真实 Token（如有）、墙钟时间、失败类型、Challenge/Trace-Back/Re-plan 次数。

使用现有仓库的配对 Runner 时需经适配审查；不要替换已有 Job、预算、归档或重放合同。不读取隐藏金标来影响当前题目的解题路线。

## 10. STAR 核心的 33 个验收用例（SC-024）

建立 `ScriptedModelAdapter`、`FakeClock`、`FakeToolRunner` 与可控存储故障注入。至少实现以下测试：

| Test ID | 输入或故障 | 必须断言 |
| --- | --- | --- |
| AC-01 | Explore=SOLVED，整题 Accept | 同一 Explore 会话中润色；完成；Planner 调用数为 0 |
| AC-02 | Explore=SOLVED，整题 Reject | 进入 Plan；保留发现；不得标通过 |
| AC-03 | Explore=PARTIALLY_SOLVED | Meta 决定重试或规划；轮数不超上限 |
| AC-04 | Plan 非法编号或循环 | 修复有界；无效计划不执行 |
| AC-05 | Goal=NO, Logic=PASS, verdict=ACCEPT | 判为无效裁决，禁止推进 |
| AC-06 | easy-verify 无执行证据 | 不写成 verified 或 formally_proved |
| AC-07 | 第三轮 Challenge 接受 | 双方保留三轮辩论；仅接受一次 |
| AC-08 | 达到最大 Challenge 次数 | 升级 Meta；无死循环 |
| AC-09 | 第 N 步 Traceback 至 M | 归档 M..N、下游成果失效、保留可救援成果 |
| AC-10 | TRACE_BACK 缺失/越界 M | 禁止猜测；有记录的升级或终止 |
| AC-11 | APPROVE_REPLAN | 老版本留档；新版本生成；禁止方向带入 |
| AC-12 | 同题多 Plan 与不同题 | 同题 Meta 历史延续；不同题会话隔离 |
| AC-13 | 整题校验不通过 | 有界重试；最终状态不伪称 verified |
| AC-14 | 模型/工具超时、网络异常 | 正确分类；部分结果保存；重试受限 |
| AC-15 | 在归档与快照间强制中断 | 恢复不重复接受、不丢归档、不重复记账 |
| AC-16 | 预算不足 | 不再派发；结果 JSON 合法；标明预算终止 |
| AC-17 | 所有功能关闭 | 无额外工具与模型调用；单次路径可测试 |
| AC-18 | 比赛默认入口回归 | 文件与调用合同保持；`final_response` 非空且 JSON 可序列化 |
| AC-19 | Meta 请求直接执行代码或跨题读取 | 访问被拒；审计保留脱敏拒绝事件 |
| AC-20 | 相同配置的配对运行 | 可导出模型/题目/版本/预算/用量来源与失败分类 |
| AC-21 | 跨计划四层记忆的独立性 | Meta 历史与账本持续；Reasoner/Verifier 只在规定会话窗口保存 |
| AC-22 | 会话新建和 resume 后状态变更 | 最新角色投影被注入且不跨题；旧状态不会覆盖最新 |
| AC-23 | 同名题不同 run 与进程重启 | 不会复用错误 session；真实 resume 或本地重构可验证 |
| AC-24 | timeout/code_issue/stuck 三种诊断 | 结构化输出具体动作与任务；动作经控制器核验 |
| AC-25 | Meta 下达纯推理指令后模型想执行 Python | 工具被运行时白名单拒绝；模式改变留痕 |
| AC-26 | Replan 后探索含多个研究子任务 | 研究委派与汇总进入新计划；所有子任务计费、非代码 |
| AC-27 | easy-verify 存在 Python 代码片段 | 有真实沙箱回执后再送审；异常无法冒充 verified |
| AC-28 | Replan 同时产生禁用路线和救援结论 | 新会话均可见且旧记录未丢；原错结论不可用 |
| AC-29 | Conjecture/失效结论出现于账本 | 不提升到已证事实，不能当作活动引理 |
| AC-30 | Verifier/Meta 整题意见矛盾或调用失败 | 来源分别标识；未获 Verifier 审查不得标整题验证通过 |
| AC-31 | 三层 Prompt 的触发和工具权限 | 记录激活 Skill；注入视图版本；禁止越权工具 |
| AC-32 | 流式半途超时与重启 | 片段持久化但不解析为终态；调用不重复提交 |
| AC-33 | 关闭扩展或比赛预算中断 | 未授权子任务/预检不启动；输出准确 Profile 与跳过原因 |

**Exit rule**：所有本期功能必须由具体用例覆盖。`pytest` 缺失不是修改运行时依赖的理由；仓库要求的 `uv run python -m unittest discover -s tests -p "test_*.py"` 必须通过。已知跳过要报告原因。


## 11. 全量审计补丁：新增核心协议（SC-028..SC-038）

此章是规范要求，不是可随意省略的设计建议。所有新增条目与人类版第 9 节共享同一个需求编号，来源分类和差异矩阵见 `STAR_CORE_COMPONENT_AUDIT.md`。

### 11.1 四层记忆与原子同步（SC-028, SC-035）

**MUST** 分别维护：Reasoner 计划尝试连续上下文、Verifier 单步 Challenge 连续上下文、Meta 整题生命周期历史、Orchestrator 持久正负事实账本。`star_reference` 默认全部有效；全局关闭 Memory 只能作为标注清楚的 ablation。

```yaml
EvidenceRecord:
  record_id: string
  kind: Lemma | Conjecture | Computation | Definition | Answer
  statement: string
  evidence_level: executed_code | llm_reviewed | unverified
  source_step: integer | null
  source_plan_version: integer
  source_verifier_ref: string | null
  dependency_ids: list[string]
  status: active | invalidated | archived
  provenance_refs: list[string]
FailureRecord:
  record_id: string
  failure_type: false_premise | invalid_inference | timeout | code_issue | stuck | stale_plan | other
  plan_version: integer
  source_step: integer | null
  reason: string
  forbidden_directions: list[string]
  rescued_result_ids: list[string]
  scope_conditions: list[string]
  archive_ref: string
  active: boolean
```

**MUST** 保留“审查通过”与“形式化证明通过”的边界：本期没有 Lean 证明保证，故即便被 Verifier 接受也不能设为 `formally_proved`。`Conjecture` 若进入账本，只能作为待证命题，不能被下游当作已证前提。

**MUST** 通过唯一事件 ID 原子更新 `state.json`、事件日志和从其生成的 `PROBLEM_STATE.md`。`confirmed_failures_ledger` 跨重规划不清空；`rescued_result_ids` 仅允许指向满足依赖完整性检查、仍有效的结论。角色历史只是上下文缓存，**不是**写入权威账本的途径。

Exit gate：AC-21, AC-28, AC-29。

### 11.2 会话启动、恢复与持续注入（SC-029, SC-030）

**MUST** 每次模型调用前，检查上次看到的 `state_revision` 并生成适用角色的最新状态投影。在新建或恢复 Copilot CLI 会话的路径上，通过 `sessionStart` 语义注入；API 适配路径通过 `prepare_role_context(role, state_revision, run_id)` 注入。当前消息已包含同版本投影时应做去重，不得无界堆叠。

```yaml
SessionRecord:
  session_key: string
  provider_session_id: string | null
  run_id: string
  run_salt: string
  role: reason | verify | meta | reason_noncoding | explore
  plan_version: integer | null
  step_id: integer | null
  last_injected_state_revision: integer
  created_at: iso8601
  transcript_ref: string | null
```

**MUST** 保证 `SessionRecord.run_id` 与请求 run 匹配，恢复时校验 `problem_hash/config_hash`、角色和版本范围；冲突直接拒绝。`run_salt` 防止同名问题的新运行意外碰撞。后端无法延续真实会话时，从受审计的本地对话快照和新状态投影重构相同语义，不应虚构服务端 resume 成功。

**MUST** 分别测试：同一步 Challenge 记忆连续、新步骤新 Verifier、Traceback/Replan 后新 Reasoner、Meta 跨所有计划续接、题目间隔离、重启后恢复和 stale snapshot 拒绝。

Exit gate：AC-22, AC-23。

### 11.3 Meta 诊断与动作路由（SC-031）

**MUST** 支持与 Replan 判决不同的局部干预协议：

```yaml
MetaGuidanceRequest:
  failure_type: timeout | code_issue | stuck
  source_step: int
  current_report_ref: string | null
  partial_output_ref: string | null
  intervention_history_refs: list[string]
  budget: BudgetSnapshot

MetaGuidanceResponse:
  action_type: explore_more | retry_different_method | trace_back | replan
  specific_task: string
  use_pure_reasoning: boolean
  trace_back_to: int | null
  rationale: string
```

Meta 的 `action_type` 不能代替本来就存在的 `MetaDecision`。Orchestrator 先把响应严格解析、合法化、检查资源，再决定交给 Reasoner 执行具体任务、执行 Trace-Back 或进入独立 ReplanDecision。`specific_task` 缺失不能变成自由文本“试试其他方法”后静默继续。历史干预的任务、执行结果及失败原因应回流 Meta 视图。

Exit gate：AC-24。

### 11.4 强制纯推理是实际权限，不是提示词（SC-032）

```text
IF MetaGuidanceResponse.use_pure_reasoning:
  persist("mode_changed", from="reason", to="reason_noncoding")
  invoke Reasoner with allowed_tools = []  # exclude python/shell/exec/search
  include captured partial computational evidence + concrete math question
  never run executable code from that invocation, even if response requests it
  restore prior mode only through explicit controller event
```

**MUST** 测试故意请求执行代码的模型输出在此模式被拒绝，且拒绝被记入审计日志。Reasoner 可利用已有计算证据推导，却不可悄悄恢复工具权限。

Exit gate：AC-25。

### 11.5 APPROVE_REPLAN 后受 Meta 协调的再探索（SC-033）

官方源代码实现了后重规划研究子任务委派，这不同于调用原探索 Agent 再试一次。**MUST** 在 `APPROVE_REPLAN` 被接受并归档旧计划后提供 `POST_REPLAN_REEXPLORE` 分支；受配置和全局预算管理，Meta 可以请求多个有角色隔离的非代码探索任务，汇总相互不同的方向与潜在反例，再递交新的 Planner。

```yaml
DelegatedResearchTask:
  task_id: string
  parent_replan_id: string
  prompt: string
  permitted_tools: []          # noncoding
  timeout_seconds: integer
  estimated_cost_class: low | medium
  status: pending | running | complete | failed | timed_out
  output_ref: string | null

ReExploreBundle:
  parent_replan_id: string
  tasks: list[DelegatedResearchTask]
  merged_findings_ref: string
  previous_forbidden_directions_ref: string
  provenance: "unverified_exploration"
```

受限 Profile 必须能返回 `skip_due_to_budget` 并直入 PLAN；`star_reference` 开启该能力并显式保存任务委派。框架支持并行时可并发调用；单线程环境可串行执行但须标记并行能力差异。

**MUST NOT** 将探索子任务输出直接纳入 `verified_results_ledger` 的已证引理。

Exit gate：AC-26, AC-33。

### 11.6 `[easy-verify]` 的自动预检（SC-034）

在向 Verifier 审查步骤之前，扫描结构化标签关联的代码。对受支持的 `[easy-verify]` 片段触发可信沙箱内的限时执行；附回执，永不只替换标签文字。

```yaml
CodePrecheckResult:
  step_id: integer
  code_ref: string
  executed: boolean
  exit_code: integer | null
  stdout_ref: string | null
  stderr_ref: string | null
  timeout: boolean
  sandbox_policy_version: string
  provenance: local_precheck | skipped | failed
```

Reasoner 标记 `[verified]` 时也必须能追溯真实已运行证据，Verifier 审核输入含代码、输出和结论；不能把任何数值实验升级为一般数学定理的严格证明。没有可解析代码时必须返回 `not_executed`，允许 Verifier 继续审查但不得冒称计算通过。

Exit gate：AC-27。

### 11.7 整题审查的论文／源码口径区分（SC-036）

**论文 §3.5** 可选 Meta 整题审查；**官方求解代码及探索快通道** 执行 Verifier 整题审查。本项目必须在 `review_policy` 中标记来源：

```yaml
review_policy:
  mathematical_reviewer: verifier  # separate final-session
  meta_whole_solution_risk_review: false  # optional advisory
  on_review_transport_failure: completed_unverified
```

不能用 Meta 建议代替双 Gate 数学审查。不能把上游某些 reviewer 调用失败却继续完成的行为包装成数学验证成功。

Exit gate：AC-30。

### 11.8 三层动态 Prompt 和权限白名单（SC-037）

```text
invoke(role, snapshot):
  1. assert role policy and tool whitelist
  2. system_prompt = render_role_definition(role)
  3. skills = select_only_triggered_skills(role, phase, tags, failures)
  4. context = latest_role_projection(snapshot.state_revision)
  5. request = compose(system_prompt, skills, context, task, session_history)
  6. call through ModelAdapter; retain loaded skill IDs in invocation trace
```

七种 Skill 必须可审查、非空、有触发条件。`reason_noncoding` 的工具策略必须与一般 Reasoner 真正不同。Prompt 的“禁止”语句不是工具权限的替代物。模型输出应记录使用的三层版本指纹，方便回放实验。

Exit gate：AC-31。

### 11.9 流式部分输出与安全恢复（SC-038）

**MUST** 将模型流式中断与计算超时分开处理；记录 `partial_transcript_ref`、工具最后状态、调用 ID、供应商请求 ID（若有）和 `unknown_outcome`。恢复时 Meta 读取可安全引用的部分工作和具体错误，再发出有界指令。不得把片段末尾出现的 `ACCEPT` 一词认作有效裁决，只有完整的结构化结束产物才能解析。

**MUST** 在中断中重启时严格拒绝重复事件提交；对无法确认完成状态的外部调用不声称零成本，并可让操作者选择从最近可信检查点继续。`state.json` 永久状态和会话缓存要一致。

Exit gate：AC-32。

### 11.10 规则级消融、实现差异和发布门槛

- `star_reference` 必须启用本章中属于 STAR 核心的方法；关闭仅用于明确标注的消融，且不冒充完整参考模式。
- `competition_constrained` 允许因预算跳过委派或高级验证，但必须把这些跳过作为运行事实写入 Trace。
- 每个新增协议至少关联一个 AC；禁止仅实现同名类或空函数通过测试。
- 现有官方仓库源码和论文存在口径差异时记录双方及锁定 commit；不得静默把本项目更严格的恢复机制说成上游原样实现。
- 只有 AC-01..AC-33 和完整真实运行时联调全部通过，才能声称满足本文件定义的工程 STAR Core；这仍不等于复现论文数学成绩。


## 12. 实施顺序与每切片停止条件（SC-025）

| Slice | 实施内容 | 完成条件 |
| --- | --- | --- |
| P0 | 检查原仓库、锁上游 commit、基线与边界快照 | 输出可审查的基线报告；官方入口原样 |
| P1 | `state`、`storage`、`events`、`memory`、`sessions`、`config`、`budget`、`model_adapter` | 恢复与预算单测 + AC-21..23 通过 |
| P2 | Explore、Meta 预提示、Plan、格式验证 | AC-01..04 通过 |
| P3 | Step、标签、Goal/Logic Gate、裁决解析 | AC-05..06 通过 |
| P4 | 带会话的 Challenge 与 Trace-Back | AC-07..10 通过 |
| P5 | 持久 Meta、具体干预、强制纯推理、后重规划委派、正负账本同步 | AC-11..12、AC-24..26、AC-28..29 通过 |
| P6 | Final generation、整题 Verifier、Meta 可选风险意见、部分结果 | AC-13、AC-30 通过 |
| P7 | 七类 Skills、三层 Prompt、按标签预检、沙箱、超时与流式恢复 | AC-14、AC-19、AC-27、AC-31..32 通过 |
| P8 | 全量端到端、真实客户端、配对实验适配与发布审查 | AC-15..20、AC-33 通过；真实成本与正确率独立报告 |

每一切片生成以下交付记录：`scope`、`files_changed`、`tests_added`、`test_command`、`test_result`、`known_gaps`、`next_slice`。失败时回到最小相关切片，不要通过扩大范围掩盖失败。

## 13. 来源校对清单

实施前依次检查：

- [STAR 论文与附录](https://arxiv.org/html/2605.19338)：3.1 至 3.5、A、B、C。
- [STAR 仓库 README](https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/main/README.md)：运行命令、目录和模型端点。
- [STAR config](https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/main/src/config.py)：实际源码配置。不要因 README 与代码默认模型不一致而静默选值。
- [STAR state](https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/main/src/state.py)：版本、归档、失败与会话引用。
- [STAR 探索、计划、执行、质询、失败与求解混入模块](https://github.com/Julius-Woo/STAR-PolyaMath/tree/main/src/orchestrator_mixins)：六个阶段模块。
- [MathAgent AGENTS.md](https://raw.githubusercontent.com/RUSS0718/MathAgent/develop/AGENTS.md)：比赛工程边界、验收和分支纪律。
- [technical-writing](https://raw.githubusercontent.com/cursor/plugins/main/pstack/skills/technical-writing/SKILL.md)：命令句、明确主语、每个词只赋予一种含义。

## 14. 编码 Agent 开工前检查

```text
[ ] 我阅读了当前仓库的 AGENTS.md 和已有 harness_lab。
[ ] 我知道本次是完整 STAR Core，而不是移植 Danus/SHEAF/OSVerify。
[ ] 我锁定了 STAR 官方源码的 commit 并记录与论文的差异。
[ ] 我知道完整参考模式与比赛受限模式不同。
[ ] 我能指出 SC-001..SC-043 每条需求对应的测试，包含四层记忆、Meta 非代码路径与后重规划委派。
[ ] 我不会把 LLM 接受等同于数学形式化证明。
[ ] 我不会在默认 import 时调用模型或修改官方评分路径。
[ ] 我先提交 P0 的审查结果，再按 P1..P8 逐步实现。
```

**最终完成判定**：STAR Core 的 SC-001..SC-038 实现且 AC-01..AC-33 通过；启用扩展时还须完成 SC-039..SC-043 与 AC-34..AC-44；原官方入口保持不变；真实模型环境与预算条件单独验收；公布已知差异及运行成本。任何一项未达到时，报告实际完成阶段，而不是宣称完成完整 STAR 复现。


## 15. Best-Effort 扩展实施合同（SC-039..SC-043）

> 来源：**[本项目扩展]**。本章是 v1.2 新增协议，不是 STAR 原论文机制。若启用该扩展，在硬预算耗尽后执行的应是**无模型调用的纯 Python 选择函数**。需求与人类版 §6.4 一致。

### 15.1 数据类型与约束

```yaml
CandidateStatus:
  - draft
  - eligible_unreviewed
  - locally_reviewed
  - whole_reviewed
  - refuted
  - invalidated
BestEffortStatus:
  - candidate_selected
  - no_eligible_candidate
  - not_triggered
ConfidenceLevel:
  - high
  - medium
  - low
  - rejected
CandidateRecord:
  candidate_id: str
  run_id: str
  problem_hash: str
  answer_text: str
  source_phase: str
  plan_version: int
  step_refs: list[str]
  created_event_id: str
  answer_completeness: complete | partial
  review_state: CandidateStatus
  evidence_refs: list[str]
  known_objections: list[str]
  invalidated_by: list[str]
  selection_eligible: bool
BestEffortDecision:
  status: BestEffortStatus
  selected_candidate_id: str | null
  confidence_level: ConfidenceLevel | null
  reason_codes: list[str]
  evidence_refs: list[str]
  unresolved_issues: list[str]
  excluded_candidate_ids: list[str]
  selection_rule_version: str
  termination_reason: str
```

`CandidateRecord` **MUST** 是只追加的版本记录。相同回答内容仍保留独立来源，允许在查询时去重，但不允许覆盖审查历史。无答案的流式文本不是可选候选。`confidence_level` 是证据等级，不是概率。

### 15.2 纯函数选择规则

```python
# Specification pseudocode. Do not assume these functions already exist.
def select_best_effort(snapshot: ProblemState) -> BestEffortDecision:
    records = load_candidates_from_snapshot(snapshot)
    eligible = [
        record for record in records
        if record.answer_completeness == "complete"
        and bool(record.answer_text.strip())
        and record.selection_eligible
        and record.review_state not in {"refuted", "invalidated", "draft"}
        and not has_invalidated_dependency(record, snapshot)
        and output_contract_accepts(record.answer_text, snapshot)
    ]
    if not eligible:
        return no_candidate_decision(snapshot)
    # Prefer whole-problem review, then independent applicable evidence,
    # then local review, then a complete but unreviewed answer.
    # This is evidence-based ordering, not a calibrated probability.
    ranked = rank_by_evidence(eligible, snapshot)
    chosen = stable_tie_break(ranked)
    return explain_selection(chosen, ranked, snapshot)
```

**MUST** 在硬预算到达后拒绝一切新的模型调用和工具请求。软预算阈值只能在仍有真实剩余额度时安排整理；软阈值也不能突破硬上限。所有角色和子任务共享预算记账。

### 15.3 证据与冲突

- `high`: 完整答案通过整题审查，并有适用的独立支持，无未解决实质疑点。
- `medium`: 完整答案有连贯推导或局部接受，但缺少充分的整题证据。
- `low`: 完整可解析候选缺少关键审查，或同等级候选互相冲突。
- `rejected`: 已被决定性证据否定。排除提交。

不要根据 Agent 自述写 `0.95` 之类的概率。数值置信度需要独立分布上的校准试验和明确适用范围。同一模型重复投票不构成形式化正确性。每条 `reason_code` 必须有真实 `evidence_ref` 或明确的“缺失”记录。

### 15.4 状态与输出兼容

- 原有 `RunStatus.partial_budget_exhausted` 保留。不要另建一套语义冲突的终态。
- 增加 `best_effort.status` 与 `termination_reason`；其含义与 RunStatus 不同。
- `final_response` 必须满足官方 JSON 合同。非空失败说明不是数学正确答案。
- 官方适配器按当前 `AGENTS.md` 的允许字段生成结果，内部置信和理由放到 Evidence Pack。
- `star_reference` 默认不使用此扩展；`star_best_effort` 或显式研究配置开启。`official` 不导入实验模块。

### 15.5 事件与故障处理

使用稳定事件名：`candidate_added`、`candidate_reviewed`、`candidate_refuted`、`candidate_invalidated`、`best_effort_started`、`best_effort_selected`、`best_effort_empty`、`budget_exhausted`、`request_unknown_outcome`。事件必须带 `run_id`、`state_revision`、事件唯一 ID、候选 ID（适用时）、证据引用和用量来源。快照重放不应触发新的外部副作用。

### 15.6 新增验收场景 AC-34..AC-44

| ID | 测试动作 | 断言 |
| --- | --- | --- |
| AC-34 | Explore、Step、Final 三阶段提交完整候选 | 候选版本完整、来源可追溯 |
| AC-35 | 最新候选被确证错误 | 不进入可选集合 |
| AC-36 | 回退时撤销依赖的步骤 | 所有受影响候选失效 |
| AC-37 | 模型调用额度为零，账本已有合格答案 | 不发模型或工具请求，仍能交付候选 |
| AC-38 | 模型额度为零，账本无合格答案 | 明确未完成，非空但不编造数学答案 |
| AC-39 | 两个同等级候选互相矛盾 | 记录冲突，稳定平局处理，证据等级不高估 |
| AC-40 | 尝试返回未经校准的数字 0.95 | 合同拒绝或剥离数字，只保留可追溯定性证据 |
| AC-41 | 运行官方入口的回归 | `user_agent.py` 及默认模型调用和输出结构不变 |
| AC-42 | 对同一完成的 Snapshot 执行两次重放 | 选择一致；额外模型和工具调用数为 0 |
| AC-43 | 预算到期时模型调用仍未返回 | 记录 `unknown_outcome`；不可假设未扣费，不重复提交结果 |
| AC-44 | 工具完成一个局部算术检查 | 不得宣称整题已形式化证明 |

### 15.7 与技术设计的绑定

使用 [`STAR_CORE_TECHNICAL_DESIGN_v1_2.md`](STAR_CORE_TECHNICAL_DESIGN_v1_2.md) 的 `CandidateRegistry`、`BudgetGuard`、`BestEffortFinalizer`、`EvidencePolicy`、`OfficialResultAdapter`。技术文档规定模块交互和栈选型，**本文件与人类 PRD 的需求优先于示例实现细节**。遇到不一致时停止受影响切片并记录冲突。
