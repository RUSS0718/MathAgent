# #127 readiness-28 run record

2026-11-06 北京时间 04:39:57 启动 readiness-28，04:57:23 终止。简单题成功；自然多步只完成 1/7 步，Job 以 `star_needs_review` 失败。readiness-27 结果保持独立。

## 身份与配置

- Run：`issue127-natural-20261105-readiness-28-run01`
- Manifest SHA-256：`f266fdb3921511da741072fc110dfe78d484b313c1681eacb8962ae2b7b15d7a`
- 源码 revision/SHA-256：`13a3ccc444b2cfe5dd824483e4674bbe4baed760` / `36e33434835b8338488f68248f876d3d8466fe086732062299042f8e4b261b94`
- Server SHA-256：`3ad72fa5252b5ab3fa831666218bd6577cc8a68b94874069eab2b080c0c2e952`
- 完整分母为 `simple`、`octagon-colorings`。输入 SHA-256 分别是 `389ac0685cb60be93ca7d309ad245b9455da5e44159c65ae5d12c5c897c56dde` 和 `395f5e9269c997fcc111fcd86b4a35bda59f6f63e15160bb41d63fbfc6f0be94`。
- Applied config 与 manifest 一致：`intern-s2`、thinking=false、temperature=0.2、输出 32768、stream_first、单调用 1200 秒、30 秒无流、每题 Run 14400 秒、128 model/HTTP、32 tools、16777216 本地 token 预留，best-effort 关闭。
- 服务 PID 22292 于 04:39:15 启动。Runner PID 9656 于 04:39:57 启动，于 04:57:23 退出，exit code 0。终态后按 PID、创建时间、脚本路径和 8143 监听归属核对并停止服务。
- readiness-27 的结果与任何未决请求均未恢复或重发。

## 结果与直接停因

简单题 Job `run_a13fba4730451e37df401a53de2e8445` 成功，Solver 为 `completed_llm_reviewed`，最终文本非空；3 model/HTTP、0 tools，121094 本地 token 预留，6.856 秒。

自然多步 Job `run_09b4885b65687224f18fc0a58e53d366` 失败，Solver 为 `partial_aborted`，停在 `STEP_VERIFY`。计划有 7 步，只完成 1 步。最后业务事件为 `challenge_recorded`。Verifier 输出有效 `CHALLENGE`，`goal_gate=PARTIAL`、`logic_gate=FAIL`，原因是 `verifier_tool_request_unfulfilled`。13 次模型/HTTP流均已完成；本次没有 TLS、连接或调用 deadline 停止。

最后 Verifier 流于 04:52:47.578 派发，04:52:52.915 出现首正文，04:57:20.831 收到末正文，04:57:21.692 完成；正文 4426 bytes、431 个事件。

逐调用流时间如下。时间为北京时间 2026-11-06。provider finish_reason 缺失记为 `null`。

| # | Call ID | Role | 状态/错误 | 派发 | 首正文 | 末正文 | Completion | finish_reason | 正文/事件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `solver_call_e7970946dcec7dfc80a450c68306fe49` | explore | completed | 04:40:10 | 04:40:11 | 04:40:12 | 04:40:12 | null | 123 B / 13 |
| 2 | `solver_call_812c156b644562df3dfddc6f46d3c1e7` | planner | completed | 04:40:12 | 04:40:13 | 04:40:28 | 04:40:28 | null | 2595 B / 220 |
| 3 | `solver_call_b98b63527b47d42a396b5fbb6bfdb0ba` | reasoner | completed | 04:40:29 | 04:40:30 | 04:40:48 | 04:40:49 | null | 1826 B / 167 |
| 4 | `solver_call_d6156d2dd29c78f7eb6b4211f0c71dd8` | step_verifier | protocol_failed (invalid_json) | 04:40:51 | 04:40:52 | 04:41:30 | 04:41:30 | stop | 2662 B / 262 |
| 5 | `solver_call_388ededb54f42338edd9ed22bc488652` | step_verifier | completed | 04:41:31 | 04:41:32 | 04:42:14 | 04:42:14 | null | 2663 B / 227 |
| 6 | `solver_call_c1aec42c726d569fd8ac7bf81a81419f` | step_verifier | completed | 04:42:17 | 04:42:19 | 04:43:11 | 04:43:11 | null | 2672 B / 226 |
| 7 | `solver_call_ae0b686f2a9146f43c211f24ac24e74b` | step_verifier | completed | 04:43:14 | 04:43:16 | 04:44:03 | 04:44:04 | null | 1856 B / 170 |
| 8 | `solver_call_79294c45af9ca8dce4c028586db71c05` | researcher | completed | 04:44:05 | 04:44:06 | 04:44:30 | 04:44:30 | null | 958 B / 84 |
| 9 | `solver_call_b018a27d2df3e58c4f2d21c2fe8d2a2f` | reasoner | protocol_failed (invalid_json) | 04:44:31 | 04:44:33 | 04:45:48 | 04:45:49 | stop | 2392 B / 219 |
| 10 | `solver_call_5073ed963bbcbe3b6dec53b3ce1e3a7b` | reasoner | completed | 04:45:50 | 04:45:51 | 04:47:28 | 04:47:28 | null | 2825 B / 249 |
| 11 | `solver_call_2abc745d041fa995b3767bbbd11ad996` | step_verifier | completed | 04:47:32 | 04:47:35 | 04:50:04 | 04:50:05 | null | 3453 B / 330 |
| 12 | `solver_call_59e7f5922ba0034348388d5296fb3947` | step_verifier | completed | 04:50:08 | 04:50:13 | 04:52:43 | 04:52:44 | null | 3220 B / 284 |
| 13 | `solver_call_d83b5970fa49216143b3310d63979043` | step_verifier | completed | 04:52:47 | 04:52:52 | 04:57:20 | 04:57:21 | null | 4426 B / 431 |

