# readiness-06：状态写入修复后的独立真实 API Run

截至 2026-11-05 03:23:24 UTC，Run **已执行、未完成**，持久完成计数 1/2。简单题成功，自然多步 Job 正在 PLAN。尚无自然多步最终答案、整题审查和最终绑定，不能判 readiness PASS。

## 冻结身份与执行限制

- Run：`issue127-natural-20261105-readiness-06-run01`。
- manifest SHA-256：`593a3d7957a6c2af2606587245639785410f7f005c568dbfa14b417b9de8e6cd`。
- source revision：`8f57264c44723cfe002f61300d6ebe734cc5ccfa`；source SHA-256：`4a79cbb8135e9b115886d8ea0b00a43a6480585c21c0762bf8f28090e606bdca`，含登记的未提交代码和测试差异。
- 样本：simple、vieta-equation，共2题。输入 SHA 分别为 `389ac0685cb60be93ca7d309ad245b9455da5e44159c65ae5d12c5c897c56dde`、`4c27c774fdae1528a41bdd5d3a55bff75af3fb31dca17d0f97aa1d5f6c630f99`。未强迫模型走 Planner 或工具。
- 模型 `intern-s2`，thinking=false，temperature=0.2，max_output_tokens=32768，request_timeout=900，retry=1（一次物理尝试），`star_reference`，`stream_first`。
- 每调用硬截止900秒，连续30秒无流活动停止，Run总截止3600秒。模型/HTTP各最多32次、工具8次、tokens 2097152；批次上限和原停止条件保持冻结，运行中不放宽。
- usage `observe_only`，缺失保留UNKNOWN；best-effort关闭，整题审查和最终绑定保持启用。

## 隔离与派发

服务使用独立端口8127与本批次server-data。服务实际PID **35516**，创建于 `2026-11-05T03:22:21.860722Z`；runner实际PID **19776**，创建于 `2026-11-05T03:22:57.025635Z`。完整路径、源码、脚本SHA和PID记录于本批次 `service-startup.json`、`process.json`、`execution-policy.json`。

服务启动时校验冻结source及server.py SHA；launch再次对齐source、脚本和数据目录。派发前还核对8127监听PID与startup相同，并通过该端口的公共 `/api/capabilities` 核对实际模型/transport配置。未使用旧8126配置代替。

readiness-05 因源码身份不一致取消，最后在途调用于 `03:22:30.152683 UTC` 结束；确认无dispatched/streaming/pending调用后才启动06 runner，不重发或恢复05。05/06结果不拼接。

## 初始线上证据

简单题 Job `run_0c8db1d586742aba527df1d8cd3c0c5d` succeeded，返回非空最终文本，Solver `completed_llm_reviewed`。整题审查调用首正文 `03:23:16.271101 UTC`、末正文 `03:23:18.474642 UTC`、completion `03:23:18.576661 UTC`；全题结果仍待批次结束后的独立核验。

自然多步 Job `run_4e750b0e384bb009d4dc27a44ba8b62f` running / PLAN，已自然进入Planner，首正文 `03:23:24.420547 UTC`。本次快照尚未完成该调用，不将观察时的末正文当成最终时间。脱敏快照在 `artifacts/issue127-natural-20261105-readiness-06/observation-20261105T032324.json`。

当前唯一30分钟heartbeat已转移到06，状态无变化静默；不以子智能体轮询。只读入口：`uv run python .review/issue127-natural-20261105-readiness-06/audit_live.py`。

本批次未运行完整全仓测试；状态替换修复的29项回归通过，相关既有测试和快速门禁结果见05记录。#127保持open、未验收；#128两臂NOT_RUN/open。当前结果不证明数学正确性或能力提升。

03:25:30 UTC复核：runner PID19776仍存活，持久phase=running、completed=1/2、stop_reason=null；source_identity与冻结值仍相同。自然多步Job推进至STEP_VERIFY，已报告第二个step的状态记录，并有Researcher调用在流式执行；尚未最终交付。最新快照 `observation-20261105T032530.json`。独立代码复核未发现新的已确认阻断缺陷；该结论限于本轮公开证据链，不代表全仓无bug。当前停止开发与重复离线检查，保持冻结源码等待本Run终态；唯一heartbeat归属06，不重复派发。

