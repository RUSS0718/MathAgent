# UI 复现与扩展指南

本指南记录 2026-10-22 的实现。先读 accepted 的 [工作区重设计](v0.2-workspace-redesign.md)、[统一合同](ui-unification-contract.md)、根 [DESIGN.md](../../DESIGN.md)。复现以源码、lockfile、固定 fixture 和平台截图为准；文档不能替代浏览器检查。

## 安装、运行与验证

以下为 PowerShell；从仓库根目录开始，使用 Node 24.18.0、npm 11.16.0、uv 0.10.9。Python 版本约束见 pyproject.toml；不要使用 WindowsApps 的系统 python shim。

```powershell
uv sync --locked --extra showcase
Set-Location showcase/frontend/chat-frontend
npm ci --no-audit --no-fund
npx playwright install chromium
npm audit --audit-level=high
npm run check
npm run test:browser
```

`check` 包括依赖合同、vue-tsc、13 个单元测试和生产构建，不包含浏览器测试。浏览器套件自行启动 5176 Vite 与 5177 旧页面 fixture 服务；保持端口空闲。它用合成 API 数据，不调用模型，不写真实会话。测试输出在根 `artifacts/ui-unification/browser/`。

启动可交互 fake 后端，在仓库根目录运行：

```powershell
uv run python showcase_server.py --host 127.0.0.1 --port 8090 --mode fake --data-dir artifacts/ui-reproduction
```

已构建时访问 `http://127.0.0.1:8090/dashboard`。开发时另开终端，在前端目录运行 `npm run dev -- --host 127.0.0.1`，访问 `http://127.0.0.1:5174/dashboard-assets/`；Vite 默认代理 API 到 8090，替换后端可设置 `VITE_FLASK_ORIGIN`。独立旧 Demo 在根运行 `uv run python demo_server.py --host 127.0.0.1 --port 8080`。具体可选参数先以 `--help` 核对。

涉及共享页面或发布时，在根运行：

```powershell
uv run python -m unittest discover -s tests -p "test_*.py"
uv run python demo_server.py --help
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
```

## 样式与源码所有权

所有路径以下均相对 `showcase/frontend/chat-frontend/`。不要加页面内重复 button/input 配色。

| 文件 | 责任 |
| --- | --- |
| src/styles/tokens.css | 唯一运行时颜色、字体、间距、圆角、宽度、motion、overlay token |
| src/styles/reset.css | 浏览器基础、全局焦点环、减少动态效果 |
| src/styles/primitives.css | 按钮、状态、通知、空状态、品牌和模态抽屉 |
| src/styles/workspace.css | 工作区网格、会话栏、顶栏及断点 |
| src/styles/conversation.css | 对话、输入、报告、数学内容溢出 |
| src/styles/inspector.css | 观察栏、时间线、事件摘要 |
| src/styles/review.css | PageFrame、设置、实验与证据阅读页 |
| src/styles/main.css | 导入 primitives/workspace/conversation/inspector；#app 高度 |
| src/main.ts | 加载 reset、tokens、main、KaTeX 和 review CSS |
| src/components/ui/ | 仓库拥有并维护的原语源码，不是第三方主题覆盖层 |

旧入口位于 `showcase/frontend/legacy/{demo,showcase,unbuilt}.html`、`legacy.css`、`solve.js`。根 `presentation_pages.py` 以标准库读取 tokens/reset/primitives/review 和旧模板；不会被官方 user_agent 导入。旧页面没有 Vue 运行时，修改共用 CSS 必须检查两类入口。

## 组件目录与 API

| 组件 | API 与调用约束 |
| --- | --- |
| UiButton | variant: primary/secondary（默认）/ghost/danger；iconOnly、busy、disabled；type 默认 button，可 submit/reset；默认 slot；原生 click 和属性透传。busy 禁用按钮；iconOnly 必须传 aria-label |
| UiIcon | name 为具名导入映射键；18px、stroke 1.75，aria-hidden，不承担按钮名称 |
| StatusBadge | value:string；保留中文标签及 raw code；未知状态原样展示；不将未知映射 success |
| PageFrame | title、可选 description、active:settings/campaigns/run；默认内容 slot 与 actions slot；run 高亮配对实验导航 |
| ResponsivePanel | open、label、breakpoint:number、side:left/right、id、可选 persistent；默认 slot，close 事件；窄屏原生 showModal，Escape/背景点击交给父组件关状态 |
| ComposerBar | modelValue、disabled、running、visionEnabled、可选 selectedFileName/waiting；update:modelValue、submit、cancel、upload(Event)、clearFile 事件；输入法确认不发送 |
| ReportSection | 可选 title/content/mode/status/report；report 含 answer/public_summary/stage/limitations 与 checks；统一安全 Markdown 和 KaTeX |
| AgentTimeline | events:DecodedSseEvent[]；按节点聚合、默认展开、内部管理折叠；不添加完整 prompt |
| WorkspaceInspector | open、可选 job、report:JobReport/null；close 事件；右侧断点 1180 |

图标键为 activity、download、arrowRight、arrowUp、check、chevronDown、chevronRight、experiments、menu、message、panel、pencil、plus、refresh、settings、sigma、stop、trash、close、image。扩展时只在 UiIcon 具名导入所需图标，不动态加载全集，不使用 emoji 代替操作图标。

业务路由组件 ChatWorkspace、SettingsPanel、CampaignWorkbench、RunReview 组合这些原语，不应复制其视觉实现。会话改名/删除仍调用浏览器 prompt/confirm，这是已实现交互边界，不是新增自定义对话框规范。

## 页面与状态矩阵

