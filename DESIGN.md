---
name: MathAgent Showcase
description: 本机数学工作区的浅色界面系统
colors:
  background: "#f7f8fa"
  surface: "#ffffff"
  surface-muted: "#eef2f4"
  sidebar: "#f1f4f5"
  text: "#18232f"
  muted: "#566574"
  border: "#dce2e6"
  border-strong: "#b7c3cb"
  accent: "#0f766e"
  accent-strong: "#095c56"
  accent-soft: "#9bc9c2"
  accent-wash: "#e9f5f2"
  success: "#216442"
  success-wash: "#edf7f0"
  warning: "#85520b"
  warning-wash: "#fff5e4"
  danger: "#a33131"
  danger-wash: "#fff0f0"
  on-accent: "#ffffff"
  overlay: "rgb(24 35 47 / 30%)"
typography:
  headline:
    fontFamily: "'Segoe UI', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.02em"
  title:
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "-.02em"
  section:
    fontSize: "1.125rem"
    lineHeight: 1.4
  body:
    fontFamily: "'Segoe UI', 'Microsoft YaHei', 'PingFang SC', system-ui, sans-serif"
    fontSize: ".875rem"
    lineHeight: 1.6
  report:
    fontSize: "1rem"
    lineHeight: 1.8
  label:
    fontSize: ".75rem"
    fontWeight: 600
    lineHeight: 1.5
  mono:
    fontFamily: "Consolas, 'SFMono-Regular', monospace"
    fontSize: ".875rem"
    lineHeight: 1.6
rounded:
  sm: "6px"
  md: "8px"
  lg: "12px"
spacing:
  '1': "4px"
  '2': "8px"
  '3': "12px"
  '4': "16px"
  '5': "20px"
  '6': "24px"
  '8': "32px"
  '10': "40px"
  '12': "48px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  button-primary-hover:
    backgroundColor: "{colors.accent-strong}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    rounded: "{rounded.md}"
    padding: "8px 12px"
  status-badge:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: "4px 8px"
  report-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "24px"
---

# Design System: MathAgent Showcase

## Overview

这是既有 accepted 工作区的系统整理，不引入新的品牌隐喻。依据是 `docs/frontend/v0.2-workspace-redesign.md`、`docs/frontend/ui-unification-contract.md` 与当前实现。中性浅色表面和蓝绿色强调色服务数学阅读、输入和运行观察；状态文字必须说明执行模式及验证边界。

**Key Characteristics:**

- 对话居中，运行观察与会话导航分列；窄屏使用原生模态抽屉。
- 设置、配对实验和运行证据共享阅读页框架。
- 自有 Vue 控件源码，单一 SVG 图标库；旧展示入口共享同一 token 文件。

前置 YAML 是设计记录的规范层；运行时唯一值来源是 `showcase/frontend/chat-frontend/src/styles/tokens.css`。二者有差异时核对实际实现、修正记录，禁止另建一套运行时变量。

## Colors

### Primary

蓝绿色 `accent` 用于主动作、焦点、品牌标记；`accent-strong` 用于链接及主按钮 hover/active；`accent-wash` 用于选中项与用户消息；`accent-soft` 用于选中边界。

### Neutral

`background` 是页面底色，`surface` 是阅读和控制表面，`sidebar` 是会话区，`surface-muted` 是弱容器。`text` / `muted` 区分正文和辅助信息；两级 border 区分分隔线与控件。

成功、警告、失败采用对应语义色和浅底，仅表示运行或检查状态。**The State Evidence Rule.** 状态点必须伴随文字；颜色和 completed/succeeded 都不能作为数学正确性的证明。

## Typography

正文与标题继承本机 UI 字体栈，ID 使用等宽栈。正文、报告、标签与标题层级见 YAML。欢迎标题在窄屏下降到 title 层级；页标题用 title，报告段落用 report。报告正文换行，公式容器允许局部横向滚动，禁止让整页横向溢出。

不下载外部字体。系统字体只保证同一 OS 和字体版本下的截图复现，不保证跨平台像素一致。当前系统标题字体是既有实现，不将其扩展为品牌展示字规范。

## Layout

工作区高度为 100dvh。桌面左栏 248px，右栏 320px，主列 minmax(0, 1fr)。大于 1180px 时观察栏默认打开，关闭后释放空间；不大于 1180px 时观察栏转右抽屉。不大于 760px 时左栏也转抽屉，中间占满宽度。抽屉宽 min(360px, 100vw - 32px)，关闭后不能参与背景 Tab。

对话阅读宽度上限 760px，欢迎内容上限 640px；普通阅读页上限 1120px、桌面两侧至少 32px，窄屏两侧 16px。对话独立滚动，输入栏保持可达；桌面输入栏宽 min(760px, 100% - 48px)，窄屏为 100% - 24px。设置、配对实验的双列在 760px 处变单列。间距沿用 YAML 四像素节奏。

## Elevation & Depth

常规页面依靠底色、细边界和留白区分层次，报告不加阴影。唯一共享浮层阴影是 `shadow-overlay`（`0 16px 48px rgb(24 35 47 / 16%)`），配合 overlay 用于抽屉。焦点环为 accent 的 2px outline、外偏移 3px，不用阴影替代。

## Shapes

小圆角用于状态与行内代码，中圆角用于按钮、选中行、通知，大圆角用于输入容器、用户消息和报告。状态点为圆形。默认控件最小高 40px；会话行内操作桌面 28px、移动 36px 是现有紧凑例外，不推广为其他按钮的默认尺寸。

## Components

按钮使用 primary、secondary、ghost、danger 四变体，共享间距、字重和焦点；busy 同时禁用并设置 aria-busy。图标按钮必须由调用方提供可访问名称。hover/active 改变背景和边界；禁用透明度为 .48。过渡为 160ms、cubic-bezier(.16, 1, .3, 1)，减少动态效果偏好时禁用过渡和动画。

状态徽标同时显示中文标签和原始代码；未知值原样显示，不能默认为成功。移动工作区顶部隐藏徽标原始代码是空间例外，报告和观察区仍保留模式信息。

输入栏是带边界的大圆角容器；focus-within 改为 accent 边界，textarea 仍有可见焦点。原生 Enter 提交、Shift+Enter 换行、输入法确认不提交。waiting_input 使用同一输入框补充条件。

阅读页面通过 PageFrame 提供标题、描述、actions、导航和跳转主内容链接。导航选中态使用浅强调底与深强调字。报告通过安全 Markdown 适配器与 KaTeX 显示，来源文本不直接注入 HTML。运行观察复用 ResponsivePanel；时间线默认展开，节点第一次点击即折叠。

## Do's and Don'ts

### Do:

- **Do** 从 tokens.css 与 components/ui 复用值和控件，新增页面先采用现有框架。
- **Do** 保留中文状态、模式原值、验证限制、可见焦点与失败重试。
- **Do** 在固定浏览器环境与四档宽度复核截图后更新记录。

### Don't:

- **Don't** 引入第二套框架、状态、数学渲染或图标库，或 CDN 字体与运行时资源。
- **Don't** 用渐变、大面积装饰和无信息卡片替代数学内容。
- **Don't** 将界面通过、演示数据或有限验证声明为数学能力提升。
