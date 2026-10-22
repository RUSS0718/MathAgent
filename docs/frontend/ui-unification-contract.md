# 全前端统一与复现合同

状态：实施合同，依据 2026-10-22 用户请求；完成证据见 `ui-verification.md`。

## 产品目标与范围

让数学问题输入、运行观察、公开报告、配对审阅和设置具有一致的控件与导航。
保留 accepted 的浅色中性表面、蓝绿色强调色、Vue 3 技术栈及所有公开信息边界。
覆盖 `/dashboard`、会话路径、settings、campaigns（列表与详情）、run，
以及独立官方 Demo、旧 Showcase 页面和未构建工作区提示。
不修改官方 baseline、求解预算、API 合同或算法。

## 调研与技术决策

- 现有样式重复定义按钮，设置页缺少布局，侧栏隐藏逻辑与 CSS 不一致。
- 保留 Vue、Pinia、KaTeX、Zod。采用单一 Lucide SVG 图标库，具名导入；
  UI 原语源代码归仓库所有，不叠加 Element Plus、Ant Design、Tailwind 或其他图标系统。
- 复杂焦点行为交给原生 `dialog.showModal()`；可折叠桌面侧栏与移动抽屉复用同一内容。
- Playwright 固定 Chromium、locale、timezone、viewport 和测试数据；axe 检查可访问性。
- 系统字体在同一 OS/字体版本下复现；跨 OS 不承诺逐像素一致，截图基准按平台保存。

来源：[Lucide Vue](https://v0.lucide.dev/guide/packages/lucide-vue-next)、
[原生 dialog](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog)、
[Playwright 截图比较](https://playwright.dev/docs/test-snapshots)。

## 切片与退出条件

1. 基线与风险检查：启动现有 UI，保存现状截图；验证原生抽屉可管理焦点。
2. 共用设计系统：语义 tokens、按钮、图标、状态、页面框架；依赖清单精确锁定且检查重复。
3. 页面迁移：聊天与观察、设置、实验列表/详情、运行报告、旧入口全部统一。
4. 交互回归：先用浏览器验收复现抽屉隐藏、输入法 Enter、节点首次折叠与加载失败，再修复。
5. 发布验证：前端 check/audit、浏览器、Python unittest、offline 与 Showcase 发布门禁。
6. 复现资产：DESIGN.md、UI 指南、固定 fixture、截图基准和更新规则；由独立 reviewer 核对。

## 可执行验收

- 320、768、1024、1440 宽度无页面横向溢出；完整报告和长 hash 可换行。
- 桌面隐藏观察栏后主区域扩展；移动抽屉关闭后不参与 Tab，Escape 关闭并恢复焦点。
- 中文输入法确认不发送；普通 Enter 发送，Shift+Enter 换行。
- 节点默认展开，第一次点击即折叠。
- 加载、空、失败、成功、等待输入均有文案和可用动作；错误提供重试。
- 页面导航一致；模式与验证边界明确，不把 fake/replay 或 completed 当作数学正确率。
- 可见控件有名称、焦点环和禁用状态；axe 无 serious/critical 问题。
- 前端生产依赖单一实现、精确版本；不增加第二个框架、状态库、数学渲染库或图标库。
- 固定数据不调用模型、不写真实用户会话；运行产物只写 artifacts。
