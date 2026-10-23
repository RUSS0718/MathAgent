# STAR 恢复缺口公共验收记录（SP-13 回归补齐）

日期：2026-10-24。分支 `feat/star-recovery-gap`，基点集成 tip `f77c3ec`。权威合同：`docs/engineering/star-product-recovery-gap-contract.md`。责任归属：AC-15/AC-32 属 #64/SP-08（`docs/evals/star-product-sp08.md`），AC-39/AC-40 属 #67/SP-11（`docs/evals/star-product-sp11.md`）。#64/#67 均已 closed；本记录是 SP-13 最终回归中对上述验收点的真实缺口修复与缺失验收覆盖补齐，不重开历史 issue，不修改任何旧验收记录的结论。所有证据为 fault_injection / scripted HTTP / 真实子进程退出，不是 live 数学效果；完整模式 `star_reference` / `star_best_effort` 保持 503 拒绝。

接缝沿用 #56/#64 已确认的公共边界：认证 ChatSession/Job、公共 resume/Run/report/Evidence/SSE、现有 Adapter/S3 RunBudget 账本/Solver 调度，未新建求解循环，未修改官方冻结文件（`user_agent.py`、`implementations/`、`BASELINE.json`、`requirements.txt`）。

## 切片一：AC-15 归档事务崩溃窗口（提交 `96604e7`）

| 触发 → 决策 → 实际动作 | 持久状态与用户结果 |
| --- | --- |
| 子进程在 s2 `step_reviewed`（verdict=TRACE_BACK，`trace_back_to=1`）已提交、归档事务 `trace_back_applied` 尚未提交时 `os._exit(71)` → 重启公共 resume（无 retry_call，202） | 复用已持久化 Verifier 回复应用归档：attempt-1 重执行 s1/s2/s3；公共 SSE 恰一次 `trace_back_applied`、五次 `step_reviewed`；总计 14 次出站/逻辑调用、0 unknown，原 deadline 保留；失败历史（archived_steps={s1,s2}、1 条 invalidated、0 rescued）注入重试 reasoner 上下文；最终整题审查仅含 attempt-1 的 3 条接受，旧接受不重复 |
| 子进程在归档事务 `trace_back_applied` 已提交后 `os._exit(71)`（`trace_after` 窗口） → 重启公共 resume | 直接从 STEP_EXECUTE@s1(attempt 1) 续算：同样 14 次出站、一次归档、不丢失败历史、不重复旧接受或计费；数学快照与归档同事务，重启两侧均无可分裂半提交状态 |
| `solver_states` 快照 revision 被一致改写为 999（无对应持久事件，幻影 checkpoint）→ 公共 resume 附带合法 retry_call | 修复前 202 接受并从幻影 revision 猜测续算；修复后 409 `star_recovery_revision_unavailable`，Job 保持 failed，零新增出站 |
| `workspace_jobs.problem` 改为 `2+2`（任务不匹配）→ 公共 resume 附带合法 retry_call | 修复前 202 接受、随后 job_execution_failed；修复后 409 `star_recovery_task_mismatch`，零新增出站 |

RED→GREEN 过程：四个公共用例先写失败断言。两个真实退出窗口（`trace_before`/`trace_after`，经 `tests/star_recovery_worker.py` 独立子进程与退出码 71）在集成 tip 上直接满足合同（现有 `apply_traceback` 单事务提交 + `resume_solver`/`harness.solve` 恢复路径已覆盖该精确窗口），如实记录为回归确认而非新实现；worker 仅为新窗口把预算扩到 16 次调用（归档后三步全部重执行需要 14 次）。真实 RED 缺口是两个拒绝用例：幻影 revision 与任务不匹配的 resume 均被 202 接受。最小实现位于 `showcase/star_product_recovery.py::authorize_resume`（同一 Job 控制事务内）：校验快照 `state_revision` 与行一致且 `solver_events` 中确实存在该 revision 的提交事件，校验任务 problem_hash 与快照一致，不满足即 409 拒绝；checkpoint 落后但 revision 真实存在的常规崩溃恢复不受影响（上方两个窗口用例证明）。

