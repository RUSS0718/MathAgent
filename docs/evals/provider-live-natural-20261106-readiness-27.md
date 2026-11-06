# #127 readiness-27 run record

2026-11-06 北京时间 03:38:32 启动 readiness-27，04:08:59 终止。简单题 Job 成功；自然多步 Job 在第 1 步的 `STEP_VERIFY` 以 `star_needs_review` 失败。Run 未通过 #127。readiness-26 的未决请求保持原样。

## 身份与配置

- Run：`issue127-natural-20261105-readiness-27-run01`
- Manifest SHA-256：`d0a3680d9ecda044d87738dbeffbb103b3e7f3aa86b3d15bcf2c761f86d5b35f`
- 源码 revision/SHA-256：`13a3ccc444b2cfe5dd824483e4674bbe4baed760` / `36e33434835b8338488f68248f876d3d8466fe086732062299042f8e4b261b94`
- Server SHA-256：`3ad72fa5252b5ab3fa831666218bd6577cc8a68b94874069eab2b080c0c2e952`
- 完整分母：`simple`、`octagon-colorings`。输入 SHA-256 分别为 `389ac0685cb60be93ca7d309ad245b9455da5e44159c65ae5d12c5c897c56dde` 和 `395f5e9269c997fcc111fcd86b4a35bda59f6f63e15160bb41d63fbfc6f0be94`。
- 实际 applied config 与登记一致：`intern-s2`、thinking=false、temperature=0.2、输出 32768、stream_first、单调用 1200 秒、30 秒无流、每题 14400 秒、128 model/HTTP、32 tools、16777216 本地 token 预留，best-effort 关闭。
- 服务 PID 21688 于 03:36:08 启动，Runner PID 15724 于 03:38:32 启动并于 04:08:59 退出，exit code 0。终态后按 PID、创建时间、脚本路径和 8143 监听归属核对并停止服务。
- readiness-26 的 UNKNOWN 请求未恢复、未重发。readiness-27 使用独立服务数据目录和新 Run 身份。

## 结果与直接停因

简单题 Job `run_8a348aeaa6f0079744bbdfb3c89a88b5` 成功，Solver 为 `completed_llm_reviewed`，最终文本非空；3 model/HTTP、0 tools，121050 本地 token 预留，8.014 秒。

自然多步 Job `run_7185377c0c2a3e246168e840f706f051` 失败，Solver 为 `partial_aborted`，停在 `STEP_VERIFY`，计划共 7 步但只完成 1 步。公开错误为 `star_needs_review`，没有单独 error code。最后业务事件是 `step_reviewed`：有效 `CHALLENGE`，`goal_gate=PARTIAL`、`logic_gate=FAIL`，直接原因 `verifier_tool_request_unfulfilled`。没有发生 TLS、连接或调用 deadline 停止。

自然多步 Job 有 19 次 model/HTTP、8 次已执行工具。最后 StepVerifier 调用于 04:03:53.462 派发，04:03:58.816 出现首正文，04:08:55.630 收到末正文，04:08:56.872 完成；正文 3692 bytes、328 个事件。HTTP 流完成，但 Verifier 随后因工具请求未履行而 CHALLENGE。部分文本没有升级为接受或整题审查。

逐调用首末正文、completion 和结束状态如下。时间为北京时间 2026-11-06。provider finish_reason 未提供的调用记为 `null`。

