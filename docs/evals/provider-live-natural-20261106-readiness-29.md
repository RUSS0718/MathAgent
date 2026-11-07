# readiness-29：独立工程交接与格式交付实验

2026-11-06北京时间10:23启动，当前完成1/2；简单题成功，八边形题自然进入Planner和Reasoner，仍在执行。最终交付及独立工程核验尚未完成。不能据此宣布#127 PASS；#128两臂NOT_RUN。

## 冻结身份及实际配置

- Run：`issue127-natural-20261106-readiness-29-run01`，独立端口8144。
- revision：`5c504eb0b3542c556c24ce8c3fcc0ae878c284c4`；实现提交`da42f17`，后续只清理测试文件尾空行。
- source SHA：`a93779ab12b5a779770605134f42609b2322ae77c69ffc81af0efc77940a8f6e`。
- manifest SHA：`90358ef875f504ea8e71bdb74de51f1af4536186f7795cd9a23f764e629d3422`。
- server SHA：`221c600d1918bfb5fe0f96671f2d02ed3d2c8e2bf65f2f9443093c5329bd53fe`。
- 服务PID30548，创建北京时间10:22:38.479853；runner PID6436，创建10:23:01.609076。CIM真实进程、命令行、创建时间和8144监听已核对。
- 实际capabilities显示`acceptance_mode=handoff`、`preset_version=handoff-v1`，BestEffort入口禁用；实际模型intern-s2、thinking=false、temperature=0.2、输出32768、请求1200秒、stream_first已核对。
- 两个实际Job账本limits均与manifest一致：每题512模型/HTTP、128工具、67108864本地预留、28800秒；批次双倍。30秒无流停止保持，provider usage UNKNOWN只观察。

完整登记分母仍为原simple/octagon-colorings两题原字节，未拼接旧批次、未强迫Planner或工具。原预算草案及提交前临时冻结没有派发，不与本身份混用。

## 新合同与验证

用户明确批准[工程交接合同](../engineering/handoff-delivery-contract.md)。合法CHALLENGE报告连同异议按reviewed_drafts传递，不变成已接受事实；TRACE_BACK/PROPOSE_REPLAN保留既有控制路由。真实整题REJECT仍保持数学NEEDS_REVIEW，工程交付另行独立核验。官方baseline不变，best-effort=false，硬预算/身份/真实回执/整题审查及同文本绑定保留。

修改前独立策略比较选择局部接线；复审收紧控制裁决边界。Harness与实际HTTP公共Job共8项通过；既有finalization/证明/绑定/规划聚焦回归及runtime检查通过，12项有条件测试跳过。fast、Ruff通过；新增测试尾空行已清理，diff check通过。没有跑耗时全量测试，也不把离线通过当线上完成。

真实Job：simple `run_442cab1ab9a976774b01a26ca18dddcd`成功，4次模型调用并完成整题审查；octagon `run_00d77836f8d035feb4133d908a3f047d`在STEP_EXECUTE，当前Reasoner首正文10:24:01.658515，10:24:23.723202仍在输出；不是终态时间。逐调用首末正文、completion、预算和状态持续写入ignored artifacts中的observation文件。

独立核验分开执行：原`verify_terminal.py`保留旧#127严格合同结果；`verify_handoff.py`从真实公共Job及只读DB独立核对草稿交接和审查文本身份，不信任result自报PASS。任一未知/未履行/身份或预算故障/缺审查绑定均不得工程PASS；完整分母2，不以触发子集替换。

修复轮仍12；本次为第二次用户批准策略调整，implementation_round14，live_attempt20。唯一10分钟监控`provider-live`已创建；其他窗口两个PAUSED任务未动。活动Run源码冻结，不并发派发、不恢复或重发unknown；只有明确工程缺陷才进入最小修复和新身份重跑。

## 本地监控

在工作树执行：`powershell -NoProfile -File .review/issue127-natural-20261106-readiness-29/monitor.ps1`。显示真实PID/创建时间、公共阶段/完成数/流时间和脱敏runner日志尾；进程不存在不能把残留状态文件当作活跃证据。

## 11:22终态及失败诊断

runner于北京时间11:22:39.049706正常退出（exit 0仅说明CLI正常结束，不是实验PASS）。自然题Job failed、Solver partial_aborted/protocol_failure_unrepaired，完成9/13步审查（5 ACCEPTED、4 REVIEWED），第10步Reasoner失败；最终生成、整题审查、交付绑定均未运行。简单题成功，完整分母2仍只有1题交付。

直接提供方证据：第10步原调用及唯一repair-1均返回完整68字节正文`internal error happened, status code ResponseType.INPUT_LENGTH_ERROR`，finish_reason=error。系统随后误按invalid_json处理，第一次错误引发一次无效的格式修复。这不是模型生成非法JSON的证据；提供方输入长度错误与应用误分类应分开记录。提供方精确token上下文上限未知，不能把本地UTF8输入估算当成provider token数。

原调用首正文11:22:20.134355、最后正文同一时间，completion 11:22:21.608611；repair首末正文11:22:35.765267，completion 11:22:37.296152。自然题首正文10:23:24.469554，末正文11:22:35.765267。不是1200秒截止、30秒idle或Run总预算停止。自然题25模型/HTTP、12次实际隔离工具（均success），另有26条回执/检查记录；未知远端和未知工具均0。本地charged/reserved 6,247,077 / 67,108,864，usage UNKNOWN。

只读终态重放已确认重复注入：第10步当前9条reviewed_drafts为132389 bytes，Reasoner会话保留9次完整历史；其中8份旧草稿快照精确等于当前草稿前缀，共424328 bytes。仅把注入层旧副本替换成对当前完整前缀的引用，保留原持久历史/响应/报告/回执，可将历史注入465088降为41288 bytes。该重放不是原完整HTTP消息，也不是provider token测量；实际请求本地输入估算为837827 bytes，repair为838995。较大的输入包含其他层，不能把历史节省量直接当作整个请求的新长度或保证完成。

独立旧合同：transport PASS、task/coverage/process_path FAIL、usage UNKNOWN，报告SHA fa41e5487525fe81b427efd6c5ff35c7709855f4ccf09007b947d75f6960cbe5。独立工程合同：simple PASS、自然题FAIL，最终审查NOT_RUN、binding=false，完整分母2，整体FAIL。表面非空final_response是停止说明，不是答案交付。#127仍open，#128两臂NOT_RUN。

下一步先独立比较小范围精确注入去重与重构风险，并为通用finish_reason=error分类补快速RED；尚未实施下一轮修复，不增加repair_round或启动新Run。证据在ignored artifacts/本批terminal-diagnosis.json、context-size-replay.json及两份独立报告中。
