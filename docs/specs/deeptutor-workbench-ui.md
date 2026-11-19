# MathAgent 工作台复用 DeepTutor 前端源码的实施规格

**状态**　阶段 1 已交付独立夹具预览，2026-11-19；阶段 2、3 待实施。启动、源码对照与截图复核见[预览说明](../../showcase/frontend/deeptutor-preview/UPSTREAM.md)。MathAgent 对照源码为 `efa3cfb1f3ee9d9e9a167a4b32e9f4d1cc5329f6`。上游固定为 DeepTutor `v1.7.3`，提交 `4c1e000d8563c5ac3b231baaaf149dc4dc4d2406`。[上游提交][dt-commit]

目标是让用户在同一台机器打开两个工作台，用同一道数学题判断是否采用 DeepTutor 的界面。预览直接运行上游 React 组件，范围从输入框、会话侧栏一直到答复、执行进展和右侧详情。求解、数学内容、权限与结果来源由 MathAgent 提供。第一份可看的交付是可点击的本机页面，以及新建题、求解中、完成后三种状态的并排截图。

## 打开预览后能看到什么

| 场景 | 预览的画面与操作 |
| --- | --- |
| 新建题 | 使用 DeepTutor 的页面留白、输入框、工具栏和会话选中态，显示 MathAgent 名称。点击已有示例回填题目，输入法确认候选字后还可继续编辑。题图能力开启时出现 PNG 附件按钮。 |
| 求解中 | 左栏可回到最近题目。中央保留原题和当前阶段，公开事件到达时更新。普通会话沿用完整协作星图作为过程区默认视图，切到**关键进展**后用 DeepTutor 的活动行显示每一步。点击角色可在右侧读其公开成果。 |
| 完成后 | 答复在过程区之前。公式、结论和本次检查范围一起可读。右侧面板可展开某一步的成果并返回刚才的位置。历史回放、模拟运行和实时运行各有文字标识。 |

第一轮选择上游默认的 `modern` 布局，固定系统浅色所用的 `snow` 配色及中文界面。官方聊天截图可供认风格，它拍摄于 2026-10-28。精确对照使用固定提交实际渲染的组件。[布局默认值][dt-layout] · [配色默认值][dt-theme] · [上游聊天截图][dt-shot] · [截图拍摄说明][dt-shot-notes]

## 哪些源码实际进入页面

| 页面区域 | 上游源码 | 接到 MathAgent 的位置 |
| --- | --- | --- |
| 页面框架和基础控件 | `AppShell`、`PageBar`、`modern.css`、全局样式，以及实际用到的 Button、IconButton、Dialog、状态与空态组件。[布局][dt-shell] · [主题][dt-modern] · [控件][dt-controls] | 沿用组件结构、断点、间距、焦点及选中态。产品名称和路由来自 MathAgent。 |
| 会话侧栏 | `SidebarShell`、`RecordList` 及导航控件。[侧栏源码][dt-sidebar] | 接现有会话的搜索、新建、选择、重命名和删除。普通用户与技术审阅者分别取得有权打开的入口。 |
| 输入框和示例 | `ChatComposer`、`ComposerInput`、`ChatComposer.module.css`、`StarterSuggestions`。[输入组件][dt-home] | 复用输入、附件标签和发送控件。用现有示例和答复模式替换上游知识库、模型选择、语音及动态推荐的绑定。保留文字、单张题图、图文同题三种提交合同。[题图合同](../engineering/showcase-multimodal-intake.md) |
| 消息、答复与公式 | `ChatMessageList`、`AssistantResponse`、`MarkdownRenderer`。[消息列表][dt-messages] · [答复组件][dt-answer] | 读取已保存的普通答复及其展示状态。优先复用上游排版，公式沿用 MathAgent 的安全渲染规则。公开内容显式关闭原始 HTML，只渲染允许的链接和资源。[当前渲染边界](../../showcase/frontend/chat-frontend/src/renderers/markdown-adapter.ts) |
| 关键进展 | `ActivityStack`、`ActivityRow`、`ActivityFold`、`StatusDot`。[活动组件][dt-activity] | 直接用公开事件投影填充角色、动作、状态和详情。仅当记录中有相应证据时显示代回检查、模型审阅或形式验证。[现有投影](../../showcase/frontend/chat-frontend/src/runtime/jobs/workbench.ts) |
| 右侧详情和窄屏抽屉 | `SessionViewerPanel` 的面板外壳、标题、关闭与焦点交互。[详情组件][dt-viewer] | 提供本次角色成果、来源版本和可用证据。完整星图及回放使用 MathAgent 的角色与事件语义，历史成果按所选版本打开。[角色成果合同](../frontend/role-stage-summaries-contract.md) |

