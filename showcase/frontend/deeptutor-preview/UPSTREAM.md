# MathAgent 工作台

从仓库根目录运行 `uv run --no-project python scripts/start_showcase.py web`，打开 `http://127.0.0.1:8090/dashboard`。`--mode fake` 可运行模拟后端，`--port` 可选择本机端口。启动器构建普通工作台与技术审阅页面，Flask 在同一来源提供页面和 API。

首页的示例使用本地模拟。手动输入的题目由当前服务求解。题图入口根据服务的上传能力开放。`/dashboard/session/<id>` 读取当前身份在所选数据库中可访问的会话，复用已有的任务状态、澄清、SSE、历史星图和答复组件。`#d2` 提供 D2 的公开摘录。技术审阅授权及设置等专用页使用原审阅界面。

## 独立预览

在仓库根目录运行以下命令，然后打开 http://127.0.0.1:3090/dashboard 。本机示例通过前端计时器展示阶段变化，刷新会清空最近题目。发送示例之后可切换星图和关键进展，点击角色可查看公开摘要。

~~~powershell
npm.cmd --prefix showcase/frontend/deeptutor-preview ci
npm.cmd --prefix showcase/frontend/deeptutor-preview run dev
~~~

## 源码对照

上游为 HKUDS/DeepTutor v1.7.3，固定提交见[源码树](https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web)。下列上游路径均以 web 为根。分发文本见 [LICENSE.DeepTutor](LICENSE.DeepTutor)。

| 实际触发点 | 上游文件 | 预览的复用边界 |
| --- | --- | --- |
| 页面与新建题目按钮 | app/globals.css、features/ui-layout/modern/modern.css、tailwind.config.js、shared/ui/{Button.tsx,styles.ts} | 原样采用主题和按钮。页面框架、面包屑及本地工作台状态由 app/dashboard/page.tsx 组合。 |
| 侧栏示例题库及最近题目 | components/sidebar/NavigationPrimitives.tsx | 采用 Section 和 NavigationRow 的标记与类名，将路由链接适配为本地选择按钮。搜索和历史只查询夹具。 |
| 回填题目、输入与发送 | components/chat/home/{ChatComposer.tsx,ComposerInput.tsx,ChatComposer.module.css}、lib/{composer-keyboard,use-ime-composing,use-auto-sized-textarea}.ts | Composer.tsx 提取输入和工具栏结构，原样复用样式模块和三个输入钩子或辅助函数。示例选择使用本地数据。 |
| 已完成答复 | components/common/AssistantResponse.tsx | 复用公开答复的 article 与朗读属性。本地组件负责固定文本和可信公式的 KaTeX 排版。这一阶段未迁入上游 MarkdownRenderer。 |
| 关键进展 | components/activity/{ActivityStack,ActivityRow,StatusDot}.tsx、components/activity/types.ts、shared/ui/activity-state.ts | 原样采用栈、圆点和类型，活动行新增键盘展开。九角色星图取自 MathAgent 的既有角色位置，在 React 中渲染模拟状态。 |
| 点击角色、活动行中的阶段成果、手机导航 | shared/ui/Dialog.tsx | 保留上游的焦点限制、关闭和焦点恢复，关闭图标改为原生按钮。详情内容和靠边布局属于 MathAgent，尚未迁入 SessionViewerPanel 的多标签查看器。 |

## 浏览器复核

两端使用同一道多项式题、相同的候选根和代回检查范围。旧版走浏览器拦截的公开 API，新版消费本地示例；这项检查只比较界面和交互。桌面 1280×720、手机 390×844，中文，浅色，减少动画。测试需 Node 24、两端的锁定依赖，以及旧版 Playwright 配套的 Chromium。新版先执行 npm run build、npm start，另一个终端在 chat-frontend 下运行以下旧版命令。对照端口 4190 仅供浏览器夹具使用。

~~~powershell
npm.cmd run dev -- --host 127.0.0.1 --port 4190 --strictPort
~~~

随后在 deeptutor-preview 目录运行：

~~~powershell
node tests/compare.mjs
~~~

截图保存在仓库 artifacts/deeptutor-ui-stage1。compare-1280-{new,running,done}.png 和 compare-390-{new,running,done}.png 左旧右新。preview-{1280,390}-drawer.png 记录详情。脚本检查示例输入、输入法确认、三个阶段、两道题的公式、星图成果、键盘展开、关闭焦点恢复、窄屏导航和新版外部请求数。
