# ADR-0013：Solver Harness v1.1 的 Showcase 边界与共享事务

**状态：** accepted

**日期：** 2026-10-22

**范围：** `showcase-solver-harness-v1` 的 v1.1

## 背景

STAR Core 文档要求实现确定性的探索、规划、逐步验证、质询、回退、重规划和预算兜底。当前仓库没有 `harness_lab/`，已有的产品面是 `showcase/`；`showcase_mvp` 已经承载 Run、Job、SSE、持久化和 Evidence。

v0.2 的工程合同已实现，但真实 Intern 工具闭环（`v0.2 AC-06`）仍为 `unavailable`，因此 v0.2 只能标记为 `engineering-preview`。后续开发不能再造一个平行产品面，也不能把 Solver Harness 接入冻结的官方打榜路径。

## 决策

1. Solver Harness 作为 `showcase/solver_harness/` 进入现有产品面，不新建 `harness_lab/` 或第二个顶层实验包。
2. 产品版本演进为 v1.1，但 `pyproject.toml` 的包版本保持 `0.1.0`，前端版本保持 `0.2.0`，Profile 字符串保持 `showcase_mvp`。这些是不同维度的版本或合同标识，不做隐式同步升级。
3. v0.2 文档保留原名并标记为历史合同；v1.1 使用新的实现规格承载当前范围和验收。
4. v1.1 只交付 S1 与 S2：可恢复内核、确定性 Explore 路由、Plan 交接、最小整题审查，以及预算耗尽时的合法结果。完整 Meta、逐步双 Gate、Challenge、Trace-Back、Re-plan、真实工具和 Best-Effort 扩展进入 v1.2。
5. v1.1 不宣称真实 Intern 工具闭环、STAR 完整复现或数学正确率提升。`v0.2 AC-06` 继续以 `engineering-preview` 的历史事实存在，并在 v1.2 处置。
6. Solver Harness 与现有产品 Run 共用同一个 SQLite 文件、连接和事务边界，但使用 `solver_states` 与 `solver_events` 两张表，避免污染 `runs` 的 v0.2 快照形状。
7. 新表在 `showcase/storage.py` 的 `SQLiteStore.__init__` 中创建；Solver Harness 的读写方法和 `state_revision` 比较交换放在 `showcase/solver_harness/storage.py`。现有 `showcase/storage.py` 的旧表与旧方法不改变行为。
8. S1 使用纯 Python 协议与状态机；S2 再引入 LangGraph 的条件路由。LangGraph checkpoint 不成为第二份业务权威状态。
9. 模型调用通过薄 `ModelPort` 复用现有 `showcase/adapters.py` 的传输、重试和用量处理。v1.1 的回归测试只使用 `ScriptedModelPort`，真实 Intern 适配与 live 证据进入 v1.2。
10. `ProblemState` 从第一版保留 `candidate_registry`、`best_effort_decision` 和 `finalization_reason` 三个可选字段，默认 `None`；只有对应 Feature Flag 启用后才变成具体值。

## 理由

共用 Showcase 产品面保留现有 Run、Job、SSE、Evidence 和发布门禁，不需要维护两套认证、存储和前端入口。把 STAR 状态放入独立表，既避免改变 `RunService.get_run()` 的公开快照，又保持一个数据库和一个事务边界。

先做纯 Python 内核，可以把状态、预算和事件合同在引入图调度前固定下来。早期使用 LangGraph 会让 checkpoint 与业务快照的权威关系尚未定义时就被迫绑定实现。

v1.1 只覆盖两条可观察的 Explore 分支，能够证明条件路由不是写死的单路径，同时把真实模型、工具和完整 STAR 机制的风险留在后续独立切片。

## 被否决的方案

- **新建 `harness_lab/star_core/`：** 与仓库现状和产品面不一致，会形成第二套入口、存储和文档边界。
- **把 Solver Harness 状态写入 `runs.snapshot_json`：** 会改变现有产品 Run 的公开快照形状，破坏 v0.2 API 合同。
- **在 `showcase/solver_harness/` 内新建 SQLite 连接：** 在同一个产品面内制造第二个事务边界，恢复时无法可靠对账。
- **v1.1 引入完整 LangGraph 与 Meta：** 超出 S1/S2 范围，提前引入会话、账本和图恢复问题。
- **七个 Skill 全部创建空文件：** 不符合按需加载，也不能证明任何 Skill 真正被调用。

## 后果

- `showcase/storage.py` 会增加两张表的建表语句，但旧表和旧方法保持兼容；三个既有测试文件必须原样通过。
- v1.1 的 `ProblemState` 是受限合同，不包含完整四层记忆、逐步验证和 Best-Effort 选择。
- 版本号会暂时出现“产品 v1.1、包 0.1.0、前端 0.2.0、Profile `showcase_mvp`”的差异，必须在规格和发布记录中明确说明。
- 任何改变官方 `user_agent.py`、`implementations/`、默认预算或 baseline 的变更，都超出本 ADR。
- v1.2 必须为每个延期需求提供本地 ticket、依赖和验收用例，才能关闭 v1.1。
