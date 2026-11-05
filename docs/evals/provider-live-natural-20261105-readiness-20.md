# readiness-20：带原文诊断的格式修复线上验证

第9轮自身修复3aaf2cf补充已有单次Reasoner格式修复的依据，不改变解析器。只有同Run/call/role且known invalid_json才传原始持久失败文本与json.loads错误message/position/line/column，并要求只修序列化，不重解/扩写。仅普通步骤和Challenge接入，原schema、provider payload/消息结构、一次上限及所有预算/身份/回执/审查绑定保持，unknown不重发。原因、替代方案与证据见provider-live-json-repair-20261105.md。

用户强调鲁棒性不硬编码，已另外只读执行六类语法故障检查：缺逗号、内嵌引号、代码字符串缺闭合、对象截断、Unicode/未转义换行、非法转义，均原样传入失败文本及解析位置；空文本/合法JSON无伪错误，跨Run/call/role/unknown不注入；无自动文字修补。结果保存在json-repair-robustness.json。7项公共流式接缝/保护回归与fast/Ruff通过，旧18/19四文本重放通过，但都不等于模型修复成功或数学能力提升。

北京时间21:25:11启动Run issue127-natural-20261105-readiness-20-run01。冻结revision62b975182c7ec8aee45c38a22fdbd0ae9221ae9e，source SHA3830de123bf14118e4088c9daf9997b48fedf870d747b60fe83d06372144ba27，manifest SHA6b2580982073e778de350ee6d3538e0ed1487b63dad2e73b580645ae04514648。同simple/octagon-colorings两题原字节/完整分母2、原模型及预算，独立8141服务真实PID13108/创建21:24:46.740688；runner42216/创建21:25:11.128685。实际source/script/data、监听PID、模型传输、样本字节和simple实际Job limits均核对。

观察器异常：runner于21:25:59.858373退出，Run状态stopped/unknown_job_status，observer_error.code=network_error，完成1/2。但21:26:05公共GET显示自然Job run_8fb476958c7c49f92f4416667fc3400a仍running/STEP_VERIFY（第一份Reasoner正常完成），服务PID仍在；不能把runner退出当模型失败。服务stderr同时出现Werkzeug rfile.read(10000000) MemoryError，具体内存根因及与network_error因果尚未确认。不重启/恢复runner、不并发新Run、不改冻结源码，只读监控现有服务端Job。

simple Job run_53efee839b24bd31c855ae414544b0a8 succeeded；自然题尚无最终交付。后续终态独立核验可能因观察器intent/计数而FAIL或UNKNOWN，必须如实报告，不改旧状态“凑完成”。每题128模型/HTTP、32工具、16777216预留、14400秒；单调用900秒、连续30秒无流停止；best-effort关闭，official baseline/身份/整题审查/最终文本绑定保留。用户批准的pure reasoning仅限制Reasoner，Verifier原受控计算保留。

累计repair_round9、implementation_round10、policy_change_rounds1、live_attempt12。已建立唯一每10分钟监控，服务端Job无实质变化静默，失败/完成通知；旧代理已关闭，无子代理持续轮询。

```powershell
uv run python .review/issue127-natural-20261105-readiness-20/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=13108 OR ProcessId=42216" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-20/logs/server.stderr.log -Tail 10
```

#127未验收/open，#128两臂NOT_RUN/open，不以局部格式修复回归代替线上完整闭环。

21:58终态核查：自然Job于21:54:24左右failed/star_needs_review，Solver interrupted/CHALLENGE，前2步接受、第3步VERIFYING。最后reason_noncoding从21:39:22.058750派发，首正文21:39:24.465587、末正文21:54:21.913639、末流活动21:54:23.162852，没有finish_reason或completion，触发900秒单调用硬截止，call unknown_outcome/error_category=timeout。是请求结果UNKNOWN，不是模型答错、JSON失败或30秒空闲；原请求不恢复重发。

自然题15模型/HTTP、2工具，本地charged824161/16777216、墙钟1740.21/14400秒，unresolved_attempts=1、unknown_tool_calls=0。Provider usage仍UNKNOWN；本批没有format repair调用，不能声称新修复有效或无效。非空partial不满足最终生成/整题审查绑定。无活跃模型调用，不把服务进程存活说成任务仍运行。

从公共GET做零模型独立核验：整体FAIL、task/process_path FAIL、transport PASS、coverage UNKNOWN（dispatch_intent_unresolved）、usage检查FAIL（budget_projection_mismatch），导出SHA154c49c9958cb0079384be61062819798192f6a34edac3329cc5f98737361ede。usage检查失败是runner早退的持久账本投影与服务终态不一致，不是将缺provider usage判FAIL，不能伪写PASS或改旧status/intent。该观察器证据缺口与Job900秒超时分别归档。

独立代理01a1ac02-0e9c-7ac2-afed-285f039eb4fd正在有界只读审查GET network_error后立即弃批与服务MemoryError证据，比较局部观察韧性改进与框架风险；未改源码、未新增修复轮或派发新Run。当前时点系统空闲物理内存约467MB/15541MB、空闲虚拟内存约3271MB；这是21:58后观测，不能反推21:25异常时用量或断言由本应用占满内存。两份存活历史Python服务私有内存约258MB和212MB，不归因全部系统内存压力。#127仍未验收，#128两臂NOT_RUN。
