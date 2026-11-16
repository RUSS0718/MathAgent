# #183 当前机器真实服务阶段记录

## 2026-11-16：格式验收与重启中断

用户将本票退出条件改为完整流程、正确格式及稳定答案读取；不再独立核对
数学内容。适用[合同当前口径](../engineering/faithful-service-183-contract.md)，
历史失败不升级、未触发不算通过，#183/#168 仍开放。

live31 冻结源码 `19ef7881dd286b5584e70b162fb4a5596e3b5e04`，配置 SHA256
`df24b52eac4bad622ac108883b94c6f3fd01ffb2adf1a46703ec528e2b36f42c`，
Job `run_cc46710e947a82cfa5b57a2cf900a797`。原始 SQLite 最后事件8876，
北京时间09:48:10.669815，Planner streaming；系统启动时间09:48:44。
未发现本轮旧进程或临时检查仍在运行。`identity.py` 返回0，无源码/配置漂移。
观察器 exited_without_final_status，不能冒认为正常终态或模型超时。

同库以 `SHOWCASE_WORKER_ENABLED=False` 恢复后，真实 HTTP `/health` 200；
公共 Job failed/needs_review，最后 Planner Attempt unknown，前10次已返回，
共11次请求、4次工具、675874本地计账token、1个未决。原 deadline 与授权
上限保持，未重新提交或重发未知。恢复投影 wall_time 包含停机至恢复的间隔，
不当作模型实际执行耗时。无完整最终答案，不通过完整流程验收。
证据 `artifacts/issue-183/live31/{recovery-job.json,recovery-report.json,
service.stderr.log,source-identity.json}`。恢复服务仅供只读核对，另记进程身份。

新场景 live32 仅计划验证短恒等式交付、可信缓存来源及条件性第二次自然命中；
不再追加四次多项式数学试错。真实结果另记，当前不算通过。

## 2026-11-16：#185 交付后接续及 live28

用户确认 #185 增量验收后，`0d9f86d` 已推送，#185 已关闭；本票和 #168 保持开放。
live28 源码 `5b435999874096b45748171e313eed18c9812703`，配置 SHA256
`e00d8711ade0349e2d006cfcd0f12ceedf7ec2377fb4a76d5d95e47b8027025d`。
同一普通双参数四次式输入，显式启用按需策略，完整工具/Population 配置及原
48/48/8、2097152、3600 秒授权不变，参考答案未送模型。

Job `run_5c75694426e1eb3871a2a3b9b7e277e7` 在 233.191 秒后失败：
`star_needs_review / adaptive_closing_reserve_required`。4 次实际请求均完成，
0 未决，1 次 Python，210480 本地估计/预留；provider usage 全部未知。
两次 Intake（含用户 no 澄清）、Explore 请求真实计算、Explore 工具续接。
初稿参数候选错误；工具代码推导了正确边界，但续接返回 schema 本身，
判为已知协议失败。随后转规划前，时间预留 4320 秒超过原根 3600 秒而停止；
无 Planner 实际调用、完整候选或最终审查，不算正确交付。

时间估算错误为把每个逻辑调用的配置份额再乘 `(retry+1)`。运输层重试共享
同一逻辑截止；最小修复仅将时间预留改成 `calls * timeout`，不改根预算、
deadline、调用/HTTP/token 准入、unknown 或数学标准。公共 Job 故障红见证
`adaptive-time-red-02`；最初 SSE 夹具未登记动态 schema 的失败不算本故障红。
公共夹具为已有非流式计量 transport，绿色前补齐 Planner method_id；
`adaptive-time-green-02` 两项通过，`adaptive-time-regression` 13 项通过，
Ruff 通过。两个独立静态审查（Standards Aquinas、Spec Cicero）无剩余发现，
未独立运行测试；不把公共夹具当真实 SSE 成功。

真实 UI 无页面脚本错误，只读刷新零写、答案和 Attempt 未变；终态后服务及
临时检查已结束。产品修改前运行 identity.py 返回 0。原失败、四份未知计量、
旧 unknown 保持，不恢复旧 Run。下一 live29 仅新建一次普通 Job，观察同一
输入是否越过原时间误阻断；不扩大授权、不随机追加。仍无完整深度、自然
热切换/F4 成果继续及可信缓存当前重验的正向闭环，本票未完成。

