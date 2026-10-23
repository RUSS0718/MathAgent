# SP-12 Workbench 持久生命周期验收

日期：2026-10-24。归属 #68 / SP-AC-21；开发基点 `25aaca16f66433d7a284391a9fbe73237f805086`。合同见 `docs/engineering/star-product-sp12-contract.md`。

## 交付与证据类别

RunReview 展示同 Run 的持久计划/步骤双 Gate、活动计划版本/尝试、Meta 裁定、回退失效与救援数、模式/证据身份、预算未知消耗、候选版本/选择排除信息、最终 S4 观察历史。回执保留 scope/环境/内容引用；仅同 Run 的合法 SHA-256 引用生成后端授权下载链接。普通非内容寻址引用明确不代表已保存执行产物。

修复已有报告仍显示 unavailable 的错误分支；显式恢复 HTTP 成功后开启 store 新代际，保留 SSE 游标拒绝旧事件。状态刷新以持久报告为准；SSE 触发合并的只读刷新，并按 revision 拒绝旧摘要覆盖。步骤协议合法与步骤接受分开：只有 valid 且 ACCEPT 显示已接受。terminal 文案为执行结束，不暗示数学正确。

模式选择读取服务端 capabilities；包含准确的受限 Best-Effort 身份，不写死完整模式永远可用或不可用。本片未实现/解锁完整预设，SP-13负责服务器依赖和最终发布门禁。

## 真实公共浏览器接缝

命令在 `showcase/frontend/chat-frontend/`：`npx playwright test -c playwright.product.config.ts`。配置启动真实 create_app/临时SQLite与Vite。真实 InternModelAdapter/InternChatClient 向本地有限 HTTP provider 发请求；无 page.route/mockWorkspace，无替代求解循环。提供方故障注入只控制外部回复/断连/延迟，Registry polynomial_check 为真实执行。测试身份为 fault_injection，replay 为明确的只读重放。无真实 Intern 云端调用，无数学效果结论。

本地提供方最多28次请求/Run，标准产品硬预算28 logical/28 HTTP/2 tools；受限兜底应用硬预算1/1/0；deadline应用硬限0.5秒。provider只记录Run计数，不输出prompt或凭证。临时服务/数据随测试进程退出清理，截图/日志/trace写被忽略 artifacts。

| 真实同 Run 触发链 | 浏览器观察与验证 |
| --- | --- |
| NEED_PLAN → planner → reasoner → 双Gate → final_generator → 新整题Verifier | 320/768/1024/1440 的持久计划/版本/候选/审查；报告存在不出现错误空态；最终六次真实HTTP请求 |
| 同一完成Run刷新、reload、沿游标重连、候选replay、Evidence下载、并发report/evidence查询 | provider实际计数保持6；replay明确标识；导出文件名绑定Run；无私有step_id/证明文本；Axe无违规、无pageerror、无整页横溢 |
| provider真实断连 → unknown_outcome → 人工明确新身份重试 | reload前后仍1次请求，无自动重试；点击后同Run实际完成，共4次请求，界面不固化旧failed |
| 实际在途请求 → 用户取消 → reload | canceled保持，不显示空白成功，只有1次提供方请求 |
| 四步计划 → Trace-Back → 依赖失效/独立救援 → 新步骤完成 | 失效2/救援1、回退至步骤2可见；实际18次请求 |
| Trace-Back → PROPOSE_REPLAN → Meta批准 → planner v2 → final | 活动计划2/尝试2、旧计划归档与救援可见；实际18次请求 |
| 一次Explore后硬预算终止的受限Best-Effort | 原候选及candidate_selected可见；replay不增调用（1次）；unknown/needs_review不伪装审查成功 |
| NEED_PLAN后硬预算终止 | 明示无完整候选与failed，不呈现空白成功（1次调用） |
| 实际provider延迟越过deadline | failed可见，已有持久报告不报unavailable（1次调用） |
| 真实Registry polynomial检查 | report回执executed=true/source=local_precheck、累计1次工具；最终unknown；不可解析引用不伪造下载 |

## TDD与实际检查

以下均为 2026-10-24 在 `feat/showcase-sp12-review`（基点 `25aaca1`）上的新鲜重跑结果，不沿用开发期自报。

- 初始 store RED：`confirmResume is not a function`；最小实现后 store 单测通过，旧 terminal 事件 ID 仍被游标拒绝。
- 初始公共 HTTP RED：报告无 `progress`；增加独立白名单投影模块后通过，私有证明文本不进入摘要（`tests/test_star_product_summary.py` 断言证明原文不出现）。
- 前端（`showcase/frontend/chat-frontend/`）：`npm ci --no-audit --no-fund` 成功（66 packages，约 9 秒）；`npm audit --audit-level=high`：0 vulnerabilities；`npm run check`：依赖合同、类型检查、14 unit（node test runner，含新增恢复代际 store 测试）、构建 PASS（约 7 秒）。
- 真实公共浏览器：`npx playwright test -c playwright.product.config.ts` 12 tests PASS，35.0 秒，含四宽度 Axe 与截图。开发期首轮 replan 场景由于测试 provider 漏接 meta 角色进入 unknown，修复外部 fixture 后通过，未降低产品断言。本轮新鲜重跑第一次尝试因本机缺少 Playwright `chromium_headless_shell-1248` 可执行文件 12 tests 环境性失败（11.3 秒）；按需执行 `npx playwright install chromium` 后整套通过，属环境补装而非产品代码缺陷。
- 既有 synthetic STAR 浏览器（`npx playwright test star-mode star-decisions star-recovery`，现有 `playwright.config.ts` 已 ignore 真实套件文件）：11 tests PASS，9.6 秒；明确只作表现/稀有字段反例，不替代上表真实 HTTP 链。
- 相关 Python（仓库根 `uv run python -m unittest`）：`test_star_product_summary/final_binding/recovery/hints/best_effort` 共 49 tests PASS，73.773 秒。提交前补记：`test_star_product_private_receipt`（工具隐私回执脱敏）2 tests、`test_star_product_traceback`（Trace-Back 失效/救援投影来源）3 tests、`test_star_product_tools`（真实 Registry 回执）4 tests，合计 9 tests PASS，18.665 秒。
- 最终静态检查：`uv run python scripts/check_workspace.py --offline` → `workspace_contract=PASS`；`uv run python scripts/check_test_seams.py` → `contract_test_seams=PASS`；官方冻结文件（BASELINE.json、user_agent.py、requirements.txt、README.md）`git diff` 无差异。
- 全量 Python 与完整 release 不在本片重复执行，由 SP-13 固定集成 tip 统一门禁。

## 限制

完整reference与完整Best-Effort真实路径取决于SP-13服务端门禁；本片浏览器证据均为明确受限模式。Docker内容下载的真实隔离执行证据沿用SP-09，本轮仅跑真实polynomial Registry及引用显示，不声称重跑Docker。安全进程崩溃恢复的数学不重复执行由SP-08公共Python回归覆盖；本轮浏览器验证真实unknown显式重试，未重做整个Flask进程崩溃重启。API鉴权/跨题产物隔离沿用既有后端合同，前端仅同Run引用构造授权URL；无额外访问权。旧全页像素golden未批量更新，因为修复错误空态会改变运行详情截图；本片新真实四宽度截图保存在artifacts。
