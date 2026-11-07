# #127 readiness-25 run record

2026-11-06 北京时间启动的新冻结批次于 01:40:36 终止，未通过 #127。简单题 Job 成功；自然多步题在首步审查请求阶段终止。该结果保留为历史批次，不恢复、不重发。

## 身份与配置

- Run：`issue127-natural-20261105-readiness-25-run01`
- Manifest SHA-256：`892f52071a548e7647754d637c5d6be7d3e1840d4168f49f8303522b0cbb92e8`
- 源码 revision `13a3ccc444b2cfe5dd824483e4674bbe4baed760`，source SHA-256 `36e33434835b8338488f68248f876d3d8466fe086732062299042f8e4b261b94`。
- 完整分母仍为 `simple` 与 `octagon-colorings`；两题源字节哈希与 readiness-24 相同，均匹配本批登记。
- 模型配置：`intern-s2`、`thinking=false`、temperature `0.2`、输出上限 `32768`、`stream_first`、client 请求截止 `1200` 秒、30 秒流空闲策略、每题 Run 截止 `14400` 秒；每题预算 `128` model/HTTP、`32` tools、本地 token 预留 `16777216`；best-effort 关闭。
- 实际公共 capabilities 为 `live/intern`，applied config 与 manifest 一致，固定 Docker 隔离预检通过。readiness-25 服务 PID `15752` 与 8143 监听所有权核对一致；Runner PID `27800` 于 01:40:36.546（北京时间）正常退出。两个 Job 终态后已停止本批服务。

## 结果与停因

简单题 Job `run_053d61bbdffccae1627b9cffaf63ef2a` 成功，Solver `completed_llm_reviewed`，有非空答案与同文本绑定；本结果只说明该 Job 执行成功，不升级自然多步能力验收。

自然多步 Job `run_9053c259f8207e9209e45cf7a2a324d3` 在 `STEP_VERIFY` 失败，Solver 为 `interrupted`、revision `1469`，公共 Job 错误为 `star_needs_review`。最后业务阶段事件为 `step_review_dispatched`；末调用为 `step_verifier`，调用身份 `run_9053c259f8207e9209e45cf7a2a324d3:step-verifier:1:1`。该调用于 01:40:26.192 派发，01:40:36.340 最后活动，约 `10.147` 秒后以 `timeout` 记为 `unknown_outcome`；没有响应头、流事件、正文或 completion，finish reason 和 provider usage 均缺失。不能据此断言请求未发送或 provider 未处理，保留一个 unresolved attempt，不恢复、不重发。

当时已完成的自然题调用依次为 Explore、Planner、Reasoner：dispatch 到 completion 分别为 01:39:41.768–01:39:43.073、01:39:43.208–01:40:09.310、01:40:09.567–01:40:25.779；正文 bytes 为 `123`、`4199`、`1474`。第四个 Verifier 调用只有上述 dispatch 与最后活动时刻，无正文和 completion。自然题共 `4` model/HTTP 调用、`0` 工具；本地 charged/reserved `176562/16777216`，墙钟 `54.874/14400` 秒，未决请求 `1`、未知工具 `0`。provider usage 对四个调用均保持 `UNKNOWN`。非空终止文本不构成最终交付；整题审查为 `unknown`，finding 为 `whole_review_not_bound`。

## 配置缺陷与独立核验

检查冻结的 `.review/issue127-natural-20261105-readiness-25/server.py` 后，确认本地传输包装器将 `strict_provider_post` 的 requests timeout 强制覆盖为 `(10, 30)`。Requests 将 tuple 解释为分别用于连接和读取的 timeout；它不是 1200 秒总调用 deadline。虽然本次 public attempt 记录的 effective timeout 约 `1199.999` 秒，底层连接仍被本地包装器限制为 `10` 秒，早于登记的 30 秒无流窗口。现场约 `10.147` 秒停止与此配置高度吻合，但底层异常子类型没有持久化，故不能声称已证明这次具体发生的是 connect timeout；远端结果仍为 `UNKNOWN`。

独立子智能体比较局部修复与小型重构后建议只在新批次将连接与读取的底层 timeout 均从既有 `stream_idle_seconds` (`30`) 取得，保留独立的 `1200` 秒逻辑调用 deadline，不改 HTTP retry、预算或审查合同。小型重构会扩大传输与 deadline 语义的回归面，当前没有相应收益证据，因此不采用。诊断时另做了不含凭证的注册主机 TCP/443 与 TLS 握手，只证明该时点连通，不能反证原始 UNKNOWN。

独立零模型派发核验报告为 `FAIL`：transport `PASS`、task `FAIL`、coverage `FAIL`、process_path `FAIL`、usage `UNKNOWN`；coverage 完成 `1/2`，path_completed `0`。报告 SHA-256：`e4a637db44c3b4c78788610ccd40d9d5443f1d8211520372b500e2794eb3ccc3`。核验在 01:50:30（北京时间）以 `verify_terminal.py` 完成并导出。Issue #127 保持 open；#128 两臂仍为 `NOT_RUN`。
