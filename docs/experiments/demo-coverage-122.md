# Demo 覆盖矩阵与 CLI readiness 合同（#122）

2026-11-03 用户授权补充：新冻结 provider-live manifest 可显式选择 `usage_policy=observe_only`；省略该字段仍按 `required` 执行。只有终态成功、`unresolved_attempts=0`、`unknown_tool_calls=0` 的已知传输允许忽略缺失 usage 的停止条件。缺失 usage 仍为未知，保留最大预留与硬预算；未决请求、未知工具、配置/绑定缺陷仍停止。独立报告继续分别显示 task、transport、coverage 与 usage，不把本选项解释为用量核验通过。该选项不修改官方求解路径、运行时预算或整题审查。

状态：#122 文档基线，日期：2026-11-02；实现进度于 2026-11-03 追加到[阶段验收记录](../evals/showcase-experiment-cli-124-128.md)。本文定义 #124–#128 的产品范围、设计边界和验收合同；矩阵数据保存在同目录的 [机器可读覆盖矩阵](demo-coverage-matrix.json)。合同保持冻结，当前覆盖状态以矩阵和阶段验收记录为准。

## 目标与边界

维护者可以从论文与固定上游来源追踪到本仓库实际代码、脱敏的 Job/Run trace、离线合同和 provider-live 证据。每条证据都标明运行路径与状态。离线、scripted、loopback、Docker、replay 和 provider-live 不互相替代。

官方评分入口仍是根目录 user_agent.py。Showcase 和 Solver Harness 只从显式产品入口运行。#122–#128 不改变官方文件、默认调用预算、JSON 输出合同或官方模型调用数。新增 CLI 预检不发模型或工具请求。运行产物写入被忽略的 artifacts/<run_id>/，公开报告只导出脱敏白名单字段。

本票只冻结覆盖与 readiness 合同。后续实现 #124–#128 的进度不改变原合同。已有 CLI 提供 health、capabilities、session、job、file、probe 和 campaign 命令；它不等于后续实验登记 CLI。机器矩阵只记录当前证据，不授予 provider-live 调用权限，也不把“covered”变成通用能力声明。

## 固定来源与版本