| # | Call ID | Role | 状态/错误 | 派发 | 首正文 | 末正文 | Completion | finish_reason | 正文/事件 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `solver_call_39e8473b81fb5d64dc64c658768e954d` | explore | completed | 03:38:46.789 | 03:38:47.516 | 03:38:48.031 | 03:38:48.124 | null | 123 B / 13 |
| 2 | `solver_call_da285131dde52af043dce3e827fbb4d4` | planner | completed | 03:38:48.263 | 03:38:49.036 | 03:39:01.430 | 03:39:01.527 | null | 2283 B / 186 |
| 3 | `solver_call_ce2fcd1fc7f219290ef8bc83c2b8ba15` | reasoner | completed | 03:39:01.742 | 03:39:02.544 | 03:39:17.691 | 03:39:17.878 | null | 1754 B / 160 |
| 4 | `solver_call_19fb698f0986144d4e358ff40c3bd4d4` | step_verifier | protocol_failed (invalid_json) | 03:39:18.265 | 03:39:19.268 | 03:40:06.445 | 03:40:06.655 | stop | 3321 B / 341 |
| 5 | `solver_call_29ba0a7df449785c04a48193cc1ee6e8` | step_verifier | completed | 03:40:07.027 | 03:40:08.229 | 03:41:00.122 | 03:41:00.387 | null | 3049 B / 267 |
| 6 | `solver_call_1ddadb4cb12d02c6d6ba0b2a9d702ef2` | step_verifier | completed | 03:41:02.549 | 03:41:04.447 | 03:42:10.316 | 03:42:10.698 | null | 3050 B / 258 |
| 7 | `solver_call_7e54001ebed4bc00f498179333dce87b` | step_verifier | completed | 03:42:13.209 | 03:42:15.479 | 03:43:18.008 | 03:43:18.503 | null | 2382 B / 207 |
| 8 | `solver_call_aceebc4e70d9c7e4ab90ee54dd0179ed` | researcher | completed | 03:43:19.449 | 03:43:20.606 | 03:43:32.637 | 03:43:33.126 | null | 490 B / 40 |
| 9 | `solver_call_0a5b5d15f7d3310d0c2c8b9638aabf7a` | reasoner | completed | 03:43:34.314 | 03:43:35.604 | 03:44:50.935 | 03:44:51.564 | null | 2331 B / 214 |
| 10 | `solver_call_c713960b5e45d04ffcfffb45e53a86d6` | step_verifier | completed | 03:44:56.119 | 03:44:59.119 | 03:46:22.203 | 03:46:22.734 | null | 2195 B / 207 |
| 11 | `solver_call_b7b44dc5dd42083555979d40a28fcb7b` | researcher | completed | 03:46:23.921 | 03:46:25.272 | 03:47:04.727 | 03:47:05.376 | null | 1065 B / 95 |
| 12 | `solver_call_8693064e8bd2913fe34ed40bf14836a1` | reasoner | protocol_failed (invalid_json) | 03:47:07.100 | 03:47:09.321 | 03:49:05.095 | 03:49:05.720 | stop | 2621 B / 241 |
| 13 | `solver_call_7de3781c37d4f006968a6df63896d2f0` | reasoner | completed | 03:49:06.870 | 03:49:09.315 | 03:51:22.098 | 03:51:22.800 | null | 2886 B / 244 |
| 14 | `solver_call_d3e58708a1753aeaa8fae59f2f1a8ede` | meta | completed | 03:51:28.268 | 03:51:30.243 | 03:52:09.507 | 03:52:10.331 | null | 820 B / 73 |
| 15 | `solver_call_32869fdb1119c4282b237ae377744354` | meta | completed | 03:52:12.387 | 03:52:14.380 | 03:52:56.249 | 03:52:57.224 | null | 973 B / 74 |
| 16 | `solver_call_67a92488e06935b8a532d3b6b2ab8f05` | reason_noncoding | completed | 03:52:59.190 | 03:53:00.858 | 03:55:52.255 | 03:55:53.062 | null | 3262 B / 274 |
| 17 | `solver_call_0036453393d29026ec34aa9df1a9bfb1` | step_verifier | completed | 03:55:55.639 | 03:55:58.525 | 03:59:40.522 | 03:59:41.659 | null | 3532 B / 316 |
| 18 | `solver_call_3c3af0648cebe5ab7ff80aa1083b3f58` | step_verifier | completed | 03:59:45.711 | 03:59:49.774 | 04:03:47.900 | 04:03:49.113 | null | 3509 B / 290 |
| 19 | `solver_call_3ec7a88b1ef2bee08ba9bcac48df22fd` | step_verifier | completed | 04:03:53.462 | 04:03:58.815 | 04:08:55.630 | 04:08:56.872 | null | 3692 B / 328 |

## 工具回执与根因分类

工具回执显示 4 次隔离执行成功（exit 0），4 次模型生成代码执行失败（exit 1）；失败项均为 `executed=true`、`unknown_outcome=false`、`cleanup_verified=true`。未执行请求未计入 8 次工具预算。失败 stderr 的脱敏尾部为：

- `SyntaxError: '(' was never closed`，298 bytes，stdout 0 bytes。
- `IndexError: list index out of range`，148 bytes，stdout 0 bytes。
- `TypeError: 'tuple' object is not callable`，两次各 347 bytes，stdout 均为 0 bytes。

这些是模型生成 Python 代码错误。容器实际执行并返回 exit code，清理已核实；未知工具结果为 0。证据没有显示隔离依赖缺失、资源不足、预算拒绝或应用导入故障。失败记录没有提供修复代码缺陷的依据，未修改源码，也未增加 challenge 或重试上限。

## 预算、交付与独立核验

自然多步实际账本：1389990/16777216 本地 token 预留，19/128 logical calls 与 HTTP，8/32 tools，1812.428/14400 秒 Run wall time，工具执行 11.078 秒。4 个工具执行失败有明确 exit 1 与清理回执。provider prompt/completion/total usage 对 19 次调用均为 UNKNOWN；本地 estimate 是 UTF-8 字节估算，不是 provider token 计数。未决 HTTP attempt 为 0。

最终文本非空，文本 SHA-256 为 `63b4cac5af68b0f271e2535e1a9d100e260d3987ccb86048dab6663f57b7e179`。但整题核验为 UNKNOWN，finding 是 `whole_review_not_bound`，因此文本未达到完整交付验收。

Runner 脱敏日志尾部没有异常 traceback，服务 stderr 无业务异常。终态后的本地只读 GET 读取到 Job、report 和 evidence，均返回 200。终态独立零模型派发核验为 FAIL，报告 SHA-256 `6a82f21bf6d6741dcd8d2ad35e96525bc4a56f8c0d261239c92c4d5e0e605543`：

| 检查 | 结果 | 原因 |
| --- | --- | --- |
| task | FAIL | job_failed_or_canceled |
| coverage | FAIL | batch_stopped_before_completion |
| process_path | FAIL | natural_multistep_evidence_inconsistent |
| transport | PASS | all_samples_passed |
| usage | UNKNOWN | usage_unresolved |

Coverage 为 registered 1、audited 1、planned 1、incomplete 1、path_completed 0。缺少多步路径完成、步骤接受、整题审查和绑定通过的独立证据。#127 保持 open；#128 两臂保持 `NOT_RUN`。本次真实尝试计为第 18 次；自身工程修复轮仍为 12，策略调整 1，出网前准备失败 5。

Artifacts：`artifacts/issue127-natural-20261105-readiness-27/`。冻结配置：`.review/issue127-natural-20261105-readiness-27/`.
