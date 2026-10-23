# SP-04 产品路径验收记录

日期：2026-10-23。父规格[#56](https://github.com/RUSS0718/MathAgent/issues/56)，本票[#60](https://github.com/RUSS0718/MathAgent/issues/60)。合同见[SP-04产品集成验收合同](../engineering/star-product-sp04-contract.md)。本记录证明受控回复下的工程接线，不证明数学正确率或真实 Intern 效果。

## 公共产品证据

验收从认证的`POST /api/agent/jobs`进入真实 STAR Harness、controller、InternModelAdapter和共享S3预算/控制边界。测试只替换HTTP传输，有限回复标为`fault_injection`。运行期间真实出站角色请求独立计数；没有真实 API 调用。

| 行为 | 公开触发和结果 | 实际出站证据 |
| --- | --- | --- |
| Explore 四路由 | SOLVED润色后整题审查；REJECT后保留发现进入Plan；PARTIALLY_SOLVED经Meta决定RETRY或PLAN；NEED_PLAN和UNKNOWN进入Planner。 | `tests/test_star_product_planning.py`按Role和Planner输入检查实际动作及发现。 |
| Plan修复 | 非法依赖把实际无效计划和结构错误送回Planner；修复最多一次。非法计划不派发Reasoner，Job失败且验证为unknown。畸形JSON也只触发一次修复，之后关闭执行。 | 同一Run最多2次Planner请求；畸形JSON、超限、重复ID、无效依赖和空目标在`tests/test_star_product_gates.py`覆盖。 |
| 双Gate推进 | 合法YES/PASS/ACCEPT只接受一次，并在下一步请求中带入此前已接受且带依赖来源的结果。相互矛盾的Gate和格式错误的Verifier回复都不推进步骤；Job失败，Solver以`partial_aborted`留在`STEP_VERIFY`。 | `tests/test_star_product_gates.py`比较Role请求数、步骤顺序、SSE接受事件、Job及Run Solver状态。 |
| 提示来源与隐私 | 显式hint进入Planner；Meta hint使用独立字段和`hint_source=meta`。两种hint均限2000字符。应用不直接把hint输入字段复制到Job、Run、事件、报告、Evidence或聊天消息；模型生成的答案可能引用hint。公共Gate事件使用`步骤 N`序号和伪名化事件/步骤调用ID。 | `tests/test_star_product_hints.py`用固定答案检查直接字段投影、幂等冲突、输入拒绝、Planner回显的step ID在公共面被隐藏及读取时零新增调用。 |
| 预算停止 | 共享额度用尽后不派发未获准的Reasoner或后续Verifier，Job不能显示成功。 | 公开请求计数、S3逻辑调用和Job/Run状态一致。 |

未触发的Challenge、Trace-Back与重规划属于SP-05/06；安全恢复属于SP-08；生成Python及真实工具产物属于SP-09；最终交付文本绑定属于SP-10。它们不计入SP-04通过证据。没有运行live批次。Evidence读取是只读检查，不调用模型或工具。

## 提示输入与认证边界

可选Job字段`solver_hint`只接受`star_limited`模式下的非空文本，最多2000字符。内容单独存储并参与该STAR请求的幂等摘要，不改变未提供hint的legacy请求摘要。`solver_options`仍在入队前拒绝。Meta生成的预计划hint经过相同长度和非空检查；非法回复不会到达Planner。

公开Solver事件使用带Run盐的事件ID摘要，Gate事件以计划顺序发布`步骤 1`、`步骤 2`等序号，不发布Planner的内部step ID。step-scoped模型调用ID也以稳定摘要进入公开attempt和Evidence。

应用不直接把hint输入字段复制到Job DTO、Run快照、SSE、报告、Evidence或ChatSession消息。`hint_prepared`事件只投影`none`、`user`或`meta`类别。模型生成的最终答案是公开内容，模型可能在其中重复hint。本票测试的固定答案没有重复hint，因此只证明应用没有直接投影该字段。

当前loopback认证固定为一个`local-user`，因此无法通过公共接口构造另一个owner。未认证Job查询、事件、报告和会话请求返回401；本记录不声称跨owner验收通过，也不通过数据库私有种入伪造owner。

## 检查结果

| 检查 | 结果 |
| --- | --- |
| `uv run pytest tests/test_star_product_planning.py tests/test_star_product_gates.py tests/test_star_product_hints.py tests/test_star_product_jobs.py tests/test_star_product_tools.py tests/test_star_product_control.py tests/test_star_product_budget.py tests/test_star_product_research_budget.py tests/test_reports.py tests/test_solver_harness_explore.py tests/test_solver_harness_star_routing.py tests/test_solver_harness_step_report.py tests/test_solver_harness_verification.py tests/test_solver_harness_review.py -q` | PASS，72项，45.36秒；覆盖公开Job、Run、SSE、报告、Evidence、步骤ID隐私面和Gate状态。 |
| `uv run ruff check showcase/evidence.py showcase/run_budget.py showcase/solver_harness/verification.py showcase/star_product_events.py showcase/star_product_pipeline.py tests/star_product_support.py tests/test_solver_harness_verification.py tests/test_star_product_gates.py tests/test_star_product_hints.py tests/test_star_product_planning.py` | PASS |
| `uv run python scripts/check.py --offline` | PASS，378项，271.368秒；`repository_check=PASS`。 |
| `uv run python scripts/check_showcase_release.py` | PASS，发布门内离线检查378项，`showcase_release=PASS`。 |
| `git diff --check` | PASS |
| `git diff -- BASELINE.json user_agent.py implementations requirements.txt` | 空差异 |
| `npm ci --no-audit --no-fund` | PASS，安装66个包 |
| `npm audit --audit-level=high` | PASS，0 vulnerabilities |
| `npm run check` | PASS，依赖合同、类型检查、13项单元测试和构建 |
| `npm run test:browser -- tests/browser/star-decisions.spec.ts --workers=1` | PASS，5项：320、768、1024、1440宽度各1项，另有原始step ID不渲染的反例；Axe违规0，页面console错误/警告0 |
| 浏览器截图 | 保存在忽略的`artifacts/ui-unification/browser/star-decisions-*/star-decisions-{320,768,1024,1440}.png` |

测试使用有限fault-injection回复，不能支持真实模型能力、数学正确率提升或完整STAR声明。完整模式仍需后续票完成机制和发布门槛。
