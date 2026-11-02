# SP-11 公共候选与 Best-Effort 验收

日期：2026-10-23；责任 #67 / SP-AC-19、SP-AC-20；合同见 `docs/engineering/star-product-sp11-contract.md`。基点 871f709，已合并集成 17a4c81 的独立反证协议。证据均为 fault_injection / scripted HTTP 或 replay，不是 live 数学效果。

## 产品行为与同一 Run 证据

用户在现有认证 Job API 显式指定 `solver_mode=star_limited_best_effort`；身份 `preset_version=sp11-v1`。该模式仅在服务器启用受限 STAR 后可用，沿用可信 features、原 S3 账本、Registry、数学状态和 Job/checkpoint；不接受 HTTP feature patch。`star_reference` / `star_best_effort` 继续 503，完整能力不在此宣称。

| 触发 → 决策 → 动作 | 持久状态与用户结果 | 证据 |
| --- | --- | --- |
| Explore 一次调用用完额度 → 纯选择 → 不派发润色/Verifier | 同 Run candidate_history、best_effort、非空答案及 S4 selection | public test `test_explicit_limited_best_effort_selects_without_extra_call` |
| 两个完整 Explore 版本 → 同级文本不同 → 保留冲突 | 固定规则选择 `1+1=2`，两个版本保留，等级 low，无概率 | `test_conflict_retains_both_complete_candidates_and_qualitative_grade` |
| Challenge 更新完整答案 → 实际 Verifier 接受新文本 | 旧候选不继承 ACCEPT；Step 两版独立历史；Final 独立生成/审查版本 | `test_challenge_review_only_updates_the_actual_complete_candidate` |
| Trace-Back → 区间失效 → 排除旧错误及依赖候选 | 只交付独立 safe answer，失效候选保留追加历史及排除理由 | `test_traceback_excludes_complete_candidates_from_invalidated_dependencies` |
| 独立反证 FOUND → 将实际候选标 refuted → 不选择 | 无合格候选，保留诚实说明；5 次原账本调用后无额外调用 | `test_independent_counterexample_refutes_candidate_before_budget_selection` |
| model/HTTP/tool/token 额度或 deadline → 确定性终止 | 模型/Verifier/工具不再派发；本地 token 准入拒绝不冒充 unknown HTTP | 对应公共预算测试 |
| deadline 后迟到润色 → 只保留原候选 | 迟到用量结算、数学结果不采纳、unknown 调用保留；纯选择事务重新计算相等后才准许提交 | `test_deadline_finalizes_only_persisted_candidates_and_retains_late_unknown` |
| 取消与 deadline 竞争 → 取消优先 | canceled 不发布迟到候选，不执行选择 | `test_cancel_beats_expired_pure_selection_and_cannot_publish_late_candidate` |
| 相同持久快照 replay / 重开服务查询 | 决定一致、快照 hash 一致、版本和历史不变、零外部调用 | `test_reopened_job_and_replay_are_immutable_and_do_not_dispatch` |

公共只读入口为 `GET /api/agent/jobs/<job_id>/candidate-replay`，先按原 Job 所有权鉴权，再从同一事务读取 Solver 状态与事件。返回 `evidence_kind=replay`、audit 和白名单 decision；不恢复 Harness、不执行选择写入。Job/Run、报告和 Evidence 的 `solver` 提供候选历史与决定。引用公开为不透明身份，省略 prompt、会话历史、角色状态、内部请求、problem_hash 和原始选择源记录；`export_result` 仍仅允许 `final_response`。

## RED、旁路与检查

实际 RED：新模式最初 400；Challenge 候选因严格 schema 被拒绝；独立反证候选仍 eligible；HTTP 上限后没有选择；token 准入拒绝成为 interrupted；deadline 封存后无 final_response。每个失败后实施最小接线，再运行公共测试成为 GREEN。

最小旁路将纯 selector 替换为强选已反驳候选，公共无候选验收确实触发 AssertionError；交付文本被改写时，S4 `artifact_changed`、`needs_review`，不能继承所选对象的绑定。

已运行：

- 公共 SP11 聚焦用例 14 项 PASS（含工具硬上限的单项检查）；不包含真实提供方调用。
- 候选、BestEffort、纯 replay、独立反证相关 34 项 PASS；随后新增的 SP11 用例另由聚焦检查覆盖。
- 较早公共 STAR 产品回归 95 项 PASS，3 项环境跳过；共享预算/deadline 的最终变更由后续全量门禁覆盖。
- legacy Workspace/Job 控制回归 7 项 PASS。
- `uv run ruff check showcase tests/test_star_product_best_effort.py` PASS；`git diff --check` PASS。
- 全量检查结果在本节下方补记。

## 限制与下一切片

本票交付受限产品 API 的候选/兜底机制，不解锁完整参考或完整 BestEffort。SP12 负责 Workbench 选择、生命周期、候选审阅及新 mode 的前端报告 schema；SP13 负责固定上游独立复核、真实 Intern 批次和最终发布判断。LLM 审查与有限计算不等同完整数学证明，多个 LLM 意见不计独立证明。未触发研究/工具的用例不声称这些机制执行成功。

最终门禁补记：`uv run python scripts/check_showcase_release.py` 返回 `showcase_release=PASS`，该命令内包含完整 unittest、服务入口、Solver release、官方基线和发布证据校验。首轮 `uv run python scripts/check.py --offline` 的 workspace/seam 检查 PASS，但其长驻测试进程在 legacy execution_mode 修复前已加载旧模块，观察到失败后被后启动的完整 release PASS 取代，未把该首轮标为 PASS。最终已对 legacy Workspace/Job 7 项及 SP11 完整聚焦集重新验证。官方冻结 `user_agent.py`、`implementations/`、`BASELINE.json`、`requirements.txt` 相对 871f709 差异为空。
