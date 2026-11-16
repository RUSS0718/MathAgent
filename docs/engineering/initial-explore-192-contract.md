# #192 首次探索容量合同

2026-11-17；实施基点 adc01500a6bdfae8c76bdcd8ed6f0871663de6b0。
承接 #189/#190/#191；只影响显式 Showcase 新 Run，2048 是工程假设，
不是 provider token 测量或性能结论。自然 S/D/U 由集成后主控唯一运行。

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
4. 有效 cap 贯通原 reservation、stream/nonstream payload、Attempt、
   serialized 估计、fingerprint/profile。非流证据明确为 documented，
   不冒用旧32768 stream profile，不宣称新 cap 已 provider-live 验证。
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
