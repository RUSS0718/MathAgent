# Solver Harness v1.1 实现规格

**状态：** accepted for `showcase-solver-harness-v1`  
**日期：** 2026-10-22  
**产品版本：** v1.1  
**基线：** `develop@700f42317df35aab6ae3f7bcda5193a4c88e17d0`  
**上游合同：** [STAR Core Agent 实施规格](../prd/STAR_CORE/STAR_Core_v1_2/STAR_CORE_SPEC_AGENT_v1_2.md)  
**决策：** [ADR-0013](../adr/0013-solver-harness-boundary-and-shared-transaction.md)

## 1. 范围与成功标准

v1.1 在 `showcase` 产品面内交付 Solver Harness 的 S1 内核与 S2 Explore 控制面：

- 一个可持久化、可恢复、带 `state_revision` 的 Solver Run；
- 确定性的 Explore 结果和两条可观察分支；
- 探索直接解出后的最小整题审查；
- 探索被拒后进入 Plan 的交接；
- 预算耗尽时返回合法、非编造的结果；
- 完整记录延期到 v1.2 的需求、ticket、依赖和验收用例。

**v1.1 完成定义：** 下文 AC-SH-01 至 AC-SH-08 在离线脚本模型和假工具下通过；三个既有回归文件未修改且通过；`docs/evals/showcase-solver-harness-v1.1-acceptance.md` 记录实际命令与结果；所有 SC-001..SC-043 都有 v1.1 或 v1.2 的唯一归属。

**v1.1 不证明：** STAR 论文复现、数学正确率提升、真实 Intern 工具闭环、完整 Meta-Strategist、逐步双 Gate、Challenge、Trace-Back、Re-plan、四层会话记忆、沙箱或 Best-Effort 候选选择。真实 Intern 工具闭环指 `v0.2 AC-06`，与 STAR 的 `STAR AC-06` 不是同一验收。

## 2. 已确认的边界

1. 新代码位于 `showcase/solver_harness/`；不创建 `harness_lab/` 或其他顶层实验包。
2. 产品版本为 v1.1；`pyproject.toml` 保持 `0.1.0`，前端保持 `0.2.0`，Profile 保持 `showcase_mvp`。
3. Solver Run 与产品 Run 共用同一个 SQLite 文件、连接和事务边界，但状态和事件分别写入 `solver_states`、`solver_events`。
4. 新表由 `showcase/storage.py:SQLiteStore.__init__` 创建；读写和 revision 事务位于 `showcase/solver_harness/storage.py`。
5. 现有 `runs`、`events`、`checkpoints`、`artifacts` 表和其方法行为不变。
6. S1 使用纯 Python；S2 才使用 LangGraph 条件边。LangGraph checkpoint 不替代业务状态。
7. v1.1 模型统一经过 `ModelPort`；测试只使用 `ScriptedModelPort`。
8. `ProblemState.candidate_registry`、`best_effort_decision`、`finalization_reason` 均存在且默认 `None`。
9. v1.1 不启用真实代码执行；`ToolPolicy` 默认全部拒绝。
10. 不修改根 `user_agent.py`、`implementations/`、`BASELINE.json`、官方预算或前端入口合同。

## 3. 垂直切片

### 3.1 S1：可恢复内核

S1 的最小可执行路径为：

```text
create Solver Run
  -> persist initial ProblemState
  -> call ScriptedModelPort once
  -> receive Explore result
  -> persist event + new revision
  -> restore from SQLite
  -> return JSON-compatible internal result
```

S1 成功后必须能回答：

- 同一 `run_id` 的状态和事件在进程重建后是否一致；
- 过期 `expected_revision` 是否被拒绝；
- 模型调用前是否检查预算；
- 预算不足时是否零新增调用并返回合法状态；
- 未启用扩展时三个扩展字段是否为 `None`。

### 3.2 S2：Explore 条件路由

S2 必须覆盖两条分支：

```text
EXPLORE -> SOLVED -> EXPLORE_REVIEW -> ACCEPT -> TERMINAL
EXPLORE -> SOLVED -> EXPLORE_REVIEW -> REJECT -> PLAN -> WAITING_PLAN
```

