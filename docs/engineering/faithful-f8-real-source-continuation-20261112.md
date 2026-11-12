# F8 修复后源码接续条款

日期：2026-11-12。状态：frozen；版本 `faithful-f8-real-v1.3`。补充 [v1.2](faithful-f8-real-recovery-20261112.md)。这是观察故障后的修订，不能称整轮事前预注册。Standards（Fermat）与Spec（Russell）均确认本条款无阻塞，允许冻结；报告出口与接续glue须另行验收。

## 实际故障及修复

第七个首次主槽 B/AIME2025/aimeI5 共完成26次HTTP，其中18次Meta返回非法 `CONTINUE + trace_back_to=1`；产品正确拒绝，但保留META_DECIDE阶段并重复派发，最终failed/needs_review。原Run与26次调用全部保留，不能重派该槽或把其改为通过。#157 登记F8-R19。

最小修复只让已取得响应但非法的Meta决定持久终止为 `partial_aborted/invalid_meta_decision`；传输unknown沿用原恢复，不新增调用、预算、求解或验证能力。Standards（Fermat）与Spec（Russell）均已解除产品差异阻塞。先红1项、后绿1项，聚焦23项通过；身份/恢复50项中49通过、1项因缺少独立验证Docker image ID跳过。证据：`artifacts/faithful-f8-meta-fix-20261112/`。阶段门禁尚待运行，不把聚焦检查当最终门禁。

## 新源码实验合同

产品修改提交并通过最终门禁后，新manifest冻结实际源码SHA、内容hash及门禁来源，并绑定全部父manifest和原始结果hash。原始七槽不可修改、删除、插补或重派；仅继续原序列63个未派发主槽。原98登记分母及70个A/B/C/D/G必需主槽不变，E与F条件沿用原合同，原绝对截止与每Run预算不延长，参考、输入、prompt与工具身份保持原封存值。

源码版本分层报告登记、完成、失败、未知和数学判定；跨版本的组间比较必须标记 `not_comparable`，不把修复前后的正确率合并解释为机制收益。可以报告98槽的完成覆盖，但不能用它替代同版本可判定子集。G只复用同源码C的同session；已完成C对应G不重新派发。

已知完成的非法Meta响应按v1.2全部HTTP、来源、模型、工具、预算和当前终态绑定规则归因后，可记failed并继续下一未派发槽；必须额外绑定当前 `result_reason=invalid_meta_decision` 与本次 `meta_invalid` 事件。unknown、本地processing失败、隔离/绑定/预算异常继续硬停止，不泛化失败白名单。第七槽旧无进展失败单独归因R19，不放宽其为数学失败。

## 退出条件

新接续glue及唯一性/版本/拒绝unknown验收经双轴审查后方可派发。最终门禁期间不修改源码、测试、配置、脚本或文档。其余退出条件沿用v1/v1.1/v1.2：70主槽首次终态、合格F双臂、28槽隔离辅助审查、G解释评价、分层报告和完整性包；必需not_run尚存时#157保持开放。官方重评分unavailable，真人L3 not_run，provider usage缺失observe_only，均不伪造。

## 重启及修复后的接续 v1.4

状态：frozen；版本`faithful-f8-real-v1.4`。2026-11-12 Standards（Galileo）与Spec（Boyle）均确认本节合同无阻塞，可冻结；这不批准尚未实现的manifest、历史核验器或接续glue，也不代替产品修复的复查。上述v1.3历史冻结不变。来源为[#157](https://github.com/RUSS0718/MathAgent/issues/157)、[#158](https://github.com/RUSS0718/MathAgent/issues/158)、[#159](https://github.com/RUSS0718/MathAgent/issues/159)。这是观察故障后的修订，不称原始预注册。用户2026-11-12已授权修复后继续真实实验，不延长原资源预算或截止。

保留41份首次主槽：1 completed、39 failed、1 unknown；原98登记、70必需和28辅助抽样槽不变。只有`length-manifest.json`原序列去掉已启动B/C/G PutnamB1后的29个槽可以新派发；新manifest必须证明这些槽无intent、无dispatch、无结果，唯一性与原次序不变。E原题域unsupported及F真实条件保持，G仅复用本接续中同源码C的同session；D按已冻结的真实Population配置执行，容量探测不是数学或SLA结论。

重启单例仅为G/PutnamB1 Run `run_03ad176df0e535dda3a5ed466442b81b`。原始DB/WAL/raw快照、恢复副本及公开Job/Report/Evidence/result均按封存hash核对；现有原生恢复只作用于副本且未发网络请求。该Run仍unknown/unresolved，Planner远端结果未知，不重发、不resume、不改成failed/completed或数学incorrect。允许将这一已诊断的中断记为归档处置并继续未派发槽；未来unknown、length、OOM、processing、绑定/清理/预算异常仍硬停止，不能泛化本单例处置。

历史核验与新派发分离：原R07已冻结合同、companion、依赖模块hash、父manifest、原源码SHA及其真实门禁、输入/配置、原DB/账本/调用谱系和原截止全部保留。通过独立版本的只读核验器复核历史快照，允许当前产品源码不同；不修改旧绑定函数、冻结对象、失败记录或旧门禁，不伪造当前source_identity为旧版本。历史核验器必须核实原Git版本的实际源码成员与原门禁source manifest一致，复用原语义断言，并拒绝缺失、篡改、未知角色/工具或不同Run。重启单例的原草稿不冒称已冻结；其相同事实锚点纳入本节及新companion，完整双轴通过后才形成正式处置。

新派发必须有本次实际源码SHA、runtime hash及唯一成功的完整阶段门禁，保留新源码层与旧源码层的not_comparable边界。每次prepare/run及实际新Job派发均核对完整当前源码身份、配置、prompt、模型/provider、输入/参考、工具镜像与环境、预算和父manifest链；原绝对截止`1794813953.698563`（2026-11-16 15:25:53.698563 +08:00）不延长。凭证只使用已授权私密环境，不写入manifest或证据包。固定模型与调用条件沿用真实批次；缺失usage仍observe_only，不能抹掉已知的远端unknown。

最小接缝验收包括：41/29/98/70守恒、原序列唯一性、不同源码/配置/截止拒绝、原R07语义与所有绑定字节漂移拒绝、精确重启unknown处置及未来unknown拒绝、原DB/WAL不变、C到F真实暂停和同源双臂/父恢复、实际报告来源与unknown分母，以及#159空答案pass/fail拒绝而unresolved保留。不得用fixture freeze或mock结果替代正式封存、真实工具、provider-live或数学判断。先通过失败/成功检查与双轴复查，再冻结源码并运行门禁；门禁期间不改源码、测试、配置、脚本或文档。

退出沿用原合同：29剩余主槽的首次记录、14个C实际F筛查及适用双臂、固定28槽R1/R2独立代理与R3核对、G五维解释、来源分层报告及独立最终包校验。primary_settled仅表示证据归档，单列disposed_unknown，原unknown继续保留在总登记与未知计数中；空答案只能unresolved。真人L3 not_run、官方重评分unavailable，参考答案正确率不得称官方分数。必需not_run或应执行F/审查/包仍缺失时#157不关闭。
