# readiness-05：执行观察器失败与仍在运行的 Job

截至 2026-11-05 03:11:39 UTC，本批次 **已执行、未完成，不能判 PASS**。原 Run 不恢复、不重发。此记录追加观察证据，不修改旧 manifest、status 或完成计数。

- 工作树：`Challenge-Cup-2026-readiness-fixes`；源码 revision `8f57264c44723cfe002f61300d6ebe734cc5ccfa`，含冻结的未提交差异。
- source SHA-256：`3805b2b201c04fb4c1d29ba4f75e743da0af0c791e425d35093f5d850547ddc3`。
- manifest SHA-256：`2afc6566ef93a8627079807df7ac8a59e7d7778e957ec6d7bb66d08c45f5492f`。
- Run：`issue127-natural-20261105-readiness-05-run01`；预登记分母 2，runner 持久完成计数 1/2。
- 模型 `intern-s2`，thinking 关闭，temperature 0.2，输出上限 32768，`stream_first`，usage `observe_only`，best-effort 关闭。
- 每调用 900 秒、连续 30 秒无流活动停止、Run 3600 秒，未知请求不重发。预算与停止条件不放宽。

## 已确认事实

简单题 Job `run_7a8622de0df41bbfd9fa22e1d5b81a15` 成功，返回非空最终文本，整题审查 accepted、同文本绑定 same_artifact。最终文本 SHA-256 为 `b59cdf2ec87ec66630e61e3aa81629fe1700b9579404a74e71dbf3b9a5814097`。

自然多步 Job `run_de9732e0c0e0955385714dec80600ec9` 当前仍为 running，Solver 位于 STEP_VERIFY、revision 4920。已形成计划并实际执行步骤处理、Researcher 和后续核验；仍缺最终答案、整题审查和最终文本绑定。最近 step_verifier 调用首个正文时间为 `03:09:47.108024 UTC`，本次观察最后正文为 `03:11:38.976055 UTC`，completion 尚未到达。该观察时间不能当作最终末 token 时间。

runner PID 17952、创建时间 `2026-11-05T03:01:31.353502Z`，已因 PermissionError 退出。`experiment_runner._write_status()` 的 `os.replace()` 返回 WinError 5，随后尝试写停止状态再次失败。因此 `status.json` 残留 running；这不是服务端 Job 终态，也不是模型答错。证据在忽略目录 `artifacts/issue127-natural-20261105-readiness-05/logs/run.stderr.log` 与 `process.json`。

服务实际由 readiness-04 的 server.py 启动，数据位于 readiness-04/server-data。05 的 CLI 沿用了同一端口。公共模型、传输预检匹配不能独立证明服务进程加载了 05 冻结的全部源码。目录隔离与服务源码身份需单独核查；不得把本批次拼入其他批次凑成 readiness。

只读补充快照为 `artifacts/issue127-natural-20261105-readiness-05/observation-20261105T031139.json`。快照只保留状态、公开调用别名、流时间、预算和最终文本摘要，不保存题目、prompt 或工具参数。

## 本轮修复与验证边界

此前已修复独立 verifier 的执行模式映射、已开始但未完成路径分类、计数互斥、Planner 与所生成计划的关联，以及 Explore、整题 Verifier 和跨 plan/attempt 工具回执消费关系。公开事件补足对应身份投影并过滤原始 ID 与工具载荷。

当前聚焦 unittest 共 61 项，59 项通过、2 项按 Docker 条件跳过；快速合同门禁 PASS，官方 baseline 文件无差异。这些证据不替代真实 API 验收。状态替换失败正在独立复现；临时读锁是待验证解释，尚不能断言为本次现场唯一根因。

#127 保持 open，readiness 未通过。#128 两臂均 NOT_RUN，保持 open。usage 保留 UNKNOWN，不阻断已完成答案、不标 PASS；没有数学正确性或能力提升结论。

## 状态文件修复（03:16 UTC）

`_write_status()` 现仅对 Windows WinError 5 做至多三次原子替换尝试，总退避 150 毫秒。持续失败或其他错误仍向上传播；旧 status 文件不截断，临时文件清理。新回归通过真实 Windows CreateFileW 的不共享删除句柄复现替换失败，释放读锁后验证恢复；永久失败用例确认旧文件保持不变。两个新增回归及既有实验执行器合同共 29 项通过，Ruff 与 diff-check 通过。此证据证明短暂读锁可造成同类错误及修复有效，未识别现场持锁进程。

下一批 readiness-06 的独立端口、数据目录及启动源码/脚本哈希检查已准备，尚未冻结、尚未派发。当前 Job 不恢复、不重发；本修复不能追溯改变 readiness-05 的 runner 状态。

补充验证：修改影响到的协议失败与 RB02 计算测试共 28 项，20 项通过、8 项按 Docker 条件跳过；改动源码及新增核验测试 Ruff 通过。最终状态写入修复后再次快速门禁 PASS。没有运行全仓测试或新 provider 请求。

## 身份核查与取消（03:20 UTC）

独立核查确认：8126 监听者为 readiness-04 服务 PID 23476，创建于北京时间 10:55:12。04/05 启动脚本相同，但 source SHA 分别为 `90fb5990ff36ae47efe9f73b41d9dc0484ab546570ab36e5ab4822a269b69f55` 和 `3805b2b201c04fb4c1d29ba4f75e743da0af0c791e425d35093f5d850547ddc3`；star_product_events.py 在服务启动后修改。故05的服务源码身份与manifest不一致，不能作为匹配该身份的readiness证据。该缺陷与状态写入失败分开记录。

按登记的 source_or_config_change 停止条件，对既有自然多步 Job 调用公共 cancel，一次成功返回 canceled。停止决定另存 `stop-decision.json`；原status文件不改写。取消时Solver位于 CHALLENGE，最新Reasoner首正文为 `03:19:24.037338 UTC`。03:20:51观察仍有该既有请求的流活动，最后已观察正文 `03:20:50.165377 UTC`；不能将公共Job已取消等同于物理请求已结束。不重发、不恢复，等既有请求停止后才串行启动新批次。缺最终答案、整题审查、文本绑定，usage UNKNOWN；不是数学错误结论。

最终在途调用于 `03:22:30.152683 UTC` 完成，最后正文 `03:22:29.094173 UTC`。只读确认旧Job无在途调用后启动06。05独立核验为总FAIL：transport PASS（仅登记传输配置）、task FAIL/job_failed_or_canceled、usage UNKNOWN/usage_unresolved、coverage UNKNOWN/dispatch_intent_unresolved、process_path FAIL/natural_multistep_evidence_inconsistent；自然多步登记分母1，incomplete=1，path_completed=0。runner原状态仍保留，不清理或伪造完成intent。另有已确认的服务源码身份不一致，故transport配置PASS不能解释为完整readiness PASS。
