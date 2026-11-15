# #183 当前机器真实服务阶段记录

当前状态（2026-11-15 15:06）：产品和聚焦测试提交至2736308，准备冻结执行gate-05。gate-03/04原失败保留；两处测试同步缺陷已最小修复，native第一次修复后模块失败仍未解释，已增加失败时保留原异常链。live14–21均终态，旧“准备”段保留为当时快照，以本文末尾实际结果为准。live19补有效经验拒绝、撤销继续和重启只读；live20首题可信Lean L2入库但次题未命中。自然并发、热切换、F4及缓存当前重验仍缺，#183/#168不关闭。未实证的一般L3不新增为本票门槛。

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

尚不满足本票完整退出条件。由于两类规划尝试在当前token上限受阻，用户已明确授权**仅新任务**采用2097152tokens/2400秒；48/48/8不变，旧任务不修改。live05以后任务使用该授权，当前不再等待预算选择。新增产品修复须对最终冻结源码执行门禁。

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

最终使用[交付步骤](../engineering/faithful-service-183-delivery.md)从停止状态启动真实CLI，并实际GET /health、两个既有Job及报告；delivery-*产物保留完整原答案、4/5次Attempt和缓存禁用状态，writes=[]、errors=[]。这是读取恢复，不是新增模型验收。服务仅监听127.0.0.1:8100。#183/#168保持开放，不创建接班session或关闭父票。


## 授权后的真实补验与失败诊断

以下是追加阶段记录，未替代上述原失败；源码起点47b83cdf20c509699b73953e4a57704bba86f5d2，live09/10另含source-identity.json冻结的未提交最小修复。每轮唯一后台、普通浏览器、真实Intern与适用工具，48/48/8不变；新根额度2097152 token/2400秒。各轮status、公共最终Job/Report、source-identity及实际截图在artifacts/issue-183/liveNN/。

| 轮次 | Run与实际结果 | 未满足项 |
| --- | --- | --- |
| live05 | run_5aa64a944e476d2e12beeb42785e9300；11模型、2Python、659399计账token；模型选串行，route_duplicate_route_frontier | 无完整答案；提高预算未解决自然并发与推进 |
| live06 | run_f4cd31a961145db7fe15cfe0ae4f0ed6；12位数位和54且模7计数；8模型、0工具、460864计账token；串行挑战重复草稿后reasoner_checkpoint_no_progress | 无完整答案；独立DP与半数枚举参考5123724123未送模型 |
| live07 | run_8812dca648d19b6e39a3d993d632c711；4模型，正确有理数恒等式证明，Job succeeded；明确授权经验和缓存；形式化unsupported/spec_target_mismatch | 无可准入缓存来源，第二次请求未派发；自动捕获unknown观察不等于成功经验 |
| live08 | run_172a768d1e3e104b04e9ae70b8d6d420；沿用live07实际数据库与会话，4模型，正确证明，Job succeeded | rationals与rational numbers域措辞导致旧观察未注入；无采用/拒绝证据 |
| live09 | run_a6e5bdd4479460a7e1ae98eaa6a8dc1e；4模型，三个调用实际注入两条旧记录；全部memory_decisions=[] | 模型未报告经验选择；普通proof被升为require_formal=true，Job因formal_requirement_unmet失败；原失败保留 |
| live10 | run_42d98ba995e3f64767c997bca2266165；9模型、2Python、547081计账token；模型仍选serial | Step Verifier多余tool_request.label触发严格schema拒绝；有界修复后Reasoner unknown_outcome，最终star_needs_review；未重发未知调用，无完整答案 |

