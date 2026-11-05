# readiness-10：第3轮真实重跑

北京时间2026-11-05 14:36:27启动。Run issue127-natural-20261105-readiness-10-run01，manifest SHA0354a3d7cadaac95536823f27b10b9d04f7c1b3d59a6478dc510f0c7af500b08；干净revision84fcc85a88b11f5d83d9a9ce2c36b4a7a03a15fd、source SHA1d2e3c3d203bc2732d924f1b92f240a8289a25c6d1067def1a3783e1a7379ca4。

独立8131服务PID24880/14:36:10.199768，runner PID15012/14:36:27.673002。source/script/data-dir启动校验及监听PID、公共applied config核对后串行派发。原两题/模型/thinking/传输/32768输出/900秒调用/30秒无流活动/3600秒Run和原账本限额均保持，best-effort关闭、usage UNKNOWN只观察。旧Run不恢复重发。

第2轮后两项最小修复：预算准入拒绝透传既有budget终态；已确认清理且unknown_outcome=false的工具timeout不误计未知。回归先RED后GREEN，24项集成通过，最后7项定向与快速门禁、Ruff通过，baseline无差异。修复不自动改善数学审查或保证交付。

14:36:58完成1/2：简单题Job run_2d9c5c138f1c66a5bd63b8196754cbf7 succeeded，非空文本且completed_llm_reviewed；自然多步Job run_0dc01cd4c4595b5564370c364f792b59 running/STEP_EXECUTE。首Reasoner正文14:36:52.527675，流仍进行，最终末正文须终态观察。完整逐调用时间与脱敏尾部由audit_live.py记录在artifacts/issue127-natural-20261105-readiness-10/observation-*.json。

唯一provider-live自动化每10分钟指向本批次，已实施修复3轮、新错误轮次2；5轮时独立比较局部修复与小型重构收益风险再选择。#127仍未通过，#128两臂NOT_RUN。监控命令：uv run python .review/issue127-natural-20261105-readiness-10/audit_live.py；process.json含PID/创建时间，logs/run.stderr.log保留错误尾部。运行中源码冻结。


## 第3轮终态：北京时间15:04:14真实预算停止

完成1/2，Job failed/star_needs_review；Solver partial_budget_exhausted/TERMINAL，revision10515，exhaustion_reason=shared_admission_budget_exhausted。计划3步，step1接受，step2仍核验；27 logical、26 HTTP、2工具，charged1,959,505/2,097,152。下一请求完整输入和冻结输出预留无法准入，未出网，末次call为budget_rejected/run_budget_exhausted。未知远端调用0、unresolved_attempts0、unknown_tool_calls0。第3轮两项分类修复在现场生效，不能再将真实预算停止算成adapter未知。

首正文14:36:45.849851，最后已完成正文15:04:08.152164、completion15:04:09.309250；被拒调用15:04:12无正文。没有final_generator或whole_solution_verifier调用，非空停止说明不构成交付。独立总FAIL，报告SHA6598d602f84b747e5e2f2ff419b2832b9e6c7c74630b1a8f01015aee7492f934；transport_calls_mismatch及logical_call_count_mismatch反映出网前拒绝导致的投影计数差异，不是实测网络失败，缺provider计量仍UNKNOWN。

下一步未盲目重跑或放宽预算。已委派独立子智能体评估同题继续局部修复、小型重构、重新预登记自然多步样本等方案。发现可量化重复上下文候选：末次request20,840 bytes（challenge_history12,243、report7,780），同session6条历史约99,032 bytes，旧request递增8,958至20,888 bytes，各响应约1.8k；是否可只去掉已由当前上下文覆盖的历史副本，须先证明保留报告/响应/回执和语义，不因文件大就删除。当前已实施修复仍3轮、新错误轮次仍2，真实预算停止本身不作为新代码bug。详见terminal-diagnosis.json。

后续量化结果：仅部分公共前缀精确相同，旧数组末尾裁决有变化。注入层保留差异尾部并引用当前完整数组中的相同前缀；真实只读重放99,032→75,345 bytes（净23,687），4条引用，旧列表均可精确重建。持久历史和响应原样，不增加预算。新RED/GREEN及快速门禁通过，后续准备新Run11；不能据此保证自然多步交付。