当前状态（2026-11-15，live27后维护）：live27约922秒提前失败，8次完成请求、0未决、预算未耗尽；错误草稿经过质疑后被历史规格变更条件误终止。已收窄到新路线绑定的当前规格及原图证据校验；旧Run不回填、不自动追加live28。live26根超时与1未知保持，未证明整题成功；#183/#168仍开放。

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

### 15:48 最终记录：live23 失败，按用户要求停止

冻结源码 ad356042c9bd652fd9e66a792d7a5d4db6d6f840；run_728ebfabf590b69b68c0a4ccc0bc834b 于15:45终态 failed/job_execution_failed，solver partial_aborted/incomplete，原因 route_duplicate_route_frontier；没有完整 final_response，5个根义务覆盖0。12模型/12HTTP/1工具、897168本地估算计账token、1190.688秒；12请求均success/completed，provider用量仍未知，不把计量未知误报为请求失败。根限额2097152/2400及48/48/8未耗尽，直接终止原因不是超时或根预算耗尽。

Planner合法绑定并自主提出population（3独立路线）；准入因root_budget_insufficient选择serial。该并发准入拒绝与最后重复路线前沿终止是两个事件，不能混称。没有实际自然并发或热切换；Meta有intervene提议，但serial_intervention.status=skipped、pair_id=null、adoptions=[]，不计F4闭环。其假设把参数分区阈值对调：例如a=0,b=0被假设排除，实际x^4+1恒正；a=6,b=14被假设纳入，取x+1/x=-3则P/x²=-3<0。这是中间假设错误，尚未成为最终交付；独立参考始终未发模型。不据终态码猜测重复前沿的更深实现根因。

证据：artifacts/issue-183/live23/run1-final.json、run1-report.json、run1-terminal.png、source-identity.json及independent-reference.md。已核对本轮wrapper2760、observer14868、服务36180和uv17548均退出，8103无监听，MathAgent-Issue183-live23临时任务已删除；旧8100展示服务保留。截图失败提示与实际Job终态一致。

用户明确要求“等待live23结果然后停滞”，本轮至此停止：不修复、不新建模型任务、不再跑离线测试或门禁、不推送关票、不接续新session。#183/#168保持开放，自然并发/切换、F4、缓存当前重验及最终源码必要门禁仍缺；gate-05 canceled及此前失败保持原判。继续时沿用当前所选模型，具体继承型号无法确认，不猜测。这里只完成结果归档与清理，不宣称本票验收完成。

### 16:00 接续：用户授权3600秒及路线身份最小修复

用户进一步要求提高总时间并解决失败，恢复本轮工作。仅新live24根/Population时限3600秒，其余2097152 token、48/48/8及单请求360秒不变；全部旧Run不改。live23准入时原计账153131，加两路线与收尾1786422共1939553，未超2097152；实际时间要求2880秒，根总限2400、前置约221秒，时间检查必不通过。提高至3600能容纳该已观察计划，不能保证任意新计划。

已复现live23终止机制：Meta CONTINUE将action attempt0→1，计划版本1和frontier不变；sync_plan_route却要求路线初始attempt也相同，误登记后被合法的duplicate guard终止。修复39ca1e9仅移除复用检查的attempt条件；路线计账/原attempt/谱系和新求解动作身份都保留，替代新计划同前沿仍拒绝。真实run_meta→新attempt→重开DB→sync的一项回归先红STEP_EXECUTE!=TERMINAL，后绿；新版本重复反例仍拒绝。最初命令误用--output-dir只产生CLI参数错误，不算红证据；有效红绿见route-continue-red/green.json及log。37项受影响路线/恢复回归65.362秒通过、1skip未计覆盖；ruff通过，独立Standards Kuhn/Spec Ramanujan均clear，审查未自行重跑测试。

live24仅准备普通输入的新Job，沿用live23数学题，唯一诊断目的为实际准入及完整正确交付；若未触发CONTINUE则不冒称真实再次验证旧分支。参考不发模型、不固定计划/模式、未新跑整仓测试；源码/HEAD/dist/配置冻结后唯一启动并安排30分钟临时检查。当前not_run；启动后由live24/check.ps1提供实际PID/创建时间/阶段/计数/日志。旧8100保留，#183退出仍未满足。