生产前缀 `/dashboard`，Vite/fixture 前缀 `/dashboard-assets`；同一后缀由 `runtime/navigation/app-route.ts` 解析。

| 表面 / 后缀 | 固定状态与检查 |
| --- | --- |
| 工作区 /session/session-demo | workspace 空对话；conversation 有消息与报告，四档宽度 |
| 设置 /settings | 模式、能力边界与运行配置，四档宽度；加载时刷新禁用、失败后可重试 |
| 实验 /campaigns | 列表、空列表、分页禁用；四档列表 + 1440 空态 |
| 实验 /campaigns?campaign=campaign-demo | 详情、失败后保留 ID 重试，四档详情 |
| 运行 /run/run-demo | 报告、Evidence 与时间线；首次点击折叠，四档宽度；失败 Run 禁止再次取消、报告可刷新 |
| 移动工作区 | 320×800 会话抽屉和观察抽屉，焦点约束、Escape 关闭并恢复焦点 |
| 初始化 | 加载骨架、连接失败、重新连接；失败截图 1440 |
| 等待补充 | waiting_input 不永久 busy，输入可编辑，resume 原 Job；截图 1440 |
| 旧 demo/showcase/unbuilt | 320 与 1440；demo 请求失败后重试只发一个请求 |

另有 Enter 单次提交、Shift+Enter 换行、Campaign 与 Evidence 的 JSON 下载文件名验收。

加载态使用 aria-busy 与文字，错误用 alert/notice 与重试，空态说明下一步。所有核心页面要求无控制台错误、无整页横向溢出和 axe WCAG A/AA 违规。截图覆盖为 6×4 + 3×2 + 2 抽屉 + 3 状态 = 35 张；浏览器用例数随交互验收扩展，以最新验证记录为准。并非每种状态都在每种宽度截图，新增状态仍须补验收用例。

## 布局、字体与像素复现

桌面网格 248px / minmax(0,1fr) / 320px；不大于 1180px 观察栏变抽屉，不大于 760px 会话栏也变抽屉。阅读上限 760px，普通页 1120px；其他准确尺寸见 DESIGN 和 CSS。不要单改 CSS 断点而遗漏 ResponsivePanel 的 breakpoint 属性。

基准环境是 Windows 11 build 10.0.26200、Segoe UI/Microsoft YaHei 字体，Chromium revision 1248 / version 156.0.8078.4（随 Playwright 1.64.1 安装）。DPR=1、zh-CN、Asia/Shanghai、light、reducedMotion=reduce；标准视口宽 320/768/1024/1440、高 1000，抽屉高 800。字体从系统获取，KaTeX 字体由本地 npm 包构建，不访问 CDN。跨 OS、字体版本、浏览器版本不能承诺逐像素相同。

截图在 `tests/browser/snapshots/win32/`，配置按 `{platform}` 分目录。同环境比较设置 `maxDiffPixels: 0`。不要为消除差异随意放宽阈值；先检查字体、环境、fixture、等待条件和真实 UI 回归。

确认设计修改与验收内容后，前端目录运行：

```powershell
npm run test:visual:update
npm run test:browser
```

逐张检查新增/变化的 expected 图片与失败 diff，特别是失败/等待态，禁止把未加载页面或误报错当作新基准。仅提交经审阅的源码、fixture 和 expected 截图，不提交 artifacts、真实数据或 Playwright 缓存。浏览器或字体升级需独立说明环境变化、重审全部 35 张；其他 OS 必须另建该平台基准。

## 模式、公开边界与验证含义

fake 为演示、replay 为回放、live 为实时；experimental/planned/unavailable 不能悄悄显示为 live。StatusBadge 保留 raw 值方便核对，移动顶栏隐藏 code 是局部布局例外。completed 表示终止，succeeded 表示执行完成，不表示数学正确。pass/conflict/unknown 是有范围的检查结果，必须保留 limitations/public_summary；检查为空时显示 unknown。

报告只接收公开字段，经 `renderers/markdown-adapter.ts` 渲染；不得用服务返回的原始 HTML 替换适配器，不扩大 KaTeX trust 或展示隐藏推理。前端测试与 fake 数据只证明界面和合同，不构成模型能力评测。

## 依赖与安全扩展流程

生产 allowlist：Vue 3.5.44、Pinia 3.0.4、Zod 4.1.5、KaTeX 0.19.0、@lucide/vue 1.61.0。开发工具是 Playwright 1.64.1、@axe-core/playwright 4.14.0、Vite 8.1.6、@vitejs/plugin-vue 6.0.8、TypeScript 5.9.3、vue-tsc 3.3.8。直接依赖精确锁定，package-lock 同步；`scripts/check-dependencies.mjs` 检查 allowlist、版本一致和生产包单份安装。

1. 明确页面、状态与验收合同；先寻找现有组件和 tokens，写失败用例再做最小实现。
2. 控件在 components/ui 扩展，业务流程留在原业务组件；不要叠加 Element Plus、Ant Design、Tailwind、另一套路由/状态/图标/数学库。
3. 必须新增运行依赖时，先记录必要性、现有实现不足和替代方案，再同步依赖决策、allowlist、package.json/lockfile；不能绕过检查。
4. 更新 fixture、键盘与可访问性检查、四档截图；运行 check/audit/browser 与受影响 Python/发布门禁。
5. 更新 DESIGN、.impeccable/design.json 和本指南中变化的事实，审阅差异后提交一个逻辑切片。官方 baseline 保持字节不变。

本轮具体执行结果见 [UI 验证记录](ui-verification.md)。Impeccable detector 若未成功运行不得写成通过；视觉审阅与测试也不替代其运行记录。
