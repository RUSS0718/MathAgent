# #174 自主并发接线与未完成验收（2026-11-13）

状态：**实现已提交，真实自然并发验收未完成，未达到工程退出**。集成分支 `faithful-autonomous-population`，最近真实运行源码 `77696377f9a1468fa8dbe8872ddddb5381830893`。live18 已自然选择并准入两条路线，但请求在 HTTP 派发前被预算检查拒绝；不能作为真实模型并发或合格交付的通过证据。#174 保持开放，#168 完整服务仍未交付；进行中热切换属于 #175。下方首次交接材料适用于 `c14ff82`，不能替代本节接续结果。

## 接续修正与真实结果（截至北京时间 23:53）

本轮阻止只有数字的候选绕过证明及完备性义务；原始整题裁决保留，运行时资格否决单独记录并约束最终绑定和 Best-Effort。常见数学包装、润色前后同源候选一并覆盖。Planner 使用严格 schema 的精简说明与等价串行/并发示例，澄清可选辅助目标与根义务必需的辅助依赖，保持既有修复轮数、预算和冻结规格。

最新修正明确将可替代的完整证明评估为整题路线，每条路线自行建立结论、取等条件与完备性；Explore 的候选不能直接固化为已证明结果。仍允许有理由的串行选择，不修改解析、准入、方法去重或官方路径。证据在 `artifacts/issue-174-resume/shortcut-fix/`、`review-fix/` 和 `planner-guidance-new/`：保留失败见证与通过记录，27 项短路相关、17 项来源相关、2 项必需辅助目标检查，以及最新 4 项受影响检查、1 项交接断言和 2 项相关检查。各组有重叠，不相加为独立用例数。最新提示词检查仅证明请求送达，不证明真实模型服从或数学能力提升。

| 运行 | 实际结果与限制 |
| --- | --- |
| live06–live09 数位计数 | 出现过并发提案，但 JSON/schema、检查点位置或辅助目标归属失败，未取得真实并发交付；各轮源码与原始回执独立保留 |
| live10 数位计数 | Intake 生成循环依赖，未进入路线执行；不作为 Planner 修复通过证据 |
| live11 参数不等式 | 源码 `9d8dcf1`，自然串行；Reasoner 逻辑超时后保持 unknown，迟到 HTTP 已结算，不自动重发，未交付 |
| live12 同题、任选独立完整证明 | 同源码，Run `run_b6066c4a546ea517e12949f00eeafa80`；8 Attempt 全部结算，自然串行，最终 `route_duplicate_route_frontier`，无答案。Explore 错把 `(1/2,1/2,0)` 的函数值写成 `(1+t)/8`，计划沿用；独立核对为 `1/8` |
| live13 同题、路线提示修正后 | 源码 `87f5d1e`、产品 `7149215`，Run `run_4ddc17efa0f432d63f3b6214838904d6`；自然串行，备选前沿与主计划归一后相同。第 6 个 Attempt 的步骤审查进入 unknown，Job 为 `star_needs_review`，未交付 |
| live14 / live16 数位计数 | 分别在 `b218dd4`（产品 `7149215`）与 `331edf1` 上提出并发，但主计划归属或自依赖未通过；未准入，不算并发执行 |
| live15 / live17 数位计数 | 分别在 `331edf1` 与 `7769637` 上自然串行；为减少无关串行消耗，通过公共取消入口终止，原请求已结算、持久取消终态已封存；未交付 |
| live18 数位计数 | 源码 `7769637`，Run `run_73484a2738f8b8ec14fb74cbf9d93314`；自然选择 `population / independent_routes_admitted`，准入两条独立动作。两条 Reasoner 均为 `budget_rejected / run_budget_exhausted`、零 HTTP 派发；原根账本、限额与 deadline 未重置。Job 最终 `failed / star_needs_review`，两动作已结算，无并发答案 |

`331edf1` 明确主计划本身是一条完整证明路线，而不是多个方向的汇总；`7769637` 为根义务归属造成的自依赖提供定向修复反馈，不增加修复轮数或放宽解析和准入。失败见证及聚焦通过记录分别在 `artifacts/issue-174-resume/primary-route-fix/`、`root-owner-feedback/`。live18 原观察器将 JSON 字段顺序误判为预算变化；父任务以只读数据库及已初始化 dashboard 会话核对并保存 `live18-preparation/live-18-digits/parent-readonly-after-interruption.json` 与 `parent-public-job-after-interruption.json`，原失败状态不改写。

