# MathAgent 文档索引

- [#175 同任务安全串并行切换验收](evals/faithful-service-175-20261114.md)：达到用户授权调整后的开发接线退出条件；[合同](engineering/faithful-service-175-contract.md)。冻结源码 `588b40e` 的 gate-03 六阶段通过（2063 项、0 failure/error、49 skip、源码无漂移），前两轮失败、竞态红绿与双轴复审保留。自然真实热切换、完整正确交付与真实路线UI正向闭环仍留#183，#168未完成；按[接续合同](engineering/unattended-ticket-loop.md)及[当前交接](engineering/unattended-ticket-handoff.md)继续#176。

- [#174 自主并发开发接线验收](evals/faithful-service-174-20261113.md)：达到用户授权调整后的开发退出条件。冻结源码 `b8c4ec8` 的 gate-02 六阶段通过（2048 项、0 failure/error、49 skip、源码无漂移）；原 gate-01 的 4 项测试 profile 失败及最小修复保留。真实自然并发完整交付、实际路线 UI 与刷新正向闭环留待 #183，#168 完整服务仍未完成。#175后续进展见上方入口；unknown 不重发。

- [#173 关联改题验收](evals/faithful-service-173-20261113.md)：B3 改题停止旧派发并创建关联新任务；真实新题独立交付 5，旧迟到结算隔离、刷新零新增调用，最终源码只读恢复通过。双轴修复复查无剩余问题；冻结 `9978157` 门禁 6/6 通过（2020 项、49 skip、源码无漂移）。仅交付本票，#168 完整服务仍未完成。

- [#172 必要条件澄清验收](evals/faithful-service-172-20261113.md)：B2 同任务提问、回答适用性复判和规格 v2 已取得真实三角形面积 12 的证据，刷新 0 POST、同 Attempt；双轴复查无阻塞。冻结源码 `1c37325` 门禁 6/6 通过（2016 项、49 skip、源码无漂移），达到本票工程退出；#168 完整服务仍未交付。

- [#171 提交响应丢失恢复验收](evals/faithful-service-171-20261113.md)：B1 已完成持久身份、只读找回、多标签防重和明确再次求解；双轴复查清零，冻结源码 `c87c33f` 门禁 6/6 通过（2008 项、49 skip、源码无漂移）。真实旧 Run 刷新及第二标签 0 POST、Attempt 不变；#168 完整服务仍未交付。

- [Faithful 自主 Agent 完整本机服务实施规格](https://github.com/RUSS0718/MathAgent/issues/168)：已拆分 #169–#183，按 A–H 端到端切片推进。[首票 #169 验收记录](evals/faithful-service-169-20261113.md)包含普通输入、真实 2+3 整题检查与刷新证据。[#170 验收记录](evals/faithful-service-170-20261113.md)已完成简单题真实 Planner→三个串行工作块→Python→整题绑定与只读恢复；最终 gate-03 六阶段通过（2007 项、0 failure/error、49 skip、源码无漂移），达到本票工程退出，交付 SHA 见 #170 完成评论。完整服务仍未交付，后续票按真实依赖领取。验收以少量真实模型、工具和浏览器场景跑通为主，不新增准确率、性能或大样本门槛。
- [Faithful 自主能力调度与前端闭环决策地图](https://github.com/RUSS0718/MathAgent/issues/160)：2026-11-12 七项决策完成，规划退出；实施要求已汇总到 #168，完整服务尚未交付。能力准入、普通输入、动态调度、形式化、记忆及前端合同见地图的已决事项。
- [自主服务实施交接与验收决议](https://github.com/RUSS0718/MathAgent/issues/167#issuecomment-6828389803)：首次交付在当前机器完成；按端到端切片接通真实服务，减少无关或重复离线测试，保留关键故障检查、阶段门禁与真实模型、工具、浏览器验收。既有未提交草稿须按决议核对，不算已验收实现；官方路径与独立 F8 数学评测保持各自边界。

- [对话式工作台集成合同](engineering/conversation-workbench-contract.md)：新主页替换旧聊天布局；共享事件投影、真实 Job/SSE、线程/星图/计划及来源边界。验收结果见 [工作台集成记录](evals/conversation-workbench-20261112.md)。

- [S09/F3 受限形式化实施记录](evals/faithful-s09-20261109.md)：门禁源码 `4df0953`；最终门禁06 6/6通过（1683项、0 failure、0 error、2 skip），Reference 发布41项通过；真实 L2/L3、AC23 公共 Job/Report/Evidence 路线和桌面/移动 UI 验收完成，状态为 `engineering-preview`。2 skip 未计通过，真实 provider、自然题及独立数学效果未验证。[S09 合同映射](engineering/faithful-s09-contract.md)记录公共入口、持久断言和证据范围。

- [#156 完整并发接管与验收](evals/faithful-population-20261109.md)：接续门禁06在源码 `5d80f90` 上6/6通过（1624项、42skip）；新增12项验收与102项聚焦通过，八组公共入口/持久证据逐项映射。42skip仍未执行，旧Docker专项独立记载；真实provider/容量/SLA/数学效果未验证，#156/#146保持开放。

## Faithful 实施入口（截至2026-11-12）

- [F8-R18 空答案辅助审查修复](evals/faithful-f8-empty-review-20261112.md)：#159 的真实空答案身份 pass/fail 已拒绝、unresolved 保留；本地 adapter 接入及 hash 见记录。41/29 与固定28槽不变，#157仍未完成。[Python 工具拒绝后的有界纠正](evals/showcase-tool-recovery-20261112.md)另见 #158；两项均只有离线修复证据。

- [F8真实执行与故障处置](evals/faithful-f8-real-20261112.md)：2026-11-12用户交接#158/#159并授权恢复，接续准备增量见记录首节及[v1.4合同](engineering/faithful-f8-real-source-continuation-20261112.md)。41份首次仍为1 completed、39 failed、1 unknown，29槽未派发，unknown不重发；新源码完整门禁及正式接续身份待验收。R20源码`315ae9b`的6/6、1917项、42skip是历史证据，不能替代新源码门禁。F8实验及#157未完成。

- F8 真实接续修复：[新源码接续条款 v1.3](engineering/faithful-f8-real-source-continuation-20261112.md)已双轴冻结；该条款中的7/63是R19时点历史截面，当前以[真实执行记录](evals/faithful-f8-real-20261112.md)的41/29及重启unknown处置为准。跨源码比较标not_comparable，原失败不覆盖；实验与报告尚未完成，#157保持开放。

- F8 真实题集接续在 [#157](https://github.com/RUSS0718/MathAgent/issues/157)：[真实试点冻结合同](engineering/faithful-f8-real-protocol-20261111.md)为 `faithful-f8-real-v1`，双轴审查问题已解除。14题参考材料事前封存；初始A/B/C/G必需56槽，容量准入后D的14槽纳入当前70个必需主槽，F仍为真实条件任务。容量探测不等于D自然题验收；E原题目标域不支持且工具专项分开。官方重评分unavailable，usage缺失observe_only。冻结不是实验完成，旧工程试点及门禁证据保持原样。

- F8/#154 已按 faithful-f8-v1.1.1-engineering 达到 `engineering-preview`：[冻结合同及评审记录](engineering/faithful-f8-protocol-20261111.md)、[分层验收记录](evals/faithful-f8-20261111.md)。2026-11-11 用户明确将真人替换为 R1/R2 子智能体隔离初审、R3 核对；14 题登记 98 槽全部 not_run，28 个抽查槽各角色均 unresolved，辅助链 complete 不代表数学通过。固定 L1 25 项、71 项 F8 聚焦及七组失败见证通过，双轴问题清零；门禁源码 `e40d240`，`faithful-f8-20261111-02` 6/6 通过（1915 项、0 failure/error、42 skip、source_changed=false），42 skip 与 F6/F7 的 ID／原因一致且不计通过。首轮真实 Lean timeout 与 SQLite 锁错误保留，有界诊断通过但间歇根因未确认。核心与阶段证据包均已封存；independent_math/provider-live/自然题求解/官方重评分继续 not_run，11 个 baseline 文件只确认字节一致。

- F7/#153 已达到 `engineering-preview`：[任务合同](engineering/faithful-f7-contract.md)、[分层验收记录](evals/faithful-f7-20261111.md)。只读 Run/依赖图/F6 交付和等级、版本化段落深链与刷新/重开恢复完成；门禁源码 `1da9aee`，`faithful-f7-20261111-01` 6/6 通过（1844 项、0 failure/error、42 skip、`source_changed=false`）。37 项后端聚焦、52 项前端单测、5 项最终浏览器及真实 Lean L2/L3 专项通过，双轴问题已清零。500 节点 synthetic 三次渲染 P95 149 ms；最大真实样本仅 2 个命题，二者不混称。42 skip 与 F6 逐项一致，不计通过；11 个 baseline 文件字节一致，本轮未重新评分。F8/#154 后续已完成修订冻结，当前状态以上方 F8 入口为准。

- F7/F8 范围与协议材料：[F7 只读系统视图与深链合同](engineering/faithful-f7-contract.md)、[F8 A–G 评测协议 v1](engineering/faithful-f8-protocol-20261111.md)、[F6 42 项 skip 原因与等级覆盖审计](evals/faithful-f6-skip-audit-20261111.md)。GitHub 正式入口为 [F7 #153](https://github.com/RUSS0718/MathAgent/issues/153) 与 [F8 #154](https://github.com/RUSS0718/MathAgent/issues/154)。

- F6/#152 已达到 `engineering-preview`：[任务合同](engineering/faithful-f6-contract.md)、[分层验收记录](evals/faithful-f6-20261111.md)。逐段来源定位、独立输出身份、同源 Best-Effort 交付及旧 Run 策略边界完成；门禁源码 `c1d17bc`，`faithful-f6-20261111-02` 六阶段通过（1832 项、0 failure/error、42 skip、`source_changed=false`），25 项表达/API、5 项 Chromium 和双轴修复复查通过。首轮 readiness 迟到用量间歇失败保留，根因未确认，第二轮成功不证明已修复。独立受控 rubric 为 8/10，不外推自然题质量；真实 provider、自然题及数学效果 `not_run`。F7 工程退出见上方入口；F8/#154 先完成协议评审冻结。

- S10/F4/F5 实施与阶段验收记录：[验收报告](evals/faithful-s10-20261111.md)及[合同映射](engineering/faithful-s10-contract.md)；`faithful-s10-20261111-02` 最终门禁 6/6 阶段通过（1821 项、0 failure、0 error、42 skip、`source_changed=false`），S10 达到 `engineering-preview` 并可进入下一阶段。135 项非 Docker S10 回归、前端 46 项单测/构建、9 项 F4/F5 Playwright 用例及快速检查通过。首轮门禁 01 的前端并行端口竞态失败保留在独立证据目录并已修复。42 项 skip 未计通过；固定 Lean、provider-live、容量/SLA、自然题与独立数学效果仍按独立证据层级记录。门禁源码 hash `421b9face1da7e8aa687a67ceecc4ff31fd0db495b24ebe707136ce1398e71c6`；#130 已追加 S10 路线进展并建议下一入口 #152，#146/#150/#151 未评论或关闭。S10 已提交为 `b02f8b4`；历史门禁与 artifacts 的证据身份保持不变。

S01–S09（含 S06、串行 F2/S08、F3/S09）和 S10/F4/F5 均达到 `engineering-preview` 工程退出。S09 源码门禁 SHA 为 `4df095355d2eb5c39f94ba24cb7e367486973428`，随后纯文档交接 SHA 为 `f7d9c530978fbcbf453e06ba0a24500cb9593721`；门禁 6/6 通过，2 项显式 Docker readiness integration 测试 skip 未计通过。S10 门禁源码 hash 为 `421b9face1da7e8aa687a67ceecc4ff31fd0db495b24ebe707136ce1398e71c6`，最终门禁 02 6/6 通过（1821 项、0 failure/error、42 skip），source unchanged。真实 L2/L3 和公共 Prover Route Job/Report/Evidence 验收完成，#149 已关闭，F4/F5 的 F2/F3 工程前置已满足。S10 已实现 F4 原生 Solver/APRS checkpoint 双臂执行、双次 Verifier 调用与同臂账本/复核输入绑定、父 Run 恢复；F5 已实现 Run/Population Memory 只读与 advisory 链、会话注入同意和来源链、路线级成本估算接入 APRS，以及 Global Goal Cache 的当前 Lean 复核、漂移与用户控制。来源、unknown、预算及可见证据边界逐项见 [S10 合同映射](engineering/faithful-s10-contract.md)。路线最新进度见上方 F6 入口，下一阶段按 #146 的 F7–F8 合同推进；S10 源码已提交为 `b02f8b4`。2026-11-11 本轮只读核验 #130/#146 仍 open，#150/#151 已由既有交付关闭，本轮未修改这两个 Issue。provider-live、自然题、容量/SLA 和独立数学效果仍未验证；工程门禁和受控 fixture 不构成数学能力提升证据。阶段依赖见 [#144 决议](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)、[S09 合同](engineering/faithful-s09-contract.md)和[工程门禁](engineering/development-gates.md)。

- [S06 与 S08/F2 工程退出验收](evals/faithful-s06-s08-exit-20261108.md)：门禁源码 `2f11c65`，6/6通过，1543项含42skip；分别记录基础模板输出、串行路线/APRS、双轴修复及首轮门禁失败。
- [S06基础输出合同](engineering/faithful-s06-contract.md)、[S08串行路线合同](engineering/faithful-s08-contract.md)、[重规划诊断与S09环境](evals/faithful-replan-s09-environment-20261108.md)：S09编译exit127、无L2/L3；#156可按实际前置推进，S10不可提前实施。

- [S05 与 F1/S07 工程退出验收](evals/faithful-s05-s07-exit-20261108.md)：门禁源码 `932a234`，六阶段通过，1496 项回归含 42 skip；真实图浏览器 5 项通过、50/50 样本 P95 818 ms。分别记录两阶段结论、双轴修复、首轮门禁失败和未验证边界。
- [S05 公开产物与 UI 合同](engineering/faithful-s05-contract.md)、[F1/S07 图与 GraphBootstrap 合同](engineering/faithful-s07-contract-exit-20261108.md)：真实进度、可恢复历史、脱敏图投影及 AND/OR、版本、来源与原子失效边界。

- [S04 进展与停滞调度合同](engineering/faithful-s04-contract.md)：受控方法标识、证据信用、三回合停滞、重复动作局部阻断及恢复语义。
- [S04 工程退出验收记录](evals/faithful-s04-exit-20261108.md)：源码 `13641c6`、24 项专属合同、71 项聚焦回归、六阶段门禁和浏览器回归；保留 42 项 Docker skip 及中止记录，解除 F1/S07 的 S04 工程前置。

- [S02 上下文与容量治理退出合同](engineering/faithful-s02-exit-contract.md)：C01–C12 工程退出通过，状态为 `engineering-preview`；冻结源码 `d19aa56`，真实 provider、容量/SLA 与数学效果未验证。
- [S02 工程退出验收记录](evals/faithful-s02-exit-20261108.md)：六阶段门禁、聚焦/浏览器回归、跳过项、审查修复及能力边界。S02 退出解除 S03 工程依赖。
- [S03 规格与工作块交接合同](engineering/faithful-s03-handoff-contract.md)：S03 实现与接口合同；工程退出已通过，状态为 `engineering-preview`。
- [S03 工程退出验收记录](evals/faithful-s03-exit-20261108.md)：C01–C12 证据、六阶段门禁、聚焦/浏览器回归、跳过项、双轴审查及能力边界。S03 退出解除 S04/S05 的 S03 工程依赖；F1/S07 当前前置状态见上述 S04 验收。

- [S01 流式工程退出验收](evals/faithful-s01-exit-20261107.md)：按用户调整后的流式范围退出；六阶段冻结门禁与终审补丁分开留证，S02 的 S01 工程依赖解除。真实 provider 与数学效果未通过。
- [S01 首纵切集成验收](evals/faithful-s01-first-slice-20261107.md)：流式策略、六阶段门禁与终审补丁证据；完整 S01 及后续阶段仍未验收。
- [实施起点与 S01–S06 证据核验](engineering/faithful-implementation-entry-146.md)：实际 checkout、冻结基线同步、旧起点失败及聚焦复核；新阶段未因旧 SP 或 Intern 同名记录解除门槛。
- [完整并发实施交接](engineering/faithful-concurrency-handoff-155.md)：承接 #155 的独立 [实施票 #156](https://github.com/RUSS0718/MathAgent/issues/156)，包含原生依赖、八组验收与交付/结算边界。串行 F2 不覆盖完整并发；文档和建票不代表产品已实现。

## 当前入口与归档状态（2026-11-06）

- 本窗口所有Run的停因、根因边界和冻结身份统一见[逐Run错误索引](evals/provider-live-run-error-index-20261106.md)，不再另建重复错误流水账。原始实验数据按用户授权清理，证据恢复限制见索引末节。

- 安装、组件与运行方式：[Showcase 首页](../README.md)。
- 本轮环境复盘及后续候选：[provider-live retro](evals/provider-live-retro-20261106.md)；技术栈与STAR上下文能力：[研究记录](research/star-context-memory-paper-20261106.md)。压缩和记忆方案尚未接入当前STAR直连路径。
- 最新两批：[readiness-30](evals/provider-live-natural-20261106-readiness-30.md)为第12步单调用截止、结果未知；[readiness-31](evals/provider-live-natural-20261106-readiness-31.md)为较简单题第6步流中连接异常、结果未知。两批均未完成最终生成、整题审查及文本绑定，不能统称预算耗尽。
- [工程交接合同](engineering/handoff-delivery-contract.md)是显式实验模式，不替代旧Issue验收；#127未通过且保持开放，#128线上两臂NOT_RUN，provider usage UNKNOWN。用户已要求归档线上实验，不自动重跑。
- [版本与失败对照](evals/provider-live-version-comparison-20261106.md)、[迭代审计](evals/provider-live-iteration-audit-20261106.md)、[修复循环历史](evals/provider-live-repair-cycle-20261105.md)用于追溯，不作为当前运行配置。

下方按日期保留历史入口；其中“最新”仅指各记录撰写时的状态，以本节和各批次终态为准。

文档职责：为开发者和 agent 提供版本、开发阶段、能力验收及官方边界的阅读入口。

2026-11-03 的 #124–#128 后续进展见 [provider-live 协议与 readiness 补充记录](evals/provider-live-readiness-followup-20261103.md)。该记录区分角色协议探测、公共 CLI readiness、usage 暂缓验收和未实现的配对路径。

2026-11-04 的当前源码三题复验、简单题与中等题新 Run 结果、流式首末正文时间及独立核验见 [provider-live readiness follow-up](evals/provider-live-readiness-followup-20261104.md)。

2026-11-04 的 #128 离线配对执行切片与覆盖状态见 [实验 CLI #124–#128 阶段记录](evals/showcase-experiment-cli-124-128.md)；#127 provider-live readiness 与 live 配对结论仍待单独验收。

2026-11-05 的 `handoffloose-02` 自然多步运行停在 Run 硬截止，脱敏身份、Job/Solver 状态和停止分类修复见 [#127 线上运行记录](evals/provider-live-natural-20261104-handoffloose-02.md)。该运行未通过 #127，#128 线上 pair 仍为 `NOT_RUN`；当前过度复杂度审计与离线修复进度见 [审计与修复记录](evals/overengineering-audit-20261105.md)。

2026-11-05 最新 `readiness-01` 的自然多步 trace、矛盾步骤核验、交付缺口与修复后 Issue 状态见 [#127 readiness-01 运行记录](evals/provider-live-natural-20261105-readiness-01.md)；对应 #124–#128 CLI 阶段追加及复杂度审计口径更正见[实验 CLI 阶段记录](evals/showcase-experiment-cli-124-128.md)与[审计记录](evals/overengineering-audit-20261105.md)。#127 仍 FAIL/open，#128 仍 NOT_RUN/open。

2026-11-05 `readiness-02` 在新冻结 Run 中完成简单题并实际尝试自然多步；多步 Job 因 Meta 拒绝带传输 `usage` 的合法响应而进入 `star_needs_review`，未交付最终答案。完整身份、停因、流时间、预算与验收缺口见 [#127 readiness-02 运行记录](evals/provider-live-natural-20261105-readiness-02.md)；#127 保持 FAIL/open，#128 仍 NOT_RUN/open。

较早的 `d6e9ea5-02` Run 在 `STEP_VERIFY` 失败，并记录 stream 清理时 SQLite 嵌套事务异常；该异常不能确认是 Job 首发失败根因。脱敏身份、独立核验和随后增加的事务回滚回归见[历史运行记录](evals/provider-live-natural-20261104-d6e9ea5-02.md)。

适用范围：理解 v0.1、v0.2 历史版本和当前 v1.1 Solver Harness 规格；执行规则以根 [AGENTS.md](../AGENTS.md) 为准。

## 先读哪些文档

2026-11-06 最新 #127 `readiness-28` 的简单题成功；自然多步只完成 1/7 步，末次 Verifier 因工具证据不适用于目标而以 `verifier_tool_request_unfulfilled` 停止。6 次隔离工具均 exit 0 且清理已确认，未发现新的应用缺陷；整题审查未绑定，#127 仍未通过，#128 两臂仍为 `NOT_RUN`。详见 [readiness-28 运行记录](evals/provider-live-natural-20261106-readiness-28.md)。此前 readiness-27 的模型生成代码失败见 [readiness-27 运行记录](evals/provider-live-natural-20261106-readiness-27.md)；readiness-26 的四步自然 trace 与流中 connectivity UNKNOWN 见 [readiness-26 运行记录](evals/provider-live-natural-20261106-readiness-26.md)。

2026-11-03 的[实验 CLI #124–#128 阶段记录](evals/showcase-experiment-cli-124-128.md)区分已实现的流式、串行实验执行与独立核验，以及仍未运行的 provider-live readiness 和配对执行。

## 当前 ALIGN 状态

CP-05 检查点公共 Job 验收与 #112 交接见 [CP-05 交接记录](evals/showcase-cp05-checkpoint-handoff.md)。该记录只使用受控 loopback / replay 证据，保留 #112 的 `unknown/not_run` 身份，不替代 provider-live 或数学能力验收。

最新 RB08 工程门禁、真实实验失败及逐项 ROB-AC 边界见 [RB08 发布与真实实验记录](evals/star-rb08-release.md)。冻结源码 a10481d 的发布检查、前端、54项通用及12项产品浏览器检查通过；真实原E1执行2/4后停止，E2未执行。本轮目标为建立离线简单题、多步 Reference、工具、整题审查、文本绑定与进程恢复闭环；相关聚焦用例、全仓离线合同（757 项测试）及 Showcase 发布门禁均已通过。流式保持可选，本轮未发真实提供方请求，未验证 provider-live 兼容或数学正确率。完整测试命令、接口事实及证据边界见 [#96 非流式主路径验收记录](evals/star-stream-usage-96.md)。修复切片仍在本地、尚未合并；#96 保持开放。只读 Issue 核验（2026-10-27）：#96 是 #95 的直接 blocking issue；#95 正文中 `Blocked by #94` 已过期，因为 #94 于 2026-10-26 关闭。#87 保持开放，8 个子票中 7 个完成，#95 尚未完成；#80 保持开放，ALIGN-AC-18 真实自然非快通道闭环未通过，且无 #95/#96 对 #80 的直接阻塞关系。#95/#87/#80 均不在真实验收达标前关闭，整体为 engineering-preview。下方维护版本的测试数字属于历史记录。

当前 #97 是独立的非流式验收，不以前述旧 E1/E2 通过为前置，也不重算或覆盖原批次结果；#95 仍正式受 #96 阻塞。2026-10-28 首批两题 live 批次完成，但多步样本未进入登记要求的非快通道。后续 r8 批次完成简单题后，多步 Job 的第二次 Explore 请求超时，批次以 `unknown_transport` 停止并保留一个未决 attempt。最新 v5 已提高等待预算，但简单题一次成功计算后达到工具硬限，整题审查未执行，多步题未派发；1 次 HTTP 的 2483 tokens 全部已知，没有未知或未决 HTTP attempt。三份登记均已消费，不续跑、不重试；#97 保持开放。

#97 的当前结果见[非流式就绪核对记录](evals/star-readiness-97-status.md)，执行边界见[批次执行合同](engineering/star-readiness-97-execution-contract.md)，样本及预算见[两题登记记录](experiments/star-readiness-97-preregistration-draft.md)。记录区分离线门禁、真实 provider 工程闭环和数学判定；一次成功的整批调度不代表所有路径验收通过。

上述 v5 事实属于已消费批次，保持原样且不续跑。2026-10-28 新接受的[工具额度与完整回答续接合同](engineering/star-answer-continuation-contract.md)更新后续显式 Showcase / Solver Harness 运行的预算语义：工具额度用满只拒绝新工具动作；若模型、HTTP、token 和时间额度仍允许，Run 可继续推理、消费回执、生成答案并执行整题审查。4 项合成公共 Job 用例与 1 项固定 Docker Reference 用例通过；完整发布门禁的 879 项测试零失败、零跳过，测试接缝检查和六个故障注入探针均通过。此源码门禁未发真实 provider 请求，本地受控结果不代表真实 API 行为或数学正确率。

2026-10-28 v7 已执行：[登记与预算](experiments/star-readiness-97-preregistration-draft.md)、[执行边界](engineering/star-readiness-97-execution-contract.md)和[真实结果](evals/star-readiness-97-status.md)。完整 Reference 九核心开启，扩展 candidate_registry/best_effort 关闭；两套同源码门禁各 920 项通过，官方 baseline 不变。真实多步 Run 的第二次 Explore 等待 900 秒后超时，以 `unknown_transport` 停止；没有完整数学答案或整题审查，未知用量保留预留，v7 已消费且不重跑。公开输出与脱敏归档分开保存；本次输出只有失败提示，不能视为答案完成或能力提升。历史批次不改写，#97 保持开放。

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
- [#123 Intern SSE 契约与故障覆盖](research/intern-sse-123.md)：记录官方 endpoint/payload 流式兼容规则、usage 与 task 状态分层、当前适配器默认及 #124 接入点；仅有离线/loopback 证据。
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
- [工程门禁](engineering/development-gates.md)、[身份链导航](engineering/identity-navigation.md)：开发检查入口与身份、恢复、交付绑定的源码/测试导航。
- [提交与分支规范](engineering/commit-convention.md)
- [Issue tracker](agents/issue-tracker.md)、[状态标签](agents/triage-labels.md)、[领域文档约定](agents/domain.md)
- [示例目录说明](../examples/README.md)、[比赛仓库调研](research/hackathon-winning-repo-landscape.md)

## Intern S2 五方向实验计划

- [实验开发入口](experiments/README.md)：总计划、固定 develop 审计、Intern S2 合同及五组 PRD、技术规格和 ADR。
- [#122 Demo 覆盖矩阵与 CLI readiness 合同](experiments/demo-coverage-122.md)：Showcase 当前证据及 #124–#128 的实现与验收边界。
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

最新 [readiness-05 执行观察器异常记录](evals/provider-live-natural-20261105-readiness-05.md) 区分 runner 写状态失败与服务端仍在运行的自然多步 Job；未获得 readiness PASS，#128 两臂仍 NOT_RUN。

历史批次 [readiness-06](evals/provider-live-natural-20261105-readiness-06.md) 已终态 FAIL：有界 Meta 继续处理后仍未完成整题交付。后续零索引核验与重复历史读取修复不追溯升级旧 Run；当前实验状态见顶部归档入口。
