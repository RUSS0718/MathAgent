# provider-live 修复与重跑循环

## 归档状态（2026-11-06）

用户要求结束本轮线上推进，整理仓库并集成PR #129。readiness30为第12步单调用1200秒截止、unknown_outcome；readiness31改为较简单数论题后在第6步Verifier流中connectivity中断、unknown_outcome，未触及单调用截止。旧证据原样保留，两批均未交付，不把连接错误、预算停止、协议/交接缺陷混为一类。详见各批次终态及[复盘](provider-live-retro-20261106.md)。

repair_round13、policy_change_rounds2、implementation_round15、live_attempt22。当前无活跃Run，服务已核身份停止，唯一provider-live监控删除；其他窗口任务未改。#127仍open，#128线上两臂NOT_RUN，usage UNKNOWN。代码集成只表示工程变更归入分支，不表示能力验收通过。取消单调用固定截止、压缩和记忆属于后续候选，未在本轮实现。

以下保留各阶段当时决策与后续覆盖记录，不能把最初计数/策略当当前指示。

用户于2026-11-05重新授权修复后真实重跑，每10分钟监控；从本授权起编号，超过5轮仍有新错误时先做小型简化重构。历史readiness-01至07单独保留，不重置或改写旧失败。目标仍为#127自然多步独立验收，再执行#128真实单因素配对。

第1轮：readiness-08，针对07的verifier_tool_request_unfulfilled。确认Registry的tool_schema_invalid在tool_precheck保存时丢失，模型只收到tool_error。修复保留固定白名单错误类别，不保存任意异常文本；明确提示根据已有工具schema修正不同参数或保留异议，不重复相同失败请求。原重复请求禁止重执行、局部两次工具上限、全局预算、unknown不重发保持。

新增回归先RED（错误类别缺失），修复后3项通过；真实Registry拒绝符号参数后，可在原界内执行修正的数值参数，实际provider消息保留错误类别与schema，任意错误文本不落盘。相关28项运行通过（1项条件跳过，后续新增实际消息检查单独通过），Ruff/diff与快速门禁通过。官方baseline无差异。未跑耗时全量测试，不以离线结果代替线上验收。

循环状态保存在忽略目录artifacts/provider-live-repair-cycle-20261105/cycle.json。每轮归档具体阶段、错误码、首末正文、回执与独立报告；相同根因重复和新根因分别计数，修复以证据为准，不盲目放宽配置。若是模型审查分歧而非实现bug，明确报告，不伪造PASS。

第1轮08失败：成功工具回执后的明确CHALLENGE附带重复请求被视为unfulfilled。新增根因轮次1。第2轮09前按同scope成功回执消费明确异议的小型简化修复，重复工具不执行，ACCEPT/失败/unknown不放行。原模型/预算/样本不改；不是以历史07同名stop reason混为同根因。

用户补充决策规则：累计达到5轮已实施修复时，在下一轮修改前请独立子智能体比较继续局部修复与小型重构的收益、成本、回归风险和稳定性影响，由主智能体依据证据选择并持久化理由；不预设重构更优。此规则替代此前按new_error_rounds>5强制重构的规则。活动Run期间仅分析，终态后修改；同一评估不因定时触发重复执行，新根因或范围扩大时重新评估。当前登记为第2轮，尚未到新授权循环的5轮阈值。


第2轮09失败后，第3轮前修复两项已确认分类/计数缺陷：stream adapter对HTTP token预留拒绝原样透传BudgetExhausted，未获HTTP准入不进行不存在的attempt结算，沿既有calls预算终态处理；工具账本结算只保留明确布尔执行证据，timeout仅在unknown_outcome=false且cleanup_verified=true时不计未知，历史缺字段和清理未确认仍计未知。原账本限额及logical31/HTTP30历史不改。新stream回归先RED后GREEN，明确确认0出网、0伪HTTP结算、charged不变；相关集成24项通过，快速门禁通过。工具证据安全复核收窄到bool，不复制任意status/输出。修复只改善实际状态分类，不能凭此声称样本已交付；下一轮仍须真实API和独立核验。

第3轮真实预算停止后提前做有界风险收益评估（不是凑足5轮）：独立审查确认sessions.append_exchange保留各轮challenge_history，prepare_session将其再次连同当前完整history注入，是累计前缀重复而非无限递归。选择先验证注入层精确前缀去重，优于同题盲重跑/prompt补丁/换题；仅同session且同plan/attempt/step且精确前缀相同时省略历史副本，持久原记录、当前完整history、各报告/响应/工具回执保留。字段不足/不匹配则不去重，需真实数据量化和RED/GREEN才能实施与新Run；不宣称必然交付。当前已实施仍3轮，未提前把验证候选记成已修复。


