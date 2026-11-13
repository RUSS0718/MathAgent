# #174 自主并发接线与未完成验收（2026-11-13）

状态：**实现已提交，真实自然并发验收未完成，未达到工程退出**。集成分支 `faithful-autonomous-population`，产品源码 `c14ff8221b1c4a77f5fe682cc856aa582d6b8a7f`。#174 保持开放，#168 完整服务仍未交付；进行中热切换属于 #175。

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
