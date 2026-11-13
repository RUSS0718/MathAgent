# #173 B3 实现与聚焦证据（2026-11-13）

起点及集成基线 `408e33c`；隔离 worktree `D:/project/mathagent-173-work`，分支 `feat/showcase-task-revision`。适用源码为本记录同一提交，合同见 [B3 合同](../engineering/faithful-service-173-contract.md)。本记录交付实现与聚焦验证；主窗口负责合并、双轴审查、真实服务和最终门禁，不代表父规格 #168 完整服务已交付。

| 边界 | 已观察结果 | 证据 |
| --- | --- | --- |
| 公共 Job 改题 | 基点 `/revisions` 返回 404；实现后原子停止旧派发、独立新题交付 5；旧迟到结果只结算，重复动作同 Job，内容/版本冲突拒绝 | `artifacts/issue-173/red.json`、`red.log`、`focused-05.json` |
| unknown 与容量 | 旧预算/预留及恢复来源不变，旧任务不可恢复；容量 1 时新题 queued、零新增请求，容量 2 时新题完成；已知 400 拒绝不占槽 | 同目录 `focused-05.json`、`focused-05.log` |
| 既有行为 | 同任务正式澄清消费和未改题 unknown 显式恢复仍通过 | 同组 5 项（3 项 #173、2 项既有回归） |
| 浏览器 | 一项受控 Chromium 场景：移动输入改题、晚到旧事件、独立新答案、刷新零重复 POST、双向详情链接；无 pageerror、无整页横向溢出 | `artifacts/faithful-entry-browser/faithful-entry-task-revisi-8f2e6-nd-ignores-late-old-results/revision-mobile.png`；Playwright 命令退出 0 |
| 前端 | `npm run build` 类型检查与打包通过；设计检测空结果；已有 bundle 大小提示保留 | `artifacts/issue-173/frontend-build.log` |

聚焦命令（Python 使用主工作树既有环境，前端通过 node_modules junction 复用同锁依赖）：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:\project\工程化MathAgent\Challenge-Cup-2026\.venv'
uv run --no-sync python scripts/run_unittest_report.py --expect-count 5 --summary-json artifacts/issue-173/focused-05.json --diagnostics artifacts/issue-173/focused-05.log tests.test_task_revision_173 tests.test_clarification_172.ClarificationTest.test_answer_versions_conditions_and_continues_same_job_once tests.test_faithful_service_job.FaithfulServiceJobTest.test_public_unknown_intake_retry_establishes_spec_before_solving
```

前端目录执行 `npx playwright test --config tests/faithful-entry.config.ts --grep 'task revision' --reporter line` 及 `npm run build`。首次受控浏览器失败只因 Vite 没有 Flask 的 `/dashboard/run/*` 页面壳，测试补齐该壳后同一场景通过；未修改产品路由。首轮用例加载数量不符记录 `green-01.*`，随后选择器修正后通过，不计为产品失败。

主窗口真实验收入口已交接：`POST /api/agent/jobs/{job_id}/revisions`，请求 `{message, input_version}`，沿用 CSRF 和 UUID Idempotency-Key。新任务 `result.faithful.revision_source.task_id`、旧任务 `result.faithful.revision_to.task_id`；停止字段 `result.faithful.revision_allowed=false`，旧 allowed_actions 为空。执行中的旧任务为 canceled；已失败 unknown 保持失败及原预留。浏览器区域名“关联任务与改题”，输入 `#math-question`，按钮“改题并创建新任务”。

真实配置沿用 [#172 验收](faithful-service-172-20261113.md)所指主工作树 `artifacts/issue-170-work/service.json`，既有 intern-s2、48 次模型/HTTP、8 次工具、1100 秒预算不变。主窗口审阅并授权后，从集成源码启动独立数据目录，例如：

```powershell
uv run --no-sync python showcase_server.py --mode live --host 127.0.0.1 --port 8093 --faithful-config artifacts/issue-170-work/service.json --data-dir artifacts/issue-173-work/live-data
```

普通浏览器先提交“计算 17×19，并给出计算过程。”，在上述区域改为“计算 2+3，并给出结果。”；保存两个 Job/Run、Attempt、报告与 Evidence，核对新题答案 5、双向来源和刷新不增调用。真实运行由 Dewey 准备、主窗口执行，本实现窗口为 `not_run`；全量门禁、独立数学能力评测均 `not_run`。官方 baseline 差异为空，`tests/test.md` 未读取或修改。继续使用当前选择的同一模型，具体继承型号无法确认时不猜测。