第4轮前精确离线测量纠正：真实旧history每轮最后verdict有修订，整个旧数组并不与当前前缀完全相同，初始“整字段删除”方案不能应用。改为只省略逐项完全相同的最长公共前缀，并加current_request.challenge_history长度引用，保留不同尾部，可精确重建每条旧history。仅同session(scope校验含plan/attempt)、明确同step_id且无既有引用时做注入副本转换，持久record/当前完整history/全部报告响应回执不变，跨步骤或不匹配不省略。代码约20行，不加配置或通用框架。

真实10DB只读prepare_session重放：session_history JSON由99032降到75345 bytes，净减少23687，4条引用，逐条断言旧history可精确还原且响应不变。是字节量，不等同provider token或必然交付收益。新RED因无引用字段失败，GREEN检查重建、原run不变、跨step/不同前缀保留；快速门禁通过，完整相关会话/挑战/恢复回归结果以随后追加为准。旧10仍真实预算FAIL，不追溯升级。

用户在第4轮冻结前明确授权增加预算。readiness11新登记每题128模型/HTTP、32工具、16777216 token预留、14400秒，2题批次256模型/HTTP、64工具、33554432预留、28800秒；单次900秒和30秒流空闲不变、best-effort关闭。服务实际limits与manifest同步核对，不在运行中扩预算，不改旧批次或官方baseline。上下文简化相关49项1跳过/快速门禁/Ruff通过。

用户明确计数口径：只有自身设计/实现失误的修复计一轮；TLS连接故障或真实预算不足不计。把预算拒绝误分类为unknown、已终止timeout误计未知仍属自身实现缺陷，计入。当前自身修复4轮：工具错误反馈、成功回执CHALLENGE续审、预算/timeout分类、重复挑战历史注入简化；真实预算停止和外部TLS尝试另计live_attempt，不凑5轮。


readiness12于15:44:38终态FAIL：完整Meta guidance将rationale拼为reasonale，invalid_role_schema；不是TLS/预算不足。Meta未复用既有单次格式修复是已确认自身实现缺口。本次修复只接入protocol_repair，保留新call身份、预算准入、unknown不重发、第二次错误终止，不加错拼别名。新增回归先RED后GREEN，相关17项、快速门禁、Ruff/diff通过。策略独立复核完成后登记第5次自身修复；live_attempt与repair_round分别累计。旧12非空partial文本未完成整题审查绑定，不能升级PASS，#128仍NOT_RUN。

第5轮策略独立审查已完成（代理01a1aab5-5336-72c3-951f-b42e8c918600）：没有阻断项，推荐Meta局部复用既有单次protocol_repair。主线程采纳：局部约18行源码变更可覆盖实际故障，复用身份/预算/已知失败边界；全角色dispatch重构虽可统一流程，但要协调各角色事件、身份、二次错误及Planner结构校验，成本与回归面更大，缺乏收益证据。非阻断不确定处：修复预留先记计数/事件，后续准入拒绝时可能仍保留预留计数，本次测试未覆盖预算临界点，不能据此断言线上bug。完整比较保存于artifacts/provider-live-repair-cycle-20261105/strategy-review-round5.json。自身修复累计5轮；后续新根因或范围扩大、再次改代码前须据新证据复评，不因每次定时触发重复审查。

readiness13完成2/2，task/coverage/transport PASS、usage UNKNOWN，但vieta合法FASTPATH无计划，process_path NOT_RUN，不能启动128。不是新bug，不增加修复轮。独立样本审查代理01a1aabe-9ff3-7651-8fe3-f5016850f499确认Explore可直接SOLVED，因此数学多步不等于执行trace；建议14改用有限正八边形三色染色在D8与颜色置换下的轨道计数/分类。主线程采纳一次新过程覆盖批次：6561赋值、96联合群元素，合法性/固定点分类/汇总有依赖，预期较熟知vieta更易自然拆分，但尚未实测，仍可能FASTPATH或发生数学异议。无planner/工具提示、不改路由/预算/源码，不宣称能力提升。13原分母与结果保留，新14完整分母2独立登记不拼接；若再次FASTPATH，如实记未覆盖，不反复换题抽到PASS。详见忽略目录sample-review-readiness14.json。

