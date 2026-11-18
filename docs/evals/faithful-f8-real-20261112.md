# F8 真实题集执行记录

日期：2026-11-12；本次事实截面为11:31 +08:00。状态：重启中断后归档，按用户要求完成本次交接后停止，真实实验未完成。接续 [真实合同v1](../engineering/faithful-f8-real-protocol-20261111.md)、[v1.2格式恢复](../engineering/faithful-f8-real-recovery-20261112.md)及[新源码接续v1.3](../engineering/faithful-f8-real-source-continuation-20261112.md)，执行入口为[#157](https://github.com/RUSS0718/MathAgent/issues/157)。官方重评分unavailable，真人L3 not_run，usage缺失observe_only。

## 用户授权恢复后的准备记录

以下为2026-11-12 12:31 +08:00的增量，优先于下方11:31交接时的停止安排。用户交接`bceb233`（#158本地工具拒绝后一次预算内纠正）与`b5929bf`（#159空答案只能unresolved）并明确要求继续实验。两笔源码改变需要新门禁和新manifest，不能用R20旧门禁代替。

双轴复查中Spec发现native纠正历史丢失原assistant文本，已按公共Pipeline先红后绿修复为`dc21478`；Standards（Galileo）与Spec（Boyle）复查解除。10项聚焦、53项相关回归与Ruff通过，证据`artifacts/faithful-f8-resume-20261112/product-{focused,regression}.json`。#159实际adapter hash仍为`7f26f9d49bfe0c6e0e85daca2843745293a857ad13d2bb3692bd72402001bba2`。Docker已恢复，固定Python镜像身份匹配；本截面没有发新provider请求。

[接续合同v1.4及历史文本表示增量](../engineering/faithful-f8-real-source-continuation-20261112.md)继续保持41份首次记录、29未派发、98/70/28分母、原预算和绝对截止。新只读核验器复用原R07/重启语义断言，同时核对原Git、旧gate及原raw hash；旧591成员中554份Git字节直接匹配，37份原工作树前像（6份混合换行）经有限CRLF/LF表示证明，原DB/WAL及旧冻结模块不改写。最小6项验收通过，只将authority freeze作为fixture，不构成正式派发授权；此前12项3error的字节差异记录原样保留。来源为`history-v14-acceptance-01/v141-01/receipt.json`及封存`historical-source-preimages-01/attestation.json`。

当前准入/F/报告路由的7/4/4项检查及必要依赖冻结1项检查通过。F未知双臂会按现有worker抛出硬停止，首轮测试未断言此预期异常的1error日志保留，随后修正测试，未改变worker行为。完整glue双轴结论、正式companion、一次新源码完整门禁及29槽实际执行仍待取得；尚无`resume-manifest.json`或`resume-execution-01`，不把受控检查当实验完成。用户要求后续只做必要离线检查，通过准入后直接推进原剩余槽，按真实错误归因修复，不扩展候选风险矩阵。

## R19源码门禁

非法Meta已完成决定未退出阶段导致18次无进展Meta派发；原B/AIMEI5失败保留，修复提交`d3ccd9f`。门禁及文档冻结源码`543177955392beb514bae2c26bf1c26b49986d9f`，两轴审查均解除。

命令：`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-f8-r19-20261112-01`。门禁6/6通过，1683.094秒；1916项、0 failure/error、42 skip，source_changed=false；发布27、前端52单测/类型/构建通过，audit 0。42 skip的ID与原因同上一F8/F6/F7链，均不计通过；`artifacts/faithful-f8-real-20261111/source-gate-skip-comparison.json`逐项留证。旧Lean timeout、SQLite锁及late-usage间歇根因未确认，本次成功不宣称修复。

## 首次结果与接续

98槽总登记、70个A/B/C/D/G必需主槽、14个E原题目标域不支持及条件F不变。题集/独立参考事前封存；不是独立留出题集。所有已派发槽保留首次结果，不删除、插补或重派。精确有理数9题与证明5题分栏；正式28槽辅助审查尚未执行。

实际固定Lean专项2/2为受控目标L2，不是原题通过；两Job真实并行开发探测仅确认观测容量2，不保证SLA，不替代D自然题并发。原G/AIMEI1正确且实际注入1条，不能推断记忆收益。

| 批次 | 首次主槽数 | 处置与来源 |
| --- | --- | --- |
| execution/d/continuation/recovery/verdict | 7 | 原v1/v1.1/v1.2，1完成正确、6失败/取消；R19旧产品失败保留 |
| source-execution-01 | 4 | 3个已知模型失败，B/I10 progress_action_blocked触发glue分类缺口 |
| progress-execution-01 | 3 | C/G I10 schema失败；A/I15本地unsupported not_executed回执分类缺口 |
| precheck-execution-01 | 2 | B/I15已知失败；C/I15两次planner YIELD达既有上限 |
| checkpoint-execution-01 | 2 | G/I15复用原C同源码session；A/HMMT1 polynomial schema拒绝投影需精确分类 |
| schema-execution-01 | 1 | B/HMMT1本地事件身份冲突，F8-R20产品缺陷，停止新派发 |
| r20-execution-01 | 11 | 新源码首次结果保留；最后A/PutnamA1失败触发响应分类接续审查 |
| response-execution-01 | 7 | G/PutnamA3出现两次真实Python容器OOM，原失败不覆盖；已知资源单例处置不泛化为未来OOM放行 |
| resource-execution-01 | 1 | A/PutnamB1两次已知HTTP响应，第二次length截断；failed/unresolved保留 |
| length-execution-01 | 3 | B/C各failed，G因主机重启中断为unknown；未重发 |

glue分类补充均用原封存Job红绿及拒绝反例、两轴审查，保留原失败；不改产品、prompt或预算，不把未执行/拒绝回执计工具通过。manifest父链及各result/job hash逐项核对。各批具体manifest/hash、归因与审查见ignored `artifacts/faithful-f8-real-20261111/`及#157评论。旧工程试点98 not_run不改写。

## R20修复与已完成源码门禁

Run `run_ea0fab0d6197be919b4b5d12ea7764f5`共11HTTP全部已知完成，产品在Verifier计算续审→claim目标修复→重复计算请求时，两个不同call_id的预留事件共用compute-1后缀，出现SolverEventConflictError。单进程精确复现证据为`artifacts/faithful-f8-r20-fix-20261112/red-exact.json/log`；不归为数学失败。最小修复`bcf9763`只给续审预留事件附确定性call身份摘要，不改请求、调用身份、预算、工具去重或恢复授权。单项绿与42项计算/反例聚焦回归通过、0 skip，fast及Ruff通过，双轴问题解除。

冻结源码为`315ae9b8975c42c742f151c3e20712b20d96217e`，runtime source hash为`a4fa9d9613ac527bb39886111c58a60463ab4970245dc55f396ba86261c53bb3`。命令：`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-f8-r20-20261112-01`。实际门禁6/6通过，1688.344秒；1917项、0 failure/error、42 skip、source_changed=false，发布27、前端52单测及类型/构建通过、audit 0。42项skip的ID/原因对照为`artifacts/faithful-f8-real-20261111/r20-gate-skip-comparison.json`；skip不计通过，受控Lean专项不能替代这些缺失项。本次归档只复用该门禁，没有重跑。

## R07接续与主机重启

资源批次的A/PutnamB1原Run `run_443b5052f7fbce491f311e652469cc70`先返回invalid_json/stop，再由既有有界格式恢复返回truncated_response/length，两次HTTP均success/200，返回Intern-S2；unknown calls/tools为空。原failed/unresolved及canceled Job保留，不能把截断答案当完整交付。只针对该单例的接续合同已双轴冻结，原32个未派发槽另建`length-manifest.json`，SHA256 `b53722b760eaa4a5c5f5303f0be800a30313bca8d02cef4526a14cb92cfe3f6b`。冻结及38/32/50项接缝验收位于`artifacts/faithful-f8-real-20261111/length-*`；未来length仍硬停止，未扩预算或重试原Run。

该执行于10:50启动，原PID35696。已保留B/PutnamB1的progress_action_blocked和C/PutnamB1的invalid_json，均failed/unresolved且按原已知模型失败规则处置。G/PutnamB1 Run `run_03ad176df0e535dda3a5ed466442b81b`尚在PLAN时中断。用户确认主机重启，系统启动时间为10:57:46.5 +08:00；PID已不存在，status.json仍写running是陈旧文件。重启前监控shell曾出现0x800705AF页文件不足，只能确认监控命令启动失败，未证实其造成solver退出，也未确认重启根因。

原SQLite及WAL未修改；只读quick_check为ok，DB/WAL/SHM及raw副本hash保存在`reboot-diagnosis-01/`。在数据库副本上调用现有启动恢复，再通过公共Job/Report/Evidence入口封存输出；禁止网络，实际provider请求为0。原Explore completed，Planner checkpoint streaming，对应HTTP预留无终态，公开恢复投影有1个unknown call。因此该槽execution_status为unknown、math_verdict为unresolved，不能归为已知模型失败、数学错误或完成，也不能自动重发。收据SHA256分别为：

- `reboot-diagnosis-01/receipt.json`：`5d777f1a8b914cb9e359579447b0f48d6681bd0c076328950c8440ed4a477e34`。
- `reboot-diagnosis-01/capture.json`：`4ab52dc02a42bcc8a94c76c434bd3c439198900718e35b61b95ed7fbd4789283`。

以上相对证据路径均以ignored `artifacts/faithful-f8-real-20261111/`为根。原始题集、答案、模型文本、数据库与运行产物不进入提交。

## 本次归档范围与接管条件

98个总登记、70个必需主槽保持不变。目前41份首次记录为1 completed、39 failed、1 unknown；29个必需主槽未派发。唯一completed仍为原G/AIMEI1的参考答案匹配，失败与unknown均未获得数学正确/错误判定。执行、数学可判定子集及源码分层分别统计，跨源码not_comparable；不能把39个执行失败说成39道数学错误。11个官方baseline文件于交接前重新核对，全部字节匹配，没有官方重评分证据。

本轮报告接缝先保留失败案例，再验证精确unknown分支；53项显式选类聚焦回归通过，0 failure/error/skip，最后7项针对当前报告边界复查通过。早期宽选类105项为0 case failure、2 tearDown审计钩子error，原日志保留，不计通过：真实历史汇总需要只读Git子进程，旧fixture禁止所有子进程。另用仅允许固定只读Git命令、禁止网络的实际汇总入口核验，不放宽产品请求权限。证据为`report-reboot-acceptance-01/`及`reboot-handoff-integration-01.json`；后者确认40份首次归因已核验，重启unknown尚无冻结处置，primary_disposed_unknown=0，acceptance_status=incomplete。

重启接续实现及合同只到review_draft，不是派发授权；未封存`reboot-manifest.json`，未启动`reboot-execution-01`。旧`f_binding.py`保持冻结hash `dcce31b673a9a5d6e9ccb4a77cd08270d0ea8bdc72b02bbb9d9389bafc3f9384`，新的reboot父批次F映射尚未实现。后续须完成重启单例合同双轴审查、当前源码/绝对截止准入和报告/F集成后，才可另封29槽接续身份；不恢复或重发原unknown请求。此次仅文档提交也会改变revision，后续不得直接拿旧manifest绕过完整源码身份检查。

当前已派发的两个子智能体均已收尾。Poincare完成重启binding/freeze/prepare/run草稿及6项验收，28.437秒，覆盖14项语义防伪、3项hash篡改拒绝及41/29构造；验收使用真实重启证据与旧length绑定，但reboot freeze仅为内存fixture，不构成正式冻结或线上执行。收据为`reboot-binding-acceptance-01/receipt.json`，SHA256 `01f510ba8fc41424a2aa3c9b33b3097bbdf4b3c52fd5f4982974c0c75430f027`；未封存draft合同hash为`e102ed38d6efe94def31e87a57630fc3a3f3c7a0bb7bbe2e351d9cc86080953d`。

Einstein的独立Spec审查允许本轮report/capture现场归档和交接，没有宣称接续合同双轴通过。审查发现后续辅助验收阻塞：`review_contract.py`仅以run_id或answer hash为None判定缺失，固定抽中G/PutnamB1的空答案仍有空串hash，可使构造的辅助pass被接受；离线复现为`reboot-spec-review-01/verification.json`中的`blank_unknown_review_pass_accepted=true`，SHA256 `b27ff45e484e7714db7ce6b3efe148370d075e0eb9f50bbc689608b45632f77d`。当前真实结果仍unknown/unresolved，未导入错误pass。本次按用户收口只登记F8-R18，未修复；后续须先证明空答案的pass/fail被拒绝、unresolved可保留，固定28槽不能替换或缩减，再验收辅助报告。审查时旧版7项为6成功、1过时F映射预期error，日志同样保留；主代理随后将断言改为保持旧F拒绝并实际运行最终7项全绿，两个轮次不混称。

适用F的真实筛查及双臂、固定28槽隔离辅助审查、G五项rubric、完整报告和独立最终包验收仍待完成。R1/R2/R3是模型辅助，真人L3 not_run；受控Lean L2不升级为原题L3。旧Lean timeout、SQLite锁、late-usage及主机资源间歇根因均未确认。#157保持开放，本次归档不构成F8实验完成或数学能力提升。

按用户11月12日要求，本子目标交付后停止，不再派发真实实验或新增审查。旧PID已退出、临时计划检查已记录process_missing并移除；接管时先核对最新分支/源码、原始失败与unknown、截止时间及未完成审查，不重复启动。继续使用当前选择的同一模型；无法确认当前代理具体型号，不推测型号。

2026-11-12 后续修复：用户重新授权处理两个缺陷，F8-R18 的空答案判决缺口已修复并以真实身份只读复核。见 [修复验收记录](faithful-f8-empty-review-20261112.md)。上文‘未修复’保留为 ba97cd0 归档时点事实；本次不接续实验，不改变 #157 未完成状态。
