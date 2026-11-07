# readiness-07：已启动，目标清除后仅监控

2026-11-05 04:31 UTC后的最近观察：完成1/2，简单题成功，自然多步仍在STEP_EXECUTE。没有最终答案、整题审查和绑定完成证据，不能判readiness PASS。用户随后清除自动推进目标；不再开发、自动重跑或启动#128，只监控现有Run。

- Run：`issue127-natural-20261105-readiness-07-run01`。
- manifest SHA-256：`48d9e4fc0f744e2c81ea0818c781c81e3a48fea47fd42a429db15861f145dc2b`。
- 干净源码revision：`8e1e1da14ee57dd4688fc8d9ec7d2de46afcf728`；source SHA-256：`051b111e2ff766a34ebbd77bda3fe93eeed5ba15cccd19e050738def076e53c9`。
- 独立服务8128，PID14072，创建于`2026-11-05T04:30:22.938025Z`；runner PID4440，创建于`2026-11-05T04:30:45.657412Z`。
- 固定simple与vieta-equation两题，样本内容/哈希、intern-s2、thinking=false、temperature=0.2、32768输出、stream_first保持原登记。
- 每调用900秒，连续30秒无流活动停止，Run3600秒，模型/HTTP各32次、工具8次、tokens2097152；best-effort关闭，整题审查与最终绑定保持启用，usage只观察并保留UNKNOWN。

派发前核对了8128监听PID、服务启动源码/脚本SHA和数据目录，并通过该端口公共capabilities验证实际模型/传输配置。旧06已终态归档，无在途调用，服务已停止；结果不拼接。

简单题Job `run_03849565ad5fe2fb8649141268ff2097` succeeded，非空文本、Solver completed_llm_reviewed。自然多步Job `run_c9c510a3f6c850dedb1efa12b4c07746`仍running，最新观察6次模型调用、STEP_EXECUTE；首个Reasoner正文于04:31:20.727974 UTC出现。观察中末正文不是最终时间，以最终脱敏快照为准。

本轮修复：零索引核验、过时RB03次数预期、重复历史读取。相关43项回归、基础20项检查、迟到流/恢复及新增负向33项检查和快速门禁通过；官方baseline无差异。没有以这些结果替代真实交付验收。

只读入口：`uv run python .review/issue127-natural-20261105-readiness-07/audit_live.py`。本地冻结与原始脱敏运行产物位于`artifacts/issue127-natural-20261105-readiness-07/`。唯一监控`issue-127-readiness-07-run`已收窄为只读，终态独立核验并报告后删除。#127仍open、未通过；#128两臂NOT_RUN/open。配对脚本02仅准备，未生成收据或manifest、未派发。

## 2026-11-05 12:55监控确认：失败原因（北京时间）

Run于12:52:12结束，完成1/2，runner PID4440正常退出（exit_code=0且实际进程已不存在），不是runner崩溃。自然多步Job为failed，公共错误码star_needs_review。Solver持久状态partial_aborted、阶段STEP_VERIFY、revision9340，停在step2；step1已接受。最后step_reviewed的valid=false、reason=verifier_tool_request_unfulfilled。

已确认的失败链：

1. 第二步Verifier请求polynomial_check，coefficients与candidates中包含符号字符串。离线只重放参数校验（没有实际执行工具）：两字段均不符合权威POLYNOMIAL_CHECK_SCHEMA要求的有理数字符串，解析分别返回coefficient_not_rational、candidate_not_rational。
2. 该次调用留下已知tool_error回执，无计算输出、非timeout、非unknown_outcome。冻结源码中Registry的入参拒绝会被RegistryToolPort映射成tool_error；结合已存参数，证据支持入参校验拒绝路径。原回执未保留底层细分错误码，不能从回执单独还原底层异常文字。
3. 回执已确实进入下一次Verifier请求的report.tool_receipts；随后Verifier原样重复同一请求，request_digest与该回执完全相同。最后调用为同一审查round4的tool-1续接。verifier_compute.continue_review在reply_from非空且找到同digest旧回执时返回unfulfilled，阻止重复执行；该scope仅1次回执，小于局部上限2，并非局部次数用尽。
4. verification.verify_step把审查标为无效并以verifier_tool_request_unfulfilled终止，Job失败。非空final_response是终止说明，缺final_generator和whole_solution_verifier调用；外层same_artifact不等于完成整题审查绑定。

另确认诊断信息缺口：RegistryToolPort返回error字段，但tool_precheck._execute保存结果时未将其写入回执，因此Verifier收到的只有笼统tool_error。这可能妨碍纠正参数；尚不能证明它是模型重复请求的唯一原因。这里只分析并归档，未修复代码或重跑。

本次自然多步22/32次模型和HTTP、7/8次工具（6个success回执、1个tool_error），charged/reserved=1,646,276/2,097,152，墙钟1272.532秒/3600秒；最长完成调用136.493秒/900秒。没有未知远端结果，unresolved_attempts=0、unknown_tool_calls=0；unknown_attempts=22是provider用量未知，不是未知请求。实际applied config、当前source与冻结SHA、服务脚本SHA均匹配。runner stderr为空。直接停因不是传输拒绝、全局预算耗尽或流空闲停止，也不能据此判断题目答案的数学对错。

自然多步首正文12:31:00.905551、末正文12:52:09.774688、末次completion12:52:10.752546。逐调用流时间和脱敏日志尾部保存在observation快照与terminal-diagnosis.json。

独立核验总FAIL：transport PASS；task FAIL/job_failed_or_canceled；coverage FAIL/batch_stopped_before_completion；process_path FAIL；usage UNKNOWN。自然多步登记分母1，incomplete=1，path_completed=0；完整批次分母2、完成1。独立脱敏报告为artifacts/issue127-natural-20261105-readiness-07/independent-report.json，SHA-256为14f92cd59cd36522ecd5f9a8220202b0b0660690aedaaf2f66fae80c6ee9d4e8；根因诊断另存terminal-diagnosis.json。原manifest、status、源码均未修改。

#127未获得通过证据，#128两臂仍NOT_RUN。本次未修复、未重跑、未启动配对、未关闭Issue。失败诊断与报告完成后删除本批次10分钟临时监控。
