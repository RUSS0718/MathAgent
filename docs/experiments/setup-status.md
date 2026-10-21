# 本轮实验设置状态

日期：2026-10-21。基线：develop 的 5b0e1912e1cc82d7ab1ecd3bcb8ea5ffc10933ae。当前工作分支：chore/experiment-setup-intern-s2。该状态只覆盖本轮离线设置，不代表 S1–S6、五个算法或 live 实验已经完成。

## 已完成

- 读取 AGENTS.md、文档索引、相关 accepted ADR、官方 baseline 与提交规范。
- 从用户指定 develop 创建并签出本地 setup 分支，保存本地逻辑提交；没有推送远端。
- 固定并阅读 Matt Pocock skills 上游版本 5beb35b040e3de97e54fa9e386d7e42d15c295c2，采用 to-spec、to-tickets、TDD、Standards/Spec 双轴审查与 PR 模板。
- 使用 uv sync --locked --all-groups 安装锁定的开发环境，Python 为 3.12.14。
- 新增总计划、develop 审计、Intern S2 合同、五组 PRD/技术规格/ADR、研究近邻索引和默认离线实验配置。
- 实现 scripts/check_experiment_setup.py 离线预检；检查五个方向、15 份文档、五个关闭开关、预算类型和 11 个受保护文件。报告保留 network_requests=0 与 planned_not_implemented=true。
- 新增六个公开 CLI 合同测试，按 red→green 开发；审查中再以三个小数预算反例复现并修复误通过。Ruff 两文件检查通过。
- 质量 CI checkout 配置完整历史，CLI 支持 detached HEAD；Standards 与 Spec 审查的阻塞发现已修复。

## 实际验证

首次对原始 develop 运行 scripts/check.py --offline，98 项 unittest 通过。完整回归所验证的实现提交为 9dc8b9373813878900eaa64d3bf243638e9e1420；在该提交的干净 detached worktree 运行下列命令，使用同一锁定依赖环境。命令使用 --frozen --no-sync，验证时没有安装或升级依赖。随后仅做 Ruff 格式整理，已逐文件核对 Python AST 相同，并重跑六项 CLI 合同；运行行为没有改变。

| 检查 | 结果 | 说明 |
| --- | --- | --- |
| uv run --frozen --no-sync python scripts/check.py --offline | PASS；104 项测试通过，21.592 秒 | workspace contract、test seams、服务入口同时通过；只是离线工程证据 |
| uv run --frozen --no-sync python scripts/check_showcase_release.py | showcase_release=PASS | 官方基线、脱敏回放、发布声明与相关回归通过；不是 API 或数学性能验收 |
| uv run --frozen --no-sync ruff check scripts/check_experiment_setup.py tests/test_experiment_setup.py | PASS | 新增 Python 文件静态检查 |
| uv run --frozen --no-sync ruff format --check scripts/check_experiment_setup.py tests/test_experiment_setup.py | PASS | 两文件格式符合配置；AST 对照通过 |
| 六项预检 CLI 测试 | PASS；最终修复回合 0.481 秒 | 包含 profile/model、联网、预算、路径、基线与成功报告合同 |

在本轮离线设置的 detached 检查中，前端代码未变，未重新安装或执行前端构建；这不代表 GitHub 托管 CI 已经运行。PR #22 的 audit 修复和后续验证另见下文。

## 检查环境说明

默认隔离环境禁止创建本地 socket，曾使七项 HTTP 服务测试及嵌套回归失败。未为此修改测试或产品代码；在允许 127.0.0.1 临时监听的环境重跑后通过。重跑只使用离线替身，没有调用模型 API，该环境因素不作为产品修复。

检查时使用 UV_CACHE_DIR=/tmp/mathagent-uv-cache；detached 验证通过 UV_PROJECT_ENVIRONMENT 指向已安装的仓库环境。主工作树始终保持在 setup 分支。

原始日志保存在 ignored artifacts/setup-20261021/，不提交到 Git；交付包中的 validation 目录保存允许公开的离线日志副本。核验用 SHA-256 如下。

| 文件 | SHA-256 |
| --- | --- |
| final-detached-repository-check.log | 557be48f9d20690c93c0a71dad69ad866ea3aa74d1317c8d11d985bbdab28937 |
| final-release-check.log | 6b5ec07ad2519a0751d83c798d76c7f44a43c9baa303677e19b7f70a58926c16 |
| integer-budget-red.log | 1e2d20a8fe081478a8c425980ac2a72f1db62c37c266da7aa16cd845c298c047 |
| integer-budget-green.log | b02f0a8f2a2441cc95304a720e90a49439104f0a03f5a60582f6549e00881997 |

## PR #22 frontend audit follow-up

- Base 与 PR head 原本锁定相同的 Vite `8.1.5`；audit 失败来自既有依赖被新发布的 advisory 命中，不是 PR 引入。将 Vite 和锁文件更新到修复版 `8.1.6`，提交 `ed45443`。
- 本地 `npm ci --no-audit --no-fund`、`npm audit --audit-level=high` 和 `npm run check` 均通过；audit 报告 0 项，前端 6 项测试通过，生产构建成功。
- 推送后 GitHub Actions run `39562361569` 的 `quality` 与 `frontend` jobs 均通过。PR 仍为 Draft/Open；未合并、关闭或归档分支。
- 本次没有调用 Intern API；官方评分基线与默认入口未修改。

## 尚未完成

- S1–S6 的 usage 贯通、工具原生协议、Run 预算隔离、live 取消/恢复、最终证据绑定和配对 runner。
- API 短 probe、AC-06 的当前 Workspace live 证据、12 题成本试跑及数学效果评估。
- 五个方向的算法开发与实验分支启动、组合消融、学术结论。
- GitHub Issues、远端推送、PR 和合并。没有预造 Issue/PR 编号。

本地没有配置 INTERN_API_KEY，也没有仓库 .env 文件；仅检查是否存在，没有读取密钥。API 计量、账号额度和费用均未实测。配置文件中的预算是后续调度合同，不是已实施的在线限额控制。