### 16:16 live24 实际结果：总时限生效，单请求超时未知

冻结源码8d60bb7ad40e6be41c4b400aa9b94c9660698159（含修复39ca1e9），配置SHA256 7a36aaa9553da35c78e2d443474c47f894514437c7bbaab58e2dbce48e774cdd；唯一普通输入Job run_d1f7f56213dbceee5eb28b1cb4f046a1，16:00:37–16:14:54，终态failed/star_needs_review，faithful.phase=unknown。6模型/6HTTP/1工具、364419本地估算计账token、856.955秒；账本确认根时限3600、tokens2097152及48/48/8，未耗尽总时限。第6次Reasoner已收到HTTP200但未完整完成，360.345秒timeout，1 unresolved_attempt；provider usage未知与该实际未知调用分别保留，不填零或自动重发。

模型提出population，实际仅1个符合独立性判定的路线，因independent_frontiers_required选择serial；该分支先于预算检查，不得声称新时限已通过并发预算准入，亦不能以模型文字“两个独立方向”代替合法独立前沿。4个根覆盖0，没有完整答案；未进入Meta CONTINUE，未再次触发旧重复路线错误，因此39ca1e9仅有确定性红绿/恢复回归支持，不能冒称此次真实运行验证了旧分支或完整服务。

启动首次误传短SHA触发HEAD mismatch，未建worker/Job；改传完整HEAD后唯一启动成功，旧guard及旧Run未重用。唯一后台wrapper22440(08:00:22.350784Z)、observer41940(08:00:30.9072647Z)、服务37012(08:00:24.6519484Z)、uv10552(08:00:24.5586256Z)均退出，8103无监听，MathAgent-Issue183-live24检查已自动删除。终态后identity.py检查通过，确认运行中源码/配置/dist未变；旧8100服务保留且未加载本轮修复。run1-final.json、run1-report.json、run1-terminal.png及source-identity.json均保留。

本轮只完成新任务总时限授权落实及已复现路线身份缺陷的最小修复；实际正确交付仍未达到。当前无新运行，不自动重试该unknown，不增请求timeout或继续随机换题；如后续显式处置未知调用，仍走既有新调用身份/原根剩余额度及deadline合同。#183/#168保持开放，必要最终门禁尚未执行；本次未重复离线全仓测试，未推送或关票。当前选择模型保持，具体Codex型号继承未知。

### 16:30 流式策略接线修复及live25准备

用户要求修复并再跑一次。源码efff923d7ab3af931c3e835a7ef20f1700a46c79新增可选JSON stream_timeout_policy_version，经既有policy_for_version严格校验映射App配置；省略/null保持关闭，不改全局默认、旧Run或adapter策略。原新字段不获加载的2案例先红后绿；14配置及25相关S01（活跃长流/有效idle/根deadline/公共Job冻结恢复/调用依据等）共39项40.719秒通过，ruff通过。两轴McClintock/Leibniz独立只读审查clear，未独立执行测试。不据此宣称真实长流已成功。

live24草稿端点2b系数与a=±4边界错误已确认；同冻结状态按compose_request重建含Explore已计算端点输出，未发现漏传，consumed_receipt_ids空仅是无report直接引用。草稿不完整JSON且0accepted步骤，未执行其提出的工具请求，不能计正确交付。本次不把独立参考、反例或正确判据写入模型提示，真实运行仍须现有工具与Verifier纠正并完成全题。

live25已准备唯一新普通Job，沿用live24输入，显式faithful-stream-v1；新根3600秒/2097152及48/48/8、旧request配置360保持。旧360配置在新策略下不是活跃流整次硬截止，原phase/batch/Run截止仍优先。上线前preflight确认映射，新Job后核对账本及attempt的策略身份，实际是否越过360及完整正确答案以真实结果为准。启动时源码/HEAD/dist/scripts/config全部冻结，唯一后台与30分钟临时检查；不重试旧unknown。当前准备not_run，状态见artifacts/issue-183/live25/status.json；旧8100展示仍保留，#183/#168未完成，不在此切片重跑全仓门禁。

### 17:12 live25 结果：长流与自然并发实证，版本冲突失败

