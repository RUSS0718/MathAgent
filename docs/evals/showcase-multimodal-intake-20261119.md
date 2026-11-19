# Showcase 图文读题验收

2026-11-19。工作分支 `feat/showcase-multimodal-intake` 从 `develop` 的 `059fd0639732eef3bd7d1cc9b5b63a8ae12a6ed5` 新建。功能提交 `35bd5eafc1244440a8f7d69820295fc50b9492e8`，关闭能力错误码修复和最终冻结源码为 `62b930129742b7d269acd78ab810e2dc0a8afd03`。产品边界见[图文读题合同](../engineering/showcase-multimodal-intake.md)。证据路径相对于该工作树，本机产物不进 Git。

## #209 复验

原现场演示整合已由 PR #212 合入 `develop`（`5c9ae01`）；历史真人彩排记录见 [#209 验收](onsite-demo-209-20261118.md)。本轮在加图文功能之前，以 `059fd06` 生产构建和 1280×720 Chromium 复验：模拟短题一次求解 POST（202），观察进展、打开角色成果、刷新回同一任务和答复；真实 D2 的 SQLite 副本复验首屏题意、结论、审查范围、S1/S2 成果、Esc、回放与刷新。D2 新求解 POST 0，含预算的七张业务表完整摘要前后相同（SHA-256 `65109ad56b28b3064234c52c9e9cbb015686dd1ca35b71b8526fa33ed30f34fb`）。浏览器结果、截图和摘要在 `artifacts/onsite-209/`。基线构建 manifest SHA-256 为 `c162f0b2d3572c206af417168efa8c73c53bf90eaa2d5b62d9e19bdefef98473`。

没有恢复 #209 真实实验，原 C 组完整交付 2/3 不变。以下合成题冒烟不计入 #209 的实验。

## 图文能力验收

| 合同 | 公共入口及断言 | 结果与证据 |
| --- | --- | --- |
| 三种输入、基础题型、预算 | `POST /api/agent/jobs`；有效题干交给原求解，文字分类不新增模型调用，图片请求计入原 Job；小预算不可派发。 | 真实 Flask + 截获 Intern HTTP；`artifacts/multimodal/frozen-backend.json`，11/11（新功能 8 与既有工作区合同 3）。 |
| 限额、隐私、失败和身份 | PNG 128 KiB 边界、不可读不按纯文字求解，公开 JSON 无识读字段与载荷；删附件后允许原请求重放、不允许新建或更换请求；进程中断不自动重发。 | 同上；保留 `disabled-flag-red.json` 的既有错误码失败，修复后通过。 |
| 浏览器 | 生产资产 + Flask + 受控 provider/solver；纯图无文字提交，观察 pending、ready 和终稿，刷新仍为同一任务与题型。 | `artifacts/multimodal/production-browser.json`：求解 POST 1，读图请求 1，浏览器异常 0。定向 Chromium 51/51（`browser-focused.log`），前端单测 103/103、类型及构建通过（`frozen-frontend-check.log`）。生产构建 manifest SHA-256 `ddfe2679c9a462aaadcc56960973a4c188d5782d878aa128cd5f5a82c7e0aa5e`，不将 stub 结果视作数学证据。 |
| 真实模型冒烟 | 开发版用同一合成 PNG `2x+3=11`。 | Intern-S2 纯图 `run_3cafdd196c24999a2278268cb6945e1e`：读取和分类成功，后续求解 `tool_timeout`；附「手算、不调用工具」的图文任务 `run_56eb8334b81c8e3c821ac61d01536185` 交付 `x=4`，模型逻辑调用 4 次。见 `artifacts/multimodal/live-mixed.jsonl`。不代表纯图端到端稳定性或准确率。 |

全量 Chromium 未通过：直接用默认配置启动 199 项，116 通过、83 失败（`browser-frozen.log`）。部分套件需要各自的 Flask/Playwright 配置，直接启动时报端口未连接；设置页的一条相同断言也在 `059fd06` 上复现（`browser-baseline-settings.log`）。未将全部失败归因于环境。冷启动、专项真实工具与真实实验不因定向通过而视为通过。

## 门禁

首轮 `multimodal-01` 在发现禁用能力时 503 被改为 400 后主动停止，保留现场；修复后冻结 `62b9301` 启动 `multimodal-02`。快速阶段通过；离线阶段执行 2,450 项，49 跳过、0 断言失败、1 初始化错误。`test_star_experiment` 无法连接本机 Docker Desktop Linux 引擎。源码无漂移，门禁停在离线阶段。日志见 `artifacts/final-gates/multimodal-02/`。发布聚焦检查另行通过 27/27，独立执行 `npm audit --audit-level=high --json` 返回 0 告警。仍需在 Docker 引擎可用的环境补跑最终门禁。

## 纯图超时回归与复验

同一合成题 `2x + 3 = 11`，基线 `cf872a5` 上真实 Intern-S2 纯图和纯文字均返回 `x = 4`；未禁止工具的图文对照首次失败于 `tool_schema_invalid`，不归因于识读。补丁后的纯图和图文复跑均得到 `x = 4`；图文实际使用了 Python 数学工具，纯图没有请求工具。以上是真实模型冒烟，不代表自然超时已复现或题型准确率。

Flask 纯图入口故障注入：修改前工具超时导致 Job 直接失败，修改后在同一工具调用身份下续答一次，返回答案但不判为验证通过；不重跑工具。定向工作区回归 19/19，工具测试独立复跑 7/7，快速门禁通过。证据为 `artifacts/timeout-red.json`、`artifacts/timeout-green-02.json`、`artifacts/timeout-tools-retry.json`、`artifacts/timeout-live.jsonl`。Docker 启动后，另在未修改的 `cf872a5` 工作树启动 `artifacts/final-gates/docker-retry-01/`，不将该运行视作补丁版的完整门禁。