`NEED_PLAN`、`UNKNOWN` 和 `PARTIALLY_SOLVED` 使用确定性 `ExploreDecision`：

- `NEED_PLAN` / `UNKNOWN` 直接进入 `PLAN`；
- `PARTIALLY_SOLVED` 按配置选择再一次 Explore 或进入 `PLAN`，总轮数不超过 2；
- 该决策不调用模型、不保存跨计划历史，不声称是完整 Meta-Strategist。

## 4. 公共接口与数据合同

### 4.1 入口

```python
from showcase.solver_harness import SolverHarness

harness = SolverHarness(
    database_path="artifacts/solver-harness/run.sqlite3",
    model=ScriptedModelPort(...),
    verifier=ScriptedVerifierPort(...),
)
result = harness.solve(problem, metadata)
```

`result` 必须可 JSON 序列化且至少包含：

```json
{
  "run_id": "solver_...",
  "status": "completed_llm_reviewed",
  "final_response": "...",
  "verification_level": "llm_reviewed_not_formally_proved",
  "phase": "TERMINAL",
  "state_revision": 4,
  "usage": {
    "logical_model_calls": 2,
    "physical_attempts": null,
    "input_tokens": null,
    "output_tokens": null,
    "tool_calls": 0,
    "wall_seconds": 0.0
  },
  "trace": []
}
```

这是 Solver Harness 内部结果，不是官方比赛提交格式。

### 4.2 ProblemState

```python
class ProblemState(BaseModel):
    schema_version: str = "solver-harness-state-v1"
    run_id: str
    problem_hash: str
    config_hash: str
    phase: RunPhase
    status: RunStatus
    plan_version: int = 0
    attempt_index: int = 0
    exploration_findings: list[ExplorationRound] = []
    steps: dict[str, StepRecord] = {}
    accepted_results: list[AcceptedResult] = []
    failure_records: list[FailureRecord] = []
    session_refs: dict[str, str] = {}
    counters: dict[str, int] = {}
    budget: BudgetSnapshot
    usage: UsageSummary
    candidate_registry: list[CandidateRecord] | None = None
    best_effort_decision: BestEffortDecision | None = None
    finalization_reason: str | None = None
    state_revision: int = 0
    created_at: str
    updated_at: str
```

字段的 `None` 表示扩展未启用；空列表只在扩展启用后表示“已启用但无条目”。

### 4.3 端口

```python
class ModelPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelReply: ...

class VerifierPort(Protocol):
    def review_whole(self, request: WholeReviewRequest) -> WholeReview: ...
```

- `ScriptedModelPort` 和 `ScriptedVerifierPort` 是 v1.1 唯一允许的测试实现。
- `InternModelPort` 只做薄适配，复用 `showcase/adapters.py:InternModelAdapter` 的传输、重试和用量。
- 真实 Intern 联调与 live 证据属于 v1.2。

## 5. 持久化与并发

`solver_states` 至少保存 `run_id`、`state_revision`、`problem_hash`、`config_hash`、`snapshot_json`、`created_at`、`updated_at`。`solver_events` 至少保存 `run_id`、`sequence`、`event_id`、`event_json`、`created_at`。

提交规则：

```text
BEGIN IMMEDIATE
  read current revision
  reject if expected_revision != current revision
  insert event with next sequence
  replace snapshot with revision + 1
COMMIT
```

同一 `run_id` 和事件 `event_id` 不能重复提交。恢复时必须验证 `problem_hash` 与 `config_hash`。

## 6. 预算与失败

v1.1 支持：

- `max_model_calls`；
- `max_tool_calls`；
- `max_runtime_seconds`；
- 调用前的硬门禁。

预算不足时：

1. 不派发新的模型或工具调用；
2. 冻结当前状态；
3. 返回 `status=partial_budget_exhausted`；
4. 有完整 Explore 候选时返回该文本，否则返回明确的未解决说明；
5. 不声称已经完成整题审查。

失败分类至少区分 `MODEL_TIMEOUT`、`NETWORK_ERROR`、`PARSE_ERROR` 和 `MATHEMATICAL_REJECTION`。v1.1 只实现可触发、可路由的分类，不实现完整恢复策略。

