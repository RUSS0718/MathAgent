# #156 完整并发 Population 工程合同

日期：2026-11-08（Asia/Shanghai）。状态：2026-11-09接续门禁06在源码 `5d80f90` 上6/6通过，离线engineering-preview；公共验收最小纵切和未完成故障组合分层记录。分层结果与未验证项见[验收记录](../evals/faithful-population-20261109.md)，不代表真实容量或数学效果退出。依据 [#156](https://github.com/RUSS0718/MathAgent/issues/156) 与 [#155 决议](https://github.com/RUSS0718/MathAgent/issues/155#issuecomment-6704660319)。本合同不扩张串行 F2，也不解除 F3/S10 门槛。

起点：集成树 `faithful-integration/Challenge-Cup-2026`，分支 `mathagent-faithful`，HEAD `0aec0ff2bd422237782c4ae82af62fe770f4387f`，工作树干净。相对总票审计基线 `b7038798cccdf5bfdc80175ebfe68dcbf12dc2d6` 的变化为 S01–S08 及交接增量，具体证据由[索引](../README.md)定位。已核对 #144、#146、#148、#149、#155、#156；F1/F2 的工程前置已满足。Lean 缺失仍为 unavailable，不接入 L2/L3，不实施干预或记忆。

## 最小共享边界

- 新 Run 显式选择 `star_population`。可信服务配置冻结 `concurrent-aprs-v1`、`population-v1`、profile、容量来源、资源和原 deadline，摘要绑定 policy；默认及旧 Run 不切换。服务容量未知时拒绝扩展，不把离线夹具容量当成 provider 实测。
- 复用唯一 SolverHarness 与现有 `advance_product` 推进循环。每条路线持久化独立快照；一个调度动作执行一个既有 WorkUnit，仍通过现有 step/verification/challenge，不增加第二套数学接受循环。
- `population_store` 在 SolverStateStore 的 SQLite 事务内派生所有权、动作、资源和路线状态。owner/epoch fencing 覆盖派发与数学提交。身份与预留先写后发，未知不隐式重发。
- `population_evidence` 核验实际采用的命题/证据版本；从已完成 Verifier 来源合并接受记录。无关全局版本变化不直接拒绝，实际前提失效则保留历史并拒绝接受。Population 总收益去重，来源与成本不去除。
- `population_runtime` 负责轮次机会、APRS 次序、受控并发和完成事件；`population_route` 仅把现有 Harness 的分支读写绑定到持久路线快照。每路线最多一个在途 WorkUnit，新路线下一轮进入；等待不是全体完成屏障。
- 待审答案冻结后停止探索，交付继续使用独立 AnswerCandidate、整题审查和 exact-text。终止后只归档/结算迟到结果；独立已审答案与请求结算分别持久化。依赖 unknown 或共享账本不完整不得交付。
- 公开投影只列受控状态、公开身份、摘要和计量，禁止分支快照、完整 prompt、证明正文或凭证外泄。F7 增量消费真实生产者；faithful-D 的并发研究仍为 not_run，不冒称 F8 完成。

## 文件所有权与纵切

| 纵切 | 所有者及接缝 | 可执行退出条件 |
| --- | --- | --- |
| C1 | 持久化工作面：新 population_store/budget、storage/run_budget 小接缝 | 跨进程竞争/接管、旧 owner 拒绝、原子准入、未知持有、发送前身份与预留 |
| C2 | 协调者：harness/controller 的小接缝、新 runtime/route、现有 run_plan 单 WorkUnit 边界 | 受控真实 HTTP 重叠、单路线单在途、固定轮次、公平与新路线下一轮、无全体屏障 |
| C3 | 证据工作面：新 population_evidence | 无关版本变化允许、实际依赖失效拒绝、事务接受/失效、收益去重/自产与采用 |
| C4 | 协调者：新 recovery/final 生命周期接缝 | 局部 unknown、全 Run 暂停、显式新身份、复用完成动作、冻结/拒绝恢复及终止竞态 |
| C5 | 产品工作面：新 product/projection/Panel 与 API/report/Evidence 小接缝 | 公共创建/恢复/取消/读取、交付与结算分离、隐私、刷新零调用、旧 Run 与幂等兼容 |

当前逐项公共入口、断言、精确测试和未完成矩阵见[接续验收映射](../evals/faithful-population-20261109.md#接续验收映射2026-11-09门禁06前)。八组公共验收逐项沿用[完整并发交接](faithful-concurrency-handoff-155.md)，通过 Job、事件、report、Evidence/replay 和真实独立进程观察。局部测试先红后绿；阶段冻结后按[工程门禁](development-gates.md)唯一运行，集中 Standards/Spec 审查。运行产物仅在忽略的 artifacts。未通过项保留 incomplete；真实 provider、容量/SLA、自然题及数学收益分层记录，工程通过不表示能力提升。