readiness14在派发前因新题CRLF字节与内存LF哈希不一致而失败，0 Job/0模型/0账本；是自身登记失误，保守记第6轮，非产品校验bug。独立代理01a1aac2-a6c1-7000-92a4-2193b6a212ec比较后选择新15复用现有FileSampleHashResolver.hashes/read_text，不新增生成框架、不关闭校验。14 mismatch RED，新15逐样本实际字节哈希与read_text GREEN；旧14 manifest不改。live_attempt仍6，pre_dispatch_failures=1，15实际派发后才加真实尝试。策略比较保存在strategy-review-round6.json。

readiness15终态FAIL，完成1/2，前5步接受、第6步因challenge_meta_limit_reached停止，非TLS/硬预算。独立审查确认符合SP-05有界合同，不改cap。另确认Meta投影遗漏全局成果及ledger-only verifier成功回执；不能证明是单独失败根因。主线程进一步纠正“全部回执不可见”：step6成功回执已嵌报告，step1/2成功回执未嵌，只存在全局。选择局部Meta上下文补充，复用既有valid状态过滤、同scope真实成功摘要，当前目标/异议沿用steps，不新建统一投影框架。独立比较认为全角色简化范围/回归风险大于当前收益；strategy-review-round7.json记录限制。新消息接缝RED→GREEN，21项和fast/Ruff通过；子代理再补边界负例后才登记第7轮/冻结16，15原结果不升级，128仍NOT_RUN。

第7轮集成完成：22项Meta/skills/格式修复/证据边界聚焦测试GREEN，新增边界用例包含9种负例及合法current-step回执，Ruff/diff/快速门禁通过，官方baseline无差异。测试worker01a1ab2b-906a-7fc3-b1f5-ccd31aee74ad确认无测试阻断，提醒摘要与步骤报告可能重复、2804 bytes并非tokens、真实执行不证明数学正确性；这是readiness15单个终态重放，不是15个样本。旧15不升级，新16同两题原字节预检通过后冻结真实重跑。

readiness16于19:04:44终态FAIL，完成1/2，第1步挑战/Meta限额终止；26calls/2tools、2189243/16777216本地charged、3219.83/14400秒，无未知远端请求。模型计划48与原题96冲突、Meta识别96却CONTINUE是模型策略事实，不据此做数学语义硬编码。另证实CONTINUE策略没有交接给续答Reasoner：公共旧流程新增断言RED为None。独立代理01a1ab6a-f7d2-75e0-9828-b7c29748895f确认，主线程选择复用现有scope helper只读注入同scope未消费CONTINUE（7行），优于新增交接/消费框架。Verifier保持独立，计划/goal/cap不变，不把建议当证明。24项聚焦含cap不重置GREEN、fast/Ruff/diff PASS，官方baseline无差异；策略比较保存strategy-review-round8.json。第8轮修复后新17同样本/同预算新身份真实重跑，16不升级，不保证数学正确或交付。

readiness17终态FAIL，完成1/2，具体verification.reason为verifier_tool_request_unfulfilled（非Meta上限）：一次真实exit1/ImportError后Meta选择Run级pure reasoning，Verifier收到无工具策略和pure_reasoning_denied反馈后仍tool_request。独立复核01a1ab8b-0cc5-72c2-9340-a93eec99a5ca未发现新工程bug，确认提示/schema权限过滤与运行时一致；ImportError有230bytes真实stderr，不是应用导入环。修复轮仍8、不加补丁或盲重跑。已提出pure reasoning作用域业务选择，等待用户明确全Run禁止或仅Reasoner禁止、Verifier保留原受控计算。无活跃Run且诊断完成，移除临时监控；Issue127/128仍open、128两臂NOT_RUN，未来新合同后重新冻结和转移监控。

用户随后明确选择“纯推理仅限制Reasoner，Verifier保留原预算内计算”，解除待定范围。此次作为用户批准的设计合同调整单独计policy_change_rounds=1，不追溯把17判为旧工程bug；累计工程修复repair_round仍8，实施迭代implementation_round=9。独立代理01a1ab94-e473-7913-8383-5a1a1b598360建议局部调整既有执行/广告/只读三处gate，拒绝新增统一RolePolicy框架；未标执行角色默认Reasoner，Verifier只取内部source_role，不信任模型字段。合同SP06追加新作用域，旧单测按新合同调整，公共Job/Verifier/read scope先RED后GREEN。Registry/隔离/S3额度与deadline/回执保护/cap/审查绑定及best-effort关闭保持。新18同两题原字节与预算单独冻结；唯一监控待新Run启动后恢复。