## 7. 需求与验收映射

### 7.1 v1.1 用例

| ID | 场景 | 必须断言 |
| --- | --- | --- |
| AC-SH-01 | Explore SOLVED，整题审查 ACCEPT | 不进入 Plan；终态为 `completed_llm_reviewed`；`final_response` 非空 |
| AC-SH-02 | Explore SOLVED，整题审查 REJECT | 进入 Plan；保留 Explore findings；不得标为已审查通过 |
| AC-SH-03 | Explore NEED_PLAN / UNKNOWN | 确定性进入 Plan，不调用 Meta 模型 |
| AC-SH-04 | Explore PARTIALLY_SOLVED | 按配置再探索或进入 Plan；总探索轮数不超过 2 |
| AC-SH-05 | 进程重建 | 同一 `run_id` 的状态、事件和 revision 一致 |
| AC-SH-06 | 过期 revision | 拒绝写入，不覆盖更新状态 |
| AC-SH-07 | 预算耗尽 | 不新增模型/工具调用；返回可 JSON 序列化的明确状态 |
| AC-SH-08 | 扩展未启用 | `candidate_registry`、`best_effort_decision`、`finalization_reason` 均为 `None` |

### 7.2 SC 归属

| SC | v1.1 归属 | 说明 |
| --- | --- | --- |
| SC-001 | 部分 | 实验入口与官方隔离；完整发布审查在 v1.2 |
| SC-002 | 部分 | Explore/Plan 确定性转移；完整状态机在 v1.2 |
| SC-003 | 部分 | SOLVED、PARTIALLY_SOLVED、NEED_PLAN、UNKNOWN 路由；完整探索策略在 v1.2 |
| SC-004 | deferred_to_v1.2 | 预计划 Meta 与用户 Hint |
| SC-005 | 部分 | Plan 入口与版本字段；完整计划校验在 v1.2 |
| SC-006 | deferred_to_v1.2 | 逐步 Reasoner 与步骤报告 |
| SC-007 | deferred_to_v1.2 | 三类验证标签与证据 |
| SC-008 | deferred_to_v1.2 | Goal Gate、Logic Gate 与四类裁决 |
| SC-009 | deferred_to_v1.2 | 有界连续 Challenge |
| SC-010 | deferred_to_v1.2 | Trace-Back 与救援结果 |
| SC-011 | deferred_to_v1.2 | 持久 Meta 裁决 |
| SC-012 | deferred_to_v1.2 | Re-plan 与禁止方向 |
| SC-013 | deferred_to_v1.2 | 最终生成与整题审查 |
| SC-014 | deferred_to_v1.2 | 七类按需 Skill |
| SC-015 | 部分 | 仅 session 引用字段；完整四层会话在 v1.2 |
| SC-016 | 部分 | 状态、事件、revision 和恢复；完整归档协议在 v1.2 |
| SC-017 | 接口 | 仅定义 `ToolPolicy` 与默认拒绝 |
| SC-018 | 部分 | 模型/工具/时间硬门禁；完整预算体系在 v1.2 |
| SC-019 | 部分 | `ModelPort` 与真实用量字段；真实 Intern 在 v1.2 |
| SC-020 | 部分 | 错误分类；完整恢复在 v1.2 |
| SC-021 | 部分 | Solver 内部 JSON 结果；官方输出适配在 v1.2 |
| SC-022 | deferred_to_v1.2 | 完整 Feature Flag 与 Profile |
| SC-023 | 部分 | Solver 事件脱敏；完整审计在 v1.2 |
| SC-024 | 部分 | AC-SH-01..08；其余 AC 在 v1.2 |
| SC-025 | 部分 | v1.1 切片与验收记录；发布门禁在 v1.2 |
| SC-026 | deferred_to_v1.2 | 配对实验与成本统计 |
| SC-027 | 部分 | 验证级别字段，不把 LLM 审查标为形式化证明 |
| SC-028 | deferred_to_v1.2 | 四层记忆与正负账本 |
| SC-029 | deferred_to_v1.2 | 会话启动与恢复时的最新状态注入 |
| SC-030 | deferred_to_v1.2 | Session 注册、隔离与跨进程重建 |
| SC-031 | deferred_to_v1.2 | Meta 诊断与具体行动指令 |
| SC-032 | deferred_to_v1.2 | 强制纯推理与运行时工具禁用 |
| SC-033 | deferred_to_v1.2 | 后重规划的受限再探索 |
| SC-034 | deferred_to_v1.2 | `easy-verify` 预检 |
| SC-035 | deferred_to_v1.2 | 成果救援与禁止路线同步 |
| SC-036 | deferred_to_v1.2 | 整题审查角色差异 |
| SC-037 | deferred_to_v1.2 | 三层 Prompt、Skill 与权限组合 |
| SC-038 | deferred_to_v1.2 | 流式部分输出与幂等恢复 |
| SC-039 | deferred_to_v1.2 | 候选登记、版本与失效 |
| SC-040 | deferred_to_v1.2 | 预算门控与无模型调用的兜底选择 |
| SC-041 | deferred_to_v1.2 | 定性证据等级与可解释理由 |
| SC-042 | deferred_to_v1.2 | 比赛输出与内部元数据隔离 |
| SC-043 | deferred_to_v1.2 | 候选重放、计费与在途请求审计 |

