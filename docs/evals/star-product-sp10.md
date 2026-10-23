# SP-10 产品整题审查与 S4 验收

日期：2026-10-23。归属 #66 / SP-AC-18；开发基点为 `showcase-star-product@8f6f4f8`，实施合同见 `docs/engineering/star-product-sp10-contract.md`。

## 证据类别与结论

本片为 scripted/fault-injection 工程验收。公共认证、ChatSession、Job、Adapter、S3 账本、Solver、SQLite、报告与 Evidence 均使用产品路径；仅提供方 HTTP 回复可控。没有真实 Intern 调用或数学效果结论。固定来源审计中的 SC-036 / AC-30 由本片承担：步骤或 Meta 的 ACCEPT 不能替代新整题 Verifier；遵循论文最终审查要求，不复制上游 `orchestrator_solve.py:481–487` 在审核调用失败后仍接受答案的失效开放行为。上游全量逐项独立复核由 SP-13 负责。

## 同一 Run 的可复现链

| 触发 | 决策与实际动作 | 持久状态与用户结果 | 公共验收 |
| --- | --- | --- | --- |
| Explore SOLVED | 同会话润色，新的整题 Verifier 审查润色文本 | 原稿/润色稿各有身份；来源包含 Run、调用、计划、尝试及候选版本；报告与 Evidence 一致 | `test_explore_review_binds_delivery_and_preserves_versions` |
| 步骤双 Gate 接受 | final_generator 生成整题文本；REJECT 后带原审查意见重新生成并使用新 Verifier 会话 | 被拒和被接受文本各自追加观察；仅当前实际接受版本交付 | `test_reject_retries_are_bounded_and_actual_accepted_version_is_bound` |
| 连续三次整题 REJECT | 达到默认两次重试上限 | failed / partial_aborted；不显示 completed_llm_reviewed；10 次出站调用 | `test_repeated_reject_exhausts_without_reviewed_delivery` |
| 送审后交付改写 | S4 比较交付身份与实际审查对象 | 原观察保留，artifact_changed / unknown / needs_review；公开 Solver 状态降级 | `test_delivery_rewrite_cannot_inherit_whole_review` |
| 模型伪造审查引用、内部错误绑定另一文本/不存在调用 | 严格角色回复 schema；产品层核对持久 completed whole_solution_verifier 调用、实际 request 文本和 ACCEPT response | 公共交付失败；不能由非空引用或步骤意见代替审核 | `test_forged_review_reference_cannot_replace_actual_review`、`test_another_artifact_in_persisted_review_cannot_pass_public_delivery`、`test_nonexistent_audited_call_cannot_serve_as_review_reference` |
| 两个 app/SQLite 连接同时追加候选检查 | 原有 BEGIN IMMEDIATE 事务串行读最新版本并追加 | 原答案与首条整题审查保留，共三条观察；Job/Run/报告/Evidence 一致，不新增模型调用 | `test_cross_connection_append_keeps_original_whole_review_and_answer` |
| Trace-Back 后继续 / Meta Replan | 原错误成果失效，合法独立救援与当前计划成果送审 | 最终绑定当前 plan_version/attempt_index；事实以不泄漏私有 step_id 的身份与救援标记追溯 | `test_star_product_traceback.py` 两条公共流程 |

S4 的 checker_version 为 `star-whole-review-v1`，scope 为 `whole_solution_llm_review`，每条观察保留稳定 check_id、Python 环境、limitations。LLM ACCEPT 仅说明完成整题模型审查；数学 correctness/completeness 仍为 unknown。polynomial 追加只支持其有限候选范围，不升级整题证明。工具输出与可解析产物沿用 SP-09 的既有 Evidence 路径，本片未重新运行 Docker 隔离实验。

## TDD 与发现的问题

先建立公开接缝合同，再运行失败用例。最初 Explore 验收缺 checker_version；伪造不存在审查调用的反例在修复前错误 succeeded；候选版本/观察 check_id 缺失用例分别先失败。Trace-Back/Replan 验收还复现合法救援事实在 final_generator 前被丢弃，现仅允许当前账本明确保留的 rescued_results 通过既有事实过滤。交付改写反例识别了终态 Solver 原文本 reviewed 与交付对象状态的区别，查询投影按持久交付对象降级。

首次全部 STAR 回归为 72 tests、3 skipped、6 个隐私子用例失败：新增事实来源暴露模型生成的私有 step_id。现来源/依赖改为 opaque hash 引用，摘要只公开 statement artifact；修复验证记录见实际检查结果。两项内部故障注入仅用于父 spec 明确要求的旁路敏感性，不作为正常求解替代物。

## 实际检查结果

- 聚焦与相关回归：36 tests PASS，35.571 秒（`PYTHONPATH=tests`，最终绑定、Trace-Back、Job、finalize、S4、history、planning、sync evidence）。最初直接模块执行旧 S4 测试时因其同目录 import 失败；设置与 discover 相同的 tests 搜索路径后通过，没有改变运行时依赖。
- 隐私、最终绑定与 Trace-Back 聚焦：16 tests PASS，23.653 秒。
- 全部 STAR 产品回归：`uv run python -m unittest discover -s tests -p "test_star_product_*.py" -q`，72 tests PASS，3 skipped，131.410 秒。skipped 不计为对应能力通过。
- 改动文件 `uv run ruff check` 与 `git diff --check`：PASS。
- `check_showcase_release.check_baseline()`：`official_baseline=PASS`，冻结字节及官方导入边界通过；相对 `8f6f4f8` 的 `user_agent.py`、`implementations/`、`BASELINE.json`、`requirements.txt` 无差异。
- 已执行 `git merge showcase-star-product`：Already up to date，集成仍为 `8f6f4f8`。
- 曾启动完整 release 脚本，发现其包含全量测试后主动终止自身进程；未声明该次 release PASS。按主代理分工，完整 offline/release/前端门禁在合并后的集成分支统一执行，本片没有重跑全量门禁。

## 已知边界与后续

完整 reference / best_effort 模式仍拒绝启动。SP-08 负责安全阶段恢复，SP-11 负责完整候选账本及零调用选择，SP-12 负责 Workbench 生命周期展示，SP-13 负责真实 Intern 批次、上游独立复核及全量发布门禁。这里没有以离线通过替代 live，未触发 Docker/研究委派/恢复路径不计本片新增能力证据。
