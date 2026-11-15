# #185 按需求解阶段记录

2026-11-15；起点 `d4bed8a`；产品源码 `1acec35`，必要离线退出检查待执行。
#185、#183、#168 仍开放；目前缺少深度案例真实正确交付及持久化故障根因闭环。
要求和未闭合边界见 [策略合同](../engineering/adaptive-solving-185-contract.md)。

## 当前实现

- 显式 `adaptive_solving` 配置，省略保持原策略；直接候选不固定 polish，独立整题审查保留。
- 具体数学异议一次局部修正，每份候选独立 call/event 身份；拒绝消费标记覆盖结论提交前后两个恢复窗口。
- Planner 接收原失败候选、真实异议和未解决义务，并在已有请求中审查分解质量。
- 串行搜索状态区分完整规格、有效已证内容和实际工具输入/输出；排除重复身份、猜想、心跳和重复回执。
- 规格依赖语义错误接入既有一次协议修复；unknown 不自动重发。修复普通 solve 省略 metadata 时的 AttributeError。
- 高预算示例和公开策略摘要已接线；并发/形式化仍按既有能力准入。
- `45be9ef` 明确 Reasoner 检查点工具字段的合法位置及一次修复提示，原 schema 不放宽。
- `1acec35` 新 Run 冻结 `adaptive-resources-v1`；串行派发为检查/最终生成及一次共享
  协议修复留出模型、HTTP、本地 token 和时间份额。实际 HTTP 输入仍在账本准入复核；
  既有 finalization 双槽和 Population 预留不重复扣减。旧 Run 不回填，根 deadline 不重置。
- `d181536` 仅补充异常链中 SQLite 安全错误码诊断，没有冒称修复数据库根因。

## 已有必要离线证据

证据目录 `artifacts/issue-185/`（忽略产物）。`run_unittest_report.py` 通过声明数量执行：

| 接缝 | 证据 | 结果 |
| --- | --- | --- |
| 直接候选 / 一次修正 | direct-red-02、direct-green-02、boundaries | 红后绿；早期命令参数错误和夹具问题不算有效红证据 |
| 受影响 intake/config/final binding/budget | affected | 35 项通过 |
| 原串行路线边界 | routes | 19 项通过 |
| 已完成审查恢复 | recovery-red-02、recovery-green | 原失败到修正后通过；另覆盖已提交拒绝的恢复窗口 |
| 省略可选 metadata | metadata-red、metadata-green | 实际 AttributeError 红后绿 |
| 公开策略字段及只读刷新 | projection-red、projection-green | 红后绿；零刷新派发 |
| 猜想重复身份 / 不同输入同输出 | context-red、context-green | 2 项先失败后通过 |
| 真实发现的悬空规格依赖 | intake-red、intake-green、public-final | 公共 Job 红后绿；最终 3 项含未知修复结果不重发 |
| 检查点工具位置 | checkpoint-tool-red/green、checkpoint-regression | 2 项红后绿，32 项相关回归通过 |
| 共享账本与直接候选收尾预留 | reserve-red、reserve-policy | 派发反例红后绿；最终 21 项含原按需策略、公共 Job 和资源边界通过 |
| 修复不再预留自身的下一次修复 | reserve-repair-red、reserve-policy | 空响应公共 Job 先失败，再以原 4 次总额度完成修复及独立检查 |
| 异常链诊断脱敏 | diagnostic-red/green | 1 项红后绿；不是 SQLite 原故障复现或修复证明 |

双轴静态审查发现的恢复及搜索指纹缺陷已逐项修复并送复查；不算独立执行测试。
`gate-01` 在 `8064136` 快速检查通过后取消，完整离线阶段未完成，不计通过。
当前 `offline-exit-01` 只计划后端快速、完整离线、发布三阶段，遵从用户“只做必要离线测试”。
前端未改，本轮不重新安装依赖或联网 audit；三阶段结果不冒称标准六阶段门禁。

## 真实运行

`live-01` 首题 `run_035226c8ad49f22abe80610d44b9b512`：真实答案 5，独立常识核对一致；
整题 accepted、same_artifact，adaptive corrections=0，4 HTTP/模型调用，0 工具。
包含机器证明权限澄清前后两次规格处理，后续 Explore→整题检查，无固定 polish/Planner。
原观察器把 waiting_input 当结束，保留原 waiting 记录；按用户输入的普通证明意图回答 no，
继续原 Job，原预算/截止不变。恢复脚本第一次因已存在目录退出，未派发新调用。
本地计账 178964，provider usage 全部未知、0 unresolved，不能称实际消耗 178964 token。
根墙钟约333秒包含本地观察器停止期间，不当作模型计算耗时。