### 7.3 AC 归属

| AC | v1.1 对应 | 说明 |
| --- | --- | --- |
| AC-01 | AC-SH-01 | 探索解出后的整题接受路径 |
| AC-02 | AC-SH-02 | 探索解出被拒后进入 Plan |
| AC-03 | AC-SH-03、AC-SH-04 | 部分解决与需要计划的路由；不调用 Meta 模型 |
| AC-04 | deferred_to_v1.2 | 非法计划的结构校验与有界修复 |
| AC-05 | 部分 | 整题审查拒绝不得标为通过；逐步 Goal Gate 延期 |
| STAR AC-06 | deferred_to_v1.2 | `easy-verify` 证据边界 |
| AC-07 | deferred_to_v1.2 | Challenge 会话 |
| AC-08 | deferred_to_v1.2 | Challenge 上限与升级 |
| AC-09 | deferred_to_v1.2 | Trace-Back |
| AC-10 | deferred_to_v1.2 | 非法 Trace-Back 目标 |
| AC-11 | deferred_to_v1.2 | Re-plan |
| AC-12 | deferred_to_v1.2 | Meta 跨计划持久化 |
| AC-13 | 部分 | AC-SH-02 覆盖拒绝路径；有界重试延期 |
| AC-14 | deferred_to_v1.2 | 超时、网络异常与受限重试 |
| AC-15 | AC-SH-05 | 进程重建后状态和事件一致 |
| AC-16 | AC-SH-07 | 预算耗尽后不再调用 |
| AC-17 | AC-SH-08 | 扩展未启用时无额外字段值或调用 |
| AC-18 | SH-01 | 官方冻结文件 hash 检查 |
| AC-19 | deferred_to_v1.2 | 工具权限与跨题隔离 |
| AC-20 | deferred_to_v1.2 | 配对实验 |
| AC-21 | deferred_to_v1.2 | 四层记忆 |
| AC-22 | deferred_to_v1.2 | 最新状态注入 |
| AC-23 | deferred_to_v1.2 | Session 注册与跨进程重建 |
| AC-24 | deferred_to_v1.2 | Meta 诊断 |
| AC-25 | deferred_to_v1.2 | 纯推理时工具不存在或被拒 |
| AC-26 | deferred_to_v1.2 | 后重规划探索 |
| AC-27 | deferred_to_v1.2 | 标签级预检 |
| AC-28 | deferred_to_v1.2 | 正负账本联动 |
| AC-29 | deferred_to_v1.2 | 结论证据隔离 |
| AC-30 | deferred_to_v1.2 | 整题审查来源差异 |
| AC-31 | deferred_to_v1.2 | 三层 Prompt |
| AC-32 | deferred_to_v1.2 | 断流恢复 |
| AC-33 | deferred_to_v1.2 | 同预算退化与隔离 |
| AC-34 | deferred_to_v1.2 | 候选累积 |
| AC-35 | deferred_to_v1.2 | 已推翻候选 |
| AC-36 | deferred_to_v1.2 | 回退失效传播 |
| AC-37 | deferred_to_v1.2 | 预算零调用兜底 |
| AC-38 | deferred_to_v1.2 | 无合格候选 |
| AC-39 | deferred_to_v1.2 | 同等级冲突 |
| AC-40 | deferred_to_v1.2 | 置信度边界 |
| AC-41 | deferred_to_v1.2 | 结果输出隔离 |
| AC-42 | deferred_to_v1.2 | 完全重放 |
| AC-43 | deferred_to_v1.2 | 在途请求超时 |
| AC-44 | deferred_to_v1.2 | 证据级别守恒 |

