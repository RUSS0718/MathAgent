# SP-07 记忆、Skill 与局部指导验收

日期：2026-10-23。工单 [#63](https://github.com/RUSS0718/MathAgent/issues/63)，父规格 [#56](https://github.com/RUSS0718/MathAgent/issues/56)，主验收 SP-AC-11/12/25/26。设计及实现边界见[验收合同](../engineering/star-product-sp07-contract.md)。

## 公共 Job 证据

`tests/test_star_product_guidance.py` 从认证 Job HTTP 入口穿过现有 STAR controller、Solver Harness、InternModelAdapter 和共享 S3 账本。外部 Intern HTTP 使用有限 scripted 回复；所有 Job 标记 `fault_injection`。这些结果证明机制在产品路径可达，不证明真实模型效果或数学能力提升。

| 触发 | 决策与实际动作 | 持久 / 用户结果 |
| --- | --- | --- |
| Reasoner 明确返回 blocked | Meta 收到 `stuck` Guidance；`retry_different_method` 及 `specific_task` 实际进入下一次 Reasoner 请求；纯推理请求不声明计算工具 | 运行时收到伪造工具请求后仍以 `pure_reasoning_denied` 拒绝，S3 工具调用为 0；Job、SSE、报告和 Evidence 可核对安全事件 |
| Docker 管理的计算已终止并报告 timeout | Meta 收到 `timeout`；界面调用预算和回执均保留；产品实际继续新尝试 | 故障注入回执为 `unknown_outcome=false` 且 `cleanup_verified=true`；远端请求 timeout 的独立反例保持 `interrupted/needs_review`，没有 Meta 追加调用或自动重发 |
| 已结束的受控工具失败 | Meta 收到 `code_issue`，实际注入 `code-issue-resolution` 协议 | Python executor 在 Docker 边界故障注入为未执行、可确认 `unavailable`；同一 Job 的指导与状态可见 |
| Guidance 选择 `explore_more`、`trace_back` 或 `replan` | 各动作都经原 Explore、Trace-Back 或 Replan 控制器执行；唯一任务指引到达后续真实 Explorer、Reasoner 或 Planner 请求 | 探索发现携带 `unverified_exploration` 来源；回溯按步骤和依赖失效；重规划产生实际新计划 |
| Verifier 提出 Challenge | Challenge Reasoner 的真实模型请求包含 counterexample 与 verification-tag 协议 | 角色作用域的 Reasoner/Verifier 会话和最新状态投影保存在同一 Run；公开事件仅含 Skill ID、版本和摘要指纹 |
| 发起多个受限研究任务 | 同一账本依次派发两个无工具 researcher；两项成功发现进入新 Planner 的 `reexploration_findings` | Planner 实际返回新计划；成果标为 `unverified_exploration`，不被升级为已验证事实。研究取消和迟到 usage 由 `tests/test_star_product_research_budget.py` 现有公共测试覆盖 |
| 旧 Meta 决策后 Guidance 再规划 | 当前 Guidance 决策独立控制研究派发和成果救援 | 研究不接收旧 Meta 的禁行方向；旧决策选过的步骤成果不会被 Guidance 重规划救援 |
| 新计划复用旧步骤 ID | 回执按当前 report 明确引用的 receipt ID 关联，而不只匹配 step ID | 新计划不会因同名步骤上的旧 Docker 故障再次触发 Guidance |
| 第二个 Job 使用相同 ChatSession | 角色历史按 Run 身份隔离 | 第二 Run 的实际请求及注入历史均不含第一 Run 的指导哨兵；system projection revision 与请求 revision 相同 |
| 关闭并重建 SolverHarness 后继续同题 Meta session | 从同一 SQLite role registry 恢复 Meta 对话，再注入更新后的 failure / confirmed-failure ledger | `tests/test_solver_harness_sessions.py::test_recreated_role_session_keeps_history_and_injects_latest_failure_ledger` 断言历史、最新投影和 revision 一致；公共 Job worker 进程崩溃后的安全恢复仍归 SP-08 |

七类协议均从实际出站 system layer 检查 ID、版本、非空指令、触发和权限：Explore、Verifier review、verification tags、Meta intervention、数学策略、反例构造和 code-issue resolution。SSE 与 Evidence timeline 仅记录白名单 Skill ID、协议版本、触发、权限和提示指纹；完整指导文本不进入 Job、SSE、report 或 Evidence。Skills 关闭的反例也确认出站请求没有增加 `suspected_false_claim` 或探索投影。

## 检查结果

| 检查 | 结果 |
| --- | --- |
| `uv run python -m unittest tests.test_star_product_guidance tests.test_star_product_skill_context tests.test_solver_harness_sessions tests.test_solver_harness_meta tests.test_solver_harness_traceback tests.test_solver_harness_verification tests.test_star_product_traceback tests.test_star_product_research_budget -v` | PASS，46 项，42.877 秒 |
| `uv run python scripts/check.py --offline` | PASS，421 tests，388.560 秒，9 项跳过；`repository_check=PASS` |
| `uv run python scripts/check_showcase_release.py` | `showcase_release=PASS` |
| `uv run ruff check`（改动 Python 文件）及 `git diff --check` | PASS |
| 官方冻结文件相对 `606d874fcee11bc161d68aa001cd706de63afbe2` | 无差异 |
| 七项内存 mutation 探针 | PASS：删去协议、纯推理拒绝、code-issue Skill 或 Evidence 摘要，错误匹配旧步骤回执、在 Skills 关闭时仍加探索上下文，或复用旧 Meta 成果选择，公共验收均失败；源码未持久改写 |

执行 raw 与 mutation 摘要留在忽略的 `artifacts/star-sp07/`。本片没有执行 live 模型批次或 replay；现有研究取消测试覆盖 fault-injection 的迟到结果处理。没有独立数学正确率评测，因此不声称数学收益。

## 边界

登录用户看到的 guidance 事件仅公开动作、失败类型、Skill 标识、版本和指纹；`specific_task` 不进入 SSE、report 或 Evidence。只有受控且确认终止的 Docker 工具失败可产生局部指导。远端调用未知结果仍待复核；SP-08 负责服务重启恢复和人工重试。完整 STAR reference 与 best-effort 模式继续 fail closed；官方评分路径未变。
