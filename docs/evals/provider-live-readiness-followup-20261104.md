# Provider-live readiness follow-up — 2026-11-04

本轮使用当前提交 `1e4f98f90156754c49ff4715382fe91db068598c`，每次只运行一个 provider-live Job；输出 token 上限为 32768，每次调用逻辑上限为 900 秒，流空闲超过 30 秒停止，Run 总上限为 3600 秒。按当前授权，provider usage 只观察、不作为答案完成的阻断条件；缺失 usage 仍记录为 `UNKNOWN`。

## 当前源码三题结果

| Run | 结果 | transport | task | coverage | usage | 流时间 |
| --- | --- | --- | --- | --- | --- | --- |
| `issue127-simple-20261104-current-01` | 通过 | PASS | PASS | PASS | UNKNOWN | 首个正文 0.801 秒；最后正文 2.575 秒；完成 2.856 秒 |
| `issue127-medium-20261104-current-01` | 通过（FASTPATH；不构成自然多步证据） | PASS | PASS | PASS | UNKNOWN | 首个正文 0.986 秒；最后正文 7.825 秒；完成 8.306 秒 |
| `issue127-hard-20261104-current-01` | 已执行但未通过 | PASS | FAIL | UNKNOWN | UNKNOWN | 首个正文 1.045 秒；最后正文 221.468 秒；完成 222.099 秒；随后 Job 进入 needs review |

简单题和中等题均完成 `1/1`，独立核验确认整题审查和同文本交付绑定成立；其中中等题走 FASTPATH，不满足自然多步证据要求。#127 不要求“困难题”这一标签本身通过；readiness 未通过的直接原因是当前源码没有一条完整的自然多步 provider-live trace。困难题探针已观测 7 次成功流式调用，但 Job 在最终生成/整题审查前进入失败；该历史 artifact 的 `stop_reason` 记录为 `incomplete_or_unresolved_usage`，原因是当时停止分类先检查 usage unknown，掩盖了 Job 的失败终态。已补充分类回归，后续同类状态将优先报告 `job_failed_or_canceled`。Evidence 为 `whole_review=not_reviewed`、`binding=unbound`。这不是 provider transport 失败，也不是未派发。

困难题失败的最小事实是：

- transport：`PASS`，登记的流式 profile 与实际调用一致；
- task：`FAIL`，公共 Job 状态为 `failed`；
- coverage：`UNKNOWN`，最终样本没有完整终态证据；
- usage：`UNKNOWN`，7 次调用均无 provider token 分解；本地账本记录 `306731` charged/reserved tokens。该 UNKNOWN 不能解释 Job 为什么失败；具体失败类别仍未被安全 Evidence 保留；
- 未完成：整题审查和最终文本绑定。

旧 Run `issue127-hard-20261104-public-10` 的三项核心核验曾为 PASS，但它基于提交 `c8f9b182`，与本轮当前提交不同；因此不与本轮简单题、中等题拼接为同一 readiness 批次。

## Issue 判定

- **#124：实现和 provider 兼容证据完成，Issue 验收仍未完全通过。** 当前登记的 provider-live 流式 profile 已有精确 endpoint/payload/schema 兼容证据；兼容调用使用流式，未知 profile 拒绝派发，不在同一 Run 静默降级。usage 仍保留 UNKNOWN，因此不关闭 Issue。
- **#127：未通过。** 简单题和中等题的当前源码 Run 通过；困难题已执行但未通过，缺整题审查和文本绑定，因此整体 readiness 不成立。
- **#128：未覆盖/阻塞。** `run_pair()` 仍只做登记和 fail-closed 前置，不派发 baseline/variant 公共 Job；公共 Job 也没有 allowlisted 单组件配置接口。#127 readiness 未通过，不能启动配对结论。

本记录不宣称数学正确率提升，也不把 usage UNKNOWN 改写为 PASS。

## 2026-11-04 当前源码复验补充

本次使用提交 `79d00e16c4cb57a826a62d7380853110783c48ba` 的干净源码身份。两个批次分别使用独立服务数据目录、独立 Run 身份和 `usage_policy=observe_only`。每个批次的输出上限为 32768 tokens，Run 总墙钟上限为 900 秒；传输层仍按连续 30 秒无流活动停止。以下时间均为 UTC。

| Run | 结果 | 首个正文 | 最后正文 | 独立核验 |
| --- | --- | --- | --- | --- |
| `issue127-simple-live-20261104-01` | 完成 1/1 | `23:35:10.486352` | `23:35:12.427677` | `PASS` |
| `issue127-medium-live-20261104-01` | 15 分钟截止，0/1 | `23:38:54.044304` | `23:53:49.691346` | `FAIL` |

简单题 manifest SHA-256 为 `8c75e4269e9483158bfe875958c6897c9cb1e556b9332812981a1e01494fda3c`。核验结果为 coverage、task、transport `PASS`，usage `UNKNOWN`。简单题因此具备当前源码下的 provider-live 完成证据，但不产生数学正确率结论。

中等题 manifest SHA-256 为 `c3653a4742b141f69e3856e07eac83e7b76d564a79f358443cfffcd1ad8e07ea`。Job 的公共终态为 `failed`，错误码为 `run_deadline_exhausted`；核验结果为 task `FAIL`、coverage `UNKNOWN`、transport `PASS`、usage `FAIL`。该批次没有 30 秒流空闲证据，主要失败归类为 Run 截止导致的执行未完成；它不能证明题目本身不可解，也不能证明模型答案正确。

这次中等题仍未形成 #127 所需的自然多步 readiness。#127 保持 open。#128 继续保持 `NOT_COVERED`，因为 #127 前置条件未通过，且公共 Job 的组件配置、两臂派发和逐臂独立核验尚未接通。

## 2026-11-05 最新自然多步运行

最新 `handoffloose-02` Run 的冻结身份、逐调用限制、流时间及失败边界见 [独立脱敏记录](provider-live-natural-20261104-handoffloose-02.md)。它完成 1/2：自然多步 Job 在 2026-11-05 00:43:25（北京时间）以 `run_deadline_exhausted` 失败，Solver 留在 `STEP_VERIFY` / revision 10839；没有最终生成、整题审查或文本绑定。最后正文为 00:43:21.879，完成/finish 缺失；没有连续 30 秒无流活动停止证据。

该批次状态曾将 stop reason 记为 `incomplete_or_unresolved_usage`。当前代码已修正为：若观察到 Job 仍运行且原硬截止已过，优先记录 `hard_limit`；请求未知状态仍独立保持 UNKNOWN，不恢复、不重发。新回归测试验证此分类。此修复只校正观察器停因，不改变历史 Run，也不证明线上多步交付已修复。

#127 仍 FAIL / open；#128 仍 NOT_RUN / open，usage 仍 UNKNOWN。未发起新 provider 调用。
