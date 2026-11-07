# #155 完整并发 Population/APRS 本地实施交接

**状态：** 实施交接文档，不是产品实现记录。
**核对日期：** 2026-11-07。
**工作树：** mathagent-faithful，核对时 HEAD=e6b6b8919ac266694c36eb0205e5f79fb3ef3953。
**范围：** 交接同一 Run 内多 CandidateRoute 并发搜索；本文档不代表产品实现或付费实验。

## 已补齐的实施承接

已创建 [完整并发实施票 #156](https://github.com/RUSS0718/MathAgent/issues/156)，并通过 GitHub REST 写入、读回核验原生关系：父票 #146，blocked_by 为 F1 #147 和串行 F2 #148。票内 C1–C5 分别承接 policy/所有权与原子预留、轮次并发、依赖核验与收益、恢复/终止、公开交付与结算，明确增量接入 F7/F8；本页八组公共路径验收均已列入该票。没有把它们追加为串行 F2 已完成范围。

交接已回链到 [总票记录](https://github.com/RUSS0718/MathAgent/issues/146#issuecomment-6705014938) 和 [决策票记录](https://github.com/RUSS0718/MathAgent/issues/155#issuecomment-6705016228)。实施票仍开放；标签只表示合同可供实施，不解除工程前置门槛。下文的实现细节和证据缺口由 #156 继续承担，不再是没有承接票的待办。

## 决策来源与串行边界

[Issue #155 最终 resolution](https://github.com/RUSS0718/MathAgent/issues/155#issuecomment-6704660319) 冻结了完整并发 Population/APRS 的行为和验收边界。#155 已关闭为决策完成，不代表产品已实现、服务容量已测量或数学能力已提升。已读取 #155 的全部五条评论；最终 resolution 是本交接的主要行为来源。

[串行实施票 #148](https://github.com/RUSS0718/MathAgent/issues/148) 仍定义 F2/S08 串行首版：任一时刻只执行一条路线，主路线停滞后至多启动一条替代路线。它要求 F1 工程合同先通过。[总实施票 #146](https://github.com/RUSS0718/MathAgent/issues/146) 也将完整并发留作串行实测后的独立目标。不得把 #155 写成 #148 已覆盖，也不得把串行 F2 的验收结果当作并发完成证据。

本地依据的远端规格为 [Faithful implement-spec](https://github.com/RUSS0718/MathAgent/blob/docs/wayfinder-chat-output-prototype-20261106/docs/specs/mathagent-faithful-implement-spec-20261107.md)，读取 ref 为 docs/wayfinder-chat-output-prototype-20261106，文件 SHA 为 c30deb2c51ccf60fa87f68b4a5ac0eaf4630511d。规格仍将 S08/F2 定义为串行路线，并把完整并发列在首版范围之外。#155 是之后批准的增量决策，不会改变串行 Run 的冻结语义。

已读取 #146、#148、#150–154 的 issue 正文和评论集合。#146 与 F4–F8 的入口、依赖和分层验收作为集成背景；#150–154 的现有范围不会因 #155 决策自动扩张。#146、#148、#150–154 当前均无 issue 评论。实施票的创建、标签或关闭状态都不能替代代码和验收证据。

新并发 policy 仅用于显式选择的新 Run。Run 冻结 policy 版本和配置；默认关闭；已运行的旧 Run 不热切换。并发核心是同题、同一 Run 内多条 CandidateRoute 搜索，不是多 Job 吞吐，也不包括单路线内多个 WorkUnit 并行。每条路线最多一个在途 WorkUnit。同源 control/variant 两臂继续遵守 #142 的隔离合同。

官方 user_agent.py、implementations/、baseline 字节、默认预算和官方评分路径保持隔离。现有 POST /api/agent/jobs 接受 solver_mode，但公开模式枚举没有并发模式；solver_options 当前会被拒绝。后续实施票必须定义新 Run 的显式选择面、Run 冻结位置和幂等请求摘要如何绑定 policy 身份。不得假设现有 HTTP 参数已经支持并发。

## 调度机会、执行槽与服务容量

这三个概念必须分别记账和验收：

- **调度机会**是轮次给路线的派发资格。每轮固定当时可执行的路线集合，每条路线至多获得一个 WorkUnit 机会；都获得机会或明确退出后才开始下一轮。新路线从下一轮加入。轮内由 APRS 决定顺序，获准的动作可并行派发。
- **执行槽**是本地 worker 当前可接手的工作位置。等待外部结果的路线不应占住调度循环或阻塞其他路线；同一路线在其请求未完成时不能启动下一 WorkUnit。
- **实际在途服务容量**是 provider、账户、网络连接和机器当下可承载的未完成请求数及相应资源约束。某个路线不占调度机会或 worker 执行槽，不表示它的 HTTP 请求已结束、远端并发占用已释放，或 unknown 预留可释放。容量准入必须把仍未确认完成或取消的请求计入实际在途量，使用真实服务/账户/机器可核验的容量信息；unknown 保留请求身份、用量预留和容量占用状态。不得将未知容量当作无限，也不得编造并发数、费用上限或压力阈值。若无法核验可用容量，记录 unknown/not_measured，不以虚构数值通过容量验收，也不超发。

必要验证、答案审查和持久化收尾先于探索。父 Run 共享账本、原硬截止和动态收尾预留继续有效。记录请求、token、工具、时间、实际并发峰值、失败和 unknown。限流或机器压力下减少新派发，不取消已发出的请求来追逐新排名。调度机会顺序可追溯；真实 provider 完成顺序不承诺可复现。

## 路线证据与提交一致性

每条路线从独立快照推进。未验证引理不得跨路线成为已证前提。只有 Verifier/Controller 按正常审查流程接受并提交权威账本的证据，其他路线才可在后续调度中采用；采用前核验当前版本和依赖。

结果提交按实际依赖的命题版本检查。无关图版本变化经当前状态核验后允许提交，并保留原快照来源。依赖被撤销、修改或冲突时，保留历史尝试，不直接接受为有效证据，须重新审查。并发接受、撤销和图失效须在同一权威持久化边界保持一致。

重复成果保留全部路线来源和真实消耗。Population 总收益按命题版本与证据身份去重；路线统计区分自产和采用。先返回不表示策略更好；重复成果不重复增加总进度。路线选择与 AnswerCandidate 选择继续分离，APRS 不取得数学证据接受权限。

## 依赖图与增量集成

```text
S01 → S02 → S03 → S04
S01 + S03 → S05；S05 可与 S04 并行
S03 + S05 → S06
S03 + S04 → S07 / F1
S07 / F1 → S08 / F2（串行首版）
S07 / F1 → S09 / F3；F3 可与 F2 并行
S08 / F2 + S09 / F3 → S10 / F4、F5
F8 框架可先行；A–G 能力按生产者就绪逐组开放
```

后续并发实现票须依赖 S01–S06 中相关工程门槛、F1 图及原子提交合同、F2 串行路线/APRS 合同的实际验收证据。若并发实现将 Lean L2/L3 作为接受条件，再增加 F3 对应门槛；mock 不作为 Lean 证据。F4/F5 仍须满足 #150/#151 的 F2、F3 前置。F6 基础输出可按 #152 在 S03、S05 后推进，图与 Lean 深链随后增量接入。F7 基础事件/UI 可按 #153 在 S01、S03 后推进，完整视图依赖实际数据生产者。F8 按 #154 分组开放，不支持的组明确记为 unsupported/not_run。

现有 faithful-D 描述 Population/Rater/Pareto/APRS，但其依赖链仍指向串行 F2。后续评测票须明确并发 policy 的实验组、对照条件、完整分母和容量证据。未完成该合同前，串行 D 不能作为并发验收。

实施前记录实际源码 SHA、相对 #146 审计基线 b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6 的差异，以及 S01–S06/F1/F2 前置证据。Issue 关闭、文档完成或某个基础 UI 可见都不能代替这些门槛。

## 公共路径与现有实现缺口

当前可用于后续公共合同的路径：

- 创建 Job：POST /api/agent/jobs。
- 读取 Job、事件和报告：GET /api/agent/jobs/<job_id>、GET /api/agent/jobs/<job_id>/events、GET /api/agent/jobs/<job_id>/report。
- 恢复与取消：POST /api/agent/jobs/<job_id>/resume、POST /api/agent/jobs/<job_id>/cancel。
- 候选回放：GET /api/agent/jobs/<job_id>/candidate-replay。该接口只提供相邻的候选回放，不等于并发路线审计合同。
- 主要代码接缝：showcase/solver_harness/controller.py、showcase/solver_harness/storage.py、showcase/solver_harness/calls.py、showcase/run_budget.py、showcase/star_product_recovery.py、showcase/star_product_events.py、showcase/star_product_pipeline.py、showcase/flask_app.py。

SolverStateStore 已有 revision CAS 和状态/事件原子提交；RunBudgetLedger 已有请求预留与结算；恢复投影能识别未决请求。这些是可复用接缝，不证明已经支持多路线调度所有权、局部 unknown 暂停、依赖版本提交、或交付和结算分离。

本地对 showcase/ 与 tests/ 搜索了 CandidateRoute、APRS、RaterInputSnapshot、RaterEvaluation、frontier_digest 等并发实现标识，未发现完整并发调度实现。现有 star_routing、candidate_registry、Best-Effort 和 Job 恢复只提供相邻能力，不能合并推断为完整并发。

## 八项可执行验收责任

每项都须通过公共控制器、持久化和 Job 路径验证。受控 provider、屏障和故障注入可证明离线工程行为；真实服务容量、provider-live、跨进程和数学收益须各自留证。

| #155 验收 | 实施责任与失败注入 | 公共路径与可核对证据 |
| --- | --- | --- |
| 1. 多路线与轮次公平 | Solver 控制器维护路线快照和 WorkUnit 调度。注入两条路线，证明请求实际重叠、同路线最多一个在途、等待路线不阻塞其他路线、每轮各路线获得一次机会或退出、新路线下一轮加入。 | 用 POST /api/agent/jobs 创建并发 Run；通过 /events、/report 与重启后路线状态核对派发顺序、完成顺序和轮次。 |
| 2. 重复路线与资源准入 | 在路线登记和派发事务中拒绝等价 frontier 与重复动作身份。分别核对调度机会、worker 执行槽、尚未完成的实际 HTTP 请求及 unknown 预留。并发准入竞争须原子检查父账本、真实剩余服务容量、验证和收尾预留；容量/压力用真实服务约束核验。注入限流和机器压力，确认减少新派发，不释放 unknown 资源。 | 同一 Job 注入候选竞争，读取公开路线/预算事件、报告及重启后的账本。保存准入理由、各层占用、预留变化、实际消耗和并发峰值。无可靠容量读数时容量记 unknown/not_measured，不设自创数字。 |
| 3. 证据提交、失效与去重 | 在证明图和 SolverStateStore CAS/原子事件边界核验依赖版本。交错两个结果与图更新；无关变化允许重新核验后提交，实际依赖撤销、修改或冲突时保留历史并拒绝直接接受。重复成果保留来源，整体收益去重。 | 从 Job 公共路径触发交错结果和撤销，检查 /events、/report、Evidence 导出与重启快照。冲突不得部分写状态/事件；路线统计区分自产和采用。 |
| 4. 所有权与跨进程恢复 | 持久化每 Run 唯一调度 owner/version。接管时更换版本；旧 owner 的派发与数学提交必须失败。发送前持久化请求身份及资源预留；恢复复用已完成动作。 | 两个独立进程竞争同一 Run，经 /resume 和公开读取验证 fencing。进程退出覆盖身份已存但发送未确认、以及动作已完成但结果未提交的窗口。核对没有隐式重发。 |
| 5. 局部 unknown 与迟到用量 | unknown 局部暂停受影响路线及依赖动作。无依赖路线只有在实际服务容量、共享账本和收尾准入均通过时才可继续。账本不完整或收尾无法保证时暂停全 Run。重试仅在用户显式决定后使用新请求身份。迟到回执可归档结算，不自动接受为证据。 | 断流或 worker death 后检查 /events、/report 和 /resume 结果。核对 unknown 身份、容量占用状态、预留、暂停范围、新旧 ID lineage、迟到 usage 和自动派发数为零。 |
| 6. 答案冻结与终止栅栏 | 待审答案出现后停止新增探索并冻结文本版本。在途动作保留身份，不改写审查输入。审查拒绝后仅在资源准入通过时恢复合法路线。审查通过、取消或硬截止后禁止新动作；迟到结果只归档和结算。 | 通过 Job /cancel、deadline 和 final binding 制造竞态；核对审查输入 hash、交付文本、终态和迟到事件。迟到回执不得改变终止 Run 的数学状态。 |
| 7. 独立交付与请求结算分离 | 分开持久化数学交付状态和请求结算状态。答案不依赖未决结果且账本完整时，可在仍有未决请求时交付，同时保留 unknown 与预留。答案依赖 unknown 或账本不完整时拒绝交付。 | 经 /report、Job 结果和 Evidence 导出验证两种状态分别可见，刷新/恢复后一致。覆盖“答案独立可交付但请求未结清”与“依赖 unknown 必须拒绝交付”。字段名由实现票确定，本文不预设。 |
| 8. 显式 policy 与旧 Run | 定义默认关闭的新 Run policy 选择、冻结的 policy_version 和含 policy 身份的幂等摘要。新 Run 默认保持旧行为；并发 Run 不可静默降级为串行成功。旧 Run 恢复时使用原 policy。官方路径、baseline 与默认预算隔离。 | 通过 Job 创建、/resume、/report 和 replay 覆盖默认、串行、并发、幂等重放及旧 Run。核对未启用时请求与输出合同不变；检查 user_agent.py 与 baseline 字节/预算边界。 |

实现票应为八项分别指定代码所有者、失败注入、公共请求/读取路径、重启断言和证据产物。把验收映射到测试及发布证据，不用一个“并发开启”测试代替。可复用的相邻测试接缝包括 tests/test_star_product_planning.py、tests/test_solver_harness_candidates.py、tests/test_solver_harness_best_effort.py、tests/test_star_product_recovery.py、tests/test_worker_death_attempt.py、tests/test_star_product_final_binding.py 和 showcase/frontend/chat-frontend/tests/browser/star-recovery.spec.ts。这些测试当前不是并发覆盖证据。

## 答案终止、交付和结算

路线产出待审答案后，停止新探索并执行整题审查。审查期间，在途动作保持原身份和结果，不得改写正在审查的答案。审查通过后、用户取消或原硬截止到达时，禁止新求解动作并尽力取消远端请求。不能确认远端停止时，保留未决身份及资源占用/预留。

审查拒绝后，只在资源准入通过且仍有合法路线时恢复探索。另一条完全不依赖 unknown 的路线可形成独立答案；通过整题审查后可以交付。交付状态与请求结算状态分别持久化和展示。未决请求与 unknown 预留继续留账；若答案依赖未决结果或共享账本完整性受损，则禁止交付。终止 Run 的迟到回执只可归档和结算，不可改变数学状态或已交付答案。

## 后续真实实施票仍须补齐的内容

1. 将 #155 作为独立并发实现范围引用，并依赖 F1/F2 的实际工程验收。本文档和 #155 关闭都不是实现。
2. 冻结公开 policy 选择面、默认关闭行为、Run 冻结字段和幂等身份规则。当前 solver_options 不可用。
3. 为八项验收认领具体模块所有者及控制器、持久化、预算、恢复、报告/UI 的集成点。
4. 定义跨进程 owner/version、同路线在途唯一性、动作身份、结果依赖集合及原子接受边界。CAS revision 本身没有定义这些领域规则。
5. 定义局部 unknown、全 Run 暂停、容量占用、迟到 usage、显式新身份重试和终止 Run 结算的可观察状态。
6. 定义数学交付与请求结算在数据库、事件、API、报告和 Evidence 导出的合同。
7. 指定与 #150–154 的增量集成责任，尤其 F7 公开事件视图和 F8 faithful-D 并发评测范围；确认前将并发实验标 not_run。
8. 依据服务、账户与机器真实容量制定核验和测量计划。区分派发机会、worker 槽和实际在途容量；unknown 不得被当作可用容量。未测前不填并发数、压力阈值、费用上限或性能门槛。
9. 记录源码 SHA、对 #146 审计基线的差异、S01–S06/F1/F2 前置证据，以及离线、隔离工具、provider-live、自然题和独立数学评测状态。缺证据时用 incomplete、unavailable、not_verified 或 not_run。

## 原件依据与 ZIP/PDF 核验边界

#130 路线地图记录的 PDF 身份为 MathAgent_11.5.pdf，SHA-256 为 370a37110d4104ff839daf3f08d933b004bc42d41868a7df15f6576cfa14091e。已核对本地文件 C:/Users/CQX/Desktop/揭榜挂帅/MathAgent_11.5.pdf，实算 SHA-256 与 #130 记录一致。提取文本位于 C:/Users/CQX/.codex/faithful-original-pdf.txt。

提取文本的 §5.3–5.4（印刷第 12 页）描述路线的 Candidate ID、依赖快照、证明状态和成本，Population 谱系，Rater/Pareto 评价、APRS 预算分配，以及按可验证进展、探索价值、新颖性和成本调度。§7.3 描述从同一 Checkpoint/State Revision 创建对照与替代策略分支、固定比较条件、只改变预登记证明动作并独立验证。§9 包含 A–G 消融；D 组加入 Population、Rater/Pareto 与 APRS。提取文本没有明确完整并发的调度所有权、轮次规则、实际在途服务容量或 unknown 预留合同；这些具体行为仍以 #155 最终 resolution 为来源，不能倒推为 PDF 已定义。

#130 记录的 ZIP 身份为 MathAgent_MD_20261106_Faithful.zip，SHA-256 为 14651a0adb075ba466814f2b618ccc2bdefe5f0eb6cc291fbd5b897557305433。ZIP 原件尚未找到或核验，不能声称已覆盖 ZIP 全部目标。本文只记录已核对的 PDF 范围和 #155 并发增量，不替代 ZIP 原件身份核验或全目标覆盖审计。

本次没有实施产品代码、运行全仓测试、调用真实 provider、进行跨进程容量压力测试、标定服务容量或性能、执行数学能力对照。新建本文件只完成本地实施交接，不能关闭后续实施票。
