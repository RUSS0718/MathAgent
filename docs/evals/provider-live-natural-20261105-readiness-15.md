# readiness-15：样本字节登记更正后的真实过程覆盖批次

北京时间2026-11-05 16:14:51启动新Run issue127-natural-20261105-readiness-15-run01。冻结revision f16b21296604236af24fa12009676175431b1bda，source SHA a30dab8ae9701d3c0014d8f54ce63c60ea897139ba5f1abe9038510d04e3f754，manifest SHA 3c4869637628d2d13d60e860b071869bbea00f66c1175b4e5416c9b749ef1cf2。产品源码与13相同；14本地准备失败原样保留，未恢复或重发。

本批完整分母2：simple与octagon-colorings。新题为正八边形三色合法染色在几何D8及全局颜色置换下的轨道计数和分类，未在题文提示planner、role或工具；有限6561原始赋值、96群元素，预期更易自然拆分但尚无实测结论。若仍FASTPATH，如实记过程覆盖未发生，不反复换题抽到通过；13的成功答案不拼入本批。

14失败为自身登记按内存LF算哈希、落盘CRLF导致不一致，不是产品校验错误。15复用现有FileSampleHashResolver.hashes/read_text，两题实际文件字节哈希及读取均预检通过。octagon文本/输入SHA395f5e9269c997fcc111fcd86b4a35bda59f6f63e15160bb41d63fbfc6f0be94；原14错误manifest不改。独立复评推荐局部更正、不增加跨平台生成框架。保守累计repair_round=6（产品缺陷修复5、登记更正1），live_attempt=7、pre_dispatch_failures=1，外部TLS与真实预算不足不计修复轮。

独立8136服务真实PID11948/创建16:14:19.129112，runner真实PID41604/创建16:14:51.718660，实际CIM创建时间与记录仅微秒舍入差；已核对source/script/data目录、监听PID、公共applied model/transport及样本预检。模型intern-s2、thinking=false、temperature=0.2、32768输出；每题128模型/HTTP、32工具、16777216 token、14400秒，两题批次双倍；单调用900秒、连续30秒流空闲停止，best-effort关闭，官方baseline/身份/整题审查/最终绑定保留。

16:15:02初始观察，简单题run_a0f97ed8b4fa947d040afa65c3d38b27运行中、进入整题审查，完成0/2。尚未取得自然多步或本批交付结论；usage UNKNOWN只观察。已有provider-live监控已转移到15，每10分钟检查，无变化静默，失败/完成通知。

监控命令（本工作树）：

```powershell
uv run python .review/issue127-natural-20261105-readiness-15/audit_live.py
Get-CimInstance Win32_Process -Filter "ProcessId=41604 OR ProcessId=11948" | Select-Object ProcessId,CreationDate,Name
Get-Content artifacts/issue127-natural-20261105-readiness-15/logs/run.stderr.log -Tail 10
```

#127未验收/open，#128两臂NOT_RUN/open；仅在本批独立coverage/task/transport/process_path PASS且最终答案整题审查同文本绑定成立后才派发#128。未宣称数学能力提升。

16:16:22只读追加：完成1/2，简单题succeeded/completed_llm_reviewed，实际Job预算limits与manifest逐字段匹配。新octagon题run_a90015368c8d4c64aece9920d1c6bd25自然进入STEP_VERIFY，持久steps=1、4次调用，尚无最终答案；末次步骤核验首正文16:16:00.379690、末正文16:16:20.810025、completion16:16:21.044067。只说明流程已自然展开，不能提前判定整题交付或readiness PASS。

终态追加：北京时间17:33:32.481747 runner正常退出，批次完成1/2。自然题partial_aborted/TERMINAL，result_reason=challenge_meta_limit_reached，公共错误star_needs_review；最后业务事件challenge_escalation_stopped。前5步已接受，第6步仍VERIFYING。Meta调用完整成功并返回CONTINUE，随后Reasoner续答、步骤核验和反例研究后停止；新增Meta格式repair没有触发，不能声称线上修复路径已验证。

自然题累计6类角色、37次模型调用：Explore1、Planner1、Reasoner12、Step Verifier15、Researcher7、Meta1；36次completed、1次protocol_failed（step5的既有格式修复随后成功），无在途调用，3次工具。加简单题共40次模型调用、8类角色。自然题charged3011786/16777216、墙钟4706.69/14400秒，unresolved_attempts=0、unknown_tool_calls=0。缺provider用量仍UNKNOWN，不能把账本unknown_attempts=37当未知远端请求。

最后Researcher首正文17:31:21.329566、末正文17:33:25.265657、completion17:33:27.442867。没有TLS、900秒单调用超时、30秒流空闲或硬预算停止证据。非空partial文本存在，但whole_review_not_bound，未形成合格最终生成/整题审查绑定。零模型独立核验整体FAIL：task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；脱敏导出SHA cf3e880c5c38fab9d73671af4842d1bc776a9a929647c216524bcef4754aafce。

已证实的直接停因是有限挑战/Meta升级额度耗尽，尚不能据此把数学审查分歧归为代码bug。独立子智能体01a1ab10-cbe6-7b72-87bd-82803aca4b39正在有界检查最后review/反例、Meta输入上下文与CONTINUE后的升级路径，比较局部修复与简化收益风险；目前未修改源码或增加修复计数，不恢复旧Run，不放宽cap或开启best-effort。#127仍FAIL/open，#128两臂NOT_RUN/open。

独立诊断补充：终止符合SP-05有界挑战合同。history=[]是Meta自己的会话历史，不等于没有Run状态；实际消息还通过prompt_layers注入Meta状态投影。该投影包含steps，却没有plan、accepted_results、verified_results_ledger和全局执行回执。只读数据进一步收窄：step6报告已有一条成功回执；step1/2的Verifier计算成功回执只在全局账本，未嵌入各自报告，故原投影确实遗漏这两条，并非三个工具结果都不可见。完整历史HTTP消息未归档，不能证明模型没有读到任何证据，亦不能证明遗漏是本次失败的唯一原因。

主线程采纳独立建议做局部补充，优于新建统一证据框架：Meta投影补plan及复用既有有效性过滤的成果账本；提供同Run/plan/attempt、当前或有效接受步骤的成功执行回执摘要，保留来源、输出及引用，不复制完整代码，不开放工具。当前目标/异议已在steps中，不新增重复字段；挑战上限、整题审查和最终绑定不改。新增真实消息构造接缝先RED（tool_receipts/ledger缺失），修复后Meta/skills相关21项GREEN，快速门禁/Ruff通过。终态数据只读重放新摘要包含3条成功回执、2804 bytes；这不是provider tokens或在线完成证据。新修复不追溯升级旧15，后续新16沿用完整两题分母、样本和预算独立冻结。
