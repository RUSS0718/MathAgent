# F6 全量门禁 42 项 skip 审计

审计对象：`artifacts/final-gates/faithful-f6-20261111-02/repository-check/diagnostics.log`，对应冻结源码 `c1d17bc347b7fd185a905a1b86457fb63358377b`。门禁结果为 1832 项、0 failure、0 error、42 skip；skip 不计通过。诊断日志重复输出同一清单，按唯一测试 ID 去重后仍为 42 项。

## 原因分类与覆盖判断

| 数量 | 原因 | 测试范围 | L2/L3 关联判断 |
| ---: | --- | --- | --- |
| 10 | 未设置经验证的精确本地 Python Docker image ID | `test_python_executor_docker` 7 项、`test_star_product_python` 3 项 | 隔离 Python 执行和工具回执，不判定 F3 L2/L3 |
| 22 | 缺少经独立验证的本地 Docker image ID | STAR full reference / proof / recovery / protocol 等端到端链 | 一项 classified outcomes 校验 `llm_reviewed`/`tool_verified` 等证据等级，但不是 F3 L2/L3；其余不直接断言 L2/L3 |
| 8 | Docker Reference 链缺少经验证 image ID | RB02 计算 6 项、RB06 恢复 2 项 | 真实隔离计算与恢复，不直接判定 L2/L3 |
| 2 | 未启用 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` | readiness archive/coordinator | Provider/Reference 集成，不判定 L2/L3 |

**L2/L3 覆盖结论：**42 项中没有一个测试以 F3 `L2`/`L3` 判级为其直接断言目标；部分跳过项检查 `llm_reviewed`、`tool_verified` 等 Harness 证据等级，不能与形式化等级混称。F6 等级投影的非 skip 定向测试为 `tests.test_faithful_f6_presentation.FaithfulF6PresentationTest.test_l2_evidence_has_a_versioned_target_reference_without_upgrading_original_answer`。真实 Lean 与原题对应证据另见 S09 公共 Job/Report/Evidence 与浏览器记录：`docs/evals/faithful-s09-20261109.md`、`artifacts/faithful-s09-public-real-final-02/public-acceptance.json`、`browser-l2-report.json`、`browser-l3-report.json`、`artifacts/faithful-s09-public-route-evidence-final/{l2,l3}-desktop.json`。这些运行中 L2 与 L3 各有实际公共 Job，Report/Evidence 等级一致；它们是独立专项证据，不将 42 个 skip 记成通过，也不声称在 F6 最终门禁进程内重新运行 Lean。

## 唯一 skip ID 与报告原因

前 10 项的报告原因均为 `set MATHAGENT_TEST_PYTHON_IMAGE to a validated local exact image ID`。

- `test_python_executor_docker.DockerExecutorTest.test_cancellation_kills_a_sleeping_container`
- `test_python_executor_docker.DockerExecutorTest.test_container_restrictions_have_actual_failure_examples`
- `test_python_executor_docker.DockerExecutorTest.test_cpu_limit_terminates_a_busy_loop`
- `test_python_executor_docker.DockerExecutorTest.test_external_guard_catches_direct_fd_and_combined_streams`
- `test_python_executor_docker.DockerExecutorTest.test_fixed_mathematical_environment_actually_executes`
- `test_python_executor_docker.DockerExecutorTest.test_product_default_cpu_budget_runs_multi_second_computations`
- `test_python_executor_docker.DockerExecutorTest.test_timeout_kills_container_with_descendant`
- `test_star_product_python.StarProductPythonTest.test_public_job_output_limit_keeps_finite_claim_unverified`
- `test_star_product_python.StarProductPythonTest.test_public_job_policy_denial_never_dispatches_python`
- `test_star_product_python.StarProductPythonTest.test_public_job_runs_registered_python_once_and_keeps_verified_artifacts`

以下 22 项要求 independently validated local Docker image ID：

- `test_star_product_align_recovery.StarFullReferenceChainTest.test_reference_chain_completes_with_real_isolated_computation`
- `test_star_product_classified_outcomes.StarFullReferenceClassifiedOutcomeTest.test_reference_classified_computation_carries_real_isolated_receipt`
- `test_star_product_continue_identity.StarFullReferenceContinueTest.test_reference_continue_completes_new_action_and_whole_review`
- `test_star_product_explore_compute.StarFullReferenceExploreComputeTest.test_reference_explore_executes_own_isolated_computation`
- `test_star_product_full_modes.StarFullModeTest.test_capabilities_expose_verifiable_preflight_artifact_reference`
- `test_star_product_full_modes.StarFullModeTest.test_capabilities_expose_verifiable_preflight_budget_ledger`
- `test_star_product_full_modes.StarFullModeTest.test_each_core_feature_missing_or_disabled_rejects_before_enqueue`
- `test_star_product_full_modes.StarFullModeTest.test_full_best_effort_deadline_selects_only_previously_committed_candidate`
- `test_star_product_full_modes.StarFullModeTest.test_full_best_effort_selects_after_one_call_and_replays_without_dispatch`
- `test_star_product_full_modes.StarFullModeTest.test_full_flag_does_not_upgrade_limited_mode_or_default_legacy`
- `test_star_product_full_modes.StarFullModeTest.test_full_options_and_disabled_review_reject_before_model`
- `test_star_product_full_modes.StarFullModeTest.test_full_unknown_call_requires_new_identity_and_preserves_shared_deadline`
- `test_star_product_full_modes.StarFullModeTest.test_reference_easy_problem_completes_fastpath_review_and_binding`
- `test_star_product_full_modes.StarFullModeTest.test_reference_preset_is_exactly_nine_core_features_and_registry_inactive`
- `test_star_product_full_modes.StarFullModeTest.test_reference_runs_same_public_job_with_real_tool_and_whole_review`
- `test_star_product_full_modes.StarFullModeTest.test_runtime_isolation_failure_after_startup_rejects_without_model_or_job`
- `test_star_product_guidance_consumption.StarGuidanceConsumptionTest.test_reference_preset_second_traceback_consumes_only_the_new_meta_ruling`
- `test_star_product_protocol_failure.StarFullReferenceProtocolFailureTest.test_full_reference_planner_invalid_json_repairs_with_new_identity`
- `test_star_product_protocol_failure.StarFullReferenceProtocolFailureTest.test_full_reference_reasoner_invalid_json_is_known_failure_and_ends_dispatch`
- `test_star_product_replan_decision.StarReplanDecisionTest.test_reference_preset_rulings_cover_all_three_branches`
- `test_star_product_tool_ceiling.StarReferenceToolCeilingTest.test_reference_finishes_after_last_isolated_tool_call`
- `test_star_product_verifier_compute.StarFullReferenceVerifierComputeTest.test_reference_step_verifier_executes_own_isolated_computation`

以下 8 项要求 validated exact local Docker image：

- `test_star_rb02_computation.ComputationJobTest.test_execution_error_still_triggers_guidance_without_comparison`
- `test_star_rb02_computation.ComputationJobTest.test_explicit_match_still_promotes_only_finite_claim`
- `test_star_rb02_computation.ComputationJobTest.test_expression_without_stdout_cannot_back_computation_outcome`
- `test_star_rb02_computation.ComputationJobTest.test_output_without_expected_continues_review_without_meta`
- `test_star_rb02_computation.ComputationJobTest.test_stdout_from_failed_execution_is_available_but_not_compared`
- `test_star_rb02_computation.ComputationJobTest.test_true_mismatch_still_triggers_bounded_guidance`
- `test_star_rb06_recovery.RobustRecoveryTest.test_real_receipt_exit_resumes_numeric_review_once_with_original_ledger`
- `test_star_rb06_recovery.RobustRecoveryTest.test_reference_receipt_exit_resumes_same_job_through_final_review_and_binding`

以下 2 项要求启用 Docker readiness 集成环境：

- `test_star_readiness_archive_retention.StarReadinessArchiveRetentionTest.test_delivery_archive_failure_retains_terminal_job_and_sqlite_budget_ledger`
- `test_star_readiness_coordinator.StarReadinessCoordinatorTest.test_real_experiment_server_runs_both_jobs_through_loopback_provider`

## 边界

此审计只确认 skip 原因和测试目标，不把 skip 改标通过。Docker/Reference 覆盖仍为未运行状态，除非另有相同源码与固定镜像身份的专项报告。F7 浏览器主路径必须使用真实 F6 输出和锚点；synthetic 数据仅用于明确标识的图渲染压力测试。

## F7 复核

F7 冻结源码 `1da9aee2e0b4d83a0e3837575762496e452acc57` 的 `faithful-f7-20261111-01` 最终门禁为 1844 项、0 failure/error、42 skip。按唯一测试 ID 与原因逐项比对，这 42 项与上述 F6 清单完全一致。F7 另实际执行固定 Docker Lean L2/L3 交付物的浏览器验收，证据与未验证范围见 [F7 分层验收记录](faithful-f7-20261111.md)；专项通过不改变这些 skip 的状态。
