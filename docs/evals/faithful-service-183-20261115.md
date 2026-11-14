# #183 当前机器真实服务阶段记录

日期：2026-11-15（Asia/Shanghai）。源码HEAD `c01683ddf5cc526d0b5c61f2bac11f8f677975e9`，与origin一致；初轮真实求解时产品未修改；随后发现并修复缓存前端可空字段合同。适用[本票合同](../engineering/faithful-service-183-contract.md)。具体模型继承未知，保持当前设置。#183/#168仍开放，完整服务未通过。

## 新增真实证据

各轮从停止状态由唯一隐藏后台启动；原根预算均48模型/48HTTP/8工具/262144tokens/1100秒，配置SHA256 `11f870740eeaf4127a664b59f0ce82aa56b93b65a1e81844bafb4ee785638d33`，Intern、真实Python和Lean、Population准入均由既有配置启用。源码和前端构建字节、配置及脚本身份封存在各轮source-identity.json；不固定模型路线。证据均在忽略目录artifacts/issue-183/。

| 场景 | 公共Run及执行结果 | 结论 |
| --- | --- | --- |
| live01 参数四次多项式非负分类 | run_3bd131fc2da2fb3c29c8615a6cc0ed40；4HTTP、2Python；shared_admission_budget_exhausted | 失败，无完整答案；非并发证据 |
| live02 有理数恒等式首次普通提交 | run_509e8c6b7e14dc85c13e94f1fd599055；4模型；正确证明，solver.semantics.whole_review=accepted、binding=same_artifact（LLM审查），Lean formal_91e6f676fc1c43de97c9c5a0c1e43c48，缓存真实入库 | 正确解题、L2及入库通过；对应审核conclusion_mismatch，非L3 |
| live02 同会话相同题目再次普通提交 | /revisions创建run_20360dd11f279157e9e17a744d983ee9；5模型；正确答案、solver语义whole_review=accepted、same_artifact（LLM审查），独立Lean formal_74567054150946efaf01ed058e6aa34e | 正确解题及L2通过；spec hash不同，只有第二次入库，无receipt_rechecked，缓存命中未通过 |
| live03 两个独立求和量 | run_a359f79ec5dd31a70ea0ac980c813dc4；5模型、1Python；S=338350、T=25502500、总和25840850；独立直接求和吻合，solver语义whole_review=accepted、same_artifact（LLM审查） | 完整正确解题；Explore短路，未进入Planner，不算自然并发 |
| live04 增加普通分步计划要求 | run_e519560be02eb6400d6e141a0801ff6d；intake/Explore/Explore/Planner/Reasoner共5模型、0工具；计账235134，下一请求未获262144根额度准入 | 失败，shared_admission_budget_exhausted；未闭环并发/切换/干预 |

live01启动脚本最初以Windows PowerShell默认编码读取中文JSON失败，未创建worker或模型请求；脚本显式UTF8后启动，原失败保留。live03 contract中diagnostic_purpose曾误写复用#177预算；**实际service.json及账本始终为262144/1100**，没有采用#177的2097152/2400配置。此处明确纠正描述，原冻结产物不改写。

live02观察器只等/jobs，而第二次实际走/revisions；新题已创建，但等待超时触发服务清理。原status仍failed，不升级观察器结果。新Job实际上在停止前已完成；独立重启SHOWCASE_WORKER_ENABLED=False服务后，真实HTTP GET读取两个Job/报告/缓存，见readonly-run1/2.json、readonly-report1/2.json、readonly-cache.json。readonly-observation.json为writes=[]、errors=[]；真实UI可见当前Lean L2和独立Attempt。缓存管理区域的另一次定位超时保留，尚不能宣称缓存管理UI或命中恢复完整通过。独立当前Lean并不等于缓存命中。

## 覆盖与限制

