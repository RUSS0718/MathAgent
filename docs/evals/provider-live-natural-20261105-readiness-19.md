# readiness-19：用户请求的新独立重跑

用户在Codex重启后明确要求再重跑一次。本次无产品代码修改，不能据此断言重启导致或修复了18的非法JSON。旧18已终止且无在途调用，旧manifest/结果不改写，新19保持simple/octagon-colorings两题原字节、完整分母2、模型thinking/传输/预算和停止条件，不拼接旧批次。

北京时间2026-11-05 20:45:43启动Run issue127-natural-20261105-readiness-19-run01。冻结干净revision97c23d1f37000bc35b71607a7416548d95772e1c（只新增18归档文档），source SHA66f36d4369d4bf067f7972b9c0ad410fef9da5c88a790114496d45595867149c与18一致，manifest SHAa209e276eb7a5359c33cbc70b50b7bbf67d419b2afeca672e760f8002c4122fb。独立8140服务实际PID25120/创建20:45:21.306995，runner实际PID31668/创建20:45:43.777901；CIM仅微秒舍入差。

已核对源码/script/data目录、监听PID、实际模型/传输、样本字节和简单题实际Job预算limits。每题128模型/HTTP、32工具、16777216 token、14400秒，两题批次双倍；单调用900秒、连续30秒无流停止。intern-s2、thinking=false、temperature=0.2、32768输出、best-effort关闭，官方baseline、身份、整题审查和最终文本绑定保留。用户批准的纯推理仅限制Reasoner，Verifier保留原受控计算能力，线上实际是否触发须看trace。

20:46:57只读观察完成1/2：simple Job run_b8c213c461c463c75284ba96c7addbc5 succeeded/completed_llm_reviewed；自然题run_52c8a6661d3ee0f14f5d7153de58a428 running/STEP_EXECUTE，Reasoner首正文20:46:46.270200、末正文仍更新，无最终答案。未取得独立终态验收，usage UNKNOWN只观察。

repair_round仍8，policy_change_rounds=1、implementation_round=9、live_attempt=11、pre_dispatch_failures=1。本次未新增修复，不因新Run增加修复轮。已恢复唯一provider-live每10分钟监控，状态无实质变化静默，失败/完成通知；不重发或恢复未知请求。

```powershell
uv run python .review/issue127-natural-20261105-readiness-19/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=31668 OR ProcessId=25120" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-19/logs/run.stderr.log -Tail 10
```

#127未验收/open，#128两臂NOT_RUN/open。只有同批coverage/task/transport/process_path独立PASS、非空格式答案及整题审查同文本绑定后才执行单因素线上pair。不宣称数学能力提升。

终态：北京时间20:58:39.969168 runner正常退出，完成1/2。自然题公共failed/error=protocol_failure_unrepaired，Solver partial_aborted/TERMINAL、revision7243；S1已接受，S2仍VERIFYING。末业务事件protocol_failure_unrepaired（Reasoner/invalid_json），发生在S2挑战答复。原回复和一次repair-1均finish_reason=stop，严格JSON及现有非法转义救援都报Expecting ',' delimiter（pos3423/3561chars、pos3768/3850chars），未发现解析器误拒合法JSON证据。

原正文首20:52:44.464825、末20:55:17.626535、completion20:55:18.352512；repair首20:55:22.202933、末20:58:38.289431、completion20:58:39.000968。自然题12模型/HTTP、4次成功工具、本地charged678431/16777216、墙钟761.11/14400秒，unresolved_attempts=0、unknown_tool_calls=0。不是TLS、900秒或30秒流空闲停止、预算不足。Meta/pure reasoning未触发，不能写成新作用域已在线覆盖。usage仍UNKNOWN。

非空失败文本whole_review_not_bound，缺最终生成/整题审查同文本绑定。服务仍存活、进程身份匹配，本次公共GET零模型独立核验整体FAIL：task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；脱敏导出SHA2005c6189ac50b6904d172aa045c63aa89b4978fa5eb4f11573eb7ce68805a86，区别于18服务不可用的独立UNKNOWN，不拼接两批证据。

终态诊断保存至原artifacts/terminal-diagnosis.json。无新的工程bug确证，不扩大解析容错、格式修复次数或增加修复轮；旧19不恢复重发，不继续同配置盲试。无活跃Run，移除临时监控避免轮询旧状态；#127仍FAIL/open，#128两臂NOT_RUN/open，不等于任务验收完成。