后续源码 `4c79085d8f67078969d43a4c92136f0e51f5ed30` 补齐 Reasoner checkpoint 的协议及现有上下文估算。普通公共 Job 的受控传输见证确认旧实现因 `finalization_reservation_too_small` 在 HTTP 前拒绝；这些精确输入字节数来自离线见证，不能冒充 live18 未保存的 wire 数据。最终失败见证 1 项失败，修复后 20 项聚焦检查通过，包括两路线实际进入受控 HTTP 及根预算下的两次工具预检。证据在 `artifacts/issue-174-resume/native-population-budget-fix/`；没有重跑全仓门禁或真实模型。

该修复还未达到真实重跑条件：受控 YIELD→步骤 ACCEPT 探针的两条路线均停在 `stalled`，未执行下一 checkpoint；可执行探针与原失败记录保留。新鲜规格审查另发现 Verifier 估算使用旧 checkpoint，实际接收本轮新 checkpoint 与报告，长输出有超额风险；请求差异已静态确认，尚未执行长输出复现。标准轴无硬性违规，只有请求组装重复这一 P3 维护建议；规格轴 P2 和续接问题由下一修复负责。审查报告分别为仓库外 `C:/Users/CQX/.codex/174-native-budget-standards.md`、`174-native-budget-spec.md`。live19 仅完成静态准备，未绑定未来源码、未启动服务或提交 Job。

live08 起的新 Run 初始配置将根时限与 Population 根时限设为 2400 秒、动作请求上界设为 180 秒，其余预算保持模型/HTTP 各 48 次、工具 8 次、2,097,152 tokens。配置 SHA256 `9170fa5f39e8262e2ea780a54478bdd14d10e4c6da6531381d3f9a055cf97364`，不是运行中重置预算，也不是容量或 SLA 承诺。旧 1100 秒/30 秒配置的历史证据保持原样。

live13 观察脚本因快照超过 Node 子进程输出缓冲而退出，未取消或重提求解。父任务通过已初始化的普通 dashboard 会话只读获取终态，保存 `job-observed-final.json`、`persisted-observed-final.json`；原 `status.json` 的 ENOBUFS 失败保留。恢复观察最初未初始化会话的 GET 返回 401，也单独保留。两种观察失败均不算模型失败或并发验收通过；unknown 请求未重发。真实自然并发、实际路线 UI、并发完整答案及刷新仍未覆盖。

增量双轴审查见仓库外 `C:/Users/CQX/.codex/174-resume-standards-final.md` 与 `174-resume-spec-final.md`，截至 `7769637` 未发现剩余静态问题；该结论不能替代 live18 暴露的运行故障。尚未启动新的最终门禁：真实并发退出条件仍缺失，避免重复全仓离线测试。当前由父任务持有运行与观察所有权；首次交接末节的清理状态是历史快照。下一步先复现并修复预算拒绝，再用既有独立计数参考验证完整路线；不携带参考答案进入请求，不恢复或重发上述 unknown 调用。

## 实现及受控证据

合同见 [普通入口自主 Population/APRS 合同](../engineering/faithful-service-174-contract.md)。普通入口在首份 Planner 计划后、工作块执行前决定初始路线，不创建新 Job 或重置根预算。复用 Population 执行器、整题检查、答案绑定与迟到结算。工作台及报告公开实际路线、选择原因和预算。

| #174 合同 | 公共边界及断言 | 证据与状态 |
| --- | --- | --- |
| 自主选择、容量与合法替代 | Job `result.solver.execution_selection`，主计划提出选择及独立备选；容量、预算不足记录原因 | `artifacts/issue-174-work/implementation/final-focused.json`：2 项通过；真实自然选择未覆盖 |
| 独立动作、父子来源及根预算 | 同一 Job/Run、根账本与 deadline，独立 Call/Attempt；不足时串行替代，不重置计数 | 同组受控公共入口检查通过；真实并发来源未覆盖 |
| 合格答案及冲突、迟到隔离 | 冲突证据及带作用域的反驳不得提供覆盖，最终交付检查冲突；复用冻结与迟到归档 | `review-fix/{evidence,delivery,scoped}-{red,green}.json`、`scoped-focused.json`；真实并发收尾未覆盖 |
| 前端实际路线及结果 | `自主路线选择`、`实际求解路线`，既有报告预算区域 | SSR、类型检查及构建通过；真实路线 UI 未覆盖 |
| 不宣称热切换 | 只选择初始执行方式，保留配置身份及旧任务语义 | 两轴静态审查未发现剩余实现问题；#175 未实施 |

上表 `review-fix/` 均位于主工作树 `artifacts/issue-174-work/`。其他相关检查见 `implementation/regressions.json`、`review-fix/{conflict-focused,reason-focused,reason-identity-focused,shared-recovery-focused}.json`。配置检查 9 项、关键既有回归 5 项通过；不同检查组有重复用例，不合计为独立用例数。原失败与中间检查均保留。

