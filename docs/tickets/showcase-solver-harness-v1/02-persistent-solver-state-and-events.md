# 02: 持久化 Solver 状态、事件与 revision

**What to build:** 开发者可以用同一 `run_id` 创建 Solver Run，保存初始 `ProblemState`，并经由新实例读取一致的状态和事件。

**Blocked by:** #01

**Status:** ready-for-agent

**Acceptance criteria:**

- [ ] Solver 状态和事件写入 Showcase 共用 SQLite 文件中的独立表。
- [ ] 新实例读取同一 `run_id` 时得到相同状态、事件序列和 `state_revision`。
- [ ] 恢复时校验 `problem_hash`、`config_hash` 和 Run 身份。
- [ ] `solver_states`、`solver_events` 与现有 Run 表互不污染。
- [ ] 扩展字段 `candidate_registry`、`best_effort_decision`、`finalization_reason` 默认 `None`。
- [ ] 支持 STAR AC-15 的跨实例恢复和 STAR AC-17 的默认关闭字段。
