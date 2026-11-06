# readiness-18：用户批准的纯推理角色作用域

用户明确选择Meta纯推理仅限制Reasoner，Verifier保留原白名单、隔离和预算内独立计算。SP-06合同已追加新作用域，65cc804实现：执行预检、工具广告和只读工具三处既有gate按运行时角色限制Reasoner。未标source_role的普通预检默认Reasoner，只有内部Verifier路径传递自身角色；模型自报role/source_role不能授权。Meta数据与审查/绑定/cap不改，没有新增权限框架或工具。

公共Job作用域、Verifier实际计算/回执消费、0工具额度拒绝、Reasoner保持禁止、冒充角色、旧deadline/取消等30项聚焦检查通过，fast/Ruff/diff通过，官方baseline无差异。新合同用例先RED后GREEN，既有全局拒绝Verifier单测按用户选择更新。独立代理01a1ab94-e473-7913-8383-5a1a1b598360支持局部三gate方案，未采用统一RolePolicy框架，比较保存在policy-scope-review-01.json。17的旧行为不追溯算工程bug，旧FAIL仍保留。

北京时间2026-11-05 20:10:18启动Run issue127-natural-20261105-readiness-18-run01，冻结revision8c89f9388f67cc7b43d4e41856de3aa818e69bac，source SHA66f36d4369d4bf067f7972b9c0ad410fef9da5c88a790114496d45595867149c，manifest SHAa651e79e785b800296ebea68b9e2bb50b75a4f1fb0c9a452c1e0a2ece38a0519。同simple/octagon-colorings两题原字节、完整分母2、原模型thinking/传输和预算，不拼接旧批次、不强迫planner或工具。

独立8139服务实际PID8756/创建20:09:39.006687，runner实际PID38404/创建20:10:18.155890；CIM仅微秒舍入差。初次只读预检时service-startup尚未写入，服务随后正常就绪；没有派发失败请求或重复启动。已核对source/script/data、监听PID、实际模型/传输、样本字节及简单题实际Job limits。

每题128模型/HTTP、32工具、16777216 token、14400秒，两题批次双倍；单调用900秒、30秒无流停止；intern-s2、thinking=false、temperature=0.2、32768输出、best-effort关闭，原隔离、回执保护、整题审查及最终绑定保持。Verifier新许可不增加工具额度，也不能把失败/未知/未执行回执当成功。

20:10:45观察完成1/2：简单题run_b7bc52b8d9dc643a304caa48ff0a945e succeeded/completed_llm_reviewed，自然题run_2ace33865489f1d55fa225a48b9580c5 running/PLAN。Planner首正文20:10:35.350024，仍持续输出，尚无终态/最终答案或独立PASS结论；usage UNKNOWN只观察。没有证据时不声称新作用域在线触发。

修复计数repair_round仍8；另记用户批准policy_change_rounds=1、implementation_round=9、live_attempt=10、pre_dispatch_failures=1，避免把合同变化伪装成旧运行时bug。旧provider-live临时监控曾在无Run待决策时删除；用户已选择且新Run启动后恢复同ID的唯一每10分钟监控，没有重复监控。无变化静默，失败/完成通知；旧诊断代理均已关闭。

```powershell
uv run python .review/issue127-natural-20261105-readiness-18/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=38404 OR ProcessId=8756" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-18/logs/run.stderr.log -Tail 10
```

#127未验收/open；#128两臂NOT_RUN/open。终态零模型独立核验coverage/task/transport/process_path及最终格式答案/整题审查同文本绑定，通过后才执行真实单因素pair。不宣称数学能力提升。

20:40只读监控确认：runner已于20:21:24.791524正常退出，服务8756和runner38404真实进程均不存在，8139公共GET连接被拒绝，不再把cycle.json的running视为活跃。持久Run stopped、完成1/2、stop_reason=job_failed_or_canceled；自然题DB Job failed/error_code=protocol_failure_unrepaired，Solver partial_aborted/TERMINAL，在S1第一份步骤报告之前停止。

直接停因：原Reasoner及一次repair-1均完整finish_reason=stop，却返回结构不合法JSON。严格json.loads及既有非法转义救援均报Expecting ',' delimiter，原文本pos2586/2724chars、修复pos17011/17149chars，属于结构序列化问题，未见仅非法反斜杠转义的证据。未执行工具、未进入Verifier，新纯推理角色作用域本批线上未覆盖；不是“Verifier策略修复已通过”。

自然题4模型/HTTP、0工具，本地charged168616/16777216、墙钟652.07/14400秒，unresolved_attempts=0、unknown_tool_calls=0；usage保持UNKNOWN。原Reasoner正文首20:10:53.674586、末20:11:24.568302、completion20:11:24.801681；格式修复正文首20:11:26.398799、末20:21:23.155513、completion20:21:23.808359。没有TLS、900秒调用超时或30秒流空闲停止证据，非空失败文本不等于完整生成/整题审查绑定。

公共服务已退出，未重启原Run，完整公共GET独立核验无法完成。以零模型派发的不可用读取器运行现有核验器，报告明确UNKNOWN/job_evidence_unavailable（不是PASS），导出SHA1911b8f71bef57e0e1120a6a4b1912f32d4c89460ab70317602e77144c995ec4；另存terminal-diagnosis.json区分DB已确认FAIL与独立公共核验UNKNOWN，不把服务不可用误当模型请求未知。当前未确认新的工程缺陷，独立子智能体只读复核JSON结构，不修改解析器、不扩大修复次数或盲重跑。#127仍未通过/open，#128两臂NOT_RUN/open。

诊断收束：未发现解析器误拒合法JSON的新证据，不加补丁/修复轮或新调用。辅助代理基于短片段的判断不作为原文独立核验；尤其finite_computat只是诊断输出截短，不得推断真实文本在此截断（原文末字符为右大括号，finish stop）。本轮仅能确认严格解析及现有救援均拒绝结构不合法文本，不能安全猜测模型意图修补。已无活跃Run，临时监控移除以免轮询残留状态；此不等于Issue验收完成，127保持未通过、128两臂NOT_RUN。
