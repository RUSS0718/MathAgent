# S10/F4/F5 工程验收合同

日期：2026-11-10（Asia/Shanghai）。状态：实施中，以下项目未经本阶段验收不得标为通过。

权威要求：[F4 #150](https://github.com/RUSS0718/MathAgent/issues/150)、[F5 #151](https://github.com/RUSS0718/MathAgent/issues/151)、[同源干预决议 #142](https://github.com/RUSS0718/MathAgent/issues/142#issuecomment-6702797011)、[记忆决议 #143](https://github.com/RUSS0718/MathAgent/issues/143#issuecomment-6702958359)、[阶段门禁 #144](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。F2/S08 与 F3/S09 的工程退出见[文档索引](../README.md)。

实施起点：`mathagent-faithful` 的 `f7d9c530978fbcbf453e06ba0a24500cb9593721`，指定集成工作树。旧 `PairedRunner` 的双独立 Run 配对不能满足 F4 的运行中同源分叉；其结果不得写为 AC17 通过。S09 的形式化结果已具备真实固定 Lean 环境证据，但普通答案、L1 或模型审查均不得进入 F5 的形式缓存。

| 合同 | 公共入口 | 持久状态及关键断言 | 最小验证 | 当前结果 |
| --- | --- | --- | --- | --- |
| #150 AC16 失败假设 | 显式实验建议及只读 Job/Report/Evidence 投影 | 原因分类、结构化证据、候选动作、反证条件、状态；unknown 和传输失败不入因果队列 | 缺证据、错误分类、恢复后读取 | 未验收 |
| #150 AC17 同源分叉 | 已提交 Solver checkpoint 的显式 pair 操作 | 同一 run/problem/math hash、revision、graph、plan、义务/前沿及配置；只替换一个登记动作，双 branch 身份及事件隔离；拒绝跨臂访问 | 双动作、快照漂移、配置差异、跨臂读写 | 未验收 |
| #150 AC17 预算和顺序 | 父 Run 的共享预算及原 deadline | 两臂对称预留，真实请求/token/工具/时间/unknown 累计在父账本；固定种子可重放启动顺序 | 预算不足、迟到结算、重启 | 未验收 |
| #150 AC18 效果与回归 | pair 报告与父 Run 只读投影 | 全部已启动 pair 留分母；任一臂 unknown/incomplete 不插补；仅双臂可判定时计算差异，按预登记方法和样本数决定是否可给区间；父 Run 保持原 checkpoint 和 policy_version；胜出证据另走原子重审 | 单臂 unknown、样本不足、未经重审合并、policy 热切换 | 未验收 |
| #151 AC21 Run Memory | Job/Run 恢复和公开记忆视图 | 沿用原身份、预算、checkpoint、图版本与有效证据；清理不删权威账本或事件 | 重启、局部失效、清理 | 部分实施：`--faithful-memory-review` 显式启用只读 `/api/agent/jobs/{job_id}/memory`，从持久 Solver 与预算账本读取；默认无路由。重启、局部失效和清理仍未验收。 |
| #151 AC21 Population Memory | 当前 Run 的显式记忆注入及管理入口 | 成功/失败/unknown 保留来源、适用条件、版本和成本；失败/unknown 仅供诊断；命中不改变 verified_gain、证明状态或当前 policy_version | 同域命中、跨域默认拒绝、显式导入及重审 | 部分实施：`GET /api/sessions/{session_id}/population-memory` 在认证与当前聊天会话边界内只读历史路线，保留 Run、路线、状态、版本和 unknown 观察数；不提供证明或收益。新增 `FaithfulMemoryStore` 将建议性观察按用户、工作区及作用域持久隔离，并支持内部显式导入、禁用和清理墓碑；尚未接入当前 Run 或公开管理入口。真实成本、重审仍未验收。 |
| #151 AC22 Global Goal Cache | 真实固定 Lean 后端与当前环境复核；公开缓存视图 | 键覆盖目标、假设、声明、导入、环境、模板、公理政策、规格/目标版本及证明身份；仅 L2+ 且内核/依赖审计完整可写；命中重验，不升级 L3 | L1 拒写、真实 L2 重验、目标/依赖/环境漂移 | 未验收 |
| #151 AC22 用户控制 | 认证后的禁用、隐藏、清理和显式导入入口 | 来源、拒绝原因、recheck/stale/invalidated 状态及审计墓碑持久；不删权威 Run 状态 | 跨用户/工作区、清理与重启 | 未验收 |
| #146 阶段退出 | Job、Report、Evidence、浏览器及唯一最终门禁 | 官方 baseline 与默认预算不变；旧 Run 不迁移；源码 SHA、命令、skip 和分层能力证据分开记录 | 聚焦回归、双轴审查、完整门禁、桌面/移动 | 未验收 |

每一纵切先运行可稳定失败的公共验收，再实施并复跑。最终门禁只在冻结源码及审查修复完成后运行一次成功批次；长测试只保留一个后台进程。真实 provider、自然题、容量/SLA 和独立数学效果按实际结果记录，不能由离线或单对结果推断。F6–F8 与完整并发 #156 各按独立合同推进。
