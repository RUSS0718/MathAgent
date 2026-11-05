# readiness-08：新授权循环第1轮

2026-11-05北京时间13:18:25启动。Run issue127-natural-20261105-readiness-08-run01，manifest SHA-256 7efec49fb0d557a690816c6e5d9fb4225a0d7799f5d47f0d440fe0f4b9e54c9e。干净源码revision45b1d2f7452ea81f3e03a50166b3627b673a64e4，source SHA-256 604338e2df1ae00f161edf1dfcc9af696130de6d4c4dfe405c0e31186156b40a。

独立服务8129、PID13368，创建于北京时间13:18:03.893114；runner PID18660，创建于13:18:25.313665。启动时核对source/script/data-dir；派发前核对监听PID及公共实际模型/传输配置。两题同07，模型intern-s2、thinking=false、32768输出、stream_first，每调用900秒、30秒无流活动停止，Run3600秒及原账本限制不变，best-effort关闭，usage只观察UNKNOWN。旧Run不恢复重发。

13:18:59观察完成1/2：简单题Job run_916342062c2513c25cd8d9b9fa90663b成功，非空文本且completed_llm_reviewed；自然多步Job run_86ac87999e5d6994f8f6897b639072a8正在EXPLORE，尚无最终交付。逐调用首末正文时间由audit_live.py保存在本批次observation快照中；在途末正文仅是观察值。

本次修复为安全工具错误反馈及参数纠正提示，见provider-live-repair-cycle-20261105.md；新增回归先RED后GREEN，相关28项中1项条件跳过，新增实际provider消息检查通过，快速门禁通过。没有以离线测试替代真实API验收。

唯一自动化provider-live每10分钟监控，并按用户授权诊断→最小修复→新Run重跑；超过5轮仍有新错误时先做小型简化重构。当前新授权轮次1、新错误轮次0。运行中冻结源码；#127尚未通过，#128两臂NOT_RUN，均不关闭。没有数学能力提升结论。


## 第1轮终态：13:24:44失败

完成1/2，自然多步partial_aborted/STEP_VERIFY，revision4546，step_1。11次模型/HTTP，6次工具，unknown_outcome=0；末正文13:24:42.909104、completion13:24:43.398921，首正文13:18:43.510548（北京时间）。没有最终生成或整题审查，非空终止说明不是交付答案。

此次失败是新根因：Verifier自己发起的python_math已成功（executed/output_available=true、exit_code0），同scope round1的回执已送入续接，但它以CHALLENGE/PARTIAL/FAIL明确给出异议时又附上相同digest请求。continue_review无条件将该重复视为未履行，最终verifier_tool_request_unfulfilled；不是上轮参数非法或工具失败。独立总FAIL，transport PASS、task/coverage/process_path FAIL、usage UNKNOWN。报告SHA bd0e993edab73c2dd3f4903c72395e6f21c5cdcf7de69c5fefcff0b035a32457，terminal-diagnosis.json保存脱敏事实。

第2轮前最小修复：只对步骤核验的明确CHALLENGE、且同scope真实成功有输出/exit_code0的既有回执，移除冗余tool_request并交由原业务校验处理异议，不重复执行或新增调用。ACCEPT、失败或未知回执仍停止；新请求仍受原次数与预算限制。新增真实Harness回归确认一次工具执行后可通过原挑战补充流程继续；RED后GREEN，相关19项中1项跳过，新增完整路径单独通过，快速门禁通过。不是放行接受裁决或数学能力结论。