第二题 `run_5f013baf79fe7ff8c215b1cfe7dcf799`：1 次完成请求后 problem_intake_invalid_spec，
具体为 prerequisite_ids 引用未声明辅助目标；没有求解或答案。
保留失败，不重发旧 Job；触发本次协议修复接线。原第三题未派发。

`live-02` 在 `8064136` 上使用原计划的中等方程题（平方需排除增根，独立答案 x=3），
Job `run_c0f0883e2710cb78494df87c7b7d6f2e`：9 次模型/HTTP、1 工具、192.475 秒，
本地计账434645，provider usage 均未知。整题拒绝自然触发一次修正，修正不能形成完整
候选后进入 Planner/Reasoner；随后 Researcher 流中读取 Solver 状态出现封装的 SQLite
OperationalError，Job failed/job_execution_failed，没有最终答案。1 个远端未决保留，
不自动重发。预算未耗尽；不能把工程故障归因于数学难度或认作正确交付。
离线有限回放经过9个角色、766次只读观察，没有复现同一数据库故障，后续另因协议失败
退出；这不是修复证据。保留现场并补安全错误码，不加无依据的数据库重试。

`live-03` 在 `d181536` 上仅运行此前未派发的四次式参数分类题，
Job `run_b80c1d02818f7d38e2cae72ee3c65f8e`：13 次模型/HTTP、2 工具（5.171秒）、
2368.859 秒，本地计账834031，provider usage 均未知，0 未决，根预算未耗尽。
Explore 未形成完整候选后自然规划，出现 Reasoner 检查点、局部检查及 Researcher。
最后两次 Reasoner 完整响应把 tool_request/tool_evidence_refs 直接挂在 checkpoint；
原 schema 拒绝，一次格式修复仍错，终态 protocol_failure_unrepaired。没有完整交付，
已满足部分义务不能当成整题数学成功。两次长响应约707.706/641.516秒均完整返回，
只能证明活动流可超过旧360秒，不证明难题求解成功。该数据库错误在本例未出现。
工具位置提示已用离线反例修复，修后没有追加 provider 验收。

三次运行均使用 intern-s2、adaptive-solving-v1；live-02/03 显式根额度为
96模型/96HTTP/24工具/4194304本地计账token/7200秒，配置 SHA256
`6c23cb3ed570067bb59bfae7cc2d7364022d63d2db28f141d08c4d4afe964996`。
逐次源码与输入见各 live 目录 identity、receipt、final、report、refresh；参考解析仅存
`artifacts/issue-185/independent-reference.md`，没有发送给模型。未强制预制计划或模式。

## 最小验收映射

| #185 要求 | 公共入口 / 断言 | 证据 | 结果 |
| --- | --- | --- | --- |
| 缺口及最小策略 | 显式配置、策略版本、原根身份 | 合同、配置测试、21项聚焦 | 开发接线通过 |
| 简单/中等/深度真实案例 | Job 独立检查、自然升级、真实正确交付 | live-01/02/03 | 简单正确；中等升级可达；深度正确交付未满足 |
| 身份、动作及独立核对 | identity/receipt/report/refresh 与独立解析 | 各 live 目录 | 已记录；后两例无最终答案 |
| 故障分类、重复状态及不重发 | 公共 Job/恢复、search_context、历史规格保护 | 既有 d4bed8a 30项与本次反例 | 离线通过；SQLite 根因未闭合 |
| 高预算根约束及修复收尾 | 同账本准入、原 deadline、资源策略仅新 Run | reserve-policy 21项，live预算报告 | 离线接线通过；修后真实资源效果未覆盖 |
| 正确交付及可测成本 | 真实答案与调用/工具/本地估计分开记录 | live-01/02/03 | 不足以声称总体效率或正确率提升 |
| baseline及阶段退出 | 字节稳定；冻结源码后必要离线检查 | offline-exit-01 待执行 | 待验证；标准六阶段门禁未执行 |

继续条件：先复用当前证据，不重复启动旧 Job；unknown 零自动重发。
用户限制期间不追加真实模型测试；深度正确交付与 SQLite 根因缺口保留，不能关闭 #185。
旧 unknown、deadline 和历史失败均不改写；不声称正确率或总体效率提升。