## 8. Tickets

以下工单是本规格的本地任务合同，尚未创建 GitHub Issue。

### SH-01：冻结 v1.1 基线并建立入口

**依赖：** 无  
**范围：** 文档状态、基线 hash、官方边界检查、v1.1 验收记录骨架  
**验收：** ADR-0013、v1.1 规格和 `docs/README.md` 入口存在；官方冻结文件 hash 与基线一致；没有产品调用。

### SH-02：状态、事件与 revision 事务

**依赖：** SH-01  
**范围：** `ProblemState`、`solver_states`、`solver_events`、`commit_transition`、恢复  
**验收：** AC-SH-05、AC-SH-06、AC-SH-08；三个既有回归文件未修改且通过。

### SH-03：ModelPort 与 Explore 阶段

**依赖：** SH-02  
**范围：** `ModelPort`、`ScriptedModelPort`、Explore 结果解析、预算门禁  
**验收：** AC-SH-03、AC-SH-04、AC-SH-07；测试零网络。

### SH-04：Explore 条件路由

**依赖：** SH-03  
**范围：** 纯函数转移与 LangGraph 条件边  
**验收：** AC-SH-01、AC-SH-02；两条分支均有独立断言。

### SH-05：整题审查与 v1.1 收口

**依赖：** SH-02、SH-04  
**范围：** `VerifierPort`、`ScriptedVerifierPort`、验收记录、全部 SC 归属检查  
**验收：** AC-SH-01..08 全绿；v1.2 延期项均有 ticket、依赖和用例；发布记录明确 `engineering-preview`。

## 9. v1.2 延期合同

v1.2 至少覆盖以下独立切片，具体 ticket 在 v1.1 关闭时生成：

| Slice | 覆盖需求 | 进入条件 |
| --- | --- | --- |
| 逐步推理与双 Gate | SC-006、SC-007、SC-008、SC-027；AC-05、STAR AC-06 | SH-05 关闭 |
| Challenge 与会话 | SC-009、SC-015、SC-028、SC-029、SC-030；AC-07、AC-08、AC-21、AC-22、AC-23 | 双 Gate 通过 |
| Trace-Back 与 Re-plan | SC-010、SC-011、SC-012、SC-031、SC-032、SC-033、SC-035；AC-09、AC-10、AC-11、AC-12、AC-24、AC-25、AC-26、AC-28、AC-29 | Challenge 通过 |
| 最终审查与输出 | SC-013、SC-021、SC-036；AC-13、AC-30 | Re-plan 通过 |
| Skills、工具与恢复 | SC-014、SC-017、SC-020、SC-034、SC-037、SC-038；AC-14、AC-19、AC-27、AC-31、AC-32 | 对应角色边界稳定 |
| Best-Effort 扩展 | SC-039、SC-040、SC-041、SC-042、SC-043；AC-34、AC-35、AC-36、AC-37、AC-38、AC-39、AC-40、AC-41、AC-42、AC-43、AC-44 | 候选与证据合同稳定 |
| 真实 Intern 与发布 | SC-019、SC-023、SC-026；`v0.2 AC-06`、AC-15、AC-16、AC-17、AC-18、AC-19、AC-20、AC-33 | 沙箱、计量和发布门禁通过 |

## 10. 验证命令

```text
uv run python -m unittest discover -s tests -p "test_*.py"
uv run python scripts/check.py --offline
```

前端命令不属于 v1.1 的实现验收；若改动 `showcase/frontend/`，另行执行 `npm ci --no-audit --no-fund`、`npm audit --audit-level=high` 和 `npm run check`。