## 切片二：AC-32 流式片段恢复（提交 `a064db1`）

| 触发 → 决策 → 实际动作 | 持久状态与用户结果 |
| --- | --- |
| 服务端显式注入 `InternStreamAdapter`（新类，继承原 Adapter，仍经 `SHOWCASE_STAR_ADAPTER` 注入；默认 `InternModelAdapter` 保持整包不流式） | SSE `text_delta` 逐片经原 `calls._consume` 消费：每片由原 call_audit checkpoint 持久化后才向传输层索取下一片（传输伪造在发出第 N 片前核对第 N-1 片 partial_text 已入库）；完整包经原严格提供方 schema 校验通过才归一化为结果片段 |
| 流式 job 正常完成（explore/planner/reasoner/verifier/final 全链 6 次出站） | 公共 SSE 与 Evidence timeline 仅发布 `stream_metrics={fragments,bytes,status}`（仅片段数/字节数/状态）；片段原文、组合 prompt（"Obey this exact response schema"）、`partial_text` 键均不出现在 SSE/Job/报告/Evidence 任何公开输出；出站计量经原 S3 RunBudget 账本（logical/http 预留与结算，http_attempts=logical_calls=6），模型/工具上限不变 |
| reasoner 流第 2 片 `requests.Timeout` | 片段持久化但不解析为终态：调用保留 unknown_outcome 与原预留（reserved_tokens>0），公共 resume 无决策 409 `star_retry_decision_required`（零重发）；显式新调用 ID 重试后成功，deadline/预留不变，总计 7 次出站 |
| 流式完整包带未校准字段（`confidence: 0.95`，schema 不通过） | 不归一化：候选历史为空、调用 unknown/needs_review，公开输出无 0.95；显式新 ID 重试后成功（与 AC-40 同源反例，流式路径复验） |
| 子进程在 explore 流第 1 片已持久化、第 2 片索取前 `os._exit(71)`（`stream_exit` 窗口）→ 重启 | 保留 unknown/原预留，普通 resume 409；显式新 ID 重试全流程成功，总计 11 次出站、1 unknown，原 deadline 保留；中断片段文本不出现在任何公开输出，stream_metrics 只含计数 |

RED→GREEN 过程：RED 为 `ImportError: cannot import name 'InternStreamAdapter'`（暂存实现后测试文件即失败，能力缺失）。最小实现：`showcase/adapters.py` 新增 `InternStreamAdapter.stream_complete`（对注入客户端同一 api_base/凭据发起 `stream=True` SSE 请求，经 `current_budget().model_call` + `before_attempt/after_attempt` 走原 S3 计量，失败分类沿用 llm_client 类别）；`showcase/solver_harness/intern_port.py` 检测流式适配器后返回生成器（逐片转发、结果片前完成 finish_reason/空响应/JSON/严格 schema 校验，invocation 记录 stream 计数）；`showcase/star_product_events.py::decision_fields` 与 `showcase/evidence.py` timeline 白名单发布 `stream_metrics`。timeout 分类、unknown 保留与显式重试复用 SP-08 既有机制，未改 `calls.py`。GREEN：公共 Job 5 项验收（含真实 os._exit 窗口）全部通过。

## 切片三：AC-39 真实矛盾候选公共回放（提交 `d833454`）

| 触发 → 决策 → 实际动作 | 持久状态与用户结果 |
| --- | --- |
| 公共 Job 显式 `star_limited_best_effort`，Explore 产生 `x=1` 与 `x=2` 两个同等级完整候选（真实矛盾，非同值不同文本），预算 2 次调用用尽 | 候选历史保留两个矛盾版本；选择决定记录 `candidate_conflict`（reason_evidence 含双方公开 ID）、`confidence_level=low`；固定平局规则 `evidence-tier-then-candidate-id-v1` 选择确定 |
| 同一 Job 两次读取 `GET /api/agent/jobs/{id}/candidate-replay`，再重开服务读取 | 重放逐字节稳定；`matches_persisted_decision=true`，选中候选与持久决定一致；冲突证据等级仍为 low（`same_rank_candidate_conflict`），不高估；重放/重开零出站（2 次出站不变）；Run Evidence selection 与 Job 决定一致；公开输出不含任何数值概率 |

