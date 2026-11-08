# S05 公开产物与 UI 合同及退出记录

日期：2026-11-08（Asia/Shanghai）。工作分支：feat/faithful-s05。起点：47428eb7263cf2cb3a452df3967f81ffd88a8510。状态：工程退出通过（`engineering-preview`），图增量与最终门禁见 [S05/S07 工程验收](../evals/faithful-s05-s07-exit-20261108.md)。下方非图纵切与待完成列表保留当时快照。

依据 #144 阶段决议、#146、既有 S01/S03/S04 合同及本地 accepted Faithful implement-spec。S05 复用持久 Job/Run 事件、现有 STAR projection、ChatWorkspace、AgentTimeline 与 StarRunReview；不添加求解循环，不修改 solver_harness/**、配置入口或官方路径。

## 最小公开接口

- Run 的 progress_summary(state) 从同一持久状态生成公开进度。仅当该 Run 冻结的 problem_spec_policy.enabled 为真时，投影 root_obligations = {covered, total, items:[{ordinal,type,status}]} 和 plan_history = [{plan_version,attempt_index,status,step_count,outcome}]。不输出义务原文、内部 ID、假设或证明文本。
- 计划历史来自已保存的 failure_records：replan/problem-spec 变更保留 archived_plan，traceback 按 plan_version 与 attempt_index 保留重试尝试；当前计划来自该 Run 的 plan。历史记录只保留计划/尝试序号、状态、步骤数和失败类别。
- 时间线复用持久化脱敏事件的 role 与 created_at；浏览器读取只推进 Job 事件游标，不触发求解。SSE 与 report 继续以 Job/Run 身份隔离。
- 旧 Run 使用其已保存的 ProblemSpec 策略状态；关闭能力的 Run 保持原 progress shape，不能由服务器当前配置或刷新行为补启用。

## 验收合同

1. 用回归测试证明冻结 ProblemSpec 的安全根义务与多计划摘要，并证明关闭能力时 legacy shape 不变。
2. 浏览器端显示根义务真实覆盖数、计划/尝试历史、公开角色活动和持久时间线。长答案与历史产物可折叠查看；刷新后由 report/event 账本恢复。
3. 在 POST 回包丢失、SSE 重复/断开/重连、刷新和跨 Run 导航下，事件按持久 ID 去重，身份不串；只读请求不增加本地受控 provider 调用数。
4. 公共投影和 DOM 不暴露凭证、完整 prompt、隐藏答案、义务原文、证明正文或用户个人信息。
5. 浏览器测量仅使用真实本地受控 provider 经服务端持久化的事件。每条样本从 workspace_events.created_at 起算，到包含同一 SSE 事件 ID 的节点进入可见 DOM 为止。记录原始 UTC 时间、DOM 观察 UTC 时间和毫秒差；排序后 nearest-rank P95 使用 ceil(0.95*n) 的 1-based 样本。Route fulfill 或客户端构造事件不进入延迟样本。该受控本地结果不是 provider-live SLA。
6. S05 不呈现占位证明图或图深链；只在真实图生产者交付后增量接入。S06 Composer 与完整 F7 目标不在本切片。

## 非图纵切证据

- 实际 Job 测试覆盖一次 plan 内 traceback 重试与跨 plan replan；traceback 保留相同 plan_version 下不同 attempt_index。replan Job 以 `work_unit_prerequisites_incomplete` 失败结束，公开台账仍准确显示 root obligation 为 open，不伪报成功。
- 非图提交边界的聚焦回归：`uv run pytest -q tests/test_star_product_summary_s05.py tests/test_faithful_s05_history.py tests/test_faithful_s03_job.py tests/test_star_product_traceback.py`，14 passed in 24.66s。
- 专属真实 Chromium：`artifacts/faithful-s05-browser-run-06/`，4/4 passed；截图为该目录下 ProblemSpec 进度和长答案恢复 PNG。首轮夹具失败及 trace 被重跑覆盖情况见 `artifacts/faithful-s05/first-browser-failures.md`。
- 延迟从 SQLite `workspace_events.created_at` 起算，到浏览器可见且带同一 `data-event-id` 的 DOM 为止。原始 UTC 样本及算法记录于 `artifacts/faithful-s05-browser-run-06/faithful-s05-ProblemSpec-p-15bee-easured-persisted-event-P95/persisted-event-dom-latency.json`：47 个样本，nearest-rank ceil(0.95×47)=45，P95=441 ms。本地受控 provider 工程测量，不代表 provider-live SLA。
- 协调者对既有 product Chromium 回归证据：13/13 passed，53.8 秒，日志 `artifacts/faithful-s05/product-browser.log`，截图位于 `artifacts/faithful-s05-product-browser-20261108/`。
- 协调者对前端门禁证据：`artifacts/faithful-s05/frontend-install.log`、`frontend-audit.log`、`frontend-check.log`；npm ci/audit/check 全通过，audit 0 漏洞；Vite 513.49 kB 主包提示非阻塞。
- 首轮浏览器失败夹具已修为携带 ProblemSpec，并使用正确的 `/dashboard-assets/` 路由；生产合同未放宽。Playwright 重跑复用了 outputDir，首轮 trace 被覆盖，具体保留限制见失败记录。
- 未运行全仓长门禁；工程测试结果不表示数学能力提升。

## 尚待完成

本节为集成前历史列表，已由上述最终验收记录逐项更新；不作为当前阶段阻塞判断。

- 非图纵切 Standards/Spec 双轴只读审查由协调者独立执行；结果与修复情况待其返回后追加。
- `proof_graph_summary(state)` 惰性公开投影接线留作独立增量提交；需在 A 生产模块集成后验证真实 Job/report 输出。图消费接线完成前不宣称图 UI 验收。
- 图消费增量集成后，由协调者按冻结集成源码执行最终门禁，并区分门禁源码 SHA 与最终交接 SHA。

工程可运行性证据不表示 provider-live、SLA 或数学能力已通过。
