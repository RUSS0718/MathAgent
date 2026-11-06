# Faithful 方案相对固定 develop 的源码差距

日期：2026-11-06（Asia/Shanghai）
目标基线：`b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6`（develop / PR #129 合并提交）
范围：MA-PRD-20261106、MA-TD-20261106、技术报告提取文本，以及 S01–S10 的源码接缝、测试和既有状态。本文是只读研究记录，不是实现验收。

## 结论

**已确认：** 固定基线已有可复用的 SolverHarness、SQLite 共享事务与 revision CAS、Run 预算账本、流式调用审计、显式 unknown 恢复、单 Plan 求解与审查、依赖失效、受控计算、事件/SSE、最终答案绑定和实验配对基础。相应测试文件提供了离线行为合同；既有 readiness-30/31 记录提供两次真实运行的失败边界。

**已确认：** 这些基础不等于 Faithful 目标能力。基线没有证据证明具备有效内容增量闲置 watchdog、受容量约束且可追溯的 ContextPack、稳定原题义务账本与义务进度、完整 AND/OR 证明图、多条并存路线及 APRS 调度、Lean L2/L3 证明闭环、同一 checkpoint 的策略反事实分支，或可安全复核的跨题证明缓存。现有类名、结构校验、答案候选、整 Run 配对和模型审查均不能替代这些行为验收。

**建议：** 先把 S01–S06 作为运行可靠性与产品交付基础切片，保持官方入口隔离；S07–S10 再分别建立图语义、路线调度、形式化后端和受控干预/记忆合同。实现依赖以 MA-TD 第16节为准，研究可并行，不应把 M1–M4误读成所有工作完全串行。

**未知：** Intern S2 的可信上下文窗口、真实自然多步完整交付的稳定性、Lean 环境/资源是否能在期限内部署，以及现有实验配对接口能否经济地扩展为同 checkpoint 的策略干预，均未由本次静态审计证明。未发 provider 请求，也未运行测试或整仓门禁。

## 范围、来源与证据口径