真实协议故障后，补充了“返回数据实例而非 schema 包装”和“execution_selection 仅属于主计划”的提示。严格解析器、schema 及一次修复限制未放宽；定向检查见 `review-fix/instance-prompt-{red,green}.json`、`primary-selection-{red,green}.json`。

主要复验入口（本记录不要求再执行）：

```powershell
uv run python scripts/run_unittest_report.py --expect-count 3 tests.test_faithful_service_population
```

该模块当前共 3 项，初始实现的 2 项历史结果另见上表。专项选择器、数量与结果以对应 JSON 为准。

## 真实浏览器运行及限制

全部使用普通输入和 Enter 提交，未选择强制 Population 模式。配置为 intern-s2；根预算模型/HTTP 各 48 次、工具 8 次、2,097,152 tokens、1100 秒。Population 共用根预算，使用已有两槽观测证据及显式 30 秒动作上界；其他请求与整题收尾保持 180 秒。配置 SHA256：`d23d75d6a37f8e5111b1f9cafb1232dae7bf795e1f16f1855a297e90f3426677`。这不是 provider 容量上限或 SLA。

| 运行 | 源码 / Run | 实际结果 |
| --- | --- | --- |
| live01 不等式两种证明 | `e2eedc2` / `run_914fc6bd1f80c9676f010d35fa9e6dc0` | 4 Attempt，合法完整答案短路，证明及取等条件经人工核对正确；无 Planner、无并发选择 |
| live02 六阶二值矩阵计数 | `bd66941` / `run_bd7ef0ce5c6db5d9d5b6db5a7e61fdc5` | 3 Attempt，Explore 原回复 JSON 不合法，修复含 tool_request schema 包装，协议失败 |
| live03 同题、实例提示修正后 | `685d852` / `run_aaf520a701d1c47656a52dcf89f01967` | 4 Attempt，Explore NEED_PLAN；Planner 语法错误，修复将选择字段放入备选计划，协议失败 |
| live04 同题、主计划提示修正后 | `c14ff82` / `run_aad7fd0deb6ea3cfb3084517ebfefbec` | 6 Attempt，返回正确计数 297200；未形成路线选择，且仅数字不证明两种完整推导已交付 |
| live05 先计划、直接求和及公式求 S、T | `c14ff82` / `run_61fd60ce2d473669eb81498bf2cb8693` | 6 Attempt，规划前短路；最终 S=338350、T=57240530425 正确，但解释含算式错误，不算完整数学验收 |

live05 例如把 21² 至 30² 的和写成 6485，实际为 6585；把 `169175×338350` 写成 57240530425，实际为 57240361250。模型整题审查接受不能代替独立数学核对。

证据位于 `artifacts/issue-174-work/live-01-population/`，以及 `live02-preparation/live-02-matrices/` 至 `live05-preparation/live-05-sums/`：保留普通输入截图、Job/Run、Attempt、配置/源码身份、公共结果和持久只读快照。每轮验收器因缺失路线选择正确判失败，没有把求解 HTTP 成功计为并发成功。未达到刷新验收步骤的运行不声称刷新通过。自然并发、实际路线 UI、并发答案交付及恢复仍为 **not_run / 未覆盖**。

## 审查、门禁与交接

仓库外审查原件：`C:/Users/CQX/.codex/174-standards.md`、`174-spec.md`，修复定点复查：`174-standards-final.md`、`174-spec-final.md`。最终源码两轴未发现剩余实现问题；静态审查不替代真实验收。协议诊断见同目录 `174-live02-protocol.md`、`174-live03-protocol.md`，未导出完整 prompt 或隐藏推理。

最终门禁**未完成，不计通过**。`gate-01` 在源码 `685d852` 上因确定的主计划协议修正提前中止；`gate-02` 在 `c14ff82` 上因真实并发验收仍缺失、阶段不退出而停止，避免继续无助于补齐该缺口的全仓测试。证据为 `artifacts/issue-174-work/gates/gate-{01,02}/parent-interruption.json`；原 `status.json` 是中止时历史运行快照，不能据此认定进程仍运行。若后续满足退出条件，应冻结最终源码完成一次门禁。

不启动更多碰运气的同题重复运行。后续应先确定能自然产生独立路线的代表场景，再补公共路线、预算、答案及刷新证据。未运行独立数学效果评测，不声称能力提升。官方 baseline 保持无差异；受保护的 `tests/test.md` 未读取、修改或提交。交接继续使用当前选择的同一模型，具体继承型号无法确认，不猜测。

本票所有临时服务均已核对 PID、创建时间及结算状态后停止，8094 无监听；本票定时检查已删除。实现与修复工作树已清理，聚焦证据已复制到主工作树，历史运行目录原样保留。后续不得复用旧运行身份重发。当前没有后台测试运行或待转移的监控所有权。
