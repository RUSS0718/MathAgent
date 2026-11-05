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

## 2026-11-05 readiness-01 追加结果

新增冻结 Run 的完整身份和阶段证据见 [readiness-01 运行记录](provider-live-natural-20261105-readiness-01.md)。Run 使用源码 `2b42070fbd64145d761ceede68abe7113bdbe557`、manifest SHA-256 `d1a08223e364f4032dffeecf7c0253fe4e8f8640c7c537ab9c1998d5097ff3e9`，登记 2 题并完成 1/2。自然多步 trace 形成 4 步计划，完成第一步且有 3 次成功工具调用；第二步核验返回矛盾的 `ACCEPT / PARTIAL / PASS`，Job 以 `star_needs_review` 失败。末次 verifier 正文首 token 04:13:56.561、末 token 04:16:18.332（北京时间），流在 04:16:19.145 正常完成；这不是传输失败或数学正确性判定。缺最终答案、整题审查与文本绑定。

离线审查后修复了矛盾 verdict 的错误分类和已确认终态失败的 intent 清理，并修复三项 #128 配对证据路径问题。103 项聚焦测试通过；这不证明 provider-live 重新运行通过。旧 Run 报告的 coverage UNKNOWN 是 intent 分类问题；usage 继续 UNKNOWN，不阻断答案完成也不标 PASS。

#127 保持 **FAIL / open**；#128 保持 **NOT_RUN / open**。新 provider-live Run 必须使用修复后新的源码身份、manifest 和 Run ID。未改变官方 baseline、预算或 best-effort 开关，不声称数学能力提升。

### readiness-02 前的复核补充（2026-11-05）

对 readiness-01 后的修复工作树再次独立审查，发现最后一题提交后删除 dispatch intent 的崩溃窗口，以及低层 pair 来源校验可被覆写 port/adapter/client 方法绕过的问题；另补足计数与已完成连续前缀不一致时不得清理 intent 的约束。逐项回归先复现缺陷后验证修复。

当前定向聚焦 113 项测试、快速合同门禁、Ruff、`git diff --check` 均通过，官方 baseline 文件和 `user_agent.py`/`implementations/` 无差异。上述证据只证明离线工程边界；readiness-02 还未派发。readiness-01 原记录不修改，usage 继续 `UNKNOWN` 且按本轮授权不阻断答案完成、不标 PASS；#127/#128 Issue 状态待新 Run 及配对证据更新。

### readiness-02 运行结果（2026-11-05）

前述“readiness-02 还未派发”记录的是本追加编写时的状态，现由新的冻结 Run 结果取代。完整报告见 [readiness-02 独立记录](provider-live-natural-20261105-readiness-02.md)。

该 Run 完成 `1/2`。简单题成功并通过整题审查及同文本绑定。自然多步题形成 5 步计划，报告 3 步、接受 2 步并调用工具 2 次，随后 Meta 因合法业务响应附带流式 `usage` 字段而产生 `meta_invalid`；Job 以 `star_needs_review` 失败。没有最终答案、整题审查或最终绑定。首个正文 token 为 07:49:16.763989，北京时间；最后正文 token 为 08:28:55.858159，流于 08:28:58.230553 完成。失败不是 30 秒流空闲、900 秒调用或 3600 秒 Run 截止。

两个 Run 的本地 charged/reserved 分别为 `119,709` 和 `1,985,185`，各低于 `2,097,152` 单 Run 上限。批次总计 `2,104,894` 低于批次上限 `4,194,304`；先前将批次数与单 Run 上限相比的预算疑点已撤销。Provider usage 仍为 `UNKNOWN`。

离线复现确认 Meta 解析器会拒绝完整业务响应中的传输 `usage` 附加字段。当前修复将把该容错限定到调用审计标记为 stream 的响应，并保留非流式和未登记业务字段的拒绝行为。独立 verifier 的运行模式映射、未完成路径分类、角色 plan/attempt 归属和回执消费核验也正在修复。旧 Run 不恢复、不重发；#127 为已执行未通过 `FAIL / open`，#128 为 `NOT_RUN / open`。

## 2026-11-05 readiness-05 执行观察器异常

新批次已实际派发，runner 完成计数为 1/2。简单题已交付并审查、绑定；自然多步服务端 Job 仍在推进，但 runner 因状态文件原子替换 WinError 5 退出，服务目录也沿用了 readiness-04。详细事实、冻结身份与证据限制见 [readiness-05 记录](provider-live-natural-20261105-readiness-05.md)。临时读锁解释尚待复现，不把观察器退出说成模型错误。旧 Run 不恢复、不重发；#127 readiness 未通过，#128 两臂 NOT_RUN，usage UNKNOWN。

## 2026-11-05 readiness-06 已派发

状态写入WinError 5的有界重试修复及回归通过后，05因确认服务源码身份不匹配被取消，等待最后在途调用结束。06使用独立8127服务、数据目录及启动source/script/PID核对后串行派发；当前简单题成功，多步自然进入Planner，完成1/2，尚未完成整题交付。见 [06冻结与初始运行证据](provider-live-natural-20261105-readiness-06.md)。不拼接05结果；#127未验收/open，#128两臂NOT_RUN/open，usage UNKNOWN。

## readiness-06 最终结果

06已执行未通过，完成1/2。自然多步30次模型/HTTP、2次工具后在第二步以challenge_meta_limit_reached结束；Meta出网和交接成功，最终没有最终生成或整题审查，不是硬预算/900秒/30秒流空闲停止或数学正确性判定。首末正文及独立FAIL证据见 [06最终记录](provider-live-natural-20261105-readiness-06.md)。终态对照又发现并修复独立verifier误滤attempt_index=0，另校正RB03过时调用次数预期；43项相关回归通过，旧Run不升级。#127保持open；#128两臂NOT_RUN/open。

## 新授权修复循环第1轮

07失败根因为工具参数非法、回执丢失错误码后重复请求；已修安全错误反馈与纠正提示，原次数限制不变。08已真实派发，简单题成功、多步运行中，尚未PASS。见 [08记录](provider-live-natural-20261105-readiness-08.md) 和 [循环规则](provider-live-repair-cycle-20261105.md)。每10分钟监控，超过5轮仍有新错误时先做小型简化重构；#128仍NOT_RUN。