1. 固定源码为 [b7038798](https://github.com/RUSS0718/MathAgent/commit/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6)，研究开始时本 worktree 的 `HEAD` 与该 SHA 完全一致。代码与测试链接均固定到该提交。
2. 目标材料是本机解压副本：`artifacts/wayfinder-20261106/MathAgent_PRD_20261106.md`（MA-PRD-20261106，文档日期 2026-11-06）及 `artifacts/wayfinder-20261106/MathAgent_Technical_Design_20261106.md`（MA-TD-20261106，文档日期 2026-11-06）。二者是本轮实施依据。
3. 报告背景来自 `artifacts/wayfinder-20261106/report.txt` 的 PDF 提取文本。其封面文本标注报告 V3.1、完成日期 2026-11-04；仅用于辨认目标机制，不覆盖 ZIP/Markdown 方案。当前资料目录没有原 ZIP 或 PDF 二进制，因此未独立校验文件哈希、排版或提取完整性。父决策地图记录的输入文件及哈希见 [Issue #130](https://github.com/RUSS0718/MathAgent/issues/130)。
4. **事实**表示固定源码、测试文本、已归档验收记录或 GitHub 当前状态可直接核对；引用测试只说明存在相应测试合同，本次没有重跑。**建议**是待实施的最小风险验证；**未知**是缺少本次可用证据，不能推断为支持或不支持。
5. 逐项检查代码路径和对应测试名，未读取或更改 `tests/test.md`；未运行模型、provider、Docker、整仓测试或发布门禁。

技术报告摘要列出八项机制：统一状态管理、图结构证明建模、反向多路线规划、种群演化搜索、自适应形式化、因果策略干预、分层记忆、依据驱动讲解。S01–S06 是可靠性、规格、公开交互和交付基础；S07 对应证明图，S08 对应路线/种群/APRS，S09 对应 Lean/规格核验，S10 合并了报告中的干预和记忆目标。八项机制与十个开发切片不是一一对应关系。

## 固定来源索引

| ID | 固定来源 | 用途 |
| --- | --- | --- |
| B01 | MA-TD 第1–2节、16–17节、18–19节来源表；本地路径 `artifacts/wayfinder-20261106/MathAgent_Technical_Design_20261106.md` | 目标基线断言、接缝、切片、验收与固定代码链接 |
| B02 | MA-PRD；本地路径 `artifacts/wayfinder-20261106/MathAgent_PRD_20261106.md` | 用户流程、异常语义及发布优先级 |
| B03 | 技术报告提取文本 `artifacts/wayfinder-20261106/report.txt`，尤其第2、4–8、18–20页 | 八项报告机制及目标背景；提取件，不是源码能力证据 |
| B04 | [仓库文档索引](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/README.md)、[事务 ADR-0013](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/adr/0013-solver-harness-boundary-and-shared-transaction.md)、[状态与恢复 ADR-0014](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/adr/0014-star-product-state-and-recovery.md) | 当前能力入口、共享 SQLite/CAS、恢复身份和职责边界 |
| B05 | [readiness-30](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/evals/provider-live-natural-20261106-readiness-30.md)、[readiness-31](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/docs/evals/provider-live-natural-20261106-readiness-31.md) | 真实运行限制；只对各自归档 Run 有效 |
| B06 | GitHub [Issue #131](https://github.com/RUSS0718/MathAgent/issues/131)、[Issue #130 决策地图](https://github.com/RUSS0718/MathAgent/issues/130)、[PR #129](https://github.com/RUSS0718/MathAgent/pull/129) | 任务合同、当前阻塞/分支背景与合并基线 |

## S01–S10 差距矩阵

### S01 超时、错误与幂等

- **事实与入口：** [`adapters.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/adapters.py)、[`request_transport.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/request_transport.py)、[`calls.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/calls.py)、[`run_budget.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/run_budget.py) 已提供绝对 deadline、流调用审计、partial/unknown、显式新调用重试和预算预留；[`workspace.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/workspace.py) 有请求 digest 与幂等键；前端 [`ChatWorkspace.vue`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/frontend/chat-frontend/src/components/ChatWorkspace.vue) 每次提交创建 key。测试入口包括 `test_adapters.py`、`test_request_transport_loopback.py`、`test_solver_harness_streaming.py`、`test_star_product_recovery.py`、`test_workspace_jobs.py`。历史事实：readiness-30 在长输出时触及 1200 秒；readiness-31 流中断时未完成终稿/整题审查/绑定，详见 B05。
- **建议与最小风险验证：** 复用现有 deadline、attempt 与 budget 合同，新增独立的首响应/有效增量闲置策略；用虚拟时钟区分正文增量与 headers、心跳、usage，覆盖 POST 回包丢失后的同 key 查回、刷新后的身份保存、unknown 不自动重发。保持 provider 的“远端是否已执行”语义为 unknown，除非明确证明未发送。
- **未知：** 固定基线是否存在可满足产品合同的内容 idle watchdog，现有浏览器 key 是否能跨 reload 恢复，30 秒/1200 秒及各 role 首响应阈值是否合适；#124 当前仍 open，#127 当前仍 open。

### S02 上下文

- **事实与入口：** [`context_injection.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/context_injection.py)、[`sessions.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/sessions.py) 已投影角色状态、保存角色历史并做特定 challenge 前缀去重；[`intern_port.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/intern_port.py) 最终将 request 序列化为单条 JSON user message。测试 `test_solver_harness_sessions.py`、`test_session_history_dedup_127.py`、`test_solver_harness_intern.py` 覆盖会话和消息构造。
- **建议与最小风险验证：** 在最终序列化边界建立派生 ContextPack，输入组成、included refs、状态/规格版本、hash 与估算大小一并记录；先去重/外存已结束历史，再摘要已结束片段，永不自由摘要固定题干、当前目标和未解决异议。用超大当前字段、工具配对、失效摘要和摘要失败验证最终 payload 容量与来源可追溯。
- **未知：** provider/model 的可信输入窗口未在本次来源中确认；token 估算误差、最小固定层超过安全 cap 时的产品交互、摘要质量与失败概率未测。没有找到已实现的 ContextPack 容量准入闭环。

### S03 规格与工作块

- **事实与入口：** [`initial_state.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/initial_state.py)、[`intern_schemas.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/intern_schemas.py)、[`plan.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/plan.py)、[`verification.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/verification.py)、[`finalize.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/finalize.py) 实现有序 Plan、步骤依赖、step gate、answer_claim 分类、整题审查和 finalization；`test_star_rb03_obligations.py`、`test_star_product_planning.py`、`test_solver_harness_verification.py` 有义务方向、缺失要求和计划行为用例。当前状态不是稳定 ProblemSpec + 全量根义务 ID/证据政策 + WorkUnit 进度账本。
- **建议与最小风险验证：** 保留原题及旧 Plan 语义，新增版本化 ProblemSpec/Obligation/WorkUnit 投影，进度只由有效裁决和证据计算；先以多要求 Pell 样例测遗漏、双方向、拆分义务分母、规格更新失效及“已覆盖但仍需整题审查”。
- **未知：** 自然语言原题自动提取义务的召回/精度、稳定 ID 在措辞改写下的策略、现有 answer_claim 分类是否能安全迁移为根义务合同，尚无自然题集验证。

### S04 进展调度

- **事实与入口：** [`controller.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/controller.py)、[`challenge.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/challenge.py)、[`meta.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/meta.py)、[`replan.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/replan.py) 已有相位控制、有限 Challenge、Meta 裁决和经决策门控的重规划；`test_solver_harness_meta.py`、`test_solver_harness_replan.py`、`test_star_product_replan_decision.py`、`test_cp05_public_job.py` 覆盖若干受控路径。技术设计明确区分既有轮数/调用上限与拟新增的“有效数学进展”停滞签名；readiness-31 也未证明无限重试。
- **建议与最小风险验证：** 在现有控制器中加入按目标、相关假设版本、策略、有效证据和异议归一化的 progress signature；先用固定脚本验证重复同动作阻止、相关新证据可重新准入、格式修复/工具续接不算数学回合、收尾预算优先。避免另建并行控制循环。
- **未知：** 2 次重复、3 个无进展回合只是待校准初值；对自然数学题的停滞检测误报、漏报和 Meta 建议质量未知，实时能力未由 fault-injection 证据证明。

### S05 公开产物与 UI

- **事实与入口：** [`star_product_events.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/star_product_events.py)、[`star_product_projection.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/star_product_projection.py)、[`ChatWorkspace.vue`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/frontend/chat-frontend/src/components/ChatWorkspace.vue)、[`AgentTimeline.vue`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/frontend/chat-frontend/src/components/AgentTimeline.vue)、SSE runtime 已有脱敏事件、持久游标续读和进度投影；`test_solver_harness_events.py`、`test_sse_contract.py`、`test_star_product_align_recovery.py` 覆盖部分合同。现有时间线按事件类别投影/聚合，不等于每个调用实例均有可展开公开产物和稳定进度。
- **建议与最小风险验证：** 复用既有事件 ID、Job/SSE、权限和脱敏路径；先将一条真实完整 role 输出以调用身份、plan/spec 版本、状态、证据引用提交并可分页读取，再验证重复事件、重连、失效产物标记和活动角色集合。避免新建事件总线。
- **未知：** 长产物的交互与无障碍体验、事件投影在多计划/多重试下是否能表达所有产物，以及真实运行中产物完整性尚未验收。

### S06 输出模式

- **事实与入口：** [`final_binding.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/final_binding.py)、[`finalize.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/finalize.py)、[`star_result_semantics.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/star_result_semantics.py) 已有最终审查、精确文本绑定和形式化状态降级语义；`test_star_product_final_binding.py`、`test_star_product_full_modes.py`、`test_star_acceptance.py` 覆盖既有模式/绑定合同。检索固定 Showcase 源码未发现 `/teach`、`/report` 命令解析或 `PresentationArtifact`/`presentation_status` 执行闭环；`ComposerBar.vue` 主要提交消息和现有 solver mode。
- **建议与最小风险验证：** 在输入首 token 解析 answer/teach/report，并把题目正文、原答案与派生展示工件分开持久化；样式失败时保留原答案，只重试整理。先验收普通消息不受误解析、样式文本不改写答案、改写触发重新审查、超时回退原答案。
- **未知：** /teach 与 /report 的样式质量、生成式说明中的新增断言核验，以及不同客户端对可选 output mode 字段的兼容性未验证。

### S07 证明图

- **事实与入口：** [`classified.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/classified.py)、[`traceback.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/traceback.py)、[`storage.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/storage.py) 已有分类成果、步骤/结果依赖、状态版本和 traceback 闭包。`test_solver_harness_traceback.py`、`test_star_product_traceback.py`、`test_star_product_classified_outcomes.py` 覆盖线性计划/依赖失效行为。固定合同先归档连续 Plan 区间，再按依赖闭包失效；它不是含多个 Proposition/Inference、AND/OR 与独立支持集合的完整图。
- **建议与最小风险验证：** 先将旧 Plan 投影为单路线图，新增不可变 proposition/inference 版本和有效支持集合；以 A、B 独立且 C 依赖 A 的图验证撤销 A 保留 B，两个 OR 支持撤销一个仍保留结论，并拒绝循环自证、悬空引用和无效前提版本。
- **未知：** 真实复杂题的图抽取准确性、节点数量下的事务/查询成本、旧 Run 转换策略及反驳证据门槛均未验证。LangGraph execution graph 不能据其名称当作数学证明图。

### S08 路线与 APRS

- **事实与入口：** [`planning.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/planning.py)、[`plan_generation.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/plan_generation.py)、[`candidates.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/candidates.py)、[`best_effort.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/best_effort.py) 支持单一当前 Plan 与答案版本/Best-Effort 选择。`test_solver_harness_candidates.py`、`test_star_product_best_effort.py`、`test_star_product_replan_decision.py` 覆盖答案候选和重规划边界；没有路线种群、路线谱系访问统计和 APRS 收益预算调度的行为证据。答案候选不等于 CandidateRoute。
- **建议与最小风险验证：** 先保留主路线和至多一条停滞触发的替代路线，串行调度；路线与答案候选分型，验证收益按根义务/证据去重，成本与访问数可回放。用同一预算脚本测重复路线不刷分、不可执行路线被过滤、预算停止可交付、checkpoint 重启后路由身份一致。
- **未知：** 路线评分权重、Population/Elo 是否带来收益、实际路数与并发是否值得、真实题上的预算分配效果未实测；报告中 APRS 的简称全称和参数也需以目标文本最终定稿为准。

### S09 Lean 与规格核验

- **事实与入口：** [`tool_ports.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/tool_ports.py)、[`verifier_compute.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/verifier_compute.py)、[`computation_evidence.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/computation_evidence.py) 与容器化 Python 工具提供受控工具/计算回执基础；[`star_result_semantics.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/star_result_semantics.py) 把 `formal_verification` 固定为 `not_verified`。`test_solver_harness_tools.py`、`test_star_rb02_computation.py`、`test_star_product_semantics.py` 覆盖部分证据合同。固定依赖及源码审计未发现 Lean/Mathlib 执行后端；结构检查、计算回执和 LLM review 均不能称作 L2/L3。
- **建议与最小风险验证：** 先以可信原生 Lean 命题做工具/环境 spike，固定 Lean、Mathlib、允许公理和 checker 身份；分别验证正确证明、错误目标、额外假设、`sorryAx`/不允许依赖、版本漂移、timeout 和 cleanup unknown。将原题—ProblemSpec—形式命题三层对应审查与 kernel 结果分开记录；未有执行器时继续报告 unknown/not verified。
- **未知：** 可安装环境、Lean 版本兼容、模型形式化能力、资源成本、对竞赛题的覆盖率及 S09 能否在 2026-11-10 前发布均未知。不能从 AST/子进程或 Python 容器推断 Lean 已接入。

### S10 干预与记忆

- **事实与入口：** [`paired.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/paired.py)、[`paired_conditions.py`](https://github.com/RUSS0718/MathAgent/blob/b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6/showcase/solver_harness/paired_conditions.py) 和实验配对 API 可固定条件、创建独立 Run 并核验单因素配置；`test_solver_harness_paired.py`、`test_experiment_pair_worker_plumbing.py` 覆盖配对/恢复。现有 Run 会话、失败账本和 checkpoint 属运行态记忆；没有同一数学 checkpoint 派生隔离动作分支并独立回灌的验收，也没有以 Goal/假设/依赖/Lean 版本为键的跨题证明缓存。整 Run 单因素对照不等于同源 Counterfactual Replay。
- **建议与最小风险验证：** 复用配对登记和冻结身份概念，但为分支引入不可变 source checkpoint hash、动作差异白名单、独立预算、证据隔离、未知臂保留及完整分母；先用确定性 scripted 运行验证双臂起点一致、互不污染、结果反馈只影响后续调度。记忆先做 Run Memory/路线经验，Lean Goal Cache 等到真实证明对象、可信键和命中重验流程成立后再启用。
- **未知：** 既有 pair manifest 能否表达 checkpoint 分叉、跨 Run 复制成本、因果效应识别和统计功效、记忆收益与污染风险、缓存重验代价均未验证。Issue #128 当前 open 且依赖 #127；本研究不构成其验收。

## 事务、恢复和状态边界

- **事实：** ADR-0013 与 `showcase/solver_harness/storage.py` 记录 Solver state/event 共用 Showcase SQLite 连接与事务，使用 `state_revision` CAS；公开 Job/SSE 是持久事件投影。工作区创建和动作也有幂等键及请求 digest。应扩展这些边界，避免第二份权威数学状态或平行事件总线。
- **事实：** 调用恢复区分已完成响应、明确未发送和结果未知；未知请求需要新的 call identity，保留旧账本和原 deadline。恢复检查点不意味着可以安全重放远端未知请求。浏览器 SSE 续读只恢复观察；不等于执行器从任意位置恢复。
- **建议：** 每个新增对象使用 run_id、state/spec revision、来源 artifact 与 schema/policy 版本；数学状态及公开事件原子提交。新旧 JSON 采用增量版本化，旧 Run 保持原解释；新开关默认关闭。S01 的请求身份、deadline 与 ledger 行为应先于 S02–S10 扩展。
- **未知：** Faithful 全状态 schema 演进、长时间事务/多 worker 竞争规模和新图形数据的持久化成本，需要在具体切片合同中量化；本次没有运行锁竞争或进程退出测试。

## 工作区差异与外部状态

### `e6b6b89` 相对目标基线

Git 祖先检查确认 `e6b6b8919ac266694c36eb0205e5f79fb3ef3953` 是固定 `b7038798` 的祖先。必须区分单次提交与两版本树差异：`git show e6b6b89` 的该次提交只改 `intern_schemas.py` 和 `test_solver_harness_intern.py`；但 `git diff --stat e6b6b89 b7038798` 涉及 138 个文件，后者还包含后续运行修复、测试和归档，不能将两版本差异缩成一次 schema 放宽。

`e6b6b89` 自身用 `handoff_obj` 允许角色回复附带字段；固定基线已改回通用严格 schema，并在 `partial_exploration` 中只注册 `role`、`action`、`findings`、`allowed_tools` 等有类型约束的字段。基线 `test_partial_exploration_accepts_only_registered_handoff_fields` 明确拒绝未知字段、错误 role/action，并保留必填字段检查；该早期测试不能证明任意 `usage` 字段均被接受。参见 [e6b6b89](https://github.com/RUSS0718/MathAgent/commit/e6b6b8919ac266694c36eb0205e5f79fb3ef3953)、[从旧工作区到固定基线的比较](https://github.com/RUSS0718/MathAgent/compare/e6b6b8919ac266694c36eb0205e5f79fb3ef3953...b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6) 和固定基线的 `showcase/solver_harness/intern_schemas.py`、`tests/test_solver_harness_intern.py`。后续实施须从固定基线重新核验，不能把旧工作区行为套用到当前能力。

完整树差异的主要代码区域包括 `adapters`、`calls`、`run_budget`、`intern_port`、`sessions`、`context_injection`、`storage`、`verification`、`finalize`、公开事件/投影及实验执行/核验链；新增或变化的测试包括进度事务、角色交接、去重、预算准入、工具反馈及独立报告核验。这说明 S01–S06 和 S10 的接缝应以 b703 的实际实现为准，不能重复照搬旧工作区缺口。138 个文件的逐项业务正确性未在本次重新运行验证；此处仅确认 Git 树差异和关键源码合同。
### GitHub 状态核对

通过 GitHub REST 只读查询核对，日期为 2026-11-06：

| 对象 | 核对状态 | 与本研究的关系 |
| --- | --- | --- |
| [PR #129](https://github.com/RUSS0718/MathAgent/pull/129) | closed，merged；合并时间 2026-11-06 09:58:13 UTC | 与目标基线对应 |
| [Issue #124](https://github.com/RUSS0718/MathAgent/issues/124) | open | 流式调用相关既有工作仍开放 |
| [Issue #126](https://github.com/RUSS0718/MathAgent/issues/126) | closed | 独立核验/报告导出前置工作已关闭；不表示 S01–S10 验收 |
| [Issue #127](https://github.com/RUSS0718/MathAgent/issues/127) | open | 自然多步 Demo readiness 尚未满足其工单关闭条件 |
| [Issue #128](https://github.com/RUSS0718/MathAgent/issues/128) | open，正文列出被 #127 阻塞 | 配对消融路径不可据此称已完成 |
| [Issue #130](https://github.com/RUSS0718/MathAgent/issues/130) | open | 父决策地图仍在收集研究与计划决策 |
| [Issue #131](https://github.com/RUSS0718/MathAgent/issues/131) | open | 本研究交付给父任务引用；不关闭、不评论、不改写状态 |

## 最小风险验证问题汇总

1. **S01：** 假时钟下 30 秒正文闲置、持续正文超过软提示、纯心跳/usage、首响应超时、Job POST 回包丢失分别得到何种状态？未知请求是否保留原 call/预算并要求显式新身份？
2. **S02：** 最终实际序列化 payload 能否在固定 cap 内，同时保留原题、当前目标、未解决异议及目标相关工具回执？超限或摘要失败是否 fail closed？
3. **S03–S04：** 多要求题能否稳定映射义务并正确计进度？重复动作/异议是否被阻止，新增相关证据是否允许恢复？有义务未完成时是否阻止整题完成？
4. **S05–S06：** 断流/刷新后能否按调用身份补读完整产物？派生表达失败或改写数学断言时，原答案与验证绑定是否仍正确？
5. **S07–S08：** 独立支持、依赖撤销、循环、路线重复、收益去重和预算重分配能否通过确定性反例？旧线性 Run 能否无损读取？
6. **S09–S10：** 固定 Lean kernel 是否能给出与原题映射分离的可复核证据？策略分支是否来自同一冻结状态且无跨臂状态/证据污染？未知结果和未触发组件是否保留在分母？

这些问题是后续验收起点，不代表本轮已经执行或通过。
