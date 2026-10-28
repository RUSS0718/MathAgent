# MathAgent 文档索引

文档职责：为开发者和 agent 提供版本、开发阶段、能力验收及官方边界的阅读入口。

适用范围：理解 v0.1、v0.2 历史版本和当前 v1.1 Solver Harness 规格；执行规则以根 [AGENTS.md](../AGENTS.md) 为准。

## 先读哪些文档

## 当前 ALIGN 状态

最新 RB08 工程门禁、真实实验失败及逐项 ROB-AC 边界见 [RB08 发布与真实实验记录](evals/star-rb08-release.md)。冻结源码 a10481d 的发布检查、前端、54项通用及12项产品浏览器检查通过；真实原E1执行2/4后停止，E2未执行。本轮目标为建立离线简单题、多步 Reference、工具、整题审查、文本绑定与进程恢复闭环；相关聚焦用例、全仓离线合同（757 项测试）及 Showcase 发布门禁均已通过。流式保持可选，本轮未发真实提供方请求，未验证 provider-live 兼容或数学正确率。完整测试命令、接口事实及证据边界见 [#96 非流式主路径验收记录](evals/star-stream-usage-96.md)。修复切片仍在本地、尚未合并；#96 保持开放。只读 Issue 核验（2026-10-27）：#96 是 #95 的直接 blocking issue；#95 正文中 `Blocked by #94` 已过期，因为 #94 于 2026-10-26 关闭。#87 保持开放，8 个子票中 7 个完成，#95 尚未完成；#80 保持开放，ALIGN-AC-18 真实自然非快通道闭环未通过，且无 #95/#96 对 #80 的直接阻塞关系。#95/#87/#80 均不在真实验收达标前关闭，整体为 engineering-preview。下方维护版本的测试数字属于历史记录。

当前 #97 是独立的非流式验收，不以前述旧 E1/E2 通过为前置，也不重算或覆盖原批次结果；#95 仍正式受 #96 阻塞。2026-10-28 首批两题 live 批次完成，但多步样本未进入登记要求的非快通道。后续 r8 批次完成简单题后，多步 Job 的第二次 Explore 请求超时，批次以 `unknown_transport` 停止并保留一个未决 attempt。最新 v5 已提高等待预算，但简单题一次成功计算后达到工具硬限，整题审查未执行，多步题未派发；1 次 HTTP 的 2483 tokens 全部已知，没有未知或未决 HTTP attempt。三份登记均已消费，不续跑、不重试；#97 保持开放。

#97 的当前结果见[非流式就绪核对记录](evals/star-readiness-97-status.md)，执行边界见[批次执行合同](engineering/star-readiness-97-execution-contract.md)，样本及预算见[两题登记记录](experiments/star-readiness-97-preregistration-draft.md)。记录区分离线门禁、真实 provider 工程闭环和数学判定；一次成功的整批调度不代表所有路径验收通过。

早期未采纳的组件合同、Reference readiness 与架构效果方案见 [STAR 架构健壮性与组件作用实验方案](experiments/star-architecture-robustness-plan.md)，仅作历史参考，不是当前验收目标。

spec #70（ALIGN-01..ALIGN-10，#71..#80）承接 #56 的语义偏移修复与重新验收：裁决消费与新动作身份、独立 ReplanDecision、Verifier/Explore 受控计算、分类账本与证明传递、协议失败与 unknown 分离、跨流程恢复，最终来源复核与发布判断见 [ALIGN-10 来源映射](evals/star-product-align10-source-mapping.md) 与 [ALIGN-10 发布记录](evals/star-product-align10-release.md)。记录区分 scripted/故障注入/live/replay 证据；真实非 Explore 快通道闭环尚未取得，历史工单关闭不升级为完整能力结论。

历史维护 #81–#86、后续 #82 及当时证据边界见发布记录顶部。当时47dc522发布检查PASS，AC-19浏览器与最终零skip详证未覆盖；离线同树648项中618通过、30跳过。这些是历史数字，不能替代上方RB08最终门禁。详见发布记录与[脱敏证据摘要](evals/star-maintenance-evidence-summary.json)。

RB-01 的仓库公共离线入口与证据边界见 [交付来源与离线复评 API](engineering/star-rb01-offline-acceptance.md)。该接口不派发模型或工具，历史重判不自动升级 #80 验收。

RB-03 的增量 `answer_claim.claim_type`、旧声明兼容、短题完整交付和受控测试边界见 [短题完整交付与证明义务合同](engineering/star-rb03-proof-obligations.md)。三调用受控测试不替代 RB-08 的真实模型验收。

RB-04 的增量执行、传输、整题审查、文本绑定和未形式化验证字段及 legacy 兼容见 [产品结果语义合同](engineering/star-rb04-result-semantics.md)。受控公共测试和前端渲染测试不替代 RB-08 的最终发布门禁。

RB-06 的零付费公共故障、真实隔离、进程恢复及五类旁路入口见 [E3 故障与恢复验收](engineering/star-rb06-e3-acceptance.md)。受控机制不标为 live 自然触发，skip 不计通过。

RB-07 的冻结题单、独立评分、双层硬预算和认证公共 Job 串行入口见 [固定实验协调器](engineering/star-rb07-experiment-coordinator.md)。受控矩阵不替代 RB-08 的真实模型与最终发布验收。

## 历史 SP 集成语境

以下 SP-01..SP-11 段落保留各阶段当时状态；其中“尚未完成”“拒绝启动”“未验证”不是当前 ALIGN 状态判断，请先读上方当前入口。

历史完整 STAR 产品集成由 [spec #56](https://github.com/RUSS0718/MathAgent/issues/56) 及 SP-01..SP-13（#57..#69）承载，承接 #23 基础设施与 #32 求解机制；当时从 [SP-01 #57](https://github.com/RUSS0718/MathAgent/issues/57) 的来源审计和风险验证开始。状态职责和恢复合同见 [ADR-0014](adr/0014-star-product-state-and-recovery.md)，范围形成过程见 [访谈记录](experiments/star-completion-interview.md)。当时新 spec 尚未完成；历史工单关闭不表示 Workbench 已贯通完整 STAR。

本次执行记录见 [产品集成执行合同](engineering/star-product-execution.md)。SP-01 已形成 [固定来源与全量验收映射](experiments/star-product-source-audit.md) 和 [风险报告](experiments/star-product-risk-sp01.md)：公共旧流程恢复有实测证据，但 STAR 接受步骤恢复尚未验证，Docker 原型输出限制存在已复现旁路。完整模式门槛仍未通过；SP-02 明确受限纵切的实现边界见 [合同](engineering/star-product-sp02-contract.md) 与 [实际验收记录](evals/star-product-sp02.md)；完整模式仍拒绝启动。

SP-03 的[共享账本与控制合同](engineering/star-product-sp03-contract.md)及[公共故障验证记录](evals/star-product-sp03.md)记录模型、重试、工具和研究的同一S3准入，取消/截止的数学事务栅栏及迟到用量；不替代后续恢复、生成Python隔离和MetaGuidance切换验收。

SP-04 的[产品集成验收合同](engineering/star-product-sp04-contract.md)和[产品路径验收记录](evals/star-product-sp04.md)覆盖Explore路由、合法Plan与双Gate的Job路径，并记录hint来源和隐私边界。验收使用fault-injection回复，不代表live模型效果；Python工具与执行产物另见SP-09验收。

SP-05 的[连续Challenge合同](engineering/star-product-sp05-contract.md)和[产品验收记录](evals/star-product-sp05.md)覆盖三轮双方历史、最新状态、单次接受、有界Meta及非法裁决拒绝，并记录界面异议/角色/用量。证据为fault-injection；恢复、最终文本绑定和live仍由后续责任票验收。

SP-06 的[回退与重规划合同](engineering/star-product-sp06-contract.md)及[产品验收记录](evals/star-product-sp06.md)覆盖同一 Job 的区间归档、依赖失效、合法救援、非法目标拒绝，以及 Meta 裁定的新计划实际执行；包含能识别失效事实复活的旁路探针。证据为 fault-injection，完整 reference 与 live 验收仍未完成。

SP-07 的[记忆、Skill 与局部指导合同](engineering/star-product-sp07-contract.md)及[公共产品验收记录](evals/star-product-sp07.md)覆盖七类协议的实际注入、受限工具故障指导、纯推理权限栅栏、三种局部恢复动作、多任务研究采纳与跨 Run 隔离。未知远端请求保持待复核；证据为 scripted/fault-injection，不代表 live 效果。

SP-08 的[安全恢复合同](engineering/star-product-sp08-contract.md)与[公共验收记录](evals/star-product-sp08.md)覆盖真实进程退出后的同一 Job 续算、已接受步骤与响应/工具回执复用、显式新身份重试、旧未知预留和原 deadline，以及并发/取消/只读反例。证据为 fault-injection；完整模式和 live 门槛仍由后续责任票验收。

SP-09 的[受控 Python 合同](engineering/star-product-sp09-contract.md)与[公共 Job 和 Docker 验收记录](evals/star-product-sp09.md)记录默认关闭的固定镜像 ID Registry 接线、S3 单次工具动作、外部 stdout/stderr 总量限制和授权产物下载。纯推理与受控工具故障的 MetaGuidance 见 SP-07 验收；完整 reference 继续拒绝启动。

SP-10 的[整题审查与交付绑定合同](engineering/star-product-sp10-contract.md)和[公共验收记录](evals/star-product-sp10.md)覆盖实际整题 Verifier、文本身份/版本/来源、改写降级、伪造引用拒绝、并发追加及回退/重规划后的合法救援绑定。证据为 scripted/fault-injection；LLM 审查不等于完整数学证明，真实验收仍由 SP-13 负责。

SP-11 的[候选与零调用选择合同](engineering/star-product-sp11-contract.md)及[公共验收记录](evals/star-product-sp11.md)记录受限 BestEffort 显式入口、候选全版本、依赖/反证排除、硬预算纯选择、S4 选择绑定与持久快照 replay。证据为 fault-injection/replay；完整模式和前端全生命周期仍受 SP-12/13 门禁约束。

| 当前任务 | 阅读顺序 | 读完应能判断 |
| --- | --- | --- |
| 了解 v0.1 做到了什么 | [能力基线](evals/v0.1-capability-baseline.md) → [开发完成记录](https://github.com/RUSS0718/MathAgent/issues/1#issuecomment-6209639217) → 下方 v0.1 文档链 | 工程完成、真实模型连接与数学效果各有什么证据 |
| 规划或评审 v1.1 Solver Harness | [v1.1 实现规格](https://github.com/RUSS0718/MathAgent/issues/32) → [STAR Core 实施规格](prd/STAR_CORE/STAR_Core_v1_2/STAR_CORE_SPEC_AGENT_v1_2.md) → [ADR-0013](adr/0013-solver-harness-boundary-and-shared-transaction.md) | v1.1 seam、v1.2 延期项、ticket 依赖和验收边界 |
| 规划或评审 v0.2 | [v0.2 PRD Lite](prd/subjective-agent-platform-prd-v0.2.md) → [v0.2 实现规格](specs/subjective-agent-platform-v0.2-spec.md) → [现状与前端接口调研](research/v0.2-planning-baseline.md) → [accepted ADR](#架构决策) | 范围、实现决策、测试 seam、验收条件和待验证假设 |
| 修改官方入口或讨论合并 | [BASELINE.json](../BASELINE.json) → [官方架构](architecture/pre-v0.1-official-agent-architecture.md) → [合并边界](release-boundary.md) | 冻结文件、调用预算、输出合同及重新验收要求 |
| 运行或演示 | [Demo 说明](demo.md) → [演示脚本](../DEMO_SCRIPT.md) → [验收门禁](ACCEPTANCE.md) | 入口、运行模式、回放和发布检查方式 |

[Solver Harness 结果导出与离线重放](evals/showcase-solver-result-replay-sh20.md) 说明 SH20 的公开函数、字段白名单与快照审计边界。

## v0.1 开发与验收文档链

下表按工程阶段导航；阶段设计、任务关闭和能力证据分别阅读。

| 阶段 | 文档 / 记录 | 用途与证据边界 |
| --- | --- | --- |
| Product Goal | [v0.1 PRD](prd/subjective-agent-platform-prd-v0.1.md) | accepted 的版本范围；不是当前完成状态表 |
| Research | [开源 Agent 调研](research/open_source_agent_landscape.md) | 机制来源与最初选型依据 |
| Risk Assessment / Spike | [风险评估](risk-assessment-v0.1.md)、[Spike 结果](risk-spike-v0.1-results.md) | 开发前连接实验；原型通过不代表产品能力通过 |
| Technical Design | [v0.1 技术设计](architecture/subjective-agent-platform-technical-design-v0.1.md)、下方 ADR | accepted 的实现边界；其中“待实现”保留开发前语境 |
| Spec / Acceptance Contract | [v0.1 实现规范](specs/subjective-agent-platform-v0.1-spec.md)、[总任务 #1](https://github.com/RUSS0718/MathAgent/issues/1) | 用户故事、接口责任、切片验收和开发完成评论 |
| Run / Persistence | [#2 Run 与 Profile](https://github.com/RUSS0718/MathAgent/issues/2)、[#3 持久化](https://github.com/RUSS0718/MathAgent/issues/3) | 开发切片合同与完成状态 |
| Agent / Tool Loop | [#4 执行循环](https://github.com/RUSS0718/MathAgent/issues/4)、[#5 工具](https://github.com/RUSS0718/MathAgent/issues/5)、[#6 文本 Adapter](https://github.com/RUSS0718/MathAgent/issues/6) | 动态循环、预算、实验工具和模型连接的实现任务 |
| Vision / Evidence | [#7 图文 Adapter](https://github.com/RUSS0718/MathAgent/issues/7)、[#8 Verification / Evidence](https://github.com/RUSS0718/MathAgent/issues/8) | 资产引用、轻量检查与导出合同 |
| Browser Vertical Slice | [#9 API 与浏览器切片](https://github.com/RUSS0718/MathAgent/issues/9) | v0.1 最小页面；不代表完整工作台或实时 SSE |
| Eval / Regression | [v0.1 能力基线](evals/v0.1-capability-baseline.md) | 当前能力结论；具体 live probes 优先于未同步的 pending 表格 |
| Demo Hardening / Release | [#10 回放与发布闸门](https://github.com/RUSS0718/MathAgent/issues/10)、[Demo](demo.md)、[脚本](../DEMO_SCRIPT.md)、[回放样例](replay/showcase-replay-v0.1.json) | 区分 live / fake / replay，检查脱敏与故障展示 |
| Quality / Release Gate | [验收门禁](ACCEPTANCE.md)、[合并边界](release-boundary.md)、[质量 CI](../.github/workflows/quality.yml)、[发布检查](../scripts/check_showcase_release.py) | 工程与官方隔离门禁；不能推导数学正确率 |
| Scoring / Delivery | [评分证据矩阵](JUDGE_SCORECARD.md)、[评分材料清单](subjective-score-checklist.md) | 视频、技术报告、结果包的交付要求；清单勾选不是成绩证明 |

[Solver v1.2 发布验收与 AC/SC 归属](evals/showcase-solver-v1.2-release.md) 区分离线工程门禁与受阻的完整 live 发布。

## v1.1 Solver Harness 规格入口

- [v1.1 实现规格](https://github.com/RUSS0718/MathAgent/issues/32)：S1/S2 seam、验收合同、SC→AC 映射和 v1.1/v1.2 ticket 边界。
- [v1.1 验收记录](evals/showcase-solver-harness-v1.1-acceptance.md)：记录 v1.1 离线验收结果、SC 归属与 engineering-preview 能力限制。
- [SH21 Intern 真实调用记录](evals/showcase-solver-intern-live-sh21.md)：记录两次未执行工具的旧样本和一次有回执续接、但未完成整题审查的新探针；六次跨三题的历史门槛仍 unavailable。
- [SH22 配对报告工程合同](evals/showcase-solver-paired-report-sh22.md)：独立 Run、同条件校验、失败保留与离线恢复；一组真实 Skills 配对已完成，能力结论仍需更多样本。
- [ADR-0013](adr/0013-solver-harness-boundary-and-shared-transaction.md)：Showcase 单一产品面、共享 SQLite 事务和版本标识决策。
- 产品版本为 v1.1；包版本保持 `0.1.0`，前端版本保持 `0.2.0`，Profile 保持 `showcase_mvp`。
- v1.1 继承 v0.2 的 `engineering-preview` 状态；`v0.2 AC-06` 真实 Intern 工具闭环延期到 v1.2。

## v0.2 历史规格入口

- **状态：** `superseded by v1.1`；以下文档只用于追溯，不作为当前开发合同。
- [v0.2 实现规格](specs/subjective-agent-platform-v0.2-spec.md)（[GitHub Issue #12](https://github.com/RUSS0718/MathAgent/issues/12)）：按已确认的测试 seam 整理问题、用户故事、实现决策、测试决策和范围边界。
- [v0.2 PRD Lite](prd/subjective-agent-platform-prd-v0.2.md)：产品目标、前后端范围、能力发布门槛和验收合同。
- [v0.2 规划调研](research/v0.2-planning-baseline.md)：v0.1 能力事实、CausalAgent 接口核对和设计取舍。
- [v0.2 Live 调试规格](specs/subjective-agent-platform-v0.2-live-debug-spec.md)：真实 Intern pipeline、CLI 合同和 Agent 节点时间线。
- [v0.2 Workbench 视觉重设计](frontend/v0.2-workspace-redesign.md)：三栏工作区、会话侧栏、中文报告和运行观察面板。

### v0.2 tickets

父规格为 [Issue #12](https://github.com/RUSS0718/MathAgent/issues/12)。以下 tickets 按依赖顺序创建；阻塞关系写在各 Issue 正文中。

| Slice | Issue | Blocked by |
| --- | --- | --- |
| Flask Showcase 与 loopback 工作区入口 | [#13](https://github.com/RUSS0718/MathAgent/issues/13) | — |
| 数学 chat-frontend、ChatSession 与 Job 创建 | [#14](https://github.com/RUSS0718/MathAgent/issues/14) | #13 |
| 持久事件流与 SSE 断线恢复 | [#15](https://github.com/RUSS0718/MathAgent/issues/15) | #14 |
| Job 控制、幂等和重启复核 | [#16](https://github.com/RUSS0718/MathAgent/issues/16) | #15 |
| 安全数学报告、Evidence 与回放 | [#17](https://github.com/RUSS0718/MathAgent/issues/17) | #15、#16 |
| `polynomial_check` 候选验证闭环 | [#18](https://github.com/RUSS0718/MathAgent/issues/18) | #17 |
| 真实 Intern 工具请求与 continuation | [#19](https://github.com/RUSS0718/MathAgent/issues/19) | #16、#18 |
| v0.2 P0 验收与发布门禁 | [#20](https://github.com/RUSS0718/MathAgent/issues/20) | #19 |
| P1 单张 PNG 题图 | [#21](https://github.com/RUSS0718/MathAgent/issues/21) | #20 |

截至 2026-10-16，GitHub #1–#10 均已关闭；总任务评论记录了开发收尾检查。仓库未找到独立的 v0.1 复盘报告、最终视频或最终技术报告文件；不能仅由任务关闭推断这些材料已经交付。

## 架构决策

- [ADR-0001：official / showcase 分离](adr/0001-profile-separation.md)
- [ADR-0002：LangGraph / DeepAgents 职责边界](adr/0002-langgraph-deepagents-boundary.md)
- [ADR-0003：实验 Python 工具与可替换 Verifier](adr/0003-experimental-python-tool-and-lightweight-verifier.md)
- [ADR-0004：V0.2 Flask 兼容入口与前端边界](adr/0004-v0-2-flask-and-frontend-boundary.md)
- [ADR-0005：V0.2 限定域 `polynomial_check`](adr/0005-v0-2-polynomial-check-contract.md)
- [ADR-0006：V0.2 单用户身份与本地持久化](adr/0006-v0-2-local-auth-and-persistence.md)
- [ADR-0013：Solver Harness v1.1 的 Showcase 边界与共享事务](adr/0013-solver-harness-boundary-and-shared-transaction.md)
- [GLOSSARY](../GLOSSARY.md)：Profile、Run、Stage、Evidence Pack 等术语。

v0.2 文档已归档为历史合同；v1.1 规格不覆盖这些 accepted ADR，也不授权修改官方 baseline。

## 工程环境与 agent 约定

- [UI 复现指导](frontend/ui-reproduction-guide.md)：后续 agent 的执行入口，包含环境、页面矩阵、组件、状态与像素回归步骤。
- [设计系统](../DESIGN.md)、[产品边界](../PRODUCT.md)：当前统一视觉语言与产品事实。
- [前端统一验收合同](frontend/ui-unification-contract.md)、[验证记录](frontend/ui-verification.md)：实施范围、实际检查结果和证据限制。

- [初始化蓝图](engineering-bootstrap-plan.md)、[Codespace 调研](research/codespace-bootstrap-landscape.md)
- [提交与分支规范](engineering/commit-convention.md)
- [Issue tracker](agents/issue-tracker.md)、[状态标签](agents/triage-labels.md)、[领域文档约定](agents/domain.md)
- [示例目录说明](../examples/README.md)、[比赛仓库调研](research/hackathon-winning-repo-landscape.md)

## Intern S2 五方向实验计划

- [实验开发入口](experiments/README.md)：总计划、固定 develop 审计、Intern S2 合同及五组 PRD、技术规格和 ADR。
- [实际 setup 状态](experiments/setup-status.md)：只记录已执行检查；proposed 文档、离线合同与 live 能力分开标记。
- [S4 最终答案 Evidence 合同](experiments/s4-final-evidence.md)：文本身份、检查范围、追加历史和离线验收接缝；不代表数学证明或能力提升。
- [S5 同题配对 Runner 合同](experiments/s5-paired-runner.md)：批次入口、独立子 Run、预算与不可变归档；离线 180 项测试及本地门禁通过，托管 CI 待核对，不代表策略效果。
- [S6 Workbench 审阅合同](experiments/s6-workbench.md)：持久配对报告、子 Run、脱敏请求与工具闭环、最终验证范围、故障恢复和导出。
- [实验配置](../experiments/campaign.json)：默认 offline、五方向关闭；配置预检不代表在线调度器已实现。

## 早期方案与时效说明

| 文档 | 阅读方式 |
| --- | --- |
| [未版本化 PRD](prd/subjective-agent-platform-prd.md)、[未版本化技术架构](architecture/subjective-agent-platform-technical-design.md) | 早期 DRAFT / 长期设想；React、FastAPI、搜索、记忆等描述不代表 v0.1 已实现或 v0.2 已批准 |
| [GAP.md](../GAP.md) | 早期路线图，包含已过期的 In progress / Planned 项；当前状态查能力基线与对应实现 |
| [原架构说明](architecture.md)、[评分材料清单](subjective-score-checklist.md) | 早期演示叙事与交付提醒；官方实现以 baseline 和版本化官方架构为准 |

能力报告中的文本、图文 pending 行与后续成功 probe 并存；读取“已完成的 live probes”小节和限制说明。当前仍未证明产品真实工具选择稳定，也没有独立数学正确率提升证据。详细核对依据见 [v0.2 规划调研](research/v0.2-planning-baseline.md)。

新增版本时，在本索引更新该版本 PRD、技术设计、任务合同和能力报告入口；设计标为 accepted、任务关闭、能力通过应分别记录来源。