本轮最小修复仅限真实故障：有理数域两个已证实别名用于advisory相关性，不修改原规格或缓存键；挑战重复checkpoint不接受、不入库，转入已有单次有界Meta升级，并在实际UI区分重复草稿与轮数耗尽。既有单步无进展守卫仍保留。公共红绿与受影响40项回归、浏览器6项及构建证据在memory-alias-*、challenge-*、affected-regression*及前端日志；仅证明工程合同，不将live10升级为成功。集中审查见reviews/*-runtime-fixes.md；完整服务缺口仍在。

缓存只读窄对比已确认live02完整规格仅output_requirements[0]措辞不同，其余规范字段相同；完整身份合同下miss正确，未删字段或降低身份来制造命中。证据cache-spec-differences.json、cache-miss-analysis.md。live09硬形式要求来源诊断见formal-requirement-analysis.md；需独立公共反例及修复，不能以降低L3资格、删除合法假设或忽略真正用户要求处理。


## 来源边界修复与Planner版本见证

形式要求来源修复不把模型require_formal布尔值视为用户权威。明确受支持的肯定句直接见证；模型声称需要或工具相关语境无法确定时，走既有必要澄清。该有限语法不声称理解所有自然语言；否定、引用及条件语境保守澄清，可能多问一次。显式客户端策略及旧冻结硬要求保留。原用户未要求机器验证的live09不追改成功。

集中Standards/Spec初审各发现同3类阻塞：模型复制澄清reason可伪授予权威，条件跨行误授予，以及authority回答被追加为数学假设。原报告保留；新增3个公共Job用例修前4个失败断言（含复制整题问题），修复仅服务器签发的持久问题绑定可消费yes/no，授权回答不进入数学assumptions。formal-source-review-green-48.log为48项通过，非真实模型补验或最终门禁。既有澄清重绑定夹具明确添加真实机器请求后保持unsupported/unmet断言，formal-clarification-green.json为9/9；旧失败日志保留。

live11：run_43ce283b0b0624af5be929aa204d4141，4模型，无完整答案。第一Plan把前提和依赖目标同放S1而自依赖；第二轮Plan结构修复但version由请求冻结1变2，执行前invalid_planner_checkpoint。实际截图又超时，观察器保持failed、completed=0，不能声称稳定UI。旧schema只要求正整数，InternPort红见证planner-version-red2证明错误版本被接受；现在仅把主Plan版本绑定到已有request.plan_version，保留alternative独立版本及最终检查。planner-version-green及planner-affected-green的18项通过只证明协议边界，使错误版本进入既有有界格式修复，不声称自然规划已恢复。


live12：run_e77c7a3305f4460ced9f71c56bfec51f，10模型、2Python、628060计账token；自然选择串行，挑战后曾继续下一STEP_EXECUTE，随后Reasoner timeout/unknown_outcome，最终star_needs_review。未耗尽2097152根token额度，无完整答案；原未知调用不重发。来源权威定点双轴复查原3P1已解除，仍不证明真实能力跑通。

Planner版本后续Spec发现P2：非checkpoint concurrent-aprs分支在const后复制schema，误约束备选Plan独立版本。公共InternPort反例planner-alternative-red为有效主版本1/备选2被拒；已将const赋值放到所有备选复制之后，仅主计划绑定版本。planner-alternative-green原负例对既有wire minimum支持作了错误假设而失败；没有扩展共享validator，修正用例后green2为19/19通过，主版本错仍拒绝、备选独立正版本接受；最终执行器原正整数检查保留。原失败记录均保留，待该P2定点复查。

下一live13代表题保持8位数位和36且模7，普通用户表达愿意额外成本、尽量两个数学方向同时推进、任一完整即可交付。Spec只读核对确认可标“普通输入下偏好驱动、模型选择的自然路线决策”，不能标“无提示自主选择”。实际选择、准入、并发派发、正确交付分别判定；参考625579不送模型，没有强制技术mode参数。当前仅准备，实际结果另记。


live13已实际终态failed：run_214bfb62cd3849e380e71e3961c264b2，8模型、2Python、451493计账token；Explore有已知invalid_json及有界修复，随后Planner timeout/unknown，最终star_needs_review，无完整答案及自然并发。两次超时的原unknown均不重发。

live12最后Reasoner调用的680条审计事件起止约181秒；内容一直输出到截止前，公请求effective_timeout_seconds=180，根2400秒与2097152 token未耗尽。request-timeout-diagnosis.json保留具体时刻及流量；这支持单次等待为瓶颈之一，不证明延长必然成功。新服务配置可选request_timeout_seconds省略仍180、显式正且不超过根时限，Population可独立更短且不超过适配器。新验收profile仅新任务用360，根48/48/8、2097152/2400及模型/thinking/32768输出/重试不变；12配置项与2个既有根截止/unknown边界通过，红入口失败仍保留。定点审查另在reviews/*-request-timeout.md。

live14准备复用live07真实旧会话/数据库，仅新建两个普通Job：先证明恒等式并明确讨论可用历史的取舍，再通过公开控制关闭注入后解另一恒等式。每项结果独立记录，不因经验未报告而跳过撤销继续检查；若出现服务器自身的机器要求来源问题，代表输入明确无该要求，以实际浏览器回答no继续，不补数学假设。此时尚未启动，不宣称通过。

## live14/15 实际结果与提示合同修正

live14首题run_112f23abbcf034cccd4458e732013963，4次模型请求，正确恒等式证明且Job succeeded。三条经验正文实际存在，模型返回三条reject，却将session_history为空解释成没有任何观察；理由与advisory供给矛盾，不能判经验有效取舍。memory-payload-diagnosis.md核对匹配源码、持久正文及纯消息重建，未取得历史完整HTTP逐字回放或provider理解证据。

公开撤销后第二题run_771e83d08769b9b9986e074cd7e5f51d遇到机器要求来源澄清。原观察器错误进入只读Run页，原failed保留；主聊天页实际有澄清框。live14-recovery通过真实UI答no并收到202，但立即把滞后的waiting_input当终态，提前停服；后续恢复发现第二次intake仅派发预留、无响应，进入unknown/needs_review。此为观察脚本中断，不能升级为撤销继续成功；live14-followup只读接续未重答、未重发。旧Run、unknown及原失败保留。

live15为run_eab367e30f7f4e2aeef41a7ec0d0bfc7，14模型、3Python、1001037计账token、2222.789秒。实际算出5123724123，与既有独立参考相符；enumeration/completeness两个义务及两个步骤审查通过，但交付format义务尚未完成，最后StepVerifier在360秒超时，Job failed/star_needs_review，无完整答案。单次216/240/246/313秒请求确曾完整返回，证明180秒限制会截断部分请求，不证明360秒保证成功。原unknown不重发。

planner-choice-analysis.md只读核对：live15首轮选择population但WorkUnit自/前向依赖导致绑定失败；第二轮修复后主动改serial。第二轮DP和配对方法的受控分类序列相同，合法计划frontier相同；未放宽去重或增设方法来制造准入。用户偏好原文保留，不能归因于序列化丢失。

三个提示修正仅澄清既有合同：区分对话history和投影advisory、让Meta协议服从当前动态schema、将时间成本/先完成偏好留给执行而非数学义务，保留真实格式及明确双证明要求。meta-protocol-red.log稳定复现两种特殊请求被旧四动作协议冲突；green移除无条件冲突，普通Meta保持既有schema。prompt-contract-green.json为41项相关回归、0失败/错误/跳过；这不证明模型语义改善。审查在reviews/*-memory-source.md、*-meta-contract.md、*-intake-preference.md及应用后复查中。尚无本轮最终全仓门禁结论。

live16/17/18仅准备，分别用于真实经验取舍后撤销继续、固定普通输出要求的缓存来源/当前重验、归纳与双射方向的普通方法建议。脚本回答澄清时改用主聊天页、等待202、忽略已答问题的滞后投影；未见公共终态时不因观察器异常直接停服。live18新profile主/Population单次等待均360，根仍2097152/2400、48/48/8；现有Run不改。未执行项继续not_run。

### 10:56 更新：live16 结果与两项最小补丁

上述准备状态为历史快照。live16 两题已 succeeded：run_53c12c174185fc098680687d4ea03d55 为4请求、run_09d5b58f30efa2d37e153246fa908122 为5请求，数学恒等式正确。首题4条 reject 仍声称空 session_history 中没有观察，理由与实际 advisory 不符，不能视为有效经验取舍。次题公开撤销后未注入记录并继续正确。监控及测试服务已清理，旧 unknown 保留。

离线见证另发现 skills/persistent_sessions 同关时正文被无条件删除。补丁将当前有效 advisory 保留于最终用户请求，仅删除深拷贝投影中的副本，保留旧嵌套输入；不从对话恢复经验、不扩大权限。稳定红覆盖四种开关，最终5项及相关50项通过，双轴无待办。实际语义效果待 live19 新建两题检验，不追改 live16。

本地延迟补丁 A 仅在原事务筛选 receipt 候选，Python 最终解码、完整公共历史、当前证明来源及 CAS/控制/期限检查保留。相关38项通过、双轴无待办。三组交替的固定离线剖析均值2.708268秒至2.190730秒，约19.1%改善；原不利单组结果仍保留，不能据此宣称真实服务或模型提速。证据见 artifacts/issue-183/latency-A-delivery.md、memory-placement-delivery.md 及 reviews。当前源码仍须最终全仓门禁。

### 11:03 更新：live19 内容取舍、撤销及只读重启

两题均 succeeded、各5请求：run_708ca947725efef197b838cfa95ff851 证明 x+x=2x；run_279b6bcdbc580efe82d0f6d9d76f4c38 证明 x+0=x。首题5条当前记录确实只有运行状态、来源和成本等诊断信息，模型逐条据此 reject，明确不含可用数学方法，理由与公开 observation 相符；不再声称没有记录。未知结果仅作诊断，未升为可信经验或正确答案。第二题公开撤销后所有调用 record_ids 为空，继续正确交付。此为内容有效拒绝及撤销继续证据，不是正向数学经验采用或性能提升证据。

测试服务正常终止后以相同源码/配置/数据库、SHOWCASE_WORKER_ENABLED=False 重启，只读浏览器刷新无写请求、无页面错误；两题 status、答案及其余持久结果（含完整请求账本、预算）一致，撤销状态保留。首题在第二题建立修订后派生 revision_allowed/revision_to 变化属当前链接视图，最初逐字比较因此失败，原失败保留；只排除这两个派生字段后其余结果完全相等。证据 artifacts/issue-183/live19/{outcomes,readonly-observation}.json 及截图。两次服务与临时30分钟检查均已结束；旧 unknown 不重发。缓存、自然并发/切换和 F4 仍未由本轮证明。

### 11:06 更新：live17 来源未准入

中断命令实际已启动 live17。首题 run_b4e1a87e66c7eef96795c597d86c7a95 succeeded、5请求、数学恒等式正确；形式生成返回 unsupported/spec_target_mismatch，无 Lean Attempt、无可信缓存条目。按事先合同不提交第二题，脚本保留 failed 原因 First task has no admissible source。服务与临时监控已清理。此轮不能证明缓存命中或当前 Lean 重验；不重发原任务，不放宽完整身份。继续只读诊断形式目标与规格差异，同时按既有合同启动 live18 数学计数代表题。

### 11:27 更新：live18 绑定拒绝与 live20 未命中

live18 run_cd1cb96fbfefc43184da053555bef7f6 为5请求/1Python，原任务 failed/invalid_problem_spec_work_units。两轮均主动选择 population，但把有先后依赖的 count_exact、proof_completeness 放入同一步；实际请求和修复反馈已明确禁止，自依赖拒绝正确。独立只读诊断未发现可解释该行为的产品缺陷，不增加 Planner 修复或同题重试。截图等待字体超时是独立观察错误，原失败保留。真实路线未执行。

live17 保存的两个原始 target 均为规范 forall x/equality；规格量词和方向确实都不同。仅补规范字段提示，公开 Intern 消息见证红绿及41项回归通过，两轴复查无待办。初次模块选择错误、0用例报告保留为失败。guard/权限/完整缓存身份未改。

live20 使用相同普通输入、最多两新题：run_b38cb641cbf3272128a912b524b88aec 正确交付，并有 formal_5b984557bedc446eb4371a37a1c7f031 的当前 Lean L2 回执、recursive_passed 来源审查和 active 缓存 eeace38bc1074402828d594183616b82；run_ac6d5a8ebf1516ad235b0d4dd5897007 正确交付但没有 receipt_rechecked。原验收 failed 保留，不能用两题正确冒充缓存命中。服务和临时监控已清理；身份差异只读诊断见 artifacts/issue-183/live20/。

所有代码修复聚焦证据与双轴报告复用，fbbb8e1 是本轮最终产品字节，须执行新的 gate-03。提交拆分时索引无上下文应用使部分提示位置与工作树不同，已用独立跟进提交对齐审查/测试过的最终文件；不声称各中间提交都经过门禁。最终门禁仍不能替代未实证能力。

### 12:19 更新：gate-03 失败及最小修复

上述“最终”产品状态为门禁前快照。gate-03 在4d0f851执行2127项，5fail/2error/42skip，source_changed=false；快速阶段通过，全仓阶段失败后未运行后续阶段。报告 artifacts/issue-183/gate-control/runs/gate-03/，原失败保留。

两处 error 是版本提示直接读取可选 schema.const：无 plan_version 的兼容请求触发 KeyError。复用公开示例测试先红1项/2子错误，再仅按 const 是否存在选择已有固定版本/正整数提示，未改schema或最终检查。15项相关回归及ruff通过，两轴复查无待办。

四处 provider_profile_unverified 由两条测试夹具 Planner 请求未登记 plan_version=1，仍为旧正整数schema指纹；实际请求已有const1。只补这两个夹具值，保留精确传输准入及所有断言，原4红/新4绿、完整模块21绿。独立两轴检查后冻结下一源码。

另1处取消/收敛用例原失败记录 reasoner client_exception/unknown，但未保留其发起 cancel 的原始响应，不能确认取消已提交；隔离1项5.847秒通过。故记未复现，不声称已修好、不更改生产取消/unknown策略；详见 artifacts/issue-183/gate-cancel-diagnosis.md。后续门禁若复现，先补原异常和取消事务顺序证据，不延长等待或放宽终态断言。

live20 未命中诊断进一步确认次题在缓存查找前已被形式准入拒绝，且首题来源澄清使规格v2、次题v1；full spec hash和量词/方向/根方向均不同，不删除身份字段或宣称提示保证一致。少量新代表题 live21 仅准备：8位/数位和36/模7计数、归纳与双射普通建议，数值和完备性分节，降低算术负担并分清两者。独立参考625579不送模型；不强制模式、不改WorkUnit绑定，最多1新题，须待最终门禁结束、实际启动时另记录身份，当前 not_run。

### 13:08 更新：gate-04 与 live21 接续

gate-04 在d354d40完成2127项，3fail/0error/42skip，source_changed=false；快速通过，全仓失败，后续阶段未运行。上一轮版本提示及四处精确传输夹具问题不再失败。剩余 native并发回执、取消收敛、显式unknown重试三例，原失败保留；取消/重试的有限捕获已复现模拟提供者在未看到converging时抛断言，并非已证明取消提交后被覆盖。诊断报告后续归档，尚未确认生产修复边界，不修改unknown或取消策略。

gate-04已终止且监控清理，live21按合同仅启动1新题；所有源码/文档/HEAD/dist冻结，期间只读诊断不落产品改动。真实能力与门禁失败分别记录，启动成功不代表本票完成。最终仍须修复已定位缺陷并按工程规则验证。

### 15:06 更新：同步夹具修复及当前目标示例

live21最终 failed/invalid_problem_spec_work_units，9请求、3工具、525804计账token、495.817秒，未进入自然路线；服务与临时检查均清理。后续不做随机同题重跑。

取消/显式重试的两例由测试复用双参与者屏障形成循环等待，捕获到实际回调原断言后，仅令每初始完整stepID参加一次屏障，保留2秒、所有调用和终态断言；2聚焦和15模块通过，提交486f84e。native测试的not-held检查及append存在竞态，两个verifier同时入选并等待原freeze事件；锁原子选择一个、等待放锁外，保留10秒和全部断言，提交bba3ec2。敏感测试同时仅在失败时附原始InternModelPort异常链，不改失败或unknown判定。两个切片独立两轴审查通过。

native原第一次修复后6项模块仍1fail，后续两个6项模块观察通过及exact1通过均保留，不改判原失败。纠正的因果探针证明：真实freeze提交后放行挂起调用，其新HTTP前预算准入拒绝，call为budget_rejected/action failed且结算后unknown_count0；在父finalization继续前结算，父任务仍正确完成1+1=2。此项不证明原未解释失败原因，不支持放宽生产冻结或导入迟到数学结果。首版跨线程查栈探针的自身错误及清理错误单列。见native-race-diagnosis及reviews中的完整边界。

Planner提示仅把固定虚构A/B实例改为当前全部根及必要辅助闭包的合法示例映射；实际计划、方法和模式仍由模型生成，schema、binder、路线独立性及核验不变。当前真实冻结规格的公开Intern消息见证red-03先因外来rootID失败，再通过全部schema及binder，输入不变。4项聚焦、45项相关回归通过；规范aux.description字段P2修正后4项复查通过，独立Standards/Spec解除。提交2736308，不宣称旧self-dependency因果已证明或实际模型能力已改善。

按用户15:03状态问题后的优先顺序，先提交冻结、执行gate-05，期间不穿插产品改动、模型运行或额外构建。全仓预计2130项，以实际报告为准，跳过仍未执行。自然能力缺口是#183关票条件，不另加成工程门禁项。潜在后续代表题尚未登记或启动。

### 15:12 更新：按用户优先真实效果调整

用户要求减少不必要离线测试、多测真实效果。gate-05在22aa5f7已过快速阶段、全仓尚未完成时中止：验证wrapper PID37612及创建时间2026-11-15T07:06:58.7608852Z后，仅终止其12个已核实子孙进程，剩余0；临时检查删除。原状态保存status-before-user-cancel.json，新状态canceled/user_priority_real_effects_before_exit_gate，不计全仓通过或失败。旧gate-03/04失败保持原判，最终退出仍须必要完整门禁。

live22已登记为当前合法示例的唯一真实观察，用与live21完全相同的普通数学输入建立一个新Job，隔离此次提示改进效果，不强制模式或填入规格/计划、不重发旧Run。源码及配置冻结后启动；参考625579不发模型，实际结果决定能力状态。后续不额外离线采样，真实失败确认缺陷时才做最小修复和必要聚焦。

### 15:26 更新：live22 正确交付及只读恢复

run_4c03a083b38c55f6601cbded768aa528 succeeded，6模型/6HTTP/2工具、343868计账token、289.868秒。交付625579，前缀DP递推及归纳完整性、四位分块双射及模7条件均与独立参考相符；整题LLM审查accepted/same_artifact，证据等级仍unknown/needs_review，不冒称形式证明。实际Explore直接解出，没有Planner、Population或切换，故新示例遵循/自然并发/F4仍未触发，不能以此次正确答案替代。

原服务正常结束、30分钟检查清理后，同源/配置/DB以worker=False重启真实页面，结果完整相同、6个Attempt未变，刷新可见625579，无写请求或页面错误；截图及readonly-observation.json保留。只读服务已停止。

接续一个不同的live23双参数四次式分类代表题（必要/充分及全部等号分支），仍普通浏览器输入及实际模型选择。独立解析参考另存ignored文件，未发送模型，未新跑离线测试。源码和配置冻结后唯一后台启动，结果另记；当前不据题目复杂度预判会触发规划或并发。