## 工具回执与停因分类

6 个工具回执均为 `exit_code=0`、`unknown_outcome=false`、`cleanup_verified=true`，stderr 均为空。部分请求只打印公式字符串；其他请求在三项颜色函数或人为构造的相等关系集合上运行有限计算。该集合不是本题八边形 proper coloring 在所审查群元素下的固定点集合。有限测试输出 `formula holds with last term: False`，未验证模型声称的容斥公式。工具执行成功并不意味着请求已完成验证。

直接停因是审查请求未获有效工具证据后产生的 CHALLENGE。现有证据定位为模型构造的验证请求与证据不适用于目标，不支持新增工程修复。没有隔离依赖缺失、资源不足、预算拒绝、未知工具结果或传输中断的证据。未扩大业务合同、挑战上限或重试次数。

两次 `invalid_json` 调用均以 finish_reason `stop` 结束，后续新身份格式修复调用完成。格式修复接缝工作正常，但不改变多步审查结果。

## 预算、交付与独立核验

自然多步账本：1000809/16777216 本地 token 预留，13/128 logical calls 与 HTTP，6/32 tools，1032.508/14400 秒 Run wall time，工具执行 9.687 秒。provider prompt/completion/total usage 均为 UNKNOWN；本地 estimate 是 UTF-8 字节估算，不是 provider token 数。未决 HTTP attempt 与未知工具回执均为 0。

最终文本非空，SHA-256 为 `63b4cac5af68b0f271e2535e1a9d100e260d3987ccb86048dab6663f57b7e179`。整题审查为 UNKNOWN，finding 为 `whole_review_not_bound`；文本没有完整交付绑定。

终态独立零模型派发核验为 FAIL，报告 SHA-256 `1e03047831e29f8b59caefabd227c813d061dea3adeb92eb65ed98ba24e160d6`：

| 检查 | 结果 | 原因 |
| --- | --- | --- |
| task | FAIL | job_failed_or_canceled |
| coverage | FAIL | batch_stopped_before_completion |
| process_path | FAIL | natural_multistep_evidence_inconsistent |
| transport | PASS | all_samples_passed |
| usage | UNKNOWN | usage_unresolved |

Coverage 为 registered 1、audited 1、planned 1、incomplete 1、path_completed 0。缺少步骤接受、多步路径完成、整题审查和绑定通过的证据。#127 保持 open，#128 两臂保持 `NOT_RUN`。本次真实尝试计为第 19 次；自身工程修复轮仍为 12，策略调整 1，出网前准备失败 5。

readiness-27 和 readiness-28 都没有证实新的应用缺陷，但都未完成多步交付。两个 Run 的具体模型和审查停因不同，均停在步骤验证；这不构成放宽审查合同的依据。本轮未修改源码，也不把没有源码变化的重跑记作修复验证。Artifacts 位于 `artifacts/issue127-natural-20261105-readiness-28/`；冻结配置位于 `.review/issue127-natural-20261105-readiness-28/`。