冻结源码1cfdc603d3ae37d1ec8a70c170ce4593cc5b2461（产品efff923），配置SHA256 1065c88735a534a0631ce5d1c8f97612ff2601e6fb54f4cde4dcde0bc59fddfd。新普通Job run_dc0853536d2dc1a7ec2bf23c8b21809e，遇真实机器证明来源澄清时按普通证明意图经UI答no（202），规格/输入v2，未预置Spec/Plan或数学参考。实际账本冻结faithful-stream-v1/effective_idle30/soft_prompt1200；物理请求记录call_policy_evidence同版，根3600/2097152及48/48/8不变，旧Run未迁移。真实Planner自主population，2独立路线获independent_routes_admitted，Reasoner于16:36:00.405835和16:36:00.467062启动，约61毫秒间隔、实际重叠。两者完成604.560/769.735秒，StepVerifier完成530.426/855.904秒，均超过旧360硬截止。证明此轮活跃长流接线与真实并发执行，不代表并发正确交付或数学能力提升。

两个Reasoner初版草稿仍错：倒数路线把参数分类大小区间倒置且写出b>=2+2|a|，SOS路线系数匹配错误、错误宣称边界b=a²/2-2。StepVerifier均CHALLENGE，没有完整答案或根义务接受；SOS质询引用实际展开正确指出x³=2p、x=2p+2qr及常数r²+1，不能忽略r=0。倒数路线质询虽然判FAIL，其修正说明仍把顶点是否在允许域及区间判据倒置，不能将LLM质询当独立正确证明。数学错误未被本次配置修复解决，独立参考仍未发模型。现有零点/分类正确性门槛不降低。

17:09左右公共Job终态failed/job_execution_failed；根耗时2244.455秒、计账1276195（本地估算，provider用量未知）、2工具，4根覆盖0，无完整final_response。账本logical_calls/http_attempts各13，公开request_attempts10条，不能直接说13次已完成物理请求。最后StepVerifier记录unknown/348.881秒，非timeout分类、无finish_reason；unresolved_attempts1。服务错误日志第745行记录SolverRevisionConflictError，调用栈指向star_product_pipeline.py:510提交formal_generation_unavailable→storage.py CAS拒绝，邻近同时有Population流活动。确认新的工程失败位置，不冒称已最小复现完整竞态或已修复；并发成功不等于完整F2退出。公共Job已失败而Solver快照仍running/POPULATION的不一致保留，不改写旧现场。失败后本轮服务退出，在途核验结算unknown；无自动重发，不把unknown归咎于新策略有效idle超时。

终态证据：run1-final.json、run1-report.json、run1-terminal.png、service.stderr.log及source-identity.json。主agent终态后identity.py退出0；wrapper19048（08:31:45.190047Z）、observer7908（08:31:52.7450859Z）、服务40932（08:31:46.5882329Z）、uv34652（08:31:46.516061Z）均退出，8103无监听、MathAgent-Issue183-live25已删除，旧8100展示保留。本轮唯一新Job已完成观察，无live26或额外门禁/模型任务；39相关离线检查复用，不再扩增测试。#183/#168开放，仍缺完整正确并发交付/切换/F4/缓存当前重验及最终必要门禁。当前选择模型保持，具体Codex继承型号未知。


### live25 后维护：并发等待误耗阶段轮数

本题为代表性双参数互反四次式非负分类，没有标准题库难度标签或已核实竞赛出处；高中竞赛代数中等偏难仅为人工判断，不作评测等级依据。

以维护前源码0c751b882f1f46800a934d5cc90bcdbeaa867b12只读分析live25原SQLite：population_updated共68次，其中last_observed_at恰64次，另外2次closing_reserve及2次调度变化。最后观察09:09:22.061821Z，持久状态仍POPULATION/running；同一时刻StepVerifier仍有流活动，随后pipeline.py:510的formal_generation_unavailable过期快照CAS失败。控制器advance_product原for range(64)将每个最长30秒的等待tick当成阶段推进，耗尽后返回给结果构建，形成提前收尾。见artifacts/issue-183/population-wait-diagnosis.json及原service.stderr.log:745。无数据库改写。

