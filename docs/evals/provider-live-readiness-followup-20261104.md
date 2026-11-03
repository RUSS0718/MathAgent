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
