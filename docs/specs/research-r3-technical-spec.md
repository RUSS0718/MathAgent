# R3 UNKNOWN 分诊与验证预算 技术设计与验收合同

状态：proposed。日期：2026-10-21。对应 PRD：docs/prd/research-r3-prd.md。架构决策：docs/adr/0010-r3-typed-verification-unknown.md。

## 目标与现有接入

先交付明确结果类型和原因感知回退，再在真实验证义务上比较翻译、求证、补充可信前提和重推的预算分配。

仓库落点：showcase/polynomial.py、showcase/verification.py、showcase/tools.py、showcase/evidence.py；形式 Adapter 作为可选 research 工具，不进入 requirements.txt 或官方入口。

具体类与文件名以实施时复核为准；不得从旧路径的 mock 合同推断当前 Workspace live 已就绪。

公共预算、停止和归档规则以 [总计划](../experiments/research-program-plan.md) 与 [ADR-0007](../adr/0007-experiment-boundary-and-budget.md) 为权威入口；本文件公共内容为便于独立审查的摘要，各方向不得自行放宽。

## 数据与接口合同

VerificationOutcome 包含 verified/refuted/unknown/skipped、reason_code、claim_hash、scope、environment_version、certificate_ref；ActionTarget 包含 retranslate/prove_more/add_verified_premise/rederive/defer。

Run 身份、动作、证据和请求记录通过稳定引用关联。请求的完整 prompt 与模型 raw 仅在授权的受限运行材料中保存；公开事件、SSE、回放和 Git 仅保存允许字段、哈希与摘要，不保存隐藏推理。

## 执行与预算

先检查 Profile 和 feature flag，再验证动作适用性；向公共账本申请 reservation，执行一条允许动作，记录已知 usage/未知计量和结果范围，绑定新的最终产物。失败、取消、预算耗尽都停止新增调度；迟到结果不能覆盖终态。

所有模型调用为 intern-s2，固定 thinking 模式。输入重复发送、计划抽取、裁判式调用、失败重试和最终收束均入账；预算预留不等于提供方计费保证。超时保留 unresolved，不自动认定零成本。所有研究策略默认关闭。

## 测试边界

公开 Tool Registry invoke 与 Verification/报告合同：捕捉结果类型、适用域、证据对象和有限回退；数学语义忠实度须用另行可信标注。

边界替身覆盖超时、429、缺失 usage、不完整响应、域外工具和取消；以预先给定的行为合同作为真值，不验证私有方法或复制实现公式。真实能力必须使用相同公开链路的 live 证据。

## 验收合同

- [ ] 域外、超时、缺依赖和反例有不同类型；UNKNOWN 不被当成假命题。
- [ ] polynomial 候选有效和覆盖 unknown 同时保留。
- [ ] 每条形式证据绑定具体命题与环境；不允许空洞证明或未审查前提。
- [ ] 有限重试耗尽后进入明确待复核状态，原解答不丢失。
- [ ] 官方字节与根 solve JSON 合同通过。
- [ ] 该方向失败时仍能返回有明确状态的部分成果，成本不丢失。
- [ ] 固定基线 SHA、配置哈希、按题分组、模型信息及所有失败进入证据清单。
- [ ] Standards 与 Spec 两轴审查完成；正、负或证据不足结论均已记录。

## 纵向切片

| Ticket | 可独立验证的交付 | Blocked by | 退出行为 |
| --- | --- | --- | --- |
| R3-01 | 验证分型和用户可理解的回退 | S2–S5 | 一个工具题与一个域外题都产生正确范围的报告。 |
| R3-02 | 可信命题上的预算干预 spike | R3-01 | 固定形式环境，对相同 UNKNOWN 比较翻译或求证追加预算。 |
| R3-03 | 原因规则与学习分诊 | R3-02 | 只在可恢复失败上比较成本和可信证据，保留所有域外案例。 |
| R3-04 | 端到端复核和归档 | R3-01 的工程出口；研究验证需 R3-03 | 工程出口确认分型、回退与报告合同；研究出口另行确认最终数学效果与语义忠实。 |

这些是拟发布到既有 GitHub tracker 的 ticket 正文摘要，不是已创建的 Issue。每个切片完成后再走下一个有效依赖，不批量先写所有实现。

## 实验协议

假设：部分 UNKNOWN 的原因可以预测下一次预算干预的可信收益，分诊能够优于固定错误码规则。

基线：不形式化流程、固定翻译/证明预算、按错误码固定分流、只加 formalizer、只加 prover、平均或随机分配。

主要指标：UNKNOWN 转可信证据率、每单位成本的可信证书、语义不忠实假通过率、最终解题正确率、工具域外覆盖、回退和失败分布。

消融：合并所有 UNKNOWN；去日志原因；去语义审查；去剩余预算；忽略编译和初始化开销的结果仅作成本偏差分析。

先 24–40 道开发题筛查可执行性与动作差异，题量依据计量结果调整；仅对有信号方向追加重复和训练。策略、阈值与成本权重在开发/校准集确定，独立确认按原始题聚类。多动作采集成本和部署路径成本分别报告，不用同一个候选池同时选择并评估最优动作。需要的数学真值按目标层级取得，弱标签明确标记。

## 停止与工程保留

如果大多数 UNKNOWN 无法被有限预算恢复，保留错误分型和规则回退；如果翻译成本吞掉收益，限制适用域；仅提高编译率不作为数学可靠性成果。

性能门参考总计划的同成本质量提升或质量非劣下成本节约，并要求相应置信区间支持。未达到性能门不自动否定接口或可靠性能力的工程价值；它们可默认关闭合入 develop。

## 归档与 PR

任一完整工程切片通过共同验收后，可独立归档并 PR 到 develop，后续学习、形式化或理论 ticket 保留 planned/blocked/inconclusive；不把研究成功设为工程保留的前置条件。

每个确认批次保存脱敏 summary、manifest、环境/配置/数据版本、请求与工具成本、失败摘要、统计与消融、保留决定和复现说明。raw 在 ignored artifacts 或指定外部证据位置；分支归档提交仅存允许材料与哈希。PR 按 Summary/Evidence/Merge Danger 组织，附默认开关、回归与已撤回主张。
