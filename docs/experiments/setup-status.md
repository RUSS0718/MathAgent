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

上述为 setup 时点记录；后续配置与阶段验收以以下增量记录为准。配置文件中的全局预算仍不是已实施的 Run 级在线限额控制。

## S1 Request Attempt 验收（2026-10-21）

- 权威规格为 GitHub [#23](https://github.com/RUSS0718/MathAgent/issues/23)，S1 ticket [#24](https://github.com/RUSS0718/MathAgent/issues/24) 已完成。实现提交 `92609ac` 已合入当前集成分支。
- 请求作用域 envelope 保留每个实际 HTTP attempt，包括失败和重试；Workspace report / Evidence 公开白名单计量，缺失或非法 usage 保持 null，不合成 total，金额保持 null。
- 离线重点合同、完整仓库检查（111 tests）、Showcase release gate、Ruff 与 diff check 通过。
- 当前环境仅检查到凭证配置存在，未读取或输出其值。使用 `uv run --frozen --no-sync python scripts/run_s1_probe.py --live` 执行已批准的唯一 G1 attempt，无重试：`thinking_mode=true`、`max_tokens=256`、HTTP 200、`finish_reason=stop`。
- requested model 为 `intern-s2`，returned model 为 `Intern-S2`；provider usage 为 prompt 123、completion 77、total 200；reasoning/cached token、provider request ID 和费用为 null。该次工程合同通过且基础 usage 可见，不证明完整内部思考计量、精确费用或数学能力提升。
- Run 为 `run_06e62b864a53bb4f0f5b9bb748d80e0e`，本地 attempt ID 为 `da9db60afa174cfda93224b4c535df5f`。脱敏计量归档：ignored `artifacts/s1-g1-e12e1e757962489183641d55966e14c9/g1-report.json`；不提交运行数据库或原始响应。
- S2–S6 尚未验收。G2 已独立批准最多 6 Run / 12 HTTP attempts、每 Run 两次生成、每次 max_tokens≤512、无重试、串行、失败不补跑；额度确认见 [#26 评论](https://github.com/RUSS0718/MathAgent/issues/26#issuecomment-6311481669)。PR #22 保持 Draft/Open。

## S2 离线闭环与 G2 失败证据（2026-10-21）

- [#25](https://github.com/RUSS0718/MathAgent/issues/25) 离线闭环通过，提交 `ad69ff5`；后续规格复核发现 Run report/Evidence 事件筛选不一致，已用 `da8b101` 修复并补成功/失败 HTTP 回归。native/text action、注册权限、schema、call ID、continuation 和 fake 来源均可查询。
- G2 辅助入口提交 `4532822`，默认离线零请求，显式 `--live` 才联网。128 项 unittest、23 项重点检查及 Ruff 通过；这些是离线工程证据。
- 执行唯一批准的 G2 批次后，6/6 Run 全部保留，实际使用 6 次 HTTP attempt。均为 HTTP 200、requested model `intern-s2`、returned model `Intern-S2`、finish reason `tool_calls`；均在 Registry 以 `tool_schema_invalid` 拒绝，未发起 continuation。G2 为 `needs_review`，[#26](https://github.com/RUSS0718/MathAgent/issues/26) 未完成，S3–S6 未启动。
- 安全参数摘要显示六次 `domain` 均为字符串，工具 schema 要求对象；同一 Registry 用对象 `{"kind":"real"}` 离线复核成功。现有证据指向模型参数形状不符合 schema，未复现校验器缺陷；未读取或公开参数字符串值、原始响应或隐藏推理。
- 六次 provider usage 合计 prompt 4048、completion 1393、total 5441；reasoning/cached 和费用仍未知。该合计仅用于本次验收消耗记录，不是 S3 的 Run 预算账本。
- 脱敏归档：ignored `artifacts/g2-live-ce9766241c9b4193b4ef988db2db50ee/g2-report.json`，SHA-256 `0aa3044d513da90bef1db7646175b42810753e3c4853f7ead88c3febbb1272b3`。失败不补跑；剩余 attempt 上限不自动授权替换失败 Run。再次 live 验收须明确新增预算。
- 用户另批预算后，用提示版本 `g2-native-tool-v2`（`a971919`）执行第二批 6 Run / 6 attempts；均仍为 `tool_schema_invalid`，未进入 continuation。安全摘要再次显示 `domain` 为字符串。仅强化提示未解决问题，不能区分模型生成不合规与托管服务处理嵌套 `oneOf` 的影响。
- 第二批 provider usage 合计 prompt 4870、completion 1494、total 6364；费用未知。归档为 ignored `artifacts/g2-live-c8a6c159a3404373aa9d6c6cb3588429/g2-report.json`，SHA-256 `31435d58bd10854b8f55ce9cc59c87e682a59eb06ed615336832ceb9bcc7f829`。
- `3cd4151` 在权威 schema 的 `domain.oneOf` 外显式增加 `type: object`，保留原分支与全部约束，并记录 schema 身份。此修正仅完成离线合同验证，托管服务效果未知；未执行第三批生成。
- 用户批准第三个独立批次后，在 `bcf1a20` 执行 G2：6/6 Run、12 HTTP attempts 全部形成 native 请求 → Registry success → 匹配 call ID 的 continuation 响应，G2 PASS，#26 完成。每次 thinking=true、max_tokens=512，无重试；前两批失败继续保留。候选集刻意含错误值，checker conflict 符合设计；通过只证明协议闭环，不证明数学能力提升、候选完备性或语义消费。
- 第三批归档：ignored `artifacts/g2-live-f5c14b5852474a7b85feb00b3428301f/g2-report.json`，SHA-256 `6d8f32818a8b50135a4ee7d8f26bae9ae42a8276b6d295b64eed63842b252f49`。此前“未执行第三批”是修正准备时点记录；当前 S2 live 硬门已通过，可进入 S3。

## S3 Run 预算隔离验收（2026-10-21）

- [#27](https://github.com/RUSS0718/MathAgent/issues/27) 的离线实现已合入集成分支，实现提交为 `9893438`、`93cf070`、`4819168`。Run 预算持久化并在每次 HTTP attempt 前原子预留，计量未知时保持未知；报告与 Evidence 提供脱敏预算快照。
- 双轴审查发现的两项 P1 已修复并复核关闭，包括并发预留与图执行计量边界、同步入口及不支持计量传输的预算绕过。Evidence 装饰器与预算实现的局部耦合作为本切片取舍保留。
- 最终重点合同 12 项通过；`uv run --frozen --no-sync python scripts/check.py --offline` 通过，146 项测试耗时 86.897 秒；`uv run --frozen --no-sync python scripts/check_showcase_release.py` 返回 `showcase_release=PASS`；`uv run --frozen --no-sync ruff check .` 与 `git diff --check` 通过。
- 发布检查与完整测试并发运行时曾出现 SSE 时序失败；顺序独立重跑发布检查后通过。该次暂态失败保留为环境与时序证据，不表述为首次检查全部通过。
- 相对 S3 前集成提交 `facd137`，`user_agent.py`、`implementations/` 与 `BASELINE.json` 无差异。此次未调用模型 API，离线合同通过不证明在线预算效果、精确费用或数学能力提升；S4–S6 尚未验收。PR #22 保持 Draft/Open。
- CI 后续暴露干净环境下的测试隔离缺陷：同步预算测试在设置替身凭证前构造客户端。本地 `.env` 曾掩盖该前提；测试现显式设置 dummy key。清除 provider 环境后的单项回归先失败后通过，重点 12 项、完整离线 146 项（83.305 秒）、顺序 release gate 和全部 pre-commit hooks 通过；没有读取或输出凭证值，也未联网调用模型。此处仅记录本地修复验收，远端 CI 状态另行核对。

## S3 Run 控制与恢复验收（2026-10-21）

- [#28](https://github.com/RUSS0718/MathAgent/issues/28) 已合入集成分支，代码验证提交 `f49ca22`，最终风险记录提交 `0f5f3a9`；完整证据见 [S3 控制风险验证](s3-control-risk-validation.md)。新增取消、截止时间、持久 LangGraph checkpoint、安全 waiting_input 恢复、重启待复核与审计保留合同。
- 预算预留与取消通过 SQLite 事务确定动作准入；已准入请求按在途处理，取消停止后续调度。终态 checkpoint 封存并冻结结束时间与耗时，迟到 usage 继续结算；安全 waiting_input 可在重启后恢复，其他不明 active checkpoint 进入 needs_review 并拒绝公开 resume。
- 双轴审查发现的问题均已修复并复核关闭。最终顺序执行：控制重点 11 项通过；`uv run python scripts/check.py --offline` 157 项测试通过（109.687 秒）；`uv run python scripts/check_showcase_release.py` 返回 `showcase_release=PASS`；`uv run ruff check showcase tests`、`uv run pre-commit run --all-files` 与 `git diff --check` 通过。check-json 无匹配文件而跳过。
- 相对前一集成提交 `d595ef9`，`user_agent.py`、`implementations/` 与 `BASELINE.json` 无差异。此次仅完成离线工程验收，未调用模型 API，不证明远端请求可撤销、精确费用或数学正确率提升。PR #22 保持 Draft/Open。

## S3 托管 CI 并发认证修复（2026-10-21）

- 托管 CI 暴露 LoopbackStore 共享 SQLite connection 的并发事务缺陷，独立复现出现 `InterfaceError`。`dc2bb35` 为连接上的事务增加 RLock 作用域，并补公开接口并发回归；未改认证合同。
- 最终顺序验证：重点 23 项通过；完整离线 158 项测试通过（136.245 秒），`repository_check=PASS`；独立 Showcase release gate、全部适用 pre-commit hooks、直接 Ruff 格式与静态检查、`git diff --check` 均通过。官方 `user_agent.py`、`implementations/` 与 `BASELINE.json` 无差异；未调用模型 API。
- 此处仅记录本地修复验收。#28 在新的托管 CI 通过前保持重新打开状态，S4 暂停；不能由本地通过推断远端 CI 已通过。PR #22 保持 Draft/Open。
