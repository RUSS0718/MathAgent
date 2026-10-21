# R1 同模型局部动作收益路由 技术设计与验收合同

状态：proposed。日期：2026-10-21。对应 PRD：docs/prd/research-r1-prd.md。架构决策：docs/adr/0008-r1-same-model-actions.md。

## 目标与现有接入

在固定 Intern S2 和总资源条件下，把继续、局部重推、适用工具检查做成可关闭动作；先规则后学习，并在 Workbench 展示脱敏动作理由与结果范围。

仓库落点：showcase/adapters.py、showcase/live_pipeline.py、showcase/tools.py、showcase/workspace.py；可复用 tests/test_live_pipeline.py 与 tests/test_live_workspace_pipeline.py 的公开行为模式。

具体类与文件名以实施时复核为准；不得从旧路径的 mock 合同推断当前 Workspace live 已就绪。

公共预算、停止和归档规则以 [总计划](../experiments/research-program-plan.md) 与 [ADR-0007](../adr/0007-experiment-boundary-and-budget.md) 为权威入口；本文件公共内容为便于独立审查的摘要，各方向不得自行放宽。

## 数据与接口合同

DecisionState 包含 problem_group、visible_prefix_ref/hash、plan_ref、completion_state、applicable_actions、remaining_budget；ActionDecision 包含 action、policy_version、reason_code、reservation_id；公共事件只输出动作和摘要。

Run 身份、动作、证据和请求记录通过稳定引用关联。请求的完整 prompt 与模型 raw 仅在授权的受限运行材料中保存；公开事件、SSE、回放和 Git 仅保存允许字段、哈希与摘要，不保存隐藏推理。

## 执行与预算

先检查 Profile 和 feature flag，再验证动作适用性；向公共账本申请 reservation，执行一条允许动作，记录已知 usage/未知计量和结果范围，绑定新的最终产物。失败、取消、预算耗尽都停止新增调度；迟到结果不能覆盖终态。

所有模型调用为 intern-s2，固定 thinking 模式。输入重复发送、计划抽取、裁判式调用、失败重试和最终收束均入账；预算预留不等于提供方计费保证。超时保留 unresolved，不自动认定零成本。所有研究策略默认关闭。

## 测试边界

公开 Model Adapter 与 Run/Job 报告合同：捕捉动作适用性、预算、结果身份及回退；不能证明真实动作更优。

边界替身覆盖超时、429、缺失 usage、不完整响应、域外工具和取消；以预先给定的行为合同作为真值，不验证私有方法或复制实现公式。真实能力必须使用相同公开链路的 live 证据。

## 验收合同

- [ ] feature flag 关闭时，官方保护文件不变且无额外调用；research 结果标记清楚。
- [ ] 工具域外不调用工具，UNKNOWN 不被标成错误或通过。
- [ ] 取消或额度不足不启动新动作；失败与回退全部入账。
- [ ] 报告绑定最终答案及适用验证，保留有害改写和未完成样本。
- [ ] 官方字节与根 solve JSON 合同通过。
- [ ] 该方向失败时仍能返回有明确状态的部分成果，成本不丢失。
- [ ] 固定基线 SHA、配置哈希、按题分组、模型信息及所有失败进入证据清单。
- [ ] Standards 与 Spec 两轴审查完成；正、负或证据不足结论均已记录。

## 纵向切片

| Ticket | 可独立验证的交付 | Blocked by | 退出行为 |
| --- | --- | --- | --- |
| R1-01 | 可见前缀上的规则动作闭环 | S1–S5 | 从同一 Run 得到可见状态，选一个动作，产生可解释的报告；含不适用和取消案例。 |
| R1-02 | 配对动作采集和简单规则对照 | R1-01 | 按题分组采集三个动作，输出包含所有成本和失败的配对结果。 |
| R1-03 | 轻量收益路由与消融 | R1-02 | 在独立校准集定规则和模型，比较最强简单规则；保留负结果。 |
| R1-04 | 冻结验证与展示归档 | R1-03 | 冻结配置后在新题评估，导出脱敏事件、指标和工程保留判定。 |

这些是拟发布到既有 GitHub tracker 的 ticket 正文摘要，不是已创建的 Issue。每个切片完成后再走下一个有效依赖，不批量先写所有实现。

## 实验协议

假设：调用前可见的错误风险、工具适用性和剩余预算，能够预测不同干预的净收益；学习策略能够超过长度与完成状态规则。

基线：B-ready、优化过的 B-direct/B-long、B-rule、固定继续/重推/工具、同适用动作集合的随机路由。

主要指标：固定总成本下的答案正确率、错转对减对转错、有害改写率、工具适用覆盖、requests/tokens、p50/p90 时间、失败与未完成率。

消融：只剩余预算；只长度/finish_reason；去工具适用性；去成本项；打乱动作标签；对照使用相同候选动作。

先 24–40 道开发题筛查可执行性与动作差异，题量依据计量结果调整；仅对有信号方向追加重复和训练。策略、阈值与成本权重在开发/校准集确定，独立确认按原始题聚类。多动作采集成本和部署路径成本分别报告，不用同一个候选池同时选择并评估最优动作。需要的数学真值按目标层级取得，弱标签明确标记。

## 停止与工程保留

若固定策略或 B-rule 已最好，保留其实现和动作接口，关闭学习路由；若收益全来自截断补全，停止认知机制主张。统计精度不足标为 inconclusive。

性能门参考总计划的同成本质量提升或质量非劣下成本节约，并要求相应置信区间支持。未达到性能门不自动否定接口或可靠性能力的工程价值；它们可默认关闭合入 develop。

## 归档与 PR

任一完整工程切片通过共同验收后，可独立归档并 PR 到 develop，后续学习、形式化或理论 ticket 保留 planned/blocked/inconclusive；不把研究成功设为工程保留的前置条件。

每个确认批次保存脱敏 summary、manifest、环境/配置/数据版本、请求与工具成本、失败摘要、统计与消融、保留决定和复现说明。raw 在 ignored artifacts 或指定外部证据位置；分支归档提交仅存允许材料与哈希。PR 按 Summary/Evidence/Merge Danger 组织，附默认开关、回归与已撤回主张。