新作用域实现保持meta.py不动，仅执行/广告/只读gate按运行时角色判断。未标source_role的普通报告预检默认Reasoner，模型自报role/source_role不能授权；Verifier路径复用既有内部receipt_extras。公共新作用域与0工具额度、旧Reasoner拒绝、Verifier计算/整题复核/取消、deadline等共30项聚焦检查通过（29项后新增1项冒充角色检查单独通过），fast/Ruff/diff通过。旧的全局纯推理Verifier拒绝单测按用户批准新合同更新；不新增工具或预算，不修改旧17。

用户追问非法JSON原因后发现新工程缺口：原repair没有失败原文/解析位置，sessions失败不追加历史，实际是在重问而非具体格式修复。选择第9轮局部上下文补充，独立比较不采用猜补parser/未验证provider JSON模式或新框架，详情provider-live-json-repair-20261105.md。两条真实出站接缝RED→GREEN、7项和fast/Ruff通过，18/19四条失败原文只读重放确认可进入修复；不声称在线已改善。新20同题/完整分母2/预算另行冻结，不扩一次repair上限。

用户条件授权调查并适度延长单调用：同题15-19无timeout，最长分别423/338/170/599/199秒，20首次901秒。末正文在截止前1秒，6884bytes/6406字符已输出，持久activity最大间隔3.27秒，非30秒idle；未完整报告。新21只把单调用900→1200，原14400Run/30秒无流/32768输出及账本限额不变，不算修复轮；manifest/config/server/policy静态一致性通过。当前内存freePhysical160~209MB且有历史MemoryError，先不叠加线上尝试，21 NOT_RUN；已清理核对身份的本任务完成服务。独立建议只试1200，不承诺完成，未读完原文；主线程另做结构与历史定量，详见provider-live-call-timeout-20261105.md。

21终态FAIL：前4步接受，第5步Verifier原/repair均invalid_json，13calls/1tool、695816/16777216、555sec/14400，非1200秒超时，独立task/coverage/process FAIL、transport PASS、usage UNKNOWN。确认原文定位helper未在Verifier owner接入；三个流式公共入口（step initial、planned whole、fast whole）均RED缺previous_response。独立代理01a1ac33-efca-72f1-af27-befcb0ed1bd5支持三处最小复用，拒绝新dispatch框架，不新增compute continuation重试/索引语义修复。第10轮补传failed_call，finalize保留base_call_id避免双后缀。8项聚焦GREEN、fast/Ruff/diff PASS、baseline无差异；不能据此保证模型修好。22同题/分母/1200秒/预算新身份冻结，不改21旧结果。

readiness-22 随后按用户重启要求取消，不计模型失败。收到明确开始后，readiness-23 的启动前隔离探针不可用，未注册 Run、未派发 provider 请求；环境恢复后以独立 manifest/Run 启动 readiness-24。24完成简单题，实际进入自然多步并有20次模型/HTTP调用、3次Python工具调用；工具回执均为 exit 0/清理确认，但没有捕获 stdout，不能作为报告数值的证据。Verifier 对步骤目标提出有效 CHALLENGE，模型未在既有挑战上限内修正目标并引用可用证据，最终以 challenge_meta_limit_reached / star_needs_review 停止。独立 task/coverage/process_path FAIL、transport PASS、usage UNKNOWN；不证明代码缺陷，不扩大挑战上限，不增加工程修复轮。完整身份、逐调用和独立报告见 [readiness-24 运行记录](provider-live-natural-20261106-readiness-24.md)。当前 live_attempt=15、工程修复轮=10、策略调整=1、出网前准备失败=5；#127仍open，#128两臂NOT_RUN。

readiness-24 后，聚焦 challenge 测试在 `test_invalid_meta_accept_does_not_accept_or_dispatch_more_work` 稳定 RED：完整 Meta JSON 中 schema 越权动作被当作可自动格式修复，额外重试后把已知协议拒绝变成 interrupted，违反 SP-05 第3条。按独立局部修复/重构比较选择从当前 schema enum 分类越权 Meta 动作、保留已知失败审计并不派发修复；其他 schema/JSON 格式修复与 unknown 不重发保持。RED→GREEN 与有限回归通过，提交 `13a3ccc`（`fix(showcase): 拒绝自动重试越权的 Meta 决策`）。

