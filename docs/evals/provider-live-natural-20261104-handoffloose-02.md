# #127 自然多步线上运行记录：handoffloose-02（2026-11-05）

本文件只记录该冻结 Run 的脱敏结果。结论为 #127 provider-live readiness **FAIL**；#128 线上配对 **NOT_RUN**。本次未评估数学正确性。

## 冻结身份与预算

- Manifest：`issue127-natural-20261104-handoffloose-02`，SHA-256 `2a1d31d96a1789b7dd2a47e6222c9f34e80d805dcc4a5c1ae5cb86af88d0a005`。
- Run：`issue127-natural-20261104-handoffloose-02-run01`。
- 源码 revision：`e6b6b8919ac266694c36eb0205e5f79fb3ef3953`；源码 SHA-256 `bd1893119502900fd4f80651fbbefd43d4a089c093efd9f08e433ee160f1e192`。
- 模型：`intern-s2`，thinking=false，temperature=0.2，输出上限 32768；每次请求上限 900 秒，Run 截止 3600 秒；传输 `stream_first`；best-effort 关闭。
- 登记样本为 1 道 simple 和 1 道自然多步题。usage policy 为 `observe_only`，未知用量保留 UNKNOWN。

## 结果与停止原因

- 进程 PID 24144 于北京时间 2026-11-04 23:43:21.539 启动，2026-11-05 00:43:24.952 退出，exit code 0。CLI 进程退出码 0 不表示 readiness 通过。
- 批次完成 1/2。simple Job 成功；自然多步 Job `run_e5184f6d5cab0387b0b28d1e4ac5bec1` 在 3600 秒 Run 截止时仍未完成。公共 Job 随后为 `failed`，错误码 `run_deadline_exhausted`，更新时间 2026-11-05 00:43:25.206。
- 自然多步题自然生成 5 步计划，Solver 持久状态为 `running / STEP_VERIFY`、plan_version=1、state_revision=10839；数据库中有 10840 条 solver event。该数量证明运行期间存在大量持久进度事件，但不能单独证明它是达到截止的唯一原因。
- 最后一段正文首 token 为 2026-11-05 00:42:02.237，末 token 为 00:43:21.879；末流没有 completion 记录，usage_known=false。末 token 至 Run 终态约 3.1 秒，没有连续 30 秒无流活动停止证据。
- 冻结核验报告：task=FAIL、process_path=FAIL、coverage=UNKNOWN、transport=PASS、usage=UNKNOWN。transport PASS 只表示观察到的配置匹配登记，不代表末流完成。usage UNKNOWN 不作为答案完成阻断，也不改写为 PASS。
- 最后独立快照有 25 logical calls、25 HTTP attempts、3 tool calls；usage 数字仍有未知/预留部分，不是 provider 已知 token 用量。自然多步 Job 没有最终生成、整题审查或最终文本绑定。

该 Run 的批次 `stop_reason` 被写成 `incomplete_or_unresolved_usage`。复核发现观察器先处理 unresolved usage，后处理到期的 running Job，掩盖了先发生的 3600 秒硬截止。这是**分类 bug**，不是 Job 截止本身的实现错误。已在本地修复判断顺序并增加 RED→GREEN 回归；旧 Run 和其 manifest 保持不变。以后同类观测应记 `hard_limit`，独立核验仍分别保留 usage UNKNOWN 和请求未决事实。

截至本记录，失败触发原因可确认为总 Run 截止；为何步骤审查续接未能在截止前交付，现有证据仍不足以归结为单一根因。SQLite 事件量和 snapshot 的全量读取是可量化的成本点，已按现有分页合同加入 SQL 限量读取；这不能代替新的线上复验，也不能声称已修复自然多步 readiness。

## 归档与 Issue 状态

- 脱敏归档目录：`artifacts/issue127-natural-20261104-handoffloose-02/`。本文件不复制 raw、prompt 或凭证。
- #127 保持 open / FAIL：仍缺自然多步最终答案、整题审查和同文本绑定。
- #128 保持 open / NOT_RUN：baseline、variant 均未派发；没有线上 pair、applied-config 或逐臂独立核验证据。
- 不改官方 baseline，不启用 best-effort，不宣称数学能力或正确率提升。
