# readiness-21：1200秒单调用试验

北京时间22:34:35启动issue127-natural-20261105-readiness-21-run01，独立8142。用户此前授权同题持续生成时适度提高时间，单调用900→1200秒；原Run14400秒、30秒无流停止、模型/HTTP128、工具32、预留16777216、两题批次双倍及32768输出保持。产品源码无变更，不计新工程修复轮，live_attempt=13，repair_round=9。

冻结revision22017deaf11596620ed5c2d00ca5deeb4b0483e2、source SHA3830de123bf14118e4088c9daf9997b48fedf870d747b60fe83d06372144ba27、manifest SHA01286f7abd0118bc52984fe9d26853f394f7f2b87917c7e005ef38c3432662ef。服务实际PID9584/创建22:34:10.616800，runner实际PID31736/创建22:34:35.931852；来源/script/data、监听PID、公共capabilities实际timeout1200与模型传输、样本字节及simple实际Job limits均核对。

启动前系统freePhysical1205MB/freeVirtual5944MB，较之前160MB物理可用内存明显恢复；不等于保证没有未来内存压力。未关闭其他应用，旧19/20已结束服务此前已核对身份清理。等待资源期间的监控已经恢复，用户明确要求不留监控空档；现有唯一provider-live每10分钟监控已转移21。

22:34:49观察完成1/2，simple run_70edbe589cae4c5d4f95485d2bd7d4e2 succeeded/completed_llm_reviewed；自然题随后串行派发，尚无独立终态或最终答案。best-effort关闭、official baseline/身份/整题审查/最终绑定保持；usage UNKNOWN只观察不标PASS。

```powershell
uv run python .review/issue127-natural-20261105-readiness-21/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=31736 OR ProcessId=9584" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-21/logs/run.stderr.log -Tail 10
```

旧20未知请求不恢复重发，不拼接旧结果。#127尚未验收/open，#128两臂NOT_RUN/open，不宣称数学能力提升。

终态：北京时间22:44:06.862395 runner正常退出，完成1/2；自然题前4步ACCEPTED，第5步VERIFYING、invalid_verifier_response/valid=false，公共star_needs_review、Solver partial_aborted/STEP_VERIFY。Verifier原回复及一次既有repair均finish_reason=stop/invalid_json；原文严格解析在结尾缺JSON分隔，repair在代码字符串边界Expecting ',' delimiter。不是1200秒/Run超预算、TLS或30秒流空闲停止。

自然题13模型/HTTP、1工具，本地charged695816/16777216、墙钟555.25/14400秒，unresolved_attempts=0、unknown_tool_calls=0，usage仍UNKNOWN。末Verifier首正文22:42:07.464680、末22:44:05.373529、completion22:44:06.110736。非空partial仍whole_review_not_bound，未完成最终生成/整题审查绑定。

公共GET独立整体FAIL：task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；脱敏导出SHA c0dd26e688f615f23054ce176e3a592127f41903e8c1ffd736aeab32c8c980ba。此次没有到1200秒限制，不能据此评价加300秒效果。旧21保持原样，不续跑。

确认同根因范围缺口候选：此前原文定位机制只由Reasoner两路径传入，Verifier既有repair入口仍缺failed_call。独立子智能体01a1ac33-efca-72f1-af27-befcb0ed1bd5正比较最小复用与统一dispatch框架风险；主线程新增step/plan-whole/fast-whole三条流式公共路径回归，先确认修复请求是否缺原文。不新增计算续接重试或结构语义修复次数，不猜补JSON，不写题目/code特例。确认后只复用既有一次repair，不能承诺模型因此一定修好；#127/#128仍open，128两臂NOT_RUN。
