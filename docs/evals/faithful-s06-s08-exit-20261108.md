# S06 与 S08/F2 工程退出验收

日期：2026-11-08（Asia/Shanghai）。集成树 `C:/Users/CQX/.codex/worktrees/faithful-integration/Challenge-Cup-2026`，分支 `mathagent-faithful`。

**S06、S08/F2 分别工程退出通过，状态均为 engineering-preview。S09 仅环境核验 unavailable，未退出；完整 F6、F3、S10 与完整并发未完成。** 本记录不声明数学或讲解质量提升。

## 身份与来源

起点为 `9cf8ef4501f3227f4218530176ca98190a7ef9cc`（工作树干净），确认上一窗口 idle、无遗留求解/门禁。未使用原工作区或 S05 树 HEAD。accepted 规格通过本地 `docs/wayfinder-chat-output-prototype-20261106` 的 git show 只读核验；核对 GitHub #146、#148、#149、#152、#144 阶段决议与后续 #156。

最终集成源码及成功门禁源码：**`2f11c65b66317b02605344dfb5f65045c88e81b3`**。后续仅文档变更，最终交接 SHA 另见交付回复。提交未 push。子代理调用省略模型 override，未主动切换模型；工具未返回具体实际继承型号，不能声称锁定或已核实上一窗口型号。

## 重规划边界

确认为产品缺陷：冻结 ProblemSpec 合法，替换步骤映射同一无前提根义务；replan 却只在 progress 开关启用时重绑 WorkUnit，导致新步骤找不到映射。`f180e7b` 对齐初始规划的 ProblemSpec 条件，未放宽前提或完成条件。公共 Job 先失败后18项回归通过；真实浏览器新计划成功、答案2、覆盖1且刷新历史正确。独立 Standards/Spec 无可行动项。完整过程、证据与 S09 结果见[专项记录](faithful-replan-s09-environment-20261108.md)。

## S06 独立结论：通过

依据[S06 合同](../engineering/faithful-s06-contract.md)。Composer 解析 /solve、/teach、/report，冻结模式/schema/policy并绑定幂等身份；普通输入和旧 Run 保持旧语义，能力默认关闭。独立 PresentationArtifact 使用当前报告/证据身份、SQLite 事务/CAS、追加历史；原答案与表达分离。数学改写/新增断言保持待验证，不沿用旧 exact-text、不升级或进入已证账本；部分义务保留范围。来源变化使旧表达需重审；整理失败/接口错误仍保留原答案，无新求解循环或隐式续算。

本轮 teach/report 是明确标注的确定性模板基础表达、引用原文，**不覆盖完整 F6 的生成讲解质量、图与形式化深链**。#152 保持 open。

后端 Standards 无阻塞；Spec 的完整生成意见按本轮 S06 范围保留后续 F6。前端双轴发现同会话迟到报告污染新 Job fallback，以及同终态刷新不重取表达；`a4a075a` 补当前 session/Job/evidence/revision/卸载守卫，并随报告重取表达。真实浏览器先复现旧 A 答案错误显示于 B，修复后4项 Chromium通过，独立双轴定向复查通过。跨会话路由会重建组件，未将不能复现的跨会话夹具误记为产品红灯。

## S08/F2 独立结论：通过

依据[S08 合同](../engineering/faithful-s08-contract.md)和 #148，复用唯一 SolverHarness。显式串行 policy 默认关闭，Run 冻结依赖停滞策略、规格及方法身份；CandidateRoute 与 AnswerCandidate 独立。规范化 frontier 使用冻结目标/前提与受控方法，改名/细拆不产生收益。主路线真实停滞后至多一条替代；路线父子、变异、停止/淘汰原因、旧版本与失效记录持久保留。

当前有效根义务和必要前提按来源/result/claim及图状态计算信用；无关引理、重复信用和失效支持不计新收益。Rater/Pareto 成本方向为真实消费越低越优，unknown 不插补；路线起点冻结信用/消费，policy固定。持久输入、向量、hash、独立停止输入与输出可重放，公开 replay 状态实际核验，不信任自报布尔值。

路线状态保护、预算快照、图失效、评分与终态在既有 SQLite 事务/CAS派生。未知预留、原 deadline、收尾保持共享账本；替代 Planner 派发前估算现有 S03 收尾请求，后续替代动作前消费执行门禁；不足停止。图失效路线保守停止，需重新审查后才可新建合法尝试，不自动清标记或复活证据。最终候选仍经独立整题审查与 exact-text 绑定。

