# readiness-16：Meta证据投影补充后的真实重跑

北京时间2026-11-05 18:10:49启动Run issue127-natural-20261105-readiness-16-run01。冻结revision28bb774cb712954e8ef54751566b2bc419e9eecb，source SHA8727e1f0cdd735ae4c43ecd816bf6ac08ef17305f546f75c3f9aabc778a157d0，manifest SHA771b92655f4595f48167d8a5146304c3f3f241e125b7bc0d9f517e9798a07561。与15保持同simple/octagon-colorings两题原始字节、完整分母2和原配置预算，不拼接15的阶段结果。

第7轮修复提交5afe917仅补Meta状态投影：plan、复用既有有效性筛选的成果账本、同Run/plan/attempt且属于当前或有效接受步骤的真实成功回执摘要。失败/not-executed/unknown/无输出/跨作用域回执不进入新摘要，源状态不变，Meta仍无工具。没有改挑战上限、审查、最终文本绑定或官方baseline，best-effort保持关闭。独立策略比较后选择局部补充，未新建统一证据框架。

实际消息构造回归先RED再GREEN，相关22项、快速门禁和Ruff/diff通过；独立测试worker补9种负例通过。15单个终态只读重放提供3条成功摘要、2804 bytes；这是字节量，不是tokens或15个样本。原step6已有一条回执，新摘要有少量重复；原step1/2的Verifier成功回执仅在全局账本，确认此前投影遗漏。不能证明该遗漏单独导致15失败，亦不能保证新16完成，不宣称数学能力提升。15的有限挑战停止符合既有合同，其原FAIL及脱敏证据不升级。

独立8137服务实际PID30392/创建18:10:26.798717，runner实际PID12684/创建18:10:49.592415；CIM创建时间与记录仅微秒舍入差。已核对source/script/data目录、监听PID、公共实际模型/传输及样本字节，简单题实际Job预算limits逐字段匹配manifest。每题128模型/HTTP、32工具、16777216 token、14400秒；两题批次双倍；单调用900秒、30秒流空闲停止，intern-s2/thinking=false/temperature=0.2/32768输出保持。

18:11:02观察完成1/2，简单题run_c76028702f0eede058070853508d89de succeeded/completed_llm_reviewed；自然题随后串行派发，尚未终态或验收。repair_round=7（6次产品自身修复、1次自身样本登记更正），live_attempt=8、pre_dispatch_failures=1。旧子代理已关闭，现有provider-live监控已转移16，每10分钟检查，无变化静默、失败/完成通知。usage仍UNKNOWN。

监控命令（本工作树）：

```powershell
uv run python .review/issue127-natural-20261105-readiness-16/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=12684 OR ProcessId=30392" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-16/logs/run.stderr.log -Tail 10
```

#127尚未验收/open；#128两臂NOT_RUN/open。只有本批coverage/task/transport/process_path独立PASS、最终非空格式答案与整题审查同文本绑定成立后，才新冻结真实配对并从公共入口串行两臂。

终态追加：北京时间19:04:44.158228 runner正常退出，完成1/2。自然题run_53916465db5695964ce7d062dea37573 partial_aborted/TERMINAL，revision14554，result_reason=challenge_meta_limit_reached；公共star_needs_review，最后业务challenge_escalation_stopped。本次停在第1步，尚无接受步骤。自然题26模型/HTTP、2工具，24completed/2protocol_failed；Meta调用1次，整批加simple共29次模型调用。协议失败不等于未知远端结果；unresolved_attempts=0、unknown_tool_calls=0，usage仍UNKNOWN。

本地账本charged2189243/16777216、墙钟3219.83/14400秒；最后Researcher首正文19:03:45.065348、末正文19:04:38.992632、completion19:04:40.568682。没有TLS、硬预算、单调用900秒或30秒流空闲停止证据。非空partial文本不等于交付；whole_review_not_bound，缺最终生成/整题审查绑定。独立整体FAIL：coverage/task/process_path FAIL、transport PASS、usage UNKNOWN；脱敏导出SHA17ca0c3e86a68dd5deba7bbdba169ea6485b2fb8c7306c231d0cec2cce5669da。

具体分歧：模型生成的8步计划将D8×S3写为48个群元素，step7也要求除以48；题目给定D8阶16且S3阶6，实际96。末次Verifier明确指出该矛盾、要求的分类未完成，另有引用未执行回执的声明仍无支持。Meta承认96却返回CONTINUE，未重规划修改原目标；随后续答/审查/反例搜索仍CHALLENGE，按同step/plan/attempt只允许一次Meta升级的SP-05合同停止。不能将此解释为传输或预算缺陷，也不能仅据模型错误和未解决审查新增代码bug。

尚未确认新的工程缺陷；独立子智能体01a1ab6a-f7d2-75e0-9828-b7c29748895f正在有界复核。当前格式交付优先的用户目标与内部须步骤接受才能继续的严格合同存在本次运行上的冲突；先报告证据，不盲重跑、换题、增加cap或绕过审查。旧16原样归档，修复计数保持7，#127/#128保持开放。

进一步工程复现：Meta输出的CONTINUE策略没有回流到续答Reasoner。实际续答请求无meta/guidance字段，非Meta角色投影亦未包含meta_decision，旧48目标继续传入。公共SP-05既有测试新增断言先RED：期望Meta plan_summary而实际None；两个Reasoner角色的独立投影测试同样RED。此交接缺口与模型错误计划分别记录，不声称单独修复即可通过。候选仅将同Run/plan/attempt/step且未消费的CONTINUE决策作为Reasoner只读上下文，不改权威目标、cap或Verifier；独立策略评估完成前未修改产品源码或派发17。

独立审查最终确认上述handoff缺口，建议最小同scope只读策略注入。主线程采纳，context_injection.py新增7行，复用既有transition_decision，只向reasoner/reason_noncoding提供未消费CONTINUE决策；不自动改目标/计划，不把Meta建议当证明，Verifier不注入，不增加消费状态或通用交接机制。公共续答和投影回归RED→GREEN，24项聚焦（含原cap不重置）及快速门禁/Ruff/diff通过，baseline无差异。错误建议仍可能锚定Reasoner，独立审查继续把关，无法保证数学或整题完成。此为第8轮自身修复，旧16仍FAIL；新17保持两题原字节/原预算另行冻结。