公共真实loopback HTTP Job见证test_more_than_64_pending_ticks_do_not_end_the_public_job：仅将等待加速并将真实worker延迟至第65次，保留真实控制器/存储/模型HTTP/审查/交付链。修复前star_needs_review、无完整答案；首个red另有未结束worker持有临时DB的清理error，保留不计独立产品故障，测试随后增加finally释放并等待worker。最小产品修改仅controller.py：在途POPULATION或converging等待不计64次上限，每轮仍check_control；非等待保留原上限，TERMINAL允许迟到结算，不抑制CAS冲突或重新派发unknown。修复后同一公共见证5.613秒通过并交付受控1+1答案；不是原题数学效果证据。

证据：population-wait-red.json/.log、population-wait-green.json/.log；3项边界最终population-wait-boundaries-final.json/.log通过（无revision等待、非等待64上限、取消/原deadline停止）；8项受影响回归population-wait-regression.json/.log在43.238秒全部通过，覆盖普通自主并发、转串行、未知不重发、原deadline、取消、完成后迟到结算、CAS保护及完成回执恢复。合计12项不同用例，ruff与diff检查通过；不重复全仓门禁。Standards审查Mill（01a1de85-e108-7973-abb1-ff8973411768）、Spec审查Godel（01a1de85-e250-7a00-8882-853f173b399d）均clear，只读且未运行测试；报告population-wait-review.md。产品维护提交SHA见git fix(showcase)并发等待提交，不以文档HEAD替代原live源码。

原live25失败与1未知仍原样；本次没有live26、额外provider请求、服务8100更新或#183完成声明。数学草稿错误、完整正确并发交付/切换/F4/缓存当前重验和阶段最终必要门禁仍未完成。


### live26 终态及流式保存热点维护

冻结源码9808696dedbf3359b062bb1eef81635ad900593e，配置SHA256 1065c88735a534a0631ce5d1c8f97612ff2601e6fb54f4cde4dcde0bc59fddfd，普通新Job run_665ec8174ffb4d4b7418fe99cfa27e01。实际模型自然选择2独立路线population，109次last_observed_at后仍未提前结果收尾，无SolverRevisionConflictError，旧64轮故障未复现。18:30左右按原根3600截止，公共failed/run_deadline_exhausted，耗时3605.661秒、计账1668311本地估算、1工具/2.375秒、unresolved_attempts1，无final_response。账本预留logical/http各15，公开attempts6，不能说15次实际完成请求。

物理记录：intake17.266秒、Explore4.300秒、Planner79.783秒完成；一Reasoner1026.899秒、4610字节/501事件完成，StepVerifier2449.208秒、4439字节/531事件到根截止timeout且无finish_reason。另一Reasoner物理记录success/stop、13742字节/1789事件但duration缺失，持久逻辑call仍streaming；原差异保留，不冒认已提交数学成果。完成的Reasoner草稿仍错误：把|a|≤4的不可达顶点当可用，又把|a|>4的可达顶点排除；其小分支宣称b≥a²/4−2，(a,b)=(2,−1)会被错误纳入而P(−1)=−3。尚无四个根义务的接受或最终审查。

唯一后台已结束；wrapper32712（09:29:55.7075408Z）、observer24084（09:30:03.5787014Z）、服务32900（09:29:57.3900690Z）、uv31216（09:29:57.3128952Z）均已退出，8103无监听，MathAgent-Issue183-live26删除；原8100未动。终态后、产品修改前identity.py无异常通过（同批命令最终exit1来自无监听查询，非身份错误）。原预检首次缺少同配置相对引用lean-manifest.json，未启动服务/模型；补复制原manifest后通过、只提交一个新Job。原失败/unknown无重试。

性能定位：原SQLite只读；get_run-profile.txt显示8498历史事件的单次读取约0.113秒。profile-route-save.py将原DB备份到内存，仅在副本调整停止状态/过期deadline以重放纯本地保存，无模型工具端口；真实RouteHarness/calls._save/population_store路径，两次保存原profile约2.35秒，主要为重复读取及深拷贝。最小修复仅population_route.py及population_store.py；复用本次current、交接新解码独占的snapshot/events、仅route_commit使用事务新解码独占population候选。保留最终数据库重读以看见observer写入并隔离载荷修改；不省略历史、receipt校验或CAS，不用长期缓存或批处理。