**复用如何计数。** 目标是六个区域各有上游 TSX 在浏览器中实际渲染。随代码维护一份 `UPSTREAM.md`，逐区列出原样采用、基于上游修改和 MathAgent 专用的文件，并指明触发该组件的页面操作。原样文件核对 Git blob，修改文件保留来源路径、固定提交和可复查的差异。只拷进目录、只引用 CSS 而自行重写整个交互、或跳回旧页，都单列为尚未完成的组件迁移。遇到耦合过重的父组件，先取其实际渲染的上游子组件，再记录替换了哪段绑定以及原因。

分发时附 Apache-2.0 文本，保留适用的上游声明，在修改文件中标明改动。若引入 `web/vendor/thinking-orbs`，同时带上该组件的 MIT 声明。保留 MathAgent 自己的标识。[上游许可证][dt-license] · [第三方声明][dt-notices]

## 预览如何接入现有工作台

预览拟放在 `showcase/frontend/deeptutor-preview/`，使用独立的 React、Next.js App Router、上游 Tailwind 配置和 npm 锁文件。现有页面由 Flask 提供 Vite 静态产物，上游则构建带 Node 服务的 Next standalone。单独启动预览能直接使用上游的 `next/navigation`、`next/dynamic`、CSS Modules 和 TSX。原有 Vue 依赖规则继续适用于原工作台，预览的新增依赖按实际导入锁定。[现有架构决定](../adr/0004-v0-2-flask-and-frontend-boundary.md) · [前端统一合同](../frontend/ui-unification-contract.md) · [上游构建配置][dt-build]

- **一个后端，两个入口。** 现有端口提供 Vue 的 `/dashboard`。Next 在另一个回环端口提供同路径及 `/dashboard/session/<id>`。两者使用同一个 `127.0.0.1` 主机名。预览将同源 `/api/*` 转给同一个 Flask 实例，透传 Cookie、CSRF、幂等键及 SSE 游标。启动日志给出两个实际地址。关闭预览即可返回原页面。[现有启动器](../../scripts/start_showcase.py) · [Flask 入口](../../showcase/flask_app.py)
- **复用数据协议。** 在浏览器端使用现有 TypeScript 请求、Zod schema、`readJobEvents` 和 `projectWorkbench`。React 只负责页面状态和取消订阅。先验证所需模块可独立导入，遇到 Vue 或 Pinia 依赖时只抽出双方需要的纯函数。上游的账户、聊天引擎、知识库和课程接口不属于预览的业务请求。[API 客户端](../../showcase/frontend/chat-frontend/src/api/client.ts) · [事件传输](../../showcase/frontend/chat-frontend/src/runtime/jobs/sse-transport.ts)
- **保留求解与读取的区别。** 用户发送时调用 `POST /api/agent/jobs`。同一次提交重试沿用原幂等键。最终答复读 `GET /api/agent/jobs/<id>/answer`，角色成果读 `role-results/<role>` 并携带所选来源版本。新旧页并排查看同一个 Job。刷新、展开、切换会话和回放新增求解与模型调用均为 0。[答复与授权合同](../engineering/reviewer-access-195.md) · [身份与恢复导航](../engineering/identity-navigation.md)

## 实施顺序与阶段交付

| 阶段 | 实施内容 | 可审阅的退出条件 |
| --- | --- | --- |
| 1 · 先看效果 | 从固定提交引入主题、控件和六个区域的可见组件。用同一组脱敏公开数据驱动两版界面，锁定时间、语言和字体环境。优先接入耦合最重的输入框和侧栏。 | 提供可点击预览，能输入题目、展开活动行、打开和关闭详情。交付三个状态的桌面并排图、一组手机图和逐区来源表。夹具标为模拟，评审可在本阶段直接判断外观。 |
| 2 · 走通一次求解 | 在 fake 模式接同一个 Flask。接入身份、会话、题图、一次提交、SSE、最终答复与角色成果。 | 从新建题走到终态，打开另一版的同一会话深链。两页的题干、Job、答案和来源相同。能在终态前看到事件，断线能续接。此阶段交付下方的一键预览命令。 |
| 3 · 补齐现有操作与页面 | 普通页覆盖澄清、改题、暂停、恢复、取消、失败、答复模式、星图与回放。随后把相同的上游框架和控件用于技术审阅授权、设置、配对实验、运行详情及按开关启用的系统视图。 | 普通身份和审阅身份各走一遍对应路由。逐项记录已迁移区域及仍跳往旧页的操作。已有历史会话可重开。各路由的功能与权限按当前合同验收。[路由清单](../../showcase/frontend/chat-frontend/src/runtime/navigation/app-route.ts) |
| 4 · 决定主入口 | 根据并排效果、六区覆盖结果和功能回归决定是否将预览作为 Showcase 默认 Web 界面。同时比较同机冷启动至可输入的时间及首屏 JS 传输量。 | 采用时先演练显式选择新版或旧版（拟用 `--ui deeptutor` 和 `--ui vue`），复开同一会话，确认进程可完整退出。更新架构决定、启动说明并执行发布门禁。选择保留原界面时，预览继续从显式入口访问。[工程门禁](../engineering/development-gates.md) |

