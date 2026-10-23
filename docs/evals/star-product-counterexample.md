# SP-13 主动反证协议修复验收

日期：2026-10-23；范围见[修复合同](../engineering/star-product-counterexample-contract.md)。这是 SP-13 独立上游复核发现的修复前置，不代表 SP-13 或完整模式交付。

## 已运行的公共验收

最初 `uv run python -m unittest tests.test_star_product_counterexample`：7 项通过，9.434 秒；随后补充了未知远端结果用例，该用例单独运行通过，1.012 秒。

首个用例在实施前失败：只有 explore/planner/reasoner/step_verifier 四次实际 HTTP，没有独立研究请求。实施后，同一认证 Job 的第五次请求为独立 researcher，输入包含原题、准确 claim、假设、原方法和已有 Conjecture；空会话历史、空工具白名单、激活反证协议。report 的同一 S3 账本为 5 logical calls / 5 attempts / 0 tools / 50 provider fixture tokens，五个调用身份互异。

| 用例 | 实际观察 |
| --- | --- |
| Verifier 对缺少完整证明的断言自报 ACCEPT，研究 FOUND | 先执行独立反证，再写 CHALLENGE / Logic FAIL；公开摘要包含反例，不执行后续步骤 |
| 研究 NOT_FOUND | CHALLENGE / Goal PARTIAL / Logic UNCERTAIN，未证方向仍为 Conjecture；有限搜索不是证明，未进入最终生成 |
| 调用额度恰为4 | 第四次 Verifier 后不派发研究；同一账本4次调用，预算终止，不接受缺失证明 |
| claim 索引不指向当前报告 | 第四次响应后拒绝，未派发独立任务，步骤不推进 |
| 研究返回工具或跨题指令 | 端口 schema 拒绝；Registry 未调用、S3 tools=0、研究结果 INVALID，步骤不接受 |
| 刻意跳过研究调度 | 持久调用与结果绑定检查拒绝接受；原公共执行验收在该旁路下产生断言失败，证明确实敏感于缺少动作 |
| NOT_FOUND 后补齐证明 | 原错误断言不进入 accepted_results；修正报告经新双 Gate 接受，最终生成只收到新结论，整题审查完成，同一 Job 9次调用 |
| 独立研究 HTTP 超时 | 原第五次调用和 unresolved attempt 保留；读取 Job/report 不重复派发，没有反证完成或步骤 ACCEPT 事件 |

读取 Job、report、SSE 与 Evidence 不新增调用。事件只公开角色、步骤序号、反证结果枚举和有界脱敏异议；研究完整输入和报告不进入公共事件。数学任务使用测试构造题，HTTP 回复为 scripted；提供方 fixture tokens 仅验证用量传递，不能当真实成本。

早期相关回归 `tests.test_star_product_counterexample tests.test_star_product_gates tests.test_star_product_challenge tests.test_star_product_skill_context` 共21项通过，40.875秒；随后增加了修正证明正向和未知结果用例。

已同步集成 `6027068`（SP-10）后执行 `uv run python scripts/check.py --offline`：436项，466.731秒，9项按既有条件跳过，`repository_check=PASS`；服务 help 与冻结边界检查通过。该批发现测试集时有本切片前7项测试，新增未知结果用例另行聚焦验收。9项跳过不计作 Docker 或完整发布能力通过。没有重复运行产品 release/前端门禁；完整 SP-13 发布门禁仍由责任票最终执行。

本组公开 Job 的 `evidence_kind=fault_injection`，HTTP 回复为 scripted；反旁路用例显式替换最小调度点。没有 live 证据。

收尾聚焦回归 `uv run python -m unittest tests.test_star_product_counterexample tests.test_star_product_gates tests.test_star_product_challenge tests.test_star_product_skill_context tests.test_star_product_final_binding`：31项通过，52.773秒，包含本切片全部8项。修改 Python 文件的 `uv run ruff check` 与 `git diff --check` 通过。

## 实现与限制

控制器不做普遍数学检测。Verifier 协议要求对适用断言填写 `answer_claim`；控制器严格核验类型、当前报告索引、非空原方法，并自行构造任务身份和无代码权限。Verifier 漏报语义触发或误称双向证明齐全仍可能发生，不能把结构化核验称为数学完备性证明。

研究对象与来源 Verifier call、研究 call、当前 claim 及调用审计响应一致才算完成。FOUND 给出反例后交回双方质询，不是机器形式化验证；NOT_FOUND 不补足证明，持久研究记录保留 Conjecture 类别。未知调用沿用现有中断和人工恢复规则，不自动重发。

没有真实模型调用、Docker 执行或能力收益结论。未改官方冻结入口/预算，没有修改恢复或最终文本绑定模块，也没有解锁 `star_reference` / `star_best_effort`。