集中双轴发现并修复：历史/CAS绕写与合法转换阻断、无生产预算/评分接线、frontier不完整、旧信用和停止原因重放循环自证、终态仍active、Challenge守卫重定向后派发、路线计数使用可归零全局基线、替代后续动作未消费收尾门禁。每组有聚焦或可执行验收；修复后受影响部分独立复查通过。完整公共 Job 真实走主停滞→一替代→整题接受→同文本绑定，结束路线completed且无active。新连接读取真实SQLite评价/裁决重算，篡改拒绝，零新增调用。

公开 RoutePanel/DTO 白名单展示谱系、状态、评分、预算及真实重放；隐藏frontier原文、私有证明和prompt。主路线真实 Chromium验证刷新恢复、身份与隐私、调用不增加；**替代链路由公共Job测试覆盖，未单独拍摄替代路线浏览器流程**，自然题/真实服务表现未验证。完整并发 Population/APRS 未实现，不以串行结果代替。

## 验证与失败记录

产物均在集成树忽略目录。协调目录：`artifacts/faithful-s06-s08-coordination/`；B早期原始失败与49项聚焦在独立树 `faithful-s08/Challenge-Cup-2026/artifacts/faithful-s08/`，A早期绑定/API日志在 `faithful-s06/Challenge-Cup-2026/artifacts/s06/`。

| 检查 | 结果与证据 |
| --- | --- |
| 最终门禁02 | `artifacts/final-gates/faithful-s06-s08-02/status.json`，6/6，1517.578秒，source_changed=false |
| 完整回归02 | 1543项，0failure、0error、42skip，1379.820秒；同目录 `repository-check/tests.json`、diagnostics.log |
| 快速/发布 | fast通过；release27项通过；CLI/HTTP/JSON和baseline边界通过 |
| 前端门禁 | npm ci/audit/check通过，0漏洞；有构建chunk体积提示，不计性能验收 |
| S06集成浏览器 | 4项通过，11.3秒，`s06-review-browser-green-03.log`，覆盖命令、丢回包同key、刷新、两类迟到响应、来源刷新 |
| 路线集成浏览器 | 1项通过，12.9秒，`routes-integrated-runtime-01.log`；局部截图已查看 |
| 运行时聚焦 | 49项通过，B树 `runtime-focused-green-06.log`；审查修复48项及6守卫通过，协调 `runtime-review-focused-01.log` |
| 首轮门禁01 | **失败保留**：1543项1failure3error42skip；source23bc202，source_changed=false；尚未进入后续阶段，不计通过 |
| 门禁修复 | 旧PLAN入口被新step守卫误挡；Challenge条件替换误触Explore guidance辅助函数。2f11c65仅两行修复，29受影响测试通过（`gate01-fix-focused-02.log`），双轴定向复查通过，再以新run ID02完整重跑 |

其他失败日志保留：route浏览器夹具缺S04 method_id、S06 Teach网络失败异步测试分支、错误会话标题定位与单请求假设、测试连接上下文误用、未接生产终态/评分/预算的候选失败。未增加等待或放宽成功条件；带green/candidate字样但退出非零的日志仍为失败。

上一轮迟到用量 evidence_mismatch 偶发失败根因仍未确认，本轮未顺手修改该模块，不声称已修复。

## S09、后续与收尾

S09 既有Docker隔离可执行，固定MathAgent镜像内 Lean 缺失，最小编译exit127；无工具链版本、证明项或L2/L3，F3未退出，S10前置不解除。未安装、下载镜像或实现后端。

42项Docker/Reference skip、真实provider、容量/SLA、自然题规格/方法语义、数学效果和讲解独立质量仍未验证。预算估算为工程准入策略，不保证真实服务完成时间或数学正确性。官方user_agent.py、implementations/、BASELINE.json及默认评分预算无变更；tests/test.md未读取/修改/提交/删除。

Gate01/02均结束，临时检查已移除，无遗留Python/uv测试进程。后续会话继续当前所选模型，不主动覆盖型号；实际继承不可核验则如实说明。按用户授权，完成本记录/索引/Issue收尾后创建新session，下一可执行主线为 #156完整并发（先核验本轮F2及S06证据）；S09 unavailable继续保留，不绕过F3开启S10，不自动关闭总票#146或完整F6/F3。
