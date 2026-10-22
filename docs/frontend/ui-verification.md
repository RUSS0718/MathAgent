# 前端统一验证记录

日期：2026-10-22。范围以 [验收合同](ui-unification-contract.md) 为准；复现入口为 [UI 复现指导](ui-reproduction-guide.md)。

## 实现范围

统一 Vue 工作区、对话报告、设置、Campaign 列表与详情、Run 审阅，以及官方 Demo、旧版 Showcase 和未构建提示页。共享语义 token 与本地组件源码，保留 Vue、Pinia、Zod、KaTeX，唯一图标库为 `@lucide/vue`。依赖合同检查限制直接依赖及核心包重复安装。

修复观察面板关闭、移动抽屉焦点、首次折叠时间线、输入法提交、等待补充条件、错误重试和正常 interrupt 被误报为 SSE 故障的问题。官方 baseline 文件没有变化；展示通过不代表数学能力提升。

## 验证环境

- Windows 11 10.0.26200；Node 24.18.0、npm 11.16.0、uv 0.10.9。
- Playwright 1.64.1；Chromium 156.0.8078.4，revision 1248。
- DPR 1、zh-CN、Asia/Shanghai、浅色、减少动画；使用系统字体。
- Vue 页面宽度 320、768、1024、1440；旧页宽度 320、1440。
- 固定合成 API fixture，不调用模型；35 张 PNG 基准，`maxDiffPixels: 0`。

## 检查结果

| 检查 | 结果 |
| --- | --- |
| `npm ci --no-audit --no-fund` | 通过 |
| `npm audit --audit-level=high` | 0 vulnerabilities |
| `npm run check` | 依赖合同、类型检查、13 项单元测试与生产构建通过 |
| `npx playwright test` | 43 项通过，未更新基准的像素比较通过 |
| 浏览器 axe / 横向溢出 / console | 视觉矩阵中的 WCAG A/AA 自动检查无违规，无横向溢出及页面错误 |
| `uv run python scripts/check.py --offline` | 190 项测试及仓库检查通过 |
| `uv run python scripts/check_showcase_release.py` | 通过 |
| Python 修改文件 Ruff、`git diff --check` | 通过 |

生产构建 JS 448.71 kB（gzip 141.30 kB）、CSS 51.64 kB（gzip 12.92 kB）。这些是构建体积，不是实测网络或性能评分。

独立视觉审阅检查了 35 张截图及相关源代码，发现等待状态 fixture 和 Campaign 成功计数不一致。修正并刷新基准后，审阅者对这两项修正复核通过，结论为可交付；该结论不等同于第二次完整独立审计。

在本地 fake Flask 服务上另外验证了实际构建页面的示例填入、提交、报告显示和三个 SSE 事件。没有进行 live 模型调用。

## 证据与限制

测试源码、固定数据、配置和 PNG 基准位于 `showcase/frontend/chat-frontend/tests/browser/` 与 `playwright.config.ts`；可重新执行。运行日志位于忽略目录 `artifacts/ui-unification/`，不作为版本库必需文件。

Impeccable launcher 下载引擎未完成，未运行其 detector；不得把本次人工审阅或 Playwright 检查称作 detector 通过。使用了 skill 的直接读取上下文降级流程。

像素完全相同要求同一系统字体、浏览器版本、视口、数据与状态。跨操作系统字体栅格化不保证逐像素相同。自动 axe 检查不是完整人工无障碍认证；这些验收也不证明数学正确率或线上服务稳定性。
