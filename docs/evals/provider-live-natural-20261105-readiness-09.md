# readiness-09：修复循环第2轮

北京时间2026-11-05 13:33:48启动，Run issue127-natural-20261105-readiness-09-run01。干净revision bad1ad513fd2b7995cf30172809c868e47660e8d，source SHA2e7021d69eb98b5fd46ab9083107367952217d39bb2246fe70ab8e7506cc7cd3，manifest SHA741eb307a3154f085a5fa25603d5747e6c951a1e66b2f2573ad0c38f0984f4d1。

独立8130服务PID41132/创建13:33:29.974020，runner PID26532/创建13:33:48.293047；启动source/script/data目录核对，监听PID及公共实际模型/传输配置匹配后派发。原两题、模型thinking、32768输出、900秒调用/30秒无流活动/3600秒Run及原账本限制不变，best-effort关闭、usage UNKNOWN只观察。上一轮无在途调用后串行启动，不恢复或重发旧Run。

本轮修复为同scope成功工具回执后的明确CHALLENGE继续原挑战，重复工具不执行；见08最终记录。真实Harness回归及失败/unknown/ACCEPT负向回归通过，相关19项中1项条件跳过，快速门禁通过；独立审查未发现合同阻断。当前13:34:15观察0/2，简单题整题审查正在流式返回，尚未通过验收。逐调用流时间在observation快照，末正文在调用完成前仅为观察值。

唯一provider-live监控每10分钟，循环状态artifacts/provider-live-repair-cycle-20261105/cycle.json记录round2/new_error_rounds1。终态先诊断并独立核验，再按用户授权最小修复新Run复跑；超过5轮仍有新错误先做小型简化重构。#127未通过、#128两臂NOT_RUN，不宣称数学能力提升。

监控命令：uv run python .review/issue127-natural-20261105-readiness-09/audit_live.py；进程记录artifacts/issue127-natural-20261105-readiness-09/process.json；日志logs/run.stderr.log。活动Run源码冻结。


## 第2轮终态：北京时间14:11:32失败

runner正常退出、完成1/2。自然多步Job failed/star_needs_review，Solver interrupted/META_DECIDE，revision12882，step_2。最终Meta在出网前无响应头、正文或completion；前一已完成调用末正文14:11:24.949912、completion14:11:26.391966，自然多步首正文13:34:21.201055。末Meta记录14:11:30.786979开始、14:11:31.802397 unknown/adapter_error。

持久账本确认31 logical但30 HTTP，最后动作是Meta logical预留，没有对应HTTP预留。charged/reserved=2,074,314，token硬限2,097,152，剩余22,838小于冻结maxoutput32,768，即使输入为0也不足以下次HTTP预留。源码before_attempt会以run_model_budget_exhausted拒绝，流适配器通用异常路径将此已知本地预算拒绝包装为adapter_error/unknown。不是基于UNKNOWN推测网络失败，不放宽预算。正在补真实ledger+stream adapter的RED/GREEN回归并核对上层预算停止分类，不恢复或重发旧Run。

另有独立不一致：一次Explore工具timeout回执unknown_outcome=false（执行器已确认终止），但公共账本unknown_tool_calls=1，需独立审查timeout是否被错误等同未知。此处不推定已经修复。

独立总FAIL：transport FAIL/transport_calls_mismatch、task FAIL、usage FAIL/logical_call_count_mismatch、coverage FAIL、process_path FAIL。缺失provider计量仍UNKNOWN；此usage FAIL是调用账本不一致，不是缺usage字段。报告SHA b7f278b18c785a46444e73bef31bd337c8dfd4276cfba26225af328c4b2b3482。根因与流时间在terminal-diagnosis.json，原批次保持不变。新增根因轮次累计2，已实施修复仍2轮，未达5轮决策门槛。#127未通过、#128 NOT_RUN。

独立审查确认第二项实现缺陷：budgeted_tool结算未保留执行器明确unknown_outcome，_summary将全部timeout计未知；已确认终止且unknown_outcome=false的managed timeout被误计。修复必须保留历史缺字段timeout的保守未知，不能全删timeout计数。两项缺陷按同一修复轮处理，尚未宣称修复完成。已分派互不重叠的adapter与工具账本实现任务，等待RED/GREEN与集成检查后才启动第3轮。

第3轮前补充：两个子智能体已分别实现stream预算准入透传与tool timeout布尔证据结算；主线程新增Solver预算停止回归证明既有上层通道可用，无需新增状态框架。24项集成和快速门禁通过。Ruff现有导入排序仅作同文件一行修正。原09仍FAIL，不追溯重写或恢复，下一轮采用10的新Run身份，预算不放宽。
