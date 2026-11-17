# #192 首次探索容量合同

2026-11-17；实施基点 adc01500a6bdfae8c76bdcd8ed6f0871663de6b0。
承接 #189/#190/#191；只影响显式 Showcase 新 Run，2048 是工程假设，
不是 provider token 测量或性能结论。自然 S2/D/U 已由主控唯一运行，见下述退出边界。

## 当前状态与第4条澄清

退出记录832b33f已推送，#192按受控工程范围关闭并重读确认；S2 支持自然 AC1，U 自然 AC2 **not_triggered**、最终 failed 不改判。原 Issue AC2 未要求必须自然，本地首次完成记 not_triggered 的规则保留；谱系/测量见[本票交接](initial-explore-192-handoff.md)，证据与跨票决定见[#189 映射](../evals/dependency-routing-189-20261117.md)。

第4条“原 reservation”指根调用预算预留，“profile”指 transport 能力匹配及请求 fingerprint。有效请求 cap 必须贯通原预算、HTTP payload、Attempt、serialized 估计及 fingerprint；不能以旧输出 cap 的 stream profile 授权新 cap。非流证据标 documented，未标定 profile 不冒充硬容量保证。

ContextPack 是独立的冻结 context envelope，允许 `max(frozen_policy.output_reserve_tokens, payload.max_tokens)` 的保守 floor 大于有效输出 cap；它不是 RunBudget 预留或实际输出量，无须降为2048。S2 的32768保守预留与2048实际请求可合法共存；uncalibrated/input_cap_tokens=null 仍不能提供硬容量保证。这是条款澄清，不删约束、不缩验收，也不修改冻结策略或根预算。

上述区分经现有源码和测试断言只读核对，未发现该差异构成实质缺陷；transport 完整逐键沿既有受控证据，自然 S2 仅有限观测，不升级为新 provider-live profile 认证。

## 冻结入口与生产者合同

- 可信 faithful JSON：`initial_explore_policy_version: "initial-explore-v1-2048"`。
- 服务配置：`SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION`；Pipeline 同名小写参数。
- Harness config：`initial_explore_policy_version`；新 Run state：
  `initial_explore_policy = {"version": "initial-explore-v1-2048"}`。
- 依赖 #190 routing policy 及其严格串行自主入口。关闭时键缺席；旧 Run
  不回填，恢复只重建本冻结键，其余 config hash 严格校验。未知版本拒绝。
- 请求级可选 `max_output_tokens=2048`，首次及其工具/正常有限协议修复继承；
  显式 `transport_override="nonstream"` 只作用于单请求，不修改共享实例。
- 公开原因白名单由本票生产：`initial_explore_output_limit`、
  `initial_explore_incomplete`；沿既有原因字段，不新增通用 DTO。
  #193 负责普通投影/文案，理由不代表 Planner 已派发。

## 行为与验收

1. 无显式依赖最多首次一个语义尝试，完整候选独立整题审查；无候选、
   NEED_PLAN/PARTIALLY_SOLVED/UNKNOWN 评估进 PLAN。工具/repair 是独立
   Attempt，不增加语义轮次；沿原次数、预算、deadline。
2. 已知 length 进 PLAN，不 repair；正常协议失败最多沿既有一次修复，
   耗尽转 PLAN。远端 unknown 保持原待审，零自动重发/Planner/fallback。
3. whole review 具体数学异议最多一次修正，取原 Run 基础 cap，
   不重新获得首次身份；其他角色与根预算不变。
4. 有效 cap 贯通原根调用预算 reservation、stream/nonstream payload、Attempt、
   serialized 估计及 transport fingerprint/profile，含义按上节澄清。非流证据明确为 documented，
   不冒用旧32768 stream profile，不把自然有限观测宣称为新 provider-live profile 认证。
5. partial findings 沿 #190 来源保留 unverified；截断 JSON 不补造候选，
   来源未知如实 unknown，不升级已证账本或重建旧来源。

公共验收接缝已由用户授权：Job/Run/config/recovery、provider HTTP outbound、
Attempt/ledger 投影。先一个红例再最小实现，受控检查流/非流容量与账本、
简单直解/已知未完成规划/修复工具/修正/unknown、旧新 Run 恢复及 hash。
聚焦回归，不运行全仓、provider/live/browser；受控通过不代表数学提升。
S/D 不能覆盖 U 路径；U 首次完成或自然 Intake 有依赖记 not_triggered，
不追加诱导。参考解在仓库外，禁止进入模型消息。

文件只按失败见证修改必要接缝；普通投影/前端归 #193。验收记录另存实际
源码 SHA、命令、count、失败、skip 与证据位置；本合同不是通过声明。