证据route-stream-red.json/.log（4次读取超过3的红见证）、route-stream-green.json/.log；最终route-stream-store-final.json/.log为15项，route-stream-public-regression.json/.log为6项（33.219秒），21项不同用例通过，ruff/diff通过。覆盖复制隔离、回调实际终止及载荷修改、候选修改后身份冲突回滚、owner/冻结/未知/预算、真实loopback并发交付、迟到结算、原deadline、取消、转串行及只读不重发。独立Spec Kepler（01a1deca-9351-79e0-aa2a-88d29a87038c）与Standards Darwin（01a1ded6-ef84-7af0-9570-79622f0acc33）均clear、只读未跑测试。

同现场无profiler、相同projection observer、交替baseline/fixed/fixed/baseline成对重放：四次保存中位2.435602→1.542778秒，约减36.66%；route-save-paired.json及paired-route-save.py保留命令，基线取固定9808696两个产品文件，原现场只读。profile下2.35→0.90秒不是无profiler真实收益数字；不据此推断远端生成耗时或整题墙钟。剩余完整历史读取仍有开销，不宣称全部消除。

维护后至多一个普通新live27核对实际效果；准备与实际运行分开，以该目录status及后续终态记录为准。无完整正确并发交付、切换/F4/可信缓存当前重验及最终门禁前不关闭#183/#168。

## live27 真实失败及历史规格保护修复

源码305949010daf45974c26af82110050f60d971be1；配置SHA1065c88735a534a0631ce5d1c8f97612ff2601e6fb54f4cde4dcde0bc59fddfd。run_60cf13e04847a4ac0703f73eacb533d9于18:58:51至19:14:13运行921.891937秒，failed/star_needs_review、partial_aborted/route_requires_reevaluation；496617本地估计/预留token、8逻辑/8HTTP且8实际公开请求均success，2工具约5.437秒，0未决。unknown_attempts=8为provider用量缺失计量，不能误报8次未知调用。模型自主选择串行，不能直接和并行live26比较整题提速。

顺序：Intake21.636秒→用户no澄清→Intake39.339秒、规格v1→v2→Explore5.872秒→Planner124.763秒后checkpoint校验失败→第二Planner206.971秒→Reasoner263.801秒→两次Python→StepVerifier147.179秒请求反例→Researcher86.669秒NOT_FOUND→CHALLENGE/Conjecture→上述保护终止。Planner和Reasoner的参数边界公式错误；Python完成有效符号计算但未证明最终结论，NOT_FOUND也不能替代证明。质疑应当保留。没有进入Meta/后续步骤/整题审查，未形成完整答案。

故障：route_graph_refresh原先遇任何历史problem_spec_change即拒绝重评，未区分澄清发生在路线创建之前。现场路线建立于v2，后续图仅新增未导入Conjecture，原支持未撤回，却被历史v1→v2记录永久阻断。最小修复为新路线冻结可选specification_version，存储校验禁止改写/删除/旧路线回填，且新绑定必须来自当前ProblemSpec；同版本才可继续原有加性图检查。旧路线无法可靠恢复绑定时保留原阻断，跨规格、冲突和支持撤回仍拒绝。

证据artifacts/issue-183/route-spec-red.log为修复前4项回归的7个失败断言（首次测试调用签名错误已纠正，日志保留有效红见证）；route-spec-green.log为新4项及原路线/派发保护22项，共26项通过。route-spec-public.log另2项公共串行Lemma/Conjecture接缝通过，20.772秒。ruff及git diff --check通过。live27/replay-spec-refresh.py只读原SQLite并在内存用生产注册入口新建同规格路线：新路线能重评、原无绑定路线仍阻断、图内容及原数据库未改；属于故障接缝重放，不能称原Run恢复或新增真实成功。

终态后identity.py返回0才进行产品修改。wrapper37716、observer39528、service31648均已退出；8103未监听，MathAgent-Issue183-live27定时检查已移除。原status、日志及terminal截图保留。修复尚未做新provider-live验证，不自动追加同题调用，也未执行本轮最终全仓门禁。

首次双轴独立审查未完成：Spec Ptolemy（01a1def8-c1c5-7231-bb7f-58e8b0debf22）与Standards Meitner（01a1def8-c2f3-7732-ac30-89ee1bd97242）均因本地代理/上游503、request recording storage unavailable退出，不能记为clear。两代理已关闭，此失败历史保留。