RED→GREEN 过程：按合同先写公共失败断言。对照集成 tip，该真实矛盾反例已由既有 `best_effort` 冲突记录与 `confidence` 定性等级机制满足，测试直接 GREEN——如实记录：本切片补齐的是 SP-13 最终回归中缺失的公共验收覆盖（精确到"真实矛盾非同值不同文本"与公共回放端点），未改变实现行为。

## 切片四：AC-40 未校准概率 schema 反例（提交 `6d87ac4`）

| 触发 → 决策 → 实际动作 | 持久状态与用户结果 |
| --- | --- |
| 公共 Job 注入 reasoner 步骤回复携带 `confidence: 0.95` | 严格提供方 schema（`additionalProperties: false`）拒绝为 `invalid_role_schema`：调用保留 unknown/needs_review，不归一化为候选（候选历史为空）；报告/Evidence/candidate-replay 公开输出无 0.95、无 confidence 字段、无 calibrated 表述 |
| 公共 Job 注入 step_verifier ACCEPT 回复携带 `confidence: 0.95` | 同样拒绝：公共 `step_reviewed` 事件不出现 ACCEPT verdict，步骤不被接受，公开输出无 0.95 |

RED→GREEN 过程：与切片三相同——公共反例在集成 tip 上已由既有严格 schema 满足，测试直接 GREEN，如实作为缺失验收覆盖补齐，不改实现。证据等级保持定性枚举，任何路径都不显示校准概率。

## 聚焦回归与检查记录（均为真实执行结果）

- `uv run python -m unittest tests.test_star_product_recovery tests.test_star_product_streaming_recovery tests.test_star_product_candidate_counterexamples -q`：34 tests PASS，65.4s（含新增 AC-15 4 项、AC-32 5 项、AC-39/40 4 项公共验收与 SP-08 既有 21 项恢复验收）。
- `uv run python -m unittest tests.test_star_product_best_effort tests.test_star_product_final_binding tests.test_star_product_budget tests.test_star_product_challenge tests.test_star_product_traceback tests.test_star_product_planning -q`：39 tests PASS，62.8s。
- `uv run python -m unittest tests.test_solver_harness_streaming tests.test_solver_harness_intern tests.test_solver_harness_candidates tests.test_solver_harness_sessions tests.test_solver_harness_finalize tests.test_solver_harness_traceback tests.test_adapters tests.test_sse_contract -q`：49 tests PASS，5.6s。
- `uv run python -m unittest tests.test_star_product_jobs tests.test_star_product_tools tests.test_star_product_runtime tests.test_star_product_summary tests.test_run_budget tests.test_solver_harness_star_routing -q`：34 tests PASS，14.6s。
- `uv run ruff check`（本次全部改动文件）：PASS。`tests/test_solver_harness_review_fixes.py` 存在 2 处先于本分支的 I001（tip 上即有，未触碰）；`tests.test_evidence_history` 以模块名直接运行存在先于本分支的导入错误（需在 tests 目录下运行），未触碰。
- 观察到一次未复现的偶发（首跑冷启动时 `wait_for` 8 秒观察窗）：同用例其后连续 19 次全部通过；如实记录，未改动产品代码。

## 边界

- 未跑全量/未跑 release 检查/未调用真实 Intern/未动 Docker：按合同仅聚焦恢复、流式、最终绑定、预算、候选相关回归；全量门禁由集成分支统一执行。
- 完整模式仍拒绝；本记录不宣称任何 live 数学能力。
- 流式注入是服务端可信配置（测试经 `SHOWCASE_STAR_ADAPTER` 显式注入 + 脚本 SSE 传输），不代表真实提供方已验证流式合同。
- 研究委派（researcher 线程池超时包装）在流式注入下超时语义退化为消费方迭代，本次切片未触及该路径（不在合同四点内），如实列为已知边界。