| 标识 | 来源 | 核验结论 |
| --- | --- | --- |
| P1 | STAR-PólyaMath，arXiv:2605.19338v1，2026-05-19；重点为 §3、§4.3、附录 A–F | 已核对 arXiv 原文版本及章节目录。本文只用它定位机制与实验设计，不复述或背书其分数。 |
| U1 | Julius-Woo/STAR-PolyaMath，固定 commit 5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d，2026-06-08 | 仓库既有来源审计记录了固定 SHA、原始文件和 43 项映射。本轮核对了 [固定 SHA 的 solve 源文件](https://raw.githubusercontent.com/Julius-Woo/STAR-PolyaMath/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d/src/orchestrator_mixins/orchestrator_solve.py) 与 execution 文件；GitHub tree 页面未能打开，因此不新增关于未读取文件的断言。 |
| PR121 | RUSS0718/MathAgent PR #121，head 4e9997dfaca9a4b5a98c67947af0a8e24b0e59f1，merge 775d00e3cdcadb6cb6aeca07a1b59093103370d4，2026-11-02 合并至 develop | PR 记录覆盖 STAR Solver、公共 Job、恢复和发布门禁，并明确其测试不代表 provider-live 稳定性或数学正确率。本 worktree 基于该 merge commit。 |

来源检查状态：P1 的 arXiv v1 原文已在线打开。U1 固定 SHA 下的 solve 与 execution 原始文件已在线打开；本轮无法核对 GitHub tree 页面，因此 tree 页面本身为 SOURCE_UNVERIFIED，完整来源定位沿用仓库固定来源审计。PR121 的合并状态、head SHA、merge SHA 和正文来自 GitHub PR 记录。凡矩阵项找不到一手论文或固定源码定位时，标 SOURCE_UNVERIFIED，并把项目自身扩展与论文机制分开。

比赛方案原件未随 worktree 提供；评分目标只按调用者提供的根 AGENTS.md 摘录处理。若后续需要逐条引用比赛方案，先补齐可核对的原件，再标记来源状态。

详细的论文机制、固定上游路径、本地代码与差异分类沿用 [SP-01 来源审计](star-product-source-audit.md) 和 [ALIGN-10 来源映射](../evals/star-product-align10-source-mapping.md)，不复制其逐项历史映射。论文报告的结果基于论文自己的模型、数据和设置；本项目使用 Intern S2 与独立的产品运行合同，不能把论文结果移作本项目效果证据。

原始来源：[STAR-PólyaMath 论文 v1](https://arxiv.org/html/2605.19338v1)、[固定上游 orchestrator 入口](https://github.com/Julius-Woo/STAR-PolyaMath/tree/5f2a86b5f4cf870be1b1d517c2d33c6932b01b7d)、[PR #121](https://github.com/RUSS0718/MathAgent/pull/121)。固定上游逐文件定位见上方来源审计，不以可变分支名代替 SHA。

相关的一手论文仅作后续设计背景，不是本项目能力证据：

| 来源 | 关联与限制 |
| --- | --- |
| [HERMES，ICML 2026](https://proceedings.mlr.press/v306/ospanov26a.html) | 相关于数学推理中的形式化验证；本地轻量审查与形式证明不可混同。 |
| [Every Rollout Counts，NeurIPS 2025](https://arxiv.org/abs/2506.15707v2) | 原始 arXiv 页面本轮未能核验，列为候选近邻；#128 只验收已登记单因素执行，不复现该方法。 |
| [SHAPE，ACL 2026](https://aclanthology.org/2026.acl-long.1114/) | 训练期阶段优势方法；不能与本项目推理期配置开关直接作同类复现。 |

## 状态含义与当前结果

机器矩阵对每项分别记录 offline、historical_live 和 cli_provider_live。能力状态只解释对应证据通道；source_audit 使用独立来源状态：

| 状态 | 含义 |
| --- | --- |
| COVERED | 指定通道有可复核证据，且该证据满足所述工程合同。 |
| FAILED | 已执行的尝试未满足合同；保留原失败与未知状态。 |
| NOT_RUN | 当前版本或指定验收流程尚未执行。 |
| NOT_COVERED | 已有结果没有触发或不能证明该能力；不得折算为通过。 |
| SOURCE_UNVERIFIED | 找不到可核验的一手来源；不得据此声称论文来源一致。 |

来源状态 VERIFIED 表示已核对所列一手页面或固定源码。SOURCE_UNVERIFIED 表示引用页面或原件未能核对；它不能转成 capability 的 COVERED。

矩阵的 offline COVERED 仅指公共接口、测试或隔离合同通过。它不推导数学正确率、自然路径触发率、真实服务兼容性或普遍可靠性。

PR #121 合并记录报告：固定源码上的 1,071 项 unittest 零失败、零跳过；发布检查的 41 项通过；前端检查和 Docker 专用用例通过。该记录也明确说明这一门禁未发真实 provider 请求。独立历史 live 结果仍按原记录解释：2026-10-26 RB08 E1 执行 2/4 后失败，E2 为 0/6；2026-10-28 #97 v7 的第二次 Explore 在等待 900 秒后 timeout，Run 进入 needs_review，没有完整答案、整题审查或文本绑定。旧 #97 登记已消费，不续跑、不改写，也不作为 #127/#128 的通过证据。

因此，当前矩阵将 CLI 对应的 provider-live 验收标成 NOT_RUN。这个状态阻止 #127 宣称简单题与自然多步 provider-live readiness 通过，也阻止 #128 宣称 live 单因素对照已完成。历史失败和其他历史成功配对保持可引用，但不能代替新 CLI、冻结登记和本票要求的证据。

provider-live manifest 的 `model.retry: 1` 表示 Intern 客户端的单次初始尝试；它不授权自动重试。预检和执行只接受这一有界配置，`retry: 0` 继续兼容 scripted 夹具，其他非零值保持拒绝。未知结果仍停止批次，resume 只复用原 Job，不重发不明请求。

## 当前覆盖映射

| 能力 | 论文定位或项目合同 | 当前实现与可观察来源 | 离线证据 | provider-live 状态 |
| --- | --- | --- | --- | --- |
| 官方路径隔离 | 项目合同：官方评分入口与 Showcase 分离 | 根 user_agent.py、implementations、BASELINE.json；发布门禁检查冻结文件和导入边界 | COVERED：PR #121 发布记录与 scripts/check_showcase_release.py | NOT_RUN：本票不执行官方或 provider 请求 |
| 简单题、Explore 快通道与最终交付 | P1 §3.2、§3.5；S4 artifact binding 为项目扩展 | showcase/solver_harness/star_routing.py、finalize.py、final_binding.py；公共 Job 的 Run、报告、Evidence 与脱敏事件 | COVERED：Solver Harness 路由、Job、final binding 公共合同；见矩阵测试引用 | NOT_RUN：#127 新 CLI 样本尚未登记或运行 |
| 规划、多步 Reasoner、逐步审查与 Challenge | P1 §3.3–§3.4 | planning.py、step.py、verification.py、challenge.py；Job timeline、Verifier 结果和步骤摘要 | COVERED：scripted / fault-injection 公共 Job 合同 | NOT_COVERED：历史 live 未稳定取得自然非快通道闭环；Challenge 自然触发也未覆盖 |
| 注册工具与隔离执行 | P1 §A、附录 B.4；项目隔离合同为适配扩展 | Tool Registry、python_executor.py、Solver Harness tool ports；报告中的工具名称、状态和脱敏回执 | COVERED：Docker 隔离专项合同；测试通过不等于模型自然选用工具 | NOT_COVERED：未在本票新 CLI live 批次中观察到 provider 发起、执行并消费工具回执的完整多步链 |
| Trace-Back、Meta 指导与重规划 | P1 §3.4、附录 B.5 | traceback.py、meta.py、replan.py、ReplanDecision；事件记录版本与裁决摘要 | COVERED：受控分支和故障注入测试 | NOT_COVERED：已有 live 记录未自然触发这些机制 |
| S3 预算、停止、取消与安全恢复 | P1 附录 A、B.5；强恢复合同为项目扩展 | showcase/run_budget.py、Job 控制、Solver checkpoint；attempt、reservation、deadline 和终态投影 | COVERED：公共 Job、进程退出、unknown、预算与迟到结算测试 | NOT_RUN：本票未验证真实 provider 在途请求的取消或恢复语义 |
| S4 最终文本身份、审查和 Evidence | P1 §3.5；哈希身份绑定为项目扩展 | showcase/final_evidence.py、solver_harness/final_binding.py；artifact hash、review scope、binding 状态 | COVERED：改写失效、并发追加与公共报告合同 | NOT_RUN：#127 需要新 CLI Run 上真实整题审查和同文本绑定证据 |
| 实验登记、只读核验与导出 | 项目工程扩展；独立报告与脱敏为工程合同 | `showcase/experiment_cli.py`、`experiment_runner.py`、`experiment_verification.py` 及其检查/报告模块 | COVERED：#125/#126 的 frozen manifest 与 verify/export CLI 合同；见对应测试 | NOT_RUN：新 CLI 尚无 provider-live 批次 |
| 单因素配对 | 项目工程扩展；P1 §4.3 仅作研究背景 | `experiment pair` 通过专用公共 Job 路由串行执行冻结 baseline/variant Runs，保存逐样本结果，并独立复核 Job/Run 身份与 applied component config | COVERED：scripted / fake-public-API 合同覆盖离线配对执行；见[阶段验收记录](../evals/showcase-experiment-cli-124-128.md) | NOT_RUN：#127 readiness 尚无 provider-live 通过记录；不得据此报告 live 配对完成 |

逐项测试文件、状态值和阻断票以 [demo-coverage-matrix.json](demo-coverage-matrix.json) 为机器读取入口。未来运行报告必须新增实际证据引用和状态，不得覆盖本页列出的历史事实。

## 后续产品需求与技术设计

### 用户与成功结果

用户是 Demo 维护者和实验研究者。用户从冻结的 manifest 预检、串行执行、只读查看、同身份安全恢复、独立核验和脱敏导出。研究者可基于已通过 readiness 的基线运行一个组件的消融或加入变体。每个结论都能追溯到源码、manifest、实际应用配置、公共 Job/Run、S3 账本、S4 绑定和脱敏归档。

### 公共路径和职责

复用现有认证公共 Job API 作为所有样本的派发与恢复入口。复用每 Run 唯一的 S3 账本、现有 Job/Run 存储、事件与报告接口、S4 final artifact binding 和 Evidence 导出。CLI 负责登记校验、串行协调、进程状态、独立对账及归档；不复制求解器、预算账本、Verifier 或 Job 状态机。配对协调可复用现有单因素条件校验，但两个 arm 都必须经过公共 Job 与 S3/S4。直接调用 SolverHarness 不能作为公共产品验收路径。

preflight 校验 manifest schema/hash、源码 SHA 与 dirty 状态、请求模型和传输配置、样本身份、预算与停止规则，且零模型和工具派发。run 只接受通过预检的不可变登记，按串行顺序为每个样本创建唯一身份；首个 unknown、账本不一致、硬限、取消或失败停止后续派发，不替换题目、不自动重试。

status 是只读机器可读快照，包含 PID、进程创建时间、当前阶段、完成数/总数、停止原因与脱敏日志末尾。resume 仅恢复原 Job 和登记身份；继承原 deadline、S3 reservation、已提交步骤和工具回执。存在未决 unknown 时进入 needs_review 并停止，绝不重放不明动作。

verify 独立读取持久 Job/Run、attempt、usage、reservation、审查与文本绑定、manifest 和归档。它不信任 runner 自报成功或进程退出码，也不发模型或工具请求。export 只从核验结果生成脱敏产物；强制项未完成、FAIL 或 UNKNOWN 时不得输出 PASS。

单因素配对固定同一题、模型、thinking 配置、传输、温度、预算、停止条件、执行环境和工具权限。每对创建独立 baseline 与 variant Run，仅允许一个登记组件配置不同。安全不变量、隔离、硬预算、整题审查和最终文本绑定不能消融。未触发机制保留在预登记分母并标 NOT_RUN 或 NOT_COVERED；不以触发子集替换主结果。多因素组合和数学能力提升结论不在 #128 范围内。

建议命令面统一挂在现有 Showcase CLI 的 experiment 子命令下：preflight、run、status、resume、verify、export 和 pair，每个命令接收相应的 manifest 或 batch ID。这是下游票的公共 CLI 合同；具体参数、字段和退出码由各票在实现前锁定，并用授权的公共接口验收。

### 后续票纵向切片与验收合同

| 票 | 交付与前置 | 最小可审查验收 |
| --- | --- | --- |
| #123 | 并行来源与协议风险审计。沿用官方 Intern endpoint 文档及实际出站 payload；loopback 覆盖正常终止、usage 缺失、畸形/空事件、断流、迟到和 timeout。 | transport、task 状态与 usage 三者分开报告；missing usage 保留未知预留，不误判为零或网络 unknown；真实 provider 能力、预算与停止探针写明。保留 #96 和旧批次身份。 |
| #124 | 依赖 #122、#123。按本次 endpoint/payload 能力对每次调用选择可验证传输。 | 兼容调用优先 SSE 并公开 delta、终态、finish reason、usage、Run 状态和预算结算。provider 原生 tools 等不支持流式的调用标出限制。禁止同一 Run 静默降级；缺 usage 保留 reservation，unknown 不自动重发。官方入口和 S3/S4/恢复合同不变。 |
| #125 | 依赖 #122、#123、#124。提供 experiment preflight、run、status、resume。 | preflight 零派发并核验源码、dirty、模型/传输、样本、预算、停止条件和 manifest hash。run 串行且唯一身份；unknown 或硬限停止。status 输出 PID、创建时间、阶段、完成计数、停止原因和日志尾部。resume 复用原 Job、deadline、账本和已提交回执。归档不含凭证、完整 prompt、隐藏推理或答案库。 |
| #126 | 依赖 #125。提供独立 verify 与 export。 | 读取实际持久状态及归档；对账派发、attempt、usage/reservation、Job、审查和文本绑定。分别输出 transport、任务、用量和覆盖状态。PASS、FAIL、UNKNOWN、NOT_RUN 明确区分；强制项失败/未知/未完成不能导出 PASS。审计零派发。 |
| #127 | 依赖 #124、#126。通过同一登记和 CLI 验收简单题、自然多步路径和适用故障。 | 简单题验证适用快路径、完整生成、整题审查与同文本绑定。至少一条自然多步真实 trace 覆盖规划、步骤、适用工具回执、最终生成、审查与绑定。不得强迫机制触发；没有自然触发就保留 NOT_RUN/NOT_COVERED 并判该项未通过。故障注入覆盖适用断流、timeout、usage 缺失或进程中断。工程结论限于可达性和稳定性。 |
| #128 | 依赖 #127。提供登记化的单因素 paired execution。 | 一对只改一个因素，baseline/variant 独立身份，核对实际 applied config 和执行顺序。题目、模型、thinking、传输、预算和安全合同相同。独立 verify 生成配对结论；未知、失败、硬限或登记不一致时不宣称完成。保持所有预登记样本及未触发项。 |

依赖图：#124 还等待独立的 #123；#125 等待 #124；#126 等待 #125；#127 等待 #124 与 #126；#128 等待 #127。#122 文档完成只解除自身依赖，不代表其余票已交付。

## readiness 出口条件

#127 的 provider-live readiness 只有在新 CLI 流程以独立冻结 manifest 执行、样本身份和预算可核验、简单题满足 S4、至少一条自然多步 Run 完整满足验收、适用故障合同通过、独立 verify 无账本或绑定差异后才能判定。provider 无法证明的 usage 必须保持 unknown；若不能取得完整证据，状态保持 UNKNOWN 或 NOT_RUN。

#128 只有 #127 的 readiness 为 PASS 后才可启动配对结论。每个 pair 经独立核验，只有两个 arm 均结束且配置差异恰为一个登记因素、没有未决预算/attempt、S4 条件满足时，才能报告 pair complete。样本质量、数学判分和统计精度必须另列；本票本身不支持能力提升声明。

任何 provider-live 批次都必须有针对该 manifest 的独立登记、硬预算、停止条件和执行授权。历史调用授权不迁移到新批次。旧 #97 的运行、登记与失败记录只读保留，不从旧 manifest 恢复，不重开、不修改，也不作为新 CLI readiness 的样本替代物。

## 既有设计决策

- ADR-0001 保持 official 与 showcase Profile 隔离。
- ADR-0002 与 ADR-0014 保持 Job 投影、Solver 状态、checkpoint 和安全恢复的既有职责。
- ADR-0003 将 Python 工具定义为受控实验工具；Docker 证据只证明固定隔离配置。
- ADR-0007 与 ADR-0013 要求共享预算和事务边界。S3 是动作准入及计量的唯一账本。
- S4 只把报告和验证绑定到同一最终 artifact 身份，不把身份匹配当作数学证明。

### 本票验证边界

目标是让后续实现者能按矩阵开展 TDD：先在已授权的公共 Job、CLI 和归档 seam 写失败验收，再做最小纵向实现。#122 不添加行为代码，不以文档测试重复文档常量。文档验收检查 JSON 可解析、矩阵字段状态合法、仓库链接有效、README 索引可达、差异只涉及本票文档，并确认官方冻结文件无变化。
