# MathAgent Showcase

MathAgent 的 Showcase 用于本地主观评测演示和工程验收。它包含 Vue 工作区、Flask API、命令行客户端，以及独立的官方入口演示页。fake 模式可离线查看交互；live 模式会调用 Intern 服务。fake、回放和结构测试不能证明数学正确性或能力提升。

## Showcase 组件

- **工作区前端**：会话与文件管理、Job 提交与恢复、SSE 执行时间线、结果报告和配对实验审阅页。源码位于 `showcase/frontend/chat-frontend/`。
- **Flask 后端**：提供工作区 API、Job 与事件流、报告和 Evidence；默认 `fake` 模式，运行数据写入忽略目录 `artifacts/`。
- **STAR SolverHarness**：显式 Showcase 路径中的 Python 编排与求解运行时，包含 Explore、Planner、Reasoner、Verifier、Meta 和 Researcher 角色；通过共享预算、隔离工具、持久状态和整题最终答案绑定组织运行。冻结实验 CLI 负责受控派发，独立核验器复核运行身份、事件与交付证据。它不是官方评分入口，也不因安装依赖而自动启用。
- **CLI**：`showcase_cli.py` 调用同一套会话、Job、事件和报告 API。
- **独立演示页**：`demo_server.py` 展示官方 `ReasoningAgent` 的 `/solve` 合同，不属于工作区，也不改变官方评分入口。

### 编排框架边界

LangGraph 承载工作区图执行及检查点；当前 STAR 产品入口在求解结束后保存图投影，不由 LangGraph 接管角色循环或自动压缩。STAR 的具体业务决策、角色协议、工具准入、预算、证据及最终绑定由仓库自己的 Python SolverHarness 实现。`pyproject.toml` 将 LangGraph 与 DeepAgents 列为 `showcase` 可选依赖。DeepAgents 只通过 `AgentAdapter` 边界提供可选角色适配器，不是 STAR 编排器，也不代表当前 STAR 路径默认使用它。

## 安装与运行

需要 Python 3.11 或 3.12、uv，以及 Node.js/npm。先在仓库根目录安装依赖：

```powershell
uv sync --locked --all-groups
```

### 离线 fake 模式

在仓库根目录启动后端：

```powershell
uv run python showcase_server.py --host 127.0.0.1 --port 8090 --mode fake --data-dir artifacts/showcase-local
```

如需前端开发服务器，在另一个终端运行：

```powershell
Set-Location showcase/frontend/chat-frontend
npm ci --no-audit --no-fund
npm run dev -- --host 127.0.0.1
```

打开 `http://127.0.0.1:5174/dashboard-assets/`。Vite 将 `/api` 请求代理到本机 8090 端口。也可先构建前端，再直接访问后端的 `http://127.0.0.1:8090/dashboard`：

```powershell
npm run build
```

以下 CLI 命令在仓库根目录执行，可检查服务或创建本地会话：

```powershell
uv run python showcase_cli.py health
uv run python showcase_cli.py session create
```

fake 模式返回确定性的演示结果，不访问模型。需要浏览器演示时，运行 `npm run dev`；前端不是后端启动的前置条件。

### Intern live 模式

在仓库根目录的未跟踪 `.env` 中配置 `INTERN_API_KEY`，然后启动 live 后端：

```powershell
uv run python showcase_server.py --host 127.0.0.1 --port 8090 --mode live --data-dir artifacts/showcase-live
```

前端开发服务器命令与 fake 模式相同。确认设置页显示 live 且凭证已配置后，CLI 的 `probe` 会创建 Job 并调用模型：

```powershell
uv run python showcase_cli.py capabilities
uv run python showcase_cli.py probe "求解 x^2-1=0，并检查候选根。"
```

`probe` 会产生真实 provider 请求；不要将其当作无 API 的本地检查。CLI 默认拒绝 fake 服务上的 `probe`。服务和 CLI 默认使用 loopback 地址及本地 cookie 文件。

官方评分入口位于根目录 `user_agent.py`，其演示页和 `/solve` 用法见 [Demo 使用说明](docs/demo.md)。

## 工程状态与验收边界

官方客观评测入口是根目录 `user_agent.py` 的 `ReasoningAgent`，评分实现位于 `implementations/`。Showcase 作为独立展示路径；未经独立验收的改动不得接入官方默认路径或改变其请求预算。官方文件和基线哈希见 [BASELINE.json](BASELINE.json)。

截至 2026-11-06，Issue #127 的 provider-live readiness **未通过**；最新 readiness-31 的自然多步结果为 UNKNOWN，未完成最终答案、整题审查和同文本绑定。Issue #128 的线上两臂均为 **NOT_RUN**。这些结果不支持数学能力提升结论；详见 [readiness-31 记录](docs/evals/provider-live-natural-20261106-readiness-31.md) 和 [文档索引](docs/README.md)。

仓库提供以下工程门禁命令：

```powershell
uv run python scripts/check_fast.py
uv run python scripts/check.py --offline
uv run python scripts/check_showcase_release.py
```

快速门禁、离线完整检查和发布检查覆盖不同范围；通过离线门禁不等于真实 provider 验收。前端检查在 `showcase/frontend/chat-frontend/` 执行：

```powershell
npm ci --no-audit --no-fund
npm audit --audit-level=high
npm run check
```

当前运行结果以实际门禁输出和对应评测记录为准；本 README 不据此宣称所有门禁已通过。发布判定及验收限制见 [v0.2 发布证据](docs/evals/v0.2-release-evidence.md)，检查范围见 [工程门禁说明](docs/engineering/development-gates.md)。

## 文档导航

- [版本、开发阶段与能力证据索引](docs/README.md)
- [Demo、Showcase 与 CLI 使用细节](docs/demo.md)
- [工程门禁与最终验收入口](docs/engineering/development-gates.md)
- [官方评分路径合并边界](docs/release-boundary.md)
- [v0.2 发布验收记录](docs/evals/v0.2-release-evidence.md)
