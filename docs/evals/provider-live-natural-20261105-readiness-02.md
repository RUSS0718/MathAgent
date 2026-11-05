# #127 自然多步 readiness-02 运行记录

日期：2026-11-05。该批次使用单独 manifest、Run ID 和服务数据目录。它没有通过 #127。

## 冻结身份与限制

- Manifest：`issue127-natural-20261105-readiness-02`；Run：`issue127-natural-20261105-readiness-02-run01`。
- 源码 revision：`f4adc569516fae483dff500d605abb8c1833c1fb`；source SHA-256：`5e63a9d3eecdd7507d94174843f0dae4f2c51ed28e546c476cd9013e94483933`。
- Manifest SHA-256：`13f1c073f040855a58c872ee43b2408a19430458b97fe53bebe20c9e726a6d7e`。
- 样本：`simple` 与自然多步 `vieta-equation`，完成数 `1/2`。多步路径没有强制启用 planner 或工具。
- 模型：`intern-s2`；thinking 关闭；temperature `0.2`；每次输出上限 `32768`；传输 `stream_first`；每次调用 `900` 秒；流空闲 `30` 秒；Run 截止 `3600` 秒。
- 每个 Run 上限：32 次模型调用、32 次 HTTP、8 次工具、`2,097,152` charged/reserved tokens、3600 秒。Best-Effort 关闭；整题审查及最终文本绑定启用；usage 只观察，未知值保留 `UNKNOWN`。

## 执行结果

简单题 Job `run_de194db309af356311c6dd4ab4d771ca` 为 `succeeded`，产生非空答案、整题审查 `accepted` 和 `same_artifact` 绑定。该样本不构成自然多步证据。

多步 Job `run_568d8b454a0c9d9b8a80f4d38f8bc075` 以 `star_needs_review` 失败。它生成 5 步计划，报告 3 步，接受 2 步，并有 2 次工具调用。没有最终答案、整题审查或最终文本绑定。两个工具结果在独立公开核验中为 `unknown`，回执消费关系没有被证明。

自然多步流的首个正文 token 时间为 **2026-11-05 07:49:16.763989（北京时间）**，最后正文 token 时间为 **08:28:55.858159**，最后一次流完成时间为 **08:28:58.230553**。31 次模型调用各自的脱敏首末正文时间、完成时间、角色、plan/attempt 版本及 usage 状态见本地忽略产物 `artifacts/issue127-natural-20261105-readiness-02/logs/readiness-02-call-timeline.json`。Job 失败发生在流完成后；没有 30 秒空闲停止，也没有 900 秒调用或 3600 秒 Run 截止证据。

Provider usage 全部未知。独立账本按每个 Run 分别记录：简单题 `119,709 / 2,097,152`，自然多步 `1,985,185 / 2,097,152`。批次总计 `2,104,894`，低于两 Run 的批次上限 `4,194,304`。因此原先把批次合计与单 Run 上限相比的疑点已撤销；没有观察到预算越界。

旧独立核验报告为 `FAIL`：coverage、process path、task 均为 `FAIL`，transport 为 `PASS`，usage 为 `UNKNOWN`。Transport PASS 只确认登记配置匹配，不代表答案已完成。报告还把 `execution_mode` 写为 `unavailable`，并把部分自然多步状态分类成 `NOT_RUN`。这些 verifier 缺陷另行修复和重核，不改变已失败 Job 的历史身份。

## 已定位的失败缺陷

Solver 持久事件末尾记录了 `meta_invalid`，公共 Job 错误为 `star_needs_review`。Meta 响应包含全部要求的业务字段和传输附加的顶层 `usage`。严格业务解析器按精确键集合拒绝该响应，随后没有继续步骤核验流程。该拒绝机制有源码、持久事件和本地重放测试支持；它不是数学正确性判断。

修复已提交为 `8f57264`：只在对应调用审计明确标记为 `stream` 时剥离传输 `usage`，其余业务键仍精确校验；非流式 `usage`、未知字段和非法枚举继续拒绝。真实 `InternModelPort` 的 mock-stream 路径、审计保留及未知字段拒绝均有回归；Meta、Intern stream、STAR routing 和 stream profile 聚焦测试共 **46 项通过**。这是离线修复证据，不能改变本 Run 的历史结果。

另确认独立 verifier 的证据投影问题：execution mode 来源映射错误；成功角色未按当前 plan version 和 attempt 过滤；已开始但未完成的计划曾标为 `NOT_RUN`；工具调用只要非零就一律返回 `UNKNOWN`。当前最小修复仍在进行，尚未合入或通过完整聚焦回归；receipt 消费证据不完整时必须保持 `UNKNOWN`。因此在独立核验修复通过前不启动新线上 Run。

## Issue 状态

- **#127：已执行未通过，`FAIL / open`。** 简单题交付成功；自然多步有 trace，但缺最终答案、整题审查和最终文本绑定。usage 为 `UNKNOWN`，不是本轮答案失败原因，也不标为 PASS。
- **#128：`NOT_RUN / open`。** baseline 与 variant 两臂均未派发。只有 #127 自然多步 readiness 独立核验 PASS 后才运行线上配对。
- 不宣称数学能力提升。该 Run 的原始身份和证据保持不变，不续跑、不恢复、不重发。