readiness-25 使用该源码及独立新 manifest/Run，简单题成功；自然多步在 STEP_VERIFY 首个 Verifier 请求处约10.147秒后 timeout，0响应头/事件/正文/completion。effective timeout约1200秒，但冻结的本地server.py把 requests timeout覆盖为(10,30)，即连接等待10秒、读取等待30秒；与30秒无流/1200秒调用策略不一致。具体底层异常子类型未保存，远端是否收到/处理请求未知，原Run保留 UNKNOWN，禁止恢复和重发。独立核验 transport PASS、task/coverage/process_path FAIL、usage UNKNOWN，报告 SHA `e4a637db44c3b4c78788610ccd40d9d5443f1d8211520372b500e2794eb3ccc3`。独立策略比较选择只在新批次由execution-policy的stream_idle_seconds提供connect/read timeout，保持逻辑deadline、budget、retry和review不变；小型传输/截止重构回归面更大且无新增收益证据。完整身份、阶段和逐调用计时见 [readiness-25 运行记录](provider-live-natural-20261106-readiness-25.md)。更新后计数：真实 provider-live 批次尝试16（#25计一次）；此前已实施自身修复10，Meta协议修复记第11轮；readiness-25明确证实新的本地连接deadline配置缺陷，待 readiness-26 完成新配置修复验证后记第12轮。用户策略调整1、出网前准备失败5；#127仍open，#128两臂NOT_RUN。

readiness-26 保留同源码SHA、同题完整分母及全部预算，以新server SHA/manifest/run identity应用连接限制修正。简单题成功；自然多步完成4步、22模型/HTTP和8工具后，step4 challenge3 的 counterexample researcher 流收到 HTTP 200 与821 bytes部分正文，但约96秒后报 `connectivity`，无 completion。Job以 `star_needs_review` / `interrupted`停止，1个远端请求UNKNOWN；不恢复、不重发。独立核验 transport PASS、task/coverage/process_path FAIL、usage UNKNOWN，报告 SHA `20befe9e6e4fc276dca0833ffba4ee432da9d48a739a35b72213509c68adb0ea`。请求期间另有多个完整超过30秒的连续provider流，readiness-25的10秒connect包装器不再施加；这验证本地配置修复在现场已生效，但不代表 provider 兼容全面通过。终态后只读TCP/TLS检查成功，不能解释先前中断或把UNKNOWN清除。用户调整timeout策略0次；工程自身修复累计12轮，其中第12轮为readiness-25发现并由readiness-26应用的底层timeout mismatch修正；真实live批次累计17，策略调整1，出网前准备失败5。Issue #127仍open，#128两臂NOT_RUN；独立报告、身份与逐调用记录见 [readiness-26 运行记录](provider-live-natural-20261106-readiness-26.md)。
readiness-27 使用全新 manifest/Run 和 readiness-26 同一源码 SHA、完整题目分母及冻结预算。简单题成功；自然多步仅完成第 1/7 步，在 STEP_VERIFY 因有效 CHALLENGE 停止，直接原因 verifier_tool_request_unfulfilled。4 次隔离工具执行 exit 1，stderr 分别显示 SyntaxError、IndexError 和两次 TypeError；清理均已验证，未知工具结果 0。错误来自模型生成代码，不是已证实应用缺陷；未增加修复轮或重试上限。19 model/HTTP、8 tools、1389990/16777216 本地 token 预留、1812.428/14400 秒；provider usage UNKNOWN，未决 HTTP 0。终态零模型派发核验 FAIL，transport PASS，task/coverage/process_path FAIL，usage UNKNOWN，报告 SHA 6a82f21bf6d6741dcd8d2ad35e96525bc4a56f8c0d261239c92c4d5e0e605543。#127 仍 open，#128 两臂 NOT_RUN；不为模型代码错误盲重跑。完整身份、19 次调用时序、预算、回执和交付缺口见 [readiness-27 运行记录](provider-live-natural-20261106-readiness-27.md)。
readiness-28 使用全新 manifest/Run、readiness-27 同一源码 SHA、完整题目分母和冻结预算。简单题成功；自然多步只完成第 1/7 步，在 STEP_VERIFY 因有效 CHALLENGE 停止，直接原因 verifier_tool_request_unfulfilled。6 次隔离工具均 exit 0、stderr 0、unknown_outcome=false、cleanup_verified=true，但有限计算集合不对应八边形 proper coloring 固定点集，且工具输出显示待验证公式不成立；这是模型验证请求与证据不适用，不是已证实应用缺陷。13 model/HTTP、6 tools、1000809/16777216 本地 token 预留、1032.508/14400 秒；provider usage UNKNOWN，未决 HTTP 0。终态零模型派发核验 FAIL，transport PASS，task/coverage/process_path FAIL，usage UNKNOWN，报告 SHA 1e03047831e29f8b59caefabd227c813d061dea3adeb92eb65ed98ba24e160d6。#127 仍 open，#128 两臂 NOT_RUN；不放宽挑战合同。完整身份、逐调用时序、工具回执和交付缺口见 [readiness-28 运行记录](provider-live-natural-20261106-readiness-28.md)。
