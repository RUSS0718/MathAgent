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
