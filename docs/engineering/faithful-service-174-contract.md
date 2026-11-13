# #174 普通入口自主 Population/APRS 合同

范围：#168 C2；进行中串并行转换属于 #175。真实模型、浏览器验收、评测记录及最终门禁由集成负责人负责。本合同不声明自然选择或数学能力已经验收。

## 公共入口及冻结范围

普通 `POST /api/agent/jobs` 不需要提交技术模式。现有自动 ProblemSpec 与 Explore 之后，首份 Planner 计划在执行任何 WorkUnit 前提出 `execution_selection: {mode: serial|population, reason}`；并发提案通过 `alternative_plans` 提供独立前沿。必要能力、容量和根预算不足时记录串行替代理由。简单题仍可直接经整题检查完成。

能力权限在新任务初始化时持久化到 `state.autonomous_routes`。选择仅发生一次，不修改 config hash，不创建新 Job/Run，不重置计数或 deadline。旧任务没有此权限记录时沿用原合同。

配置沿用 `population.capacity` 的已核实容量和来源。可选 `population.request_timeout_seconds` 设置并发动作的逻辑请求上界，必须大于零且不超过当前 adapter 的请求上界（服务 loader 上限 180 秒）。未配置时沿用 adapter。整题收尾保留原 adapter 上界；底层 socket 超时与逻辑截止不同，公开 Attempt 的 `effective_timeout_seconds` 表示实际逻辑上界，unknown 仍保留原预留并等待结算。

普通任务始终使用原 `budget`；高级 Population 预设的独立预算不替换它。运行时分别估计路线动作和整题收尾预留，派发时继续通过现有原子准入复核。

## 选择、执行及交付

| 内容 | 持久 / 公共位置 |
| --- | --- |
| 选择 | `state.execution_selection` / Job `result.solver.execution_selection` / Report `solver.solver.execution_selection` |
| 选择字段 | `version=autonomous-routes-v1`、`requested`、`selected`、`reason`、脱敏 `proposal_reason`、`independent_routes`、`capacity`、选择时 `budget` |
| 实际路线 | Job `result.solver.population.routes`，逐项 `ordinal`、`parent_ordinal`、`status`、`step_count`、`completed_steps`、`result` |
| 动作及来源 | 既有 `state.population.routes/actions`、同一根账本、独立 Call/Attempt；公共路线只展示序号 |
| 工作台 / 报告 | `自主路线选择`、`实际求解路线`；报告保留 `并发路线执行` 和 `累计预算与未知消耗` |

完整候选沿用现有义务、冲突和来源检查、独立整题 Verifier 及答案 artifact 绑定。获准收尾后冻结其余新派发；不依赖的在途或 unknown 请求单独结算。迟到回执不能改写终态答案；GET、刷新和报告读取不能新增求解。

## 聚焦验证边界

- `tests.test_faithful_service_population`：普通提交实际并发、根预算及 deadline、独立调用、动作逻辑超时与收尾上界、绑定答案与只读重开；预算不足时明确串行替代。
- `tests.test_faithful_service_config`：显式配置、原根预算和 adapter 上界、非法超时拒绝。
- 复用公共 unknown/迟到结算、简单题及 Planner checkpoint 的受影响回归；前端复用 `population-report.test.ts` 检查实际路线及预算显示。

上述受控 provider 检查只证明工程接线。自然并发选择及真实工具/模型回执以父任务验收产物为准；未执行项保持 `not_run`。

## 2026-11-14 代表场景调整

按用户“迟迟无法推进时适当降低验收标准”的授权，把反复受协议、合法串行选择与超时影响的 12 位数计数主场景替换为 6×10 棋盘骨牌计数。旧场景全部失败与 unknown 记录保留，不能因调整而变为通过。新输入表达赶时间、接受额外计算成本和独立方向竞争的普通目标，不提交技术模式或固定模型选择。

获胜路线只需正确精确整数、可复现算法及覆盖全部铺法且无重复的简明理由；不要求两条路线都完成，不要求两种完整长篇证明，不增加成功率、性能或独立能力评测门槛。仍要求同一普通任务中自然选择并实际并发、共享原根预算与独立身份、合格整题检查与答案绑定、前端实际展示和只读刷新。迟到隔离可复用既有受控故障证据，不强求本轮恰好自然出现迟到。
