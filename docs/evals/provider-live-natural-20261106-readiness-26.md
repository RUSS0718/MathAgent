# #127 readiness-26 run record

2026-11-06 北京时间启动的新冻结批次于 03:12:44 终止，未通过 #127。简单题 Job 成功；自然多步题在第 4 步、审查/反例研究调用期间因 `connectivity` 停止。未知远端结果保留，未恢复或重发。

## 身份与配置

- Run：`issue127-natural-20261105-readiness-26-run01`
- Manifest SHA-256：`dc6fbbb6479610c9243ba2d81794e2b7902f492c4ec1008ea7c0d546b7ab9903`
- 源码 revision `13a3ccc444b2cfe5dd824483e4674bbe4baed760`，source SHA-256 `36e33434835b8338488f68248f876d3d8466fe086732062299042f8e4b261b94`；server SHA-256 `3ad72fa5252b5ab3fa831666218bd6577cc8a68b94874069eab2b080c0c2e952`。
- 完整分母仍为 `simple`、`octagon-colorings`，两份输入字节 SHA 与 readiness-24/25 相同并匹配登记。
- 配置保持 `intern-s2`、thinking=false、temperature `0.2`、输出 `32768`、stream_first、单调用 `1200` 秒、无流 `30` 秒、Run `14400` 秒；每题 `128` model/HTTP、`32` tools、本地 token 预留 `16777216`，best-effort 关闭。
- readiness-25 已确认的包装器配置错误在新批次修正：底层 requests connect/read timeout 均由冻结 execution-policy 的 `stream_idle_seconds=30` 取得。上层 1200 秒逻辑调用 deadline保持独立。manifest SHA、source identity、server SHA、两题输入哈希在启动前核对一致；公共 applied config 为 live/intern 且匹配，固定 Docker 镜像和隔离预检通过。
- 服务 PID `5292`、创建时间 `2026-11-06 02:07:17.982`（北京时间）；Runner PID `4860`、创建时间 `02:08:09.990`。Runner 于 `03:12:44.761` 退出。两个 Job 终态后已停止本批服务，并确认该 PID 不再存在、8143 无监听。

## 结果与停因

简单题 Job `run_c16d356b8f36ad94c45d7b35f0a15358` 成功，Solver `completed_llm_reviewed`，有非空答案；执行 `4` 次 model/HTTP、`1` 次工具，本地 charged/reserved `169577/16777216`，wall time `12.432/14400` 秒。

自然多步 Job `run_c8ef4a8e8b2a47d37dfe5d7211796341` 失败，Solver `interrupted`、阶段 `STEP_VERIFY`、revision `16826`，完成 `4` 个步骤。自然题共有 `22` 次 model/HTTP、`8` 次工具；本地 charged/reserved `1901221/16777216`，wall time `3855.996/14400` 秒，未决请求 `1`、未知工具 `0`。provider usage 对所有调用保持 `UNKNOWN`。

末调用身份为 `run_c8ef4a8e8b2a47d37dfe5d7211796341:step-verifier:1:step4-challenge-3:counterexample`，执行角色为 `researcher`。调用于 03:11:06.570 派发，约 `3.280` 秒收到 HTTP `200` 响应头，约 `4.139` 秒出现首正文；累计收到 `821` 正文字节/`62` 个流事件。末正文时间为 03:12:41.975，最后活动 03:12:42.902；没有 finish reason 或 completion。公开 attempt 状态为 `error/connectivity`，`unknown_outcome=true`。该请求已收到部分响应，因此不能当作确定未发送；本地没有保存更细的底层异常类型，无法确定 provider 中断、网络中断或其他传输层原因。部分文本不能当作最终答案；整题审查为 `unknown`，finding 为 `whole_review_not_bound`。

当时 Job 的公开错误为 `star_needs_review`，最后业务阶段仍在步骤审查/反例研究，末次请求未完成。没有自动重试或重复执行已完成工具。终态零模型独立核验报告为 `FAIL`：transport `PASS`、task `FAIL`、coverage `FAIL`、process_path `FAIL`、usage `UNKNOWN`；`path_completed=0`。独立报告 SHA-256：`20befe9e6e4fc276dca0833ffba4ee432da9d48a739a35b72213509c68adb0ea`。

终态后对注册主机进行的只读 TCP/443 与 TLS 握手检查成功，只能证明检查时建立了 TCP/TLS，不解释先前流中断，也不把旧 UNKNOWN 改成已知结果。readiness-25 的 10 秒底层连接限制已在新配置中校正；readiness-26 的长时间流式调用达到数分钟，说明该批次不再受 10 秒 connect 配置截断，但真实自然多步验收仍失败。当前没有证据支持增加代码修复；若继续 #127，须使用新的 manifest/Run 保留本批 UNKNOWN，不恢复本调用。#127 保持 open；#128 两臂仍为 `NOT_RUN`。
