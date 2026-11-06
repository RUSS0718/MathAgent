# readiness-13：Meta单次格式修复后的真实重跑

北京时间2026-11-05 16:02:11启动，新Run issue127-natural-20261105-readiness-13-run01。冻结干净revision f3c33cc00742602f6a63061ba65563f08a1364d8，source SHA a30dab8ae9701d3c0014d8f54ce63c60ea897139ba5f1abe9038510d04e3f754，manifest SHA 338b193984239626562ab9d8896ce6220673d086f4ef8334e46615587fad1740。原12不恢复、不改写。

代码修复提交8a02776：Meta复用已有单次格式修复，已知完整协议错误才新call_id派发一次，原预算、TLS/unknown不重发及第二次失败停止保持。17项聚焦、快速门禁、Ruff/diff通过。第5轮独立审查无阻断，主线程选择局部复用，未实施全角色dispatch重构；比较、限制与计数规则见循环记录。repair_round=5，live_attempt=6；TLS/真实预算不足不计自身修复轮。

独立8134服务真实PID34852/创建16:01:32.965162，runner真实PID14748/创建16:02:11.348248；已核对实际进程、监听PID、source/script/data目录、公共applied model/transport。每题预算128模型/HTTP、32工具、16777216 token预留、14400秒，两题批次双倍；模型intern-s2/thinking=false/temperature=0.2、32768输出、900秒单调用、30秒流空闲停止，best-effort关闭、整题审查与绑定保留。简单题实际Job账本limits与manifest一致。

16:03:15只读观察：完成1/2，简单题run_f79b658356ff77babf02301130162b12 succeeded/completed_llm_reviewed；自然题run_d7781e11184cef98ee198f186c8ecdbe running/EXPLORE，未交付。当前正文流仍活动，不能把进程文件phase=starting当作Solver阶段。逐调用首末正文、completion及完整安全观察保存在本批artifacts，不代表自然多步已通过。

现有provider-live定时监控已转移到13，每10分钟检查，无变化静默，失败/完成才通知。不并行新增监控、不用子代理轮询。终态后零模型派发独立核验coverage/task/transport/process_path及整题审查同文本绑定，满足后才执行#128。当前#127未验收/open，#128两臂NOT_RUN/open，usage UNKNOWN，不宣称数学能力提升。

直接监控命令（在本工作树执行）：

```powershell
uv run python .review/issue127-natural-20261105-readiness-13/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=14748 OR ProcessId=34852" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-13/logs/run.stderr.log -Tail 10
```

终态追加：16:03:47.605442 runner正常退出，完成2/2。自然题同样completed_llm_reviewed，0计划步骤、4次模型/HTTP、0工具；其中首次Explore完整协议错误后由既有单次修复成功继续，之后Explore_polish和整题审查完成。没有进入Meta，故本批不能证明新增Meta修复已在线触发。

独立核验结果：task/coverage/transport PASS，usage UNKNOWN，process_path NOT_RUN（natural_multistep_path_not_observed，completed_without_plan=1、path_completed=0），整体NOT_RUN。这是自然多步验收范围未覆盖，不是未派发、模型答错或新增代码缺陷。两题非空答案与整题审查同文本绑定成立；审查是LLM review，不证明数学正确性。

自然题整题审查首正文16:03:41.305699、末正文16:03:47.025682、completion16:03:47.181307；自然题charged166132/16777216、墙钟73.07秒、unresolved_attempts=0。逐调用流时间在原观察归档；usage未知保持UNKNOWN。独立导出SHA256 5655f5d8a8c0ed6d0969a9d88bdc7fbd30d0eb3ce5635c5d1954fc2a5c2caebc。

后续仅重新登记更适合自然拆分的题目，不修改路由、不强迫planner/工具、不增加修复轮数；完整保留本批分母与未覆盖结果，不与新题结果拼接。#127仍未通过，#128两臂NOT_RUN。
