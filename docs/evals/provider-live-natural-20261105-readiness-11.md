# readiness-11：第4轮与用户授权的新预算

北京时间2026-11-05 15:25:41启动。Run issue127-natural-20261105-readiness-11-run01，manifest SHA426f1aea0bcd71e92dc6d9bdebe921daac1faa883efe7f9f2c2168b54e600563，干净revision68bf81947962b723a87646f501fd4edc35851ee0，source SHA99814e1bb981553588fcc5e64bdb8d2372b905f7f6787ec4585d6a57fa3bfc07。

用户在本批次冻结前明确授权增加预算：每题128模型/HTTP、32工具、16777216 token预留、14400秒；两题批次256模型/HTTP、64工具、33554432预留、28800秒。单次调用900秒、连续30秒无流活动仍停止，模型intern-s2/thinking=false/32768输出/stream_first及原两题保持，best-effort关闭、整题审查与最终绑定启用。不是运行中扩限，旧Run10预算与FAIL不改写。

独立8132服务PID28252/创建15:25:21.938663，runner PID22552/创建15:25:41.144751。启动source/script/data-dir、监听PID、公共模型/传输均核对；派发后公共Job预算limits与新manifest逐项相等，不只看声明。

15:26:17完成1/2：简单题run_6f250d2c59b41e26247684c10147df63 succeeded；自然多步run_dd9b70534d7cef9c76a9577964ddbde5 running/STEP_EXECUTE。Reasoner首正文15:26:11.011734，仍在流中，末时间以终态为准。完整逐调用首末正文由audit_live.py写入artifacts/issue127-natural-20261105-readiness-11/observation快照。

ad7db15最小上下文简化仅引用同scope同step的逐项精确公共挑战前缀，保留不同尾部，可重建旧列表，持久history/report/response/receipt原样。真实旧10只读量化session99,032→75,345 bytes；不等于token，不宣称因果收益（本轮预算亦经用户授权改变）。49项回归1条件跳过、快速门禁/Ruff通过、独立审查无阻断。#127仍未通过，#128两臂NOT_RUN，不声称数学能力提升。

唯一provider-live监控每10分钟已转移本批次；已实施修复4轮、新错误轮次2，达到5轮仍做独立收益风险评估再选择。监控：uv run python .review/issue127-natural-20261105-readiness-11/audit_live.py；process.json为PID/创建时间，logs/run.stderr.log为错误尾部。运行中源码冻结。


## 终态：15:29:39 TLS失败

Run完成1/2，runner正常退出。自然多步Job failed/star_needs_review，Solver interrupted/CHALLENGE，最后Reasoner unknown_outcome/tls，HTTP约5.093秒后失败，无响应头/正文/completion，unresolved_attempts=1。此前9次已完整返回，本次10模型/HTTP、3工具（均success），charged505726/16777216，墙钟约219.599秒/14400；预算充足。缺最终答案、整题审查及绑定，非空停止说明不构成交付。原未知调用不重发、不恢复。

独立总FAIL，transport PASS仅为profile配置一致，不能表示所有物理请求成功；task/coverage/process_path FAIL，usage UNKNOWN。独立报告SHA c4dd673f3607253e5b6b206ebcacf32852646439087241cd7f1c0f2d43f96be4。逐调用时间与诊断在terminal-diagnosis.json。保留原SSL细节不足，不能判为证书过期、服务端重置或某一特定网络原因。

15:40:12仅用默认验证socket+ssl做两次TLS握手，TLSv1.3、证书验证成功，耗时0.125/0.093秒，零HTTP/模型。只证明检查时连接已恢复，不改变旧请求UNKNOWN。计划经独立审查后以新manifest/Run12单独尝试，沿用相同源码/预算/样本，不修改TLS验证或增加自动重试。不属于第5轮代码修复：repair_round仍4，另计新授权后的live_attempt5。
