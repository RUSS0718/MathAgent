# #127 readiness-24 run record

2026-11-06 北京时间执行的新冻结 provider-live 批次已终态 `FAIL`。该结果不通过 #127，也不启动 #128。

## 身份与配置

- Run：`issue127-natural-20261105-readiness-24-run01`
- Manifest SHA-256：`878cb36930e3445c99c20da55306163eb1df560a9c3db2df5f10438790d935c9`
- 源码：revision `65d15d6d4413fc66a997277de27cdcce1de8361e`，source SHA-256 `1d79fc05bc18017f026fcd2616f2696f73e94030ac0b55affaeb3e06c3297204`，工作树干净。
- 样本分母：`simple`、`octagon-colorings`，两份源字节哈希均与登记一致。
- 配置：`intern-s2`、`thinking=false`、temperature `0.2`、输出上限 `32768`、`stream_first`；单调用 `1200` 秒、无流活动 `30` 秒、Run `14400` 秒。每题上限 `128` model/HTTP、`32` tools、`16777216` 本地 token 预留；best-effort 关闭。
- readiness-23 的启动前隔离探针未执行成功，未注册 Run，也未派发 provider 请求。Docker 环境恢复后，readiness-24 启动时实际 `star_reference` 已启用，固定镜像预检通过。

## 结果与停因

简单题 Job `run_b1aab11ab8157cafe31ca550353437eb` 成功，Solver 为 `completed_llm_reviewed`，最终答复非空。自然多步 Job `run_225e7f05f08b62e7b288a31bb4d31fa2` 失败，Solver 为 `partial_aborted`，终态有两个步骤；第一步接受，第二步仍为 `CHALLENGE`。答案文本非空，但整题审查为 `unknown`，finding 为 `whole_review_not_bound`，因此不构成完整交付。

直接停止原因为 `challenge_meta_limit_reached`。最后业务事件为 `challenge_escalation_stopped`，公共 Job 错误为 `star_needs_review`。Verifier 指出步骤目标含算术不一致，并要求修正目标、在报告中引用实际工具结果。该异议在既有挑战上限内未解决。它是模型与数学审查结果，不是已证实的工程缺陷；没有放宽挑战上限或伪造接受。

持久状态记录了三次 Python 工具调用，均为 `success`、exit code `0`、已执行且清理确认；`unknown_outcome=false`。但三份回执都没有捕获 stdout，`output_available=false` 且 `assertion_matched=false`。因此回执不能支持后续报告声称的数值；没有证据表明工具环境或执行器失败。Verifier 的描述与持久回执不一致，仍不足以证明应用缺陷。

同一自然题中有一次 Reasoner `invalid_json`，finish reason 为 `stop`，正文 `1402` bytes。新身份 `:repair-1` 的请求包含同一失败正文及解析定位（line `1`、column `1265`、position `1264`），格式修复调用随后正常完成。这验证了失败原文上下文进入实际修复调用，但不改变本题审查结论。

## 计数与独立核验

自然多步 Job 记录 `20` model/HTTP 调用、`3` 次工具调用，本地 charged/reserved `1815093/16777216`，wall time `1268.96/14400` 秒。完整批次为 `23/256` logical/model/HTTP、`3/64` tools、本地 charged/reserved `1936143/33554432`，wall time `1281.92/28800` 秒。provider prompt/completion/total usage 均缺失，保持 `UNKNOWN`；未决请求和未知工具结果均为 `0`。停止不是 TLS、预算、单调用超时或 Run 总截止。

独立零模型派发核验报告为 `FAIL`：task、coverage、process_path 为 `FAIL`，transport 为 `PASS`，usage 为 `UNKNOWN`。报告 SHA-256 为 `00fd96b39c2ca5da3dc8062fc863bddaa2160d404e7c115c2cd9c67985123731`。逐调用首末正文、completion、角色、工具回执摘要见忽略目录 `artifacts/issue127-natural-20261105-readiness-24/observation-20261105T162904.json`；完整独立报告位于同目录 `independent-report.json`。

Runner PID `9660` 于 2026-11-06 00:21:14.795（北京时间）正常退出。确认两个 Job 均终态后，停止本批服务 PID `5292`。旧 Run 与 readiness-23 的准入失败记录保持原样。此次没有代码修改，不增加工程修复轮；#127 保持开放，#128 两臂仍为 `NOT_RUN`。本结果不声明数学能力提升。
