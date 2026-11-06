# readiness-12：TLS恢复后的独立尝试

北京时间2026-11-05 15:42:43启动。Run issue127-natural-20261105-readiness-12-run01，manifest SHA6a1b635e2f3642460eed099fa0b322b180146deed268f7c7e5d5f5dc067ccc98，干净revision609056602487e86b13e41a4a031165242b7ff7f3，source SHA99814e1bb981553588fcc5e64bdb8d2372b905f7f6787ec4585d6a57fa3bfc07（与11代码一致，只有文档提交变更revision）。

用户明确TLS/真实预算不足不算修复轮，仅自身设计/实现失误算。因此repair_round仍4，live_attempt5。11最后unknown原请求不恢复重发；默认证书验证TLS握手2次通过后，用新manifest/Run单独尝试，不关闭SSL、不改传输策略或增加自动重试。不能从握手恢复推断旧请求结果或SSL具体根因。

独立8133服务PID38520/创建15:42:12.546318，runner PID28364/创建15:42:43.366833。启动source/script/data、监听PID及公共模型/传输核对后派发。沿用用户授权大预算每题128模型/HTTP、32工具、16777216 token、14400秒，两题批次双倍；单次900秒、30秒流空闲、原两题/模型thinking/32768输出保持，best-effort关闭、审查绑定启用。

15:43:17观察完成1/2：简单题run_d07ccafa5c56df1c96fb33b0a3ca3f55 succeeded；自然多步run_896faf978cf779755564d5a02c4ed6a7 running/PLAN，Planner首正文15:43:13.849825，尚无最终答案。逐调用流时间及脱敏观察在artifacts/issue127-natural-20261105-readiness-12/observation快照。唯一provider-live监控每10分钟已转移，不重复创建。

#127尚未通过，#128两臂NOT_RUN；usage UNKNOWN只观察，不宣称数学能力提升。5轮决策门槛按repair_round，外部TLS或预算本身不凑次数；预算/超时误分类等自身缺陷仍计。监控命令uv run python .review/issue127-natural-20261105-readiness-12/audit_live.py；process.json含PID创建时间，logs/run.stderr.log保留错误尾部。

终态：北京时间15:44:38 runner正常退出，完成1/2；简单题交付成功，自然多步Job run_896faf978cf779755564d5a02c4ed6a7失败。公共错误protocol_failure_unrepaired，Solver partial_aborted/TERMINAL，revision1872。阶段为Meta；其完整响应finish_reason=stop，却把必填rationale写为reasonale，产生invalid_role_schema。首正文15:44:19.367445、末正文15:44:37.634616、completion15:44:37.847362。不是TLS、工具失败或数学判错。

自然题6 logical/6 HTTP、1工具，charged259643/16777216，墙钟87.38秒；unresolved_attempts=0、unknown_tool_calls=0。账本unknown_attempts=6对应provider usage缺失，不代表6个在途未知请求。usage仍UNKNOWN。非空partial响应存在，但whole_review_not_bound，没有满足本轮要求的最终生成、整题审查和同文本最终绑定，不能当作答案完成。

终态独立核验已完成：coverage/task/process_path FAIL，transport配置证据PASS，usage UNKNOWN；整体FAIL。脱敏导出SHA256 2cef9bfa4bbec2ecfce7092852286d2f4908c2bc2f0112ce23b80b400629b8cc，逐调用时间及终态诊断保存在原artifacts批次。旧服务后来不可连接，不恢复服务或原请求；使用此前终态快照、DB与独立报告归档，不把残留process.json视为活跃证据。

已确认的自身实现缺口：Meta没有复用其他角色已有的单次格式修复。最小修复接入既有protocol_repair，只有已知完整协议失败才以新call_id重新请求一次，计入原预算；TLS/unknown不重发，第二次格式失败终止。没有添加reasonale别名或放宽角色schema。新增用例先RED（只调用一次），修复后与Meta/Challenge相关17项GREEN；Ruff、diff检查、快速门禁PASS。离线通过不替代下一批真实API验收。