03:39 UTC只读观察：自然多步当前step_2，step_1已ACCEPTED，计划共5步；已计21次模型调用、1次工具调用。出现过1次完整stop返回但JSON语法无效的Reasoner响应；独立json.loads同样在第1行第698列报告缺少逗号分隔符，已用原合同中的一次格式修复成功续接，未知请求计数为0。该诊断只保留公开调用别名、格式错误位置和响应SHA，位于 `format-diagnostic.json`，不保存原文。当前不把格式失败当作解析器bug或数学能力结论。#128仅准备脚本，不派发、不提前生成PASS收据。

03:57 UTC：Meta真实流已完整完成并继续交接给Reasoner（第28次调用），不再出现旧白名单出网拒绝或usage sidecar解析拒绝。step_2仍为STALEMATE后继续处理，只有step_1为ACCEPTED；计划5步，尚无最终答案。此时观察到的是业务核验反复质疑，不能据此判定数学对错；32次硬调用上限不放宽。

等待期间仅复跑历史记录的3个失败用例：guidance恢复与RB06 HTTP截止当前通过，RB03非法声明的第一个子项仍因预期4次/实际5次失败，3项总耗时15.339秒。独立诊断确认第5次是提交1447160已登记的一次claim-target-repair，角色step_verifier、独立:repair-1身份，最终failed/STEP_VERIFY，valid=false，逻辑和HTTP均5、未知0、Researcher0。它符合RB03非法声明不能接受的合同；旧4次预期过时。最小修正待冻结运行结束后安排，不据本轮单次通过声称已穷尽偶发故障。

## 最终终态与独立核验

Run于2026-11-05 04:09:01 UTC停止，完成1/2，runner正常退出，原stop_reason=job_failed_or_canceled。自然多步Job为failed，公共错误码star_needs_review；Solver为TERMINAL / partial_aborted，revision10199，result_reason=challenge_meta_limit_reached。最终事件challenge_escalation_stopped，upgrade_reason=meta_escalation_limit_reached：同一step_2完成有界挑战并经Meta继续处理后，步骤核验仍为valid=true、CHALLENGE/PARTIAL/UNCERTAIN，控制器按有界升级规则结束。没有最终生成或整题审查调用。存在非空终止说明文本，不能当作题目答案交付；外层同文本artifact校验也不能替代whole_solution_llm_review绑定。

自然多步首正文03:23:22.350873 UTC、末正文04:08:56.133869 UTC，末次completion04:08:58.227226 UTC。最长已完成模型调用299.400569秒，未触及900秒；没有30秒流空闲停止或未知远端结果。模型/HTTP各30/32，工具2/8，charged/reserved=1,929,714/2,097,152，墙钟约2739.882秒/3600秒。最终停因不是硬预算耗尽。此前29/32时所述预算不足是交付风险判断，不改写本次实际终止原因。

独立核验：总FAIL；transport PASS（实际登记配置）、task FAIL/job_failed_or_canceled、coverage FAIL/batch_stopped_before_completion、process_path FAIL，usage UNKNOWN。自然多步固定登记分母1，incomplete1、path_completed0；全批次仍为2题、仅简单题完成。两个工具回执已在独立投影中核实消费。账本unknown_attempts=30对应provider用量未知；unresolved_attempts=0，Solver unknown_outcome_calls=0，不混为未知请求。原独立报告及脱敏证据保留在runs/.../verification.json与independent-report.json，SHA-256为517208877eec1d9792f63f33923122735b15eb4a2671ce3fc036ce2f6f018c79；具体根因另存terminal-diagnosis.json。

### 终态核对新增发现及修复

对照本Run的公共progress与timeline发现verifier额外把合法attempt_index=0归为空，且完成路径检查也拒绝零索引。这会漏计初始attempt的成功角色；已有单测使用attempt=1未覆盖。新回归先RED（3项中2失败），删除冗余正数过滤并允许非负attempt后GREEN；缺失、负数、bool与跨attempt审查仍拒绝。连同既有核验器与RB03回归共43项通过，Ruff通过。RB03首个越界索引测试预期由4改5，与已有一次claim-target-repair合同一致，保留所有失败/无Researcher/无未知调用断言。

修复发生于06终态归档之后，不修改06原manifest/status/报告或拼接其他Run。原process_path角色投影含此已知缺陷；真实Job失败、无最终生成/审查的事实不变，不能把06升级为PASS。下一次真实调用必须使用新源码SHA、manifest及Run身份。#127 open，#128两臂NOT_RUN/open，best-effort关闭，不声称数学能力提升。06临时heartbeat于归档后移除。