S01调用生命周期、S02上下文/根预算、S03自动规格、S04进度、S05工作台、F1图的既有公共工程与真实串行证据复用[#170](faithful-service-170-20261113.md)；澄清/关联改题复用[#172](faithful-service-172-20261113.md)、[#173](faithful-service-173-20261113.md)。F2自然并发和热切换、F4串行及并发收敛后干预成果回接仍未通过；#174–177开发接线不能替代。F3本轮补真实L2及正确答案，明确机器要求/L3仍未通过。F5本轮补自然可信来源入库，命中/经验明确采用拒绝/撤销继续仍缺。F6/F7复用[#181](faithful-service-181-20261115.md)、[#182](faithful-service-182-20261115.md)表达、深链及重启只读证据；本轮新Run的完整缓存管理UI尚未通过。十二项六维证据详列artifacts/issue-183/coverage-notes.md，属文档核查，不冒称重新实测。

Provider token用量缺失仍为未知；本地预估保守计账，未填零、未自动重发unknown、未放宽原deadline。F8独立评测not_run，不宣称数学收益。官方baseline与默认路径未改。tests/test.md未读取或修改。

## 当前退出状态

尚不满足本票完整退出条件。由于两类规划尝试在当前token上限受阻，已向用户请求是否允许**仅新任务**采用#177曾用2097152tokens/2400秒；48/48/8不变，旧任务不修改。答复前不扩大预算、不新增模型请求。Standards/Spec阶段审查及文档验证另记；复用#182冻结e62d145的六阶段门禁（2105项、0failure/error、42skip），不重跑未变产品套件。

## 公共缓存UI失败与最小修复

真实API返回active条目的reason=null及会话审计cache_id=null，前端schema仅接受string/undefined，导致缓存管理不可用。保存真实readonly-cache.json与cache-ui-before.txt；现有公共schema新增反例稳定失败（cache-schema-red.log），仅将两字段改为nullish。cache-schema-green.log四项通过，原三项浏览器改用实际可空fixture后全部通过（cache-browser-green.log），构建通过。使用重建前端连接同一真实只读服务后，实际UI成功停用缓存，cache-disabled.json及cache-disabled-assertions.json确认禁用/条目不可见，原Job预算和Attempt不变；没有新增模型请求。此为实际控制补证，不代表缓存自然命中或撤销后求解继续。

证据语义补充：三个成功Job的result.verification.acceptance仍needs_review、status仍unknown；solver.semantics.whole_review=accepted只表示已实际完成LLM整题接受，binding=same_artifact表示同文绑定。不能以语义accepted升级数学形式证明；Lean L2及独立答案核对分别记录。Standards初审指出此歧义，保留原报告后明确分层。

因新增前端schema与回归，本次阶段退出须对最终冻结源码重新执行门禁，不能继续只复用#182；此前复用说明仅适用于修复前。

实际停用后再停止并重启独立进程（worker关闭），after-disable-restart-*真实GET与UI恢复disabled状态；restart-equality.json核对两个Job整个budget、request_attempts及final_response均相同，零新求解。仅支持控制与持久只读恢复，不证明后续自然任务命中或撤销后继续。

## 阶段工程检查结果

冻结源码为HEAD c01683d加本票3个前端文件及当时两份文档，source_hash=ebd9e4f0740429de30741a283d4dff722534113990b08410d4459f754275e77c。

- gate-01原命令：`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-183/gate-control/runs --run-id gate-01`。快速检查通过；完整2105项、1failure、0error、42skip，1971.376秒，source_changed=false，失败后其余阶段未执行。
- 唯一失败`tests.test_faithful_population_native_budget.NativePopulationBudgetTest.test_inflight_transport_audit_can_settle_after_another_route_freezes`预期succeeded但实际star_needs_review。原日志保留；同源码隔离1项复查通过，同模块6项通过（gate-failure-recheck、native-budget-module的json/log），原因未稳定复现，不能称已修复或原门禁通过。
- 根据工程门禁定点复验规则，gate-02使用忽略目录remaining.py调用原门禁阶段执行器，补六组mutation probes、两个CLI及原发布/前端四阶段，12/12通过、128.078秒、source_changed=false，与gate-01冻结hash一致。发布27项、前端70项、typecheck/build及audit通过（0漏洞），42skip未计通过。这是失败保留的组合证据，不是单次全仓通过。
- Standards原P2为accepted字段含义歧义，复查确认solver语义accepted与公开verification needs_review/unknown分别属不同层次；文档已明确，原报告保留。两个字段nullish修复Standards复查0新增、Spec复查无新增代码阻塞；Spec的完整服务缺口继续保留。报告在reviews/。
- 所有长测试终态，MathAgent-Issue183-*临时检查已自删除；未重启历史unknown。11个官方baseline SHA256一致，tests/test.md未读取或改动。门禁后仅文档收尾。

最终使用[交付步骤](../engineering/faithful-service-183-delivery.md)从停止状态启动真实CLI，并实际GET /health、两个既有Job及报告；delivery-*产物保留完整原答案、4/5次Attempt和缓存禁用状态，writes=[]、errors=[]。这是读取恢复，不是新增模型验收。服务仅监听127.0.0.1:8100。#183/#168保持开放，等待新任务预算选择，不创建接班session或关闭父票。