用户随后要求修小bug并提交推送。新Spec Russell（01a1df01-dc55-73c2-bce3-b4f4cba41bc5）及Standards Singer（01a1df01-dda8-7fe1-a2b7-cf53f92a3761）均发现等值异类型可绕过既有身份比较；修复为同时比较字段存在性、类型和值。route-spec-bool-red.json/.log保留1→True红见证；最终route-spec-recheck.json/.log为30项、0失败/错误/跳过，19.660秒。新增2→2.0和1→True拒绝（含有效lineage）、合法绑定注册/流转、无规格变更历史的旧路线兼容检查；其余复用相关公共回归。仅随后调整测试导入换行，ruff与diff检查通过；官方baseline共11文件SHA256保持。两轴定向静态复查均无剩余发现。此次为小范围修复提交，不是#183阶段退出，不重复全仓门禁或新增provider-live。


## 2026-11-16 live28/29 接续结果

#185 的 0d9f86d 已推送并关闭该票；继续 #183 的 5b43599、86173f5 也已推送。
live28 233.191 秒、4 次完成请求、0 未决、1 Python 后，收尾时间预留被误乘
运输重试数而拒绝规划。实际重试共享逻辑调用截止；86173f5 仅去掉该重复倍数。
公共红绿、13 项聚焦回归和两轴无发现复审见 adaptive-time-*，不重复全仓门禁。

live29 冻结 86173f5ac81917195ed546225d918db30ab388dc，配置 SHA256
 e00d8711ade0349e2d006cfcd0f12ceedf7ec2377fb4a76d5d95e47b8027025d，Job
run_da0f0b8ae8b48ac1e1fb7b8e4eeff469 failed/reasoner_checkpoint_round_limit。
1913.624 秒、14 模型/14 HTTP、6 工具、本地计账 981168 token、0 未决。
14 个物理请求全部 success，用时合计 1859.767 秒；provider 用量未知的
unknown_attempts=14 不表示 14 次远端结果未知。根 48/48/8、2097152、3600
未耗尽，不能归为预算耗尽或超时。

实际顺序：Intake→普通证明来源澄清 no→Intake v2→三次 Explore（前两次
Python 错误）→Planner→Reasoner S1→StepVerifier 及两次工具续答→Researcher
→Reasoner 局部修正→StepVerifier→Researcher→检查点轮数上限。Planner 选
population，但仅一个合法独立前沿，按 independent_frontiers_required 串行，
不算自然并发。仍停在五步计划的第一步，四根覆盖零，没有完整答案。

两轮最终审查都为 YES/PASS/ACCEPT，却将已审查换元恒等式声明为 general_proof、
both_directions_proved=false。第一轮此前错误请求符号系数 polynomial_check，
后经真实 Python 化简得到 0；最终文字确认三条 claim 成立，结构字段仍声明缺证明。
第二轮同样矛盾，Researcher 均 NOT_FOUND，依现有保守合同不补证明，遂再次返工。
原始完整调用留在本地 SQLite；限定证据见 live29/verifier-witness.json。

UI page_errors=[]，只读刷新 writes=[]、完整 result 相同；终态 identity.py 退出 0。
wrapper11484、observer43292、service21544 均退出，8103 空闲，临时检查删除。
旧 8100/PID15376 保留。上述失败及旧 unknown 不修改、不自动重发。

追加 F5 管理补验时，SQLite 副本加服务和浏览器组合操作被自动审批拒绝，理由仅
blocked by policy；没有执行备份、启动 8104 或管理写入，management01 未运行。
不绕过拒绝，不计通过或测试失败。自然并发正确交付、切换/F4、可信缓存当前核验
及最终必要门禁仍未完成，#183/#168 保持开放。


### 终态审查矛盾的最小修复

冻结 ProblemSpec 的 StepVerifier schema 将非 ACCEPT、带真实工具请求的暂定
ACCEPT、无待执行工具的终态 ACCEPT 分支区分。终态须 YES/PASS；可省略
answer_claim，声明非数值证明时须明确证明完整。数值声明及旧无规格审查保持原
兼容和保守反例兜底。修复提示要求重新核对当前证据作裁决，不静默翻转 false，
不强制保持自相矛盾的旧 verdict。首答、工具续答与 claim 目标修复共享本审查链
的一次额度，恢复时从持久调用记录识别已用额度。工具续答依据异常的实际调用
身份区分 known/unknown，unknown 不再落为旧协议失败后的 step_reviewed。

