# readiness-30：去除重复注入后的真实工程交接实验


## 终态：第12步单调用截止，未重现上下文超限

北京时间2026-11-06 14:26:16 runner退出。simple成功；自然题计划14步，已有11步审查记录（6 ACCEPTED、5 REVIEWED），在step12 Reasoner持续生成时达到单调用1200秒截止，Solver interrupted/STEP_EXECUTE，公共Job failed、error=star_needs_review、error_code为空。不能把非空final_response中的失败说明当最终答案。

末次调用14:06:09.960派发，首正文14:06:25.527，末正文14:26:10.552，末活动14:26:13.366；396事件、3222正文bytes，无finish/completion。持久事件activity_kind=deadline后unknown_outcome/timeout。不是30秒idle、未收到INPUT_LENGTH_ERROR，亦非Run总预算耗尽；提供方为何长时间未完成尚不明确。unknown请求不恢复或重发。账本unresolved_attempts=0不覆盖Solver持久unknown_outcome事实。

自然题33模型/HTTP、23工具账本计数；32条工具回执/预检记录不等于32次执行，unknown工具0。local charged/reserved 4397236/67108864、9701.04/28800秒，provider usage UNKNOWN。最终生成、整题审查、同文本绑定NOT_RUN。

零模型独立严格核验task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；工程完整分母2：simple PASS，自然题UNKNOWN（未知调用、未交付），批次FAIL。独立报告与terminal-diagnosis.json保存在本批ignored artifacts。#127保持open，#128两臂NOT_RUN；无代码修改，不增加工程修复轮。

最新用户仅授权相同输入超限原因时换领域题重跑一次。本次为单调用timeout，不满足条件，因此不自动换题、不增加时限、不启动新Run，等待用户决定；唯一监控保留并更新为等待状态。


北京时间2026-11-06 11:44:12启动。当前simple成功1/2，octagon-colorings已自然进入PLAN，尚未最终交付或独立核验。旧#127仍open，#128两臂NOT_RUN。

## 冻结与实际身份

- Run：`issue127-natural-20261106-readiness-30-run01`，独立端口8145。
- revision：`0eba346d5227babf86b662922e553cb102e2fb81`。
- source SHA：`8b8056345174cb7b628e936d49da535d29ae787bda6f9fca388b7d82c9e42163`。
- manifest SHA：`ff388abec61a2b6c93cc844bccb4f6027ef9cd1f3663fb4cb73464ac56c7a3db`。
- server SHA：`46c56f332acb224242397db04a6b316fff33a8a56d09e3705b36bdf409fe871e`。
- 服务实际PID26644/创建北京时间11:43:45.707605，runner实际PID20284/创建11:44:12.291454；CIM进程、创建时间、命令行和监听所有权已核对。
- 实际capabilities显示handoff-v1/acceptance_mode=handoff，intern-s2、thinking=false、temperature=0.2、32768输出、1200秒调用、stream_first；两个Job实际limits均与manifest一致。

仍是原simple/octagon-colorings两题原字节、完整分母2，不强迫Planner或工具，不拼接旧29结果。每题512模型/HTTP、128工具、67108864本地token预留、28800秒；批次双倍；无流30秒停止，best-effort=false，官方baseline/身份/真实审查与同文本绑定保留。usage UNKNOWN只观察。

## 第13轮修复及证据

[readiness-29](provider-live-natural-20261106-readiness-29.md)在完成9/13步审查后，step10原+repair均收到完整提供方INPUT_LENGTH_ERROR/finish error。旧Run与失败状态原样保留，终态零模型独立旧合同和新工程合同均FAIL；未恢复或重发原请求，旧服务已核身份停止。

现有记忆路径负责作用域隔离、持久历史和最新状态注入，并非按输入容量自动压缩/检索；旧去重只覆盖challenge_history，新reviewed_drafts被历史快照和当前投影反复携带。独立策略审查选择局部精确去重与通用finish error分类，不建通用压缩框架或新编排器。主线程采纳并于源码修改前持久化strategy-review-round13.json。

修复仅引用同Run/非空session_key/模式且完整前缀精确相等的历史注入副本，保留当前完整草稿，状态投影引用当前请求；持久原history/response/report/receipts不删。冻结29终态反事实消息重放从836145降为217684 bytes，完整草稿和持久记录一致。该重放不是原始HTTP或token测量，提供方精确上下文上限UNKNOWN，不保证完成。

完整finish_reason=error在JSON解析前记provider_generation_error/provider_failed并终止，不按正文字符串匹配、不再做格式repair；stop+非法JSON保留一次原修复，未完整流保持UNKNOWN。复审发现取消终态检查与保存之间的时序窗口，已将保护移至_save同一latest快照及既有revision CAS下；取消先提交不会被覆盖。独立复审通过；精确并发时序未另行复现，既有late-provider-error取消用例和3项产品控制回归通过。

42项聚焦通过，另3项产品控制回归通过；Ruff、fast和diff检查通过。测试包含stream/nonstream、任意非JSON/合法JSON错误正文、已知错误不重发、原格式修复和断流UNKNOWN、同scope匹配/不匹配、当前材料完整及持久历史不变。未跑耗时全量测试。两个子智能体均已关闭，不用代理轮询。

计数repair_round=13、policy_change_rounds=2、implementation_round=15、live_attempt=21；真实预算不足/TLS不计自身修复轮，本次是已确认自身重复与误分类修复。

## 初始实际Job与监控

simple `run_f02db777ba708241a609ef1c37f6777f`：4次调用、whole review完成、Job succeeded。自然题 `run_bb704583105548590639f6a08ec4c6c6`：正在PLAN，Planner首正文11:44:37.550932；后续首末正文/completion逐调用写入ignored artifacts的observation文件。

唯一自动监控provider-live已转移到30。手动查看：`powershell -NoProfile -File .review/issue127-natural-20261106-readiness-30/monitor.ps1`。活动Run源码冻结；不并发、不恢复重发unknown。终态分别运行本批verify_terminal.py和verify_handoff.py零模型核验，按完整分母2报告，不信result自报PASS，不因新工程PASS自动关闭原Issue或启动#128。
