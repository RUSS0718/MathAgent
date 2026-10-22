# Solver Harness v1.1 验收记录

**状态：** engineering-preview

**验收日期：** 2026-10-22

**对应规格：** [GitHub Issue #32](https://github.com/RUSS0718/MathAgent/issues/32)，SH-01..SH-05（#33..#37）。

## 离线验收结果

接缝为 `SolverHarness.solve()` 和 `SolverHarness.get_run()`。环境为 Windows、uv 管理的 CPython 3.12.13；测试使用临时 SQLite、`ScriptedModelPort` 和 `ScriptedVerifierPort`，未请求真实模型或工具。

下表测试名均位于 `tests/test_solver_harness_*.py`。2026-10-22 执行 `uv run python -m unittest discover -s tests -p "test_solver_harness_*.py"`：25 项通过，其中 `test_solver_harness_review.py` 的 8 项通过。

| 验收 | 实际测试 | 结果 |
| --- | --- | --- |
| AC-SH-01 | `test_accept_completes_without_plan_and_survives_recovery` | PASS：审查 ACCEPT 后状态为 `completed_llm_reviewed`，答案非空，无 Plan 路由 |
| AC-SH-02 | `test_reject_preserves_findings_and_hands_off_to_plan` | PASS：独立拒绝分支保留候选、worked、failed，进入 PLAN，未标记通过 |
| AC-SH-03 | `test_need_plan_routes_directly_to_plan_without_meta`、`test_unknown_routes_directly_to_plan_without_meta` | PASS：直接交接 Plan，只有 Explore 请求 |
| AC-SH-04 | `test_partial_exploration_gets_one_retry_then_routes_to_plan` | PASS：配置探索上限为 50 时仍只探索两轮 |
| AC-SH-05 | `test_run_state_events_and_revision_survive_harness_recreation`、`test_reviewed_state_and_events_survive_new_harness` | PASS：新 Harness 实例读取相同状态、事件与 revision |
| AC-SH-06 | `test_stale_revision_does_not_overwrite_a_successful_commit`、`test_replaying_the_same_event_does_not_add_a_revision_or_event` | PASS：拒绝过期写入，相同事件幂等 |
| AC-SH-07 | `test_exhausted_budget_returns_explicit_result_without_dispatch`、`test_partial_retry_checks_remaining_budget_before_dispatch`、`test_review_budget_exhaustion_adds_no_verifier_call` | PASS：耗尽后不再派发，返回合法 JSON 状态 |
| AC-SH-08 | `test_default_initialization_dispatches_no_calls`、`test_extensions_stay_none_without_added_calls`、`test_reviewed_state_and_events_survive_new_harness` | PASS：三个扩展字段保持 None；默认初始化零调用，Plan 交接不调用 Verifier |

普通预算耗尽原因记录在 `budget.exhaustion_reason` 和预算事件中，`finalization_reason` 仍为 `None`。整题审查派发占用一个 `counters.model_calls`，默认两次调用预算可覆盖一次 Explore 和一次审查。

附加边界测试通过：未配置 Verifier 时返回 `completed_unverified` 和非空未验证说明；非法裁决或空候选不能完成审查；Verifier 异常返回 `failed_runtime`，异常原文不写入结果。相同 Run 再次 `solve()` 不重复调用。

## 回归与仓库检查

| 命令 | 实际结果 |
| --- | --- |
| `uv run python -m unittest discover -s tests -p test_run_persistence.py` | PASS，3 项 |
| `uv run python -m unittest discover -s tests -p test_showcase_run.py` | PASS，6 项 |
| `uv run python -m unittest discover -s tests -p test_run_budget.py` | PASS，12 项 |
| `uv run ruff check showcase/solver_harness tests/test_solver_harness*.py` | PASS |
| `uv run ruff format --check showcase/solver_harness/review.py tests/test_solver_harness_review.py` | PASS |
| `uv run python -c "from scripts.check_showcase_release import check_baseline; check_baseline(); print('baseline_hash=PASS')"` | PASS，官方冻结文件 hash 一致 |
| `git diff --check` | PASS |
| `git diff --numstat 979d944 -- tests/test_run_persistence.py tests/test_showcase_run.py tests/test_run_budget.py` | 无输出，三个既有回归文件未修改 |

最终执行 `uv run python scripts/check.py --offline`：PASS，215 项测试通过（157.271 秒），`workspace_contract=PASS`、`contract_test_seams=PASS`，Demo 与 Showcase 的 `--help` 均成功，最终输出 `repository_check=PASS`。该运行包含既有凭证无关发布门禁的嵌套检查。

开发期间第一次完整检查与新增未验证状态用例的 RED 阶段重叠，嵌套发布检查读取了尚未实现的期望并失败。代码稳定后重新完整执行，以上述最终结果为准。

本切片工作树从集成提交 `979d944019f16478fcb808e150f759328d995162` 开始；收口时集成 tip 仍为该提交。

## SC 归属与版本边界

[父 Issue #32 的 SC-001..SC-043 主归属表](https://github.com/RUSS0718/MathAgent/issues/32) 是需求拆分的权威记录。父表中的多 ticket 项表示前后依赖切片，只有最后依赖完成才可声明关闭。下表按完成整个 SC 的最终责任 ticket 归并；前置实现仍按父表归属验收，不因本记录改写。

| 最终责任 ticket | SC 编号 | 版本 |
| --- | --- | --- |
| SH-03 #35 | 016 | v1.1 |
| SH-04 #36 | 018 | v1.1 |
| SH-05 #37 | 003 | v1.1 |
| SH-06 #38 | 006 | v1.2 |
| SH-07 #39 | 002、005、008 | v1.2 |
| SH-08 #40 | 009 | v1.2 |
| SH-09 #41 | 010、035 | v1.2 |
| SH-10 #42 | 011、031、032 | v1.2 |
| SH-11 #43 | 004、012、033 | v1.2 |
| SH-12 #44 | 015、028、029、030 | v1.2 |
| SH-13 #45 | 014、037 | v1.2 |
| SH-14 #46 | 007、017、020、034 | v1.2 |
| SH-15 #47 | 013、036 | v1.2 |
| SH-16 #48 | 038 | v1.2 |
| SH-17 #49 | 039 | v1.2 |
| SH-18 #50 | 040 | v1.2 |
| SH-19 #51 | 027、041 | v1.2 |
| SH-20 #52 | 021、042、043 | v1.2 |
| SH-21 #53 | 019 | v1.2 |
| SH-22 #54 | 022、023、026 | v1.2 |
| SH-23 #55 | 001、024、025 | v1.2 |

每个 SC 编号在此表只出现一次。v1.1 的局部实现不等于整个跨版本 SC 已关闭。STAR AC-01、STAR AC-02、STAR AC-17 对应本次接受、拒绝和扩展默认值测试；其他 STAR AC 的最终关闭仍按父 Issue 执行。

## 已知能力限制

- `v0.2 AC-06` 仍为 `unavailable`，真实 Intern 工具闭环延期至 v1.2。
- 本记录证明离线工程行为；没有真实 Intern、独立数学正确率或能力提升证据。
- Plan 仅为状态交接；完整逐步双 Gate、Challenge、Trace-Back、Meta、Re-plan、会话记忆、Skills、工具执行、流式恢复和 Best-Effort 候选选择未由 v1.1 证明。
- `completed_llm_reviewed` 表示脚本审查流程接受，不等于数学证明。运行中崩溃的请求恢复及未知计费结果仍需 v1.2 的独立验收。
- 产品版本为 v1.1；包版本为 `0.1.0`，前端版本为 `0.2.0`，Profile 为 `showcase_mvp`。官方路径保持独立。