阶段 1 已提供 `npm --prefix showcase/frontend/deeptutor-preview run dev`，在安装锁定依赖后即可用夹具预览，无需模型凭证。阶段 2 拟新增以下一键命令，启动一个 fake 后端和预览所需的前端。终端同时打印旧版与新版地址，Ctrl+C 回收该次启动的子进程。

```powershell
uv run --no-project python scripts/start_showcase.py web --mode fake --ui deeptutor
```

## 怎样验收效果

每个代码切片先保存能复现缺口的失败用例，再改源码。验收材料写入 `artifacts/<run_id>/`，记录 MathAgent 与 DeepTutor 的提交、数据来源、浏览器和窗口大小。

| 验收项 | 操作与通过条件 |
| --- | --- |
| 视觉对照 | 同一份公开夹具按相同事件位置停在新建、运行、完成三个状态。在 1440×900 对照整页，在 390×844 操作侧栏和详情抽屉。在相同内容和宽度下，输入框、活动行和侧栏选中项再与固定提交的上游组件裁图对照，逐项说明布局、字号、间距与动效的可见差异。 |
| 现场阅读 | 使用现有 D2 彩排场景，在 1280×720 首屏读到原题、因式分解、两根及整题审查范围。点击星图角色打开所选成果，Esc 后焦点回到触发点。普通页默认完整星图，只出现一张主图。受控夹具与真实历史分别记录，历史样本不可得时将该项记为未验证。[现场彩排](../evals/onsite-demo-209-20261118.md) |
| 输入与恢复 | 中文输入法确认产生 0 次提交，Shift+Enter 换行，普通 Enter 发送一次。题图开关、纯图提交和上传失败按现有合同处理。模拟提交回包丢失、SSE 中断及重复事件，恢复后只有一个 Job，每条公开进展出现一次。 |
| 答复与权限 | 覆盖成功、等待补充、取消、失败和旧会话。答复整理中或不可用时显示服务端状态。普通用户与审阅者使用独立浏览器上下文，普通用户读取技术接口得到原有拒绝结果。刷新和回放前后核对 Job、答案、来源及预算账本。公开界面只接收可展示数据，记录到 DeepTutor 业务服务的请求数为 0。 |
| 回归与交付 | 复用当前浏览器合同检查键盘、窄屏、减少动效、长公式和历史深链。两端可分别构建。默认 Web 启动、Notebook、独立 Demo、官方 baseline 和请求预算按原工程门禁核对。记录六个区域的实际复用结果与剩余差异，供主入口决策使用。 |

[dt-commit]: https://github.com/HKUDS/DeepTutor/commit/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406
[dt-layout]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/lib/ui-layout.ts
[dt-theme]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/lib/theme.ts
[dt-shot]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/assets/figs/web-dev/chat.png
[dt-shot-notes]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/assets/figs/web-dev/README.md
[dt-shell]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/layout
[dt-modern]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/features/ui-layout/modern
[dt-controls]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/shared/ui
[dt-sidebar]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/sidebar
[dt-home]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/chat/home
[dt-messages]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/features/chat/messages/ChatMessageList.tsx
[dt-answer]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/common/AssistantResponse.tsx
[dt-activity]: https://github.com/HKUDS/DeepTutor/tree/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/activity
[dt-viewer]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/components/chat/home/SessionViewerPanel.tsx
[dt-build]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/web/next.config.js
[dt-license]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/LICENSE
[dt-notices]: https://github.com/HKUDS/DeepTutor/blob/4c1e000d8563c5ac3b231baaaf149dc4dc4d2406/THIRD_PARTY_NOTICES.md