公共红 verifier-consistency-red 保留初答/续答无法交付及 schema 放过矛盾；
其中旧无规格兼容断言误含 obligation_evidence，随后修正测试夹具，不作产品故障。
green01 两项暴露了原始 request 未带扩展规格，修复提示改从实际失败调用判断；
green02 的 6 项通过。独立 Standards Jason、Spec Turing 发现续答 unknown 误分类
和组合路径重复修复，review-red 两项稳定复现后才修改。green03 的 9 项通过。
最终 verifier-consistency-regression-final 为 50 项、0 failure/error/skip，76.595 秒；
覆盖旧反例、合法部分成果、工具回执/来源、协议交接、根调用预算及 unknown。
单项 unknown-red 实际为通过（原断言不足），不作为红证据。Ruff/diff 检查通过，
11 个官方 baseline 文件 SHA256 一致；未重复全仓门禁，不代表真实求解已修好。

只读性能补查：live29 原库 mode=ro，9844 事件三次 get_run 合计约 0.326 秒，
其中 JSON 解码约 0.214 秒，见 readonly-load-profile.txt。首次探针遗漏 Row factory
导致诊断脚本异常，补齐后测量；不是运行时故障。不由该局部测量推算远端占比，
本切片不添加缓存、批处理或性能改动。

live30 仅准备一个新普通 Job，沿用 live29 数学输入、完整能力与原授权预算，
诊断修复后的审查链和完整正确交付。模型仍自主决定规划与模式；参考不发模型，
不预制规格、计划或成果。双轴复查清零、提交冻结后才启动，原 Run 不重跑。

两轴受影响部分静态复查均 clear：Standards Jason 01a1e1d5-ca1d-79e3-9860-973a1b464b99；Spec Turing 01a1e1d5-cb22-72d2-a3e4-9fd31a6050f7。两者未独立运行测试，均已关闭。


## live30 真实拦截与 oneOf 诊断误导

修复7b01eaa已推送；唯一普通Job run_16d198f6578b44b71663959667f0d29e，
配置SHA256 df24b52eac4bad622ac108883b94c6f3fd01ffb2adf1a46703ec528e2b36f42c。
720.310秒、8模型/8HTTP、2工具、本地计账529649 token、0未决；8实际请求均返回，
两个StepVerifier为已知协议失败，不是unknown；provider用量仍全部未知。
Planner首答自依赖后有界修复，只有一个合法独立前沿，走串行；S1仅安排证明，
Reasoner已列多个错误的待证猜想（边界和零点均不符合独立参考），没有完整答案。

首个StepVerifier在文字确认当前安排已完成后，仍返回ACCEPT及general_proof/false。
新协议正确拒绝并派发一次重裁；第二答仍完全相同，按合同停止。无Researcher、
无NOT_FOUND返工、没有整题正确交付；证明了真实拦截和有界停止，不证明修复提示
能够纠正模型。run1-final/report/ui/refresh及verifier-witness保留。UI无脚本错误，
刷新无写；终态identity.py退出0，自有wrapper37228、observer27316、service22120
均退出、8103空闲、临时检查删除。旧8100保留。

实际重裁的schema_errors把唯一问题报为$.verdict枚举不接受ACCEPT。根因是
_schema_diagnostics对oneOf只按分支顶层原始约束筛选，三个object分支均进入，
按错误数取第一个tie，误选非ACCEPT分支。模型第二答文字明确引用这个错误，
原proof=false未改。verifier-diagnostics-red稳定复现无tool_request及null两种
相同错误；只改诊断分支形状选择，不改接受校验或增加重试。green10项通过，
真实两答只读diagnostics-fixed-replay均仅指向$.answer_claim.both_directions_proved。

最终verifier-diagnostics-regression为51项、0 failure/error/skip、81.910秒；Ruff/diff通过，11 baseline字节一致。Standards Bacon（01a1e1ee-7350-7442-8467-eb343f10f286）与Spec Schrodinger（01a1e1ee-743f-7080-ab3c-b821a4179e34）独立静态复审均clear，未独立跑测试，已关闭。至多一个新live31准备，原输入/授权不变，源码冻结后启动。
