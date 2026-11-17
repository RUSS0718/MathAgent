# #189 目标依赖分流阶段验收

2026-11-17，Asia/Shanghai。状态：#190/#191/#192已关闭；S2/D成功、U failed、自然AC2 not_triggered。最终受验源码ada7c20444bde0a6351947c736b63fe4595e92e1已含UI与四组门禁修复；新完整Vue DOM受控fixture独立4/4、原失败8方法8/8及相关25/25通过，受影响双轴均0确认问题/0阻断。gate01仍failed，最终gate02 passed 6/6、source_changed=false，本轮工程退出条件已通过。剩余主控最终提交、推送、PR ready及关票复核；发布前#189/#193仍open、PR198 draft，不预记远端状态，不声明数学能力或效率提升。

## 源码与边界

集成分支 `dependency-routing-189`，起点为188交付 `1307aab40b8788cc408ef65fc94dfc7f2b1dc1f8`，PR198堆叠于 `user-solving-188`。不合入main，不改官方baseline、默认路径、依赖或根预算。

190交付975560a；191由fresh merger集成147f8ea，生产仅Intake指令7行；192集成5582e86，生产/测试最终快照b2b1a50。各份检查仍绑定其实际源码，不能把较早回归称为最终源码全组运行。纯文档更新另记交付SHA。

## C1–C7 证据归组

依据已提交[189设计](../engineering/dependency-routing-189-design.md)及[189 Issue](https://github.com/RUSS0718/MathAgent/issues/189)，按#189已发布要求在本记录归组为C1–C7；这些是本文证据分组，不声称其他合同原编号，不依赖用户未跟踪合同。后续历史阶段措辞按当时源码理解。

| 归组 | 公共证据与当前结果 | 限制 |
| --- | --- | --- |
| C1 | #190 公共 Job 依赖先规划、SOLVED 不短路，受控通过；见下表及190交接 | 不替代自然输入 |
| C2 | #191 live04 D 的 Intake→Plan/WorkUnit→Reasoner/Verifier→后继来源消费→最终答复已补证，S2 无依赖对照成功 | D 自然 CHALLENGE=0，异议及后继门控只沿受控覆盖 |
| C3 | S2 Explore cap2048→独立整题审查→直接交付，无 Planner；自然 AC1 通过 | 2048 是工程假设 |
| C4 | #192 受控公共 Job 覆盖首次已知未完成/截断转规划及 unknown 零自动派发 | U 自然 AC2 not_triggered，不改判为通过 |
| C5 | 受控一次修正与后续规划覆盖；U 观察到审查后修正及转 PLAN | U 最终 failed，无完整数学答案 |
| C6 | 190/192及reviewfix身份/预算边界受控覆盖；原gate01失败中的公共进程恢复已修复，原8方法8/8含restart的3subtests，相关25/25；UI副本身份审计见193验收 | 公共恢复与最终gate02通过；副本auth/init允许写，不称整库零写 |
| C7 | live04逐角色测量/人审及原a0真实普通UI；新f94a492完整Vue DOM/刷新受控fixture独立4/4，具体来源与资产见193验收 | 真实post-fix服务重启NOT_RUN，限制留仍开放#168；gate02通过不证明自然重启或效率提升 |

整体独立双轴固定范围 1307aab40b8788cc408ef65fc94dfc7f2b1dc1f8…a0a4cd2abe7524eab51cdd2d7a4b87986045d42c，规范轴与规格轴均0问题/0阻断；原件在 artifacts/issue189/final-review/{standards,spec}.md。审查不等于浏览器或最终门禁通过；终态修复另有受影响双轴，见 [#193 验收](routing-ui-193-20261117.md)。

自然源码aac4cf6498cefb9b8761976f479b90e52303537f、原真实after源码a0a4cd2与新Vue DOM来源f94a492分别登记。较早集成ea81b6b7198a2f69a0c5995ce5c587cd1134adf1/tree17aec4353149bbb4fa8d923afa32e06fc5943101已含四组修复，来源4e272e3370eb0d5ae1d5fb7c54c3f0200635210e且tree一致。最终gate02冻结源码为ada7c20444bde0a6351947c736b63fe4595e92e1/tree445fce256c5446f25915914924c7445552a994b2，受验期间source_changed=false。最终纯文档交付SHA在提交后由HEAD、PR及关票评论记录，与受验源码SHA分记。

### 原gate01失败及受影响修复

gate dependency-routing-189-01冻结a0a4cd2，终态failed，完成1/6、offline exit1、source_changed=false、elapsed2164.297秒；2311 tests、5failure、5error、42skip。原证据artifacts/final-gates/dependency-routing-189-01/status.json、repository-check/tests.json、repository-check/diagnostics.log保留。8个方法10条failure/error分四组，不因后续聚焦通过改判原门禁。

完整原因、红绿、精确命令及计数以[四组修复验收](dependency-routing-189-gate-fixes-20261117.md)和C:/Users/CQX/.codex/tmp/189-gate-fixes-handoff-20261117.md为准。当前集成已含4e272e3修复：原8方法8/8（restart含3subtests），最新合并相关25/25，0failure/error/skip；重复和重叠运行不累加为唯一覆盖。15份证据已复制并核对hash至root artifacts/gate-fixes-189/，包括green-eight.json与postmerge.json；公共进程恢复必须通过的要求保留。

两位fresh reviewer对a59450a2c650f760f73e0f4017e2af7afb6cea43…4e272e3370eb0d5ae1d5fb7c54c3f0200635210e受影响差异各自复查，规范/规格均0确认问题、0阻断；报告已复制并核对hash至artifacts/gate-fixes-189/independent-review/{standards,spec}.md。静态复查与最终门禁分别记录：原gate01失败保持，gate02已在冻结源码完成6/6；结果见下节，不将聚焦回归与全仓检查重复累加。

### 最终门禁与工程退出

#193额外真实重启门槛已按[193合同](../engineering/routing-ui-193-contract.md)及接续合同第3条撤销：旧要求为最终修复后同自然S2/D/U真实服务重启再浏览器验收，障碍为用户充分批准后安全Start仍三次被工具拒绝，原四AC不要求新增该轮重启且产品不改启动/恢复机制。替代组合为原a0真实after+只读audit、新源码完整Vue DOM/刷新、公共进程恢复测试与最终门禁，四组现均有适用范围内的通过证据，本轮工程退出条件已满足。身份/权限/预算/unknown不削弱，公共恢复不能删。未覆盖的真实post-fix服务重启仍NOT_RUN / blocked_by_tool_approval，限制留仍开放的#168；#183已closed，不转派其补验。详细UI来源与旧失败见[#193验收](routing-ui-193-20261117.md)。

最终run `dependency-routing-189-02`：`final_status=passed`、`completed=6/6`、`current_stage=completed`、`source_changed=false`，elapsed 2501.094秒。开始时间为2026-11-17T01:52:00.717451Z，结束后源码manifest的`captured_at`为2026-11-17T02:33:41.766081Z；后者是身份快照时间。证据目录为`artifacts/final-gates/dependency-routing-189-02/`，总体状态见`status.json`，冻结前后身份见`source-manifest.json`。status未单列`exit_code`字段；下表六份阶段日志均记录`EXIT_CODE 0`。

| 阶段 | 最终结果 | 证据（相对run目录） |
| --- | --- | --- |
| fast | 通过，EXIT_CODE 0 | fast.log |
| offline | testsRun=2311，failure=0、error=0、skip=42、expectedFailures=0、unexpectedSuccesses=0；2309.9602450999955秒 | offline.log、repository-check/tests.json |
| release | 27/27，42.139秒，EXIT_CODE 0 | release.log |
| frontend-install | npm ci成功，EXIT_CODE 0 | frontend-install.log |
| frontend-check | check:deps、typecheck、test:unit及build成功；单测87/87、suites=0、fail/cancelled/skipped/todo均0，duration_ms=22220.6869；EXIT_CODE 0 | frontend-check.log |
| frontend-audit | 0漏洞，EXIT_CODE 0 | frontend-audit.log |

2311为报告的testsRun，不另推算unique，也不与聚焦检查累加；42项skip仍为未执行，不计通过覆盖。阶段通过不新增自然数学或真实重启结论。

实际启动命令（仓库根）：

```powershell
uv run --no-sync python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id dependency-routing-189-02
```

offline阶段实际执行`uv run python scripts/check.py --offline --report-dir D:/project/工程化MathAgent/Challenge-Cup-2026/artifacts/final-gates/dependency-routing-189-02/repository-check`。

运行及监控已结束：临时task `MathAgent-189-dependency-routing-189-02`于北京时间2026-11-17 10:52写入`scheduled-terminal.json`后自动删除，主控10:55复核不存在；PID40112及测试子进程41976/43680/34888/11632/44264/43308/44248均已退出。清理证据入口为同run目录`controller-cleanup.json`，无检查所有权需要转移，不再启动测试。

最终文档交付提交尚未产生，交付SHA由提交后的HEAD、PR及最终关票评论记录。主控剩余事务为审阅文档、提交推送、将PR198从draft设为ready、关闭并重读复核#189/#193；发布前两票仍open、PR198仍draft，base为user-solving-188，不合main。用户最新范围为#189完成推送关票后停止，不领取#156或其他票、不创建新session；等待、不催促。

## 历史：合同到公共证据

| 要求 | 公共入口与断言 | 证据 | 当前结果 |
| --- | --- | --- | --- |
| 依赖目标先规划，SOLVED不能短路 | Job/Run/当前Spec；Planner、依赖WorkUnits、Reasoner/Verifier实际派发；未验证材料不进已证账本 | 190最终45项、集成快速5项；[190记录](../engineering/dependency-routing-190-handoff.md) | 受控pass，190已关闭 |
| 自然Intake依赖及Verifier实际作用 | 自然message→Spec→Plan→步骤反馈→最终答复，不能注入Spec/Plan | 191公共12项、角色14项、Intake9项，共35个不同方法、零skip；受控CHALLENGE后重做和后继门控 | 受控pass；自然S2/D通过，建议主控审核191退出 |
| 无依赖简单题有界直解 | 首次2048后独立整题审查，实际payload/Attempt/预算相符，其他角色基础cap不变 | 192最终21项；[192记录](../engineering/initial-explore-192-handoff.md) | 受控pass；S2自然AC1通过，保守context floor按合同澄清 |
| 未完成/已知截断转规划，unknown不自动派发 | Job及HTTP计数、公开原因、未验证来源；工具/有限修复同语义轮次 | 192最终21项及归档红绿；reviewfix工具续接完整payload/指纹和公开跨进程恢复 | 受控pass；U自然AC2 not_triggered |
| 具体数学异议一次修正及后续规划 | 同Run审查反馈、原容量与来源，二次拒绝/无具体异议沿既有规划 | 190/191公共组与192修正用例 | 受控pass；U观察到一次修正后转PLAN，最终失败 |
| 原预算/截止/旧Run及默认路径 | 新策略仅新Run冻结；旧无策略/190-only/新容量恢复，GET零新增调用 | 190恢复组、192配置/transport/ledger；reviewfix跨进程三场景、集成fast5/5 | 受控pass |
| 普通用户真实路径与权限 | 普通投影/SSE/角色生命周期/唯一answer；ID、用量、hash不进普通DOM | fresh Peirce已在独立worktree正式实施 | 未完成，193开放 |
| 数学、测量、阶段退出 | 登记题逐角色duration/HTTP计数、来源/反馈/答案与独立人审；双轴及冻结最终门禁 | 下述自然登记与后续记录 | S2/D成功、U失败；阶段双轴/最终gate未完成，189开放 |

192回归A为27项、B为47项且1项skip，均在7a87eb2；最终资源切片8项含7个重复方法。最终21项加A/B共95个不同选择器，不将重复检查累加。未验证本地Docker Reference镜像的skip保持未执行；配置准入通过不替代它。191/192 ignored证据分别20/68文件已复制root并核对哈希一致。

## 历史：分段独立审查与准入

固定比较1307aab…5582e86的规范轴0硬规范/0smell/0阻断；规格轴提出工具续接完整payload/serialized/fingerprint和公开跨进程恢复两项证据限制。唯一fresh实现者补证时复现并修复显式非流指纹漏tools、工具续接协议失败恢复后额外repair两处缺陷，51个不同测试通过、零失败/错误/跳过；生产与测试源码1037ec9，集成0b92236。详见[补证记录](dependency-routing-review-20261117.md)，40份ignored证据已复制root并逐文件校验一致。

两位fresh审阅者对5582e86…0b92236的受影响差异独立复查，规范轴0硬规范/0smell/0阻断，规格轴0已确认缺陷/0阻断，两项受控证据限制解除。原报告及复查报告均保留在仓库外 `C:/Users/CQX/.codex/tmp/189-backend-{review,rereview}-{standards,spec}-20261117.md`；后者已复制到ignored `artifacts/issue189/reviewfix/independent-review/`。自然及193不在此次结论范围。

0b92236上主控复核快速检查5/5、3.097秒、fast_check=PASS，日志及执行源码见 `artifacts/issue189/backend-preflight-reviewfix.json`。先前快速检查的工具返回在交接中未保留结果，因此本次仅重新执行快速入口，不重复51项或最终全仓门禁。

集成快速检查5/5、3.344秒、`fast_check=PASS`；可信JSON新策略经实际loader准入通过，摘要 `artifacts/issue189/backend-preflight.json`。独立临时库、worker关闭且禁止socket出站的运行时检查为ready=true，star_reference enabled、missing_capabilities为空，见 `artifacts/issue189/runtime-preflight-01.json`。没有创建题目或发送provider请求，不称线上能力验收。

## 历史：2026-11-17 live04 退出映射（关票及服务状态以当前交接为准）

自然运行适用源码 `aac4cf6498cefb9b8761976f479b90e52303537f`，分支 `dependency-routing-189`。依据仓库外独立报告 `C:/Users/CQX/.codex/tmp/189-live04-{S2,D,U}-assessment-20261117.md`；D 报告后半部补证解除第一轮公共包的 spec/WorkUnit/来源消费缺口。脱敏补证及 manifest 入口为 root `artifacts/issue189/live04/independent-D/`，15 文件已由主控校验复制；manifest SHA256 `c77800d41698009f592c6b718d4cab93cd1ec9f39e9603e69fbe9ff7529b3582`。本次只消费报告与 manifest，不访问库、raw、参考解，也不重新声称完成全仓冻结字节审计。

| 验收范围 | 实际结果与退出边界 |
| --- | --- |
| #191 自然依赖与无依赖对照 | S2、D 均 succeeded，人工数学正确，独立整题模型 ACCEPT、EXACT same_artifact。D 具备 Intake→Plan/WorkUnit→逐轮 ACCEPT→后继来源消费→最终汇总因果链；S2 无依赖字段已由补证核实。自然部分可记通过，建议主控据此完成 #191 关票审核；本次不关闭 GitHub。 |
| #191 CHALLENGE | D 五轮裁决全为 ACCEPT/PASS/YES，CHALLENGE=0；两次 YIELD 不是异议。I191-3 仅沿既有受控公共 CHALLENGE 与后继门控证据退出，不称自然异议实证。 |
| #192 AC1 | S2 首次 Explore 实际 cap2048/nonstream，独立整题审查成功，无 Planner，支持自然 AC1；2048 仍是工程假设，不是优化分位数或速度结论。 |
| #192 AC2 | 工程覆盖来自既有受控公共 Job；自然 U 为 **not_triggered**，不能写自然 AC2 PASS。首轮语义 Explore（含工具续接）返回 SOLVED，整题拒绝后仅一次修正未交付完整候选，才因 complete_candidate_unavailable 转 PLAN。这是审查后交接，不能倒算首次未完成交接。 |
| #192 合同第4条 | 原reservation为根调用预算预留；profile为transport能力/请求fingerprint。有效cap2048贯通预算/HTTP/Attempt/serialized/fingerprint沿受控证据；ContextPack允许冻结保守floor32768，不是实际输出或RunBudget预留。此为条款澄清，非删约束/缩验收；只读核对未发现实质缺陷。 |
| #193 / #189 | S2/D accepted/same_artifact 与用户接口“部分结果/未验证”矛盾，fresh Peirce已在独立worktree正式实施后端呈现与UI修复，实际依赖证据已具备；不可仅隐藏前端 notice 或伪造 ledger。UI/刷新/恢复、阶段独立双轴和最终 gate 尚未完成，#189 不退出。 |

原 Issue AC2 未要求必须自然，本地首次完成记 not_triggered 的规则保留。条款澄清后建议主控按既有受控公共 Job 工程证据完成 #192 退出审核；不将自然缺口改成通过，不改判 U 失败。GitHub 关票待主控提交。

服务8119，PID1128，创建 `2026-11-16T23:34:46.6007738Z`，按主控交接保留为只读 UI；临时 task 已删除，所有模型 Job 已终态。主控已核查 observer39852退出，仅1128存活；本文复用其核查，不冒称自行查询或清理进程。192 工作树被拒绝清理的 ignored `.venv` 保留。继续当前选择的同一模型，不覆盖型号；具体型号及跨 session 继承无法独立确认。

### 第4条源码与既有受控证据核对

只读核对自然源码 aac4cf6：`showcase/solver_harness/context_pack.py:354–358` 明确 actual_output_reserve=max(frozen policy.output_reserve_tokens,payload.max_tokens)，这是 context envelope 保守floor，不是根调用预算 reservation；比有效输出cap大不表示实际输出变大或预算越界。`showcase/stream_preference.py:135–144` 的显式非流使用实际payload/effective_max_tokens及documented证据；`showcase/adapters.py:180,314,332` 分别将实际cap传入非流调用、流式payload和Attempt；`showcase/solver_harness/adaptive_resources.py:47` 使用request cap估计当前工作，保留基础收尾容量。

`tests/test_initial_explore_transport_192.py:25–61` 的7000根额度检查实际2048 reservation（reserved减local_input_estimate）、HTTP/Attempt/serialized相符与非流fingerprint/documented；流式使用独立受控2048 profile，旧profile零派发拒绝。`tests/test_initial_explore_192.py:43–51` 的220000公共Job检查初始2048准入与基础review32768共存。复用既有192验收记录，不重新运行测试，也不将只读断言核查当作新的通过记录。

前轮把context reserve差异保留为潜在合同阻断；本轮根据上述指针明确职责后解除该疑点，未发现该差异构成实质实现缺陷。有效请求cap的预算/HTTP/Attempt/serialized/fingerprint要求完整保留，ContextPack可沿原冻结保守floor，无须改为2048或修改旧策略。uncalibrated/input_cap_tokens=null不作硬容量保证；自然S2只支持有限实际cap/transport观察，完整逐键及恢复边界仍沿受控证据，不宣称建立新provider-live profile。

## 历史：自然验收登记与时序

以下 live01–live04 准备/修复按当时源码与时间理解；NOT_RUN、尚未冻结及下一步安排均为历史，不覆盖上节自然终态。

S/D预登记于 `artifacts/issue189/preregistration/natural-cases-v1.json`，U另登记 `natural-U-v1.json`，均 `registered_not_run`。运行器只有message可进入公开Job；参考解、观察预期及判断条件不进入任何角色或验证器。D未形成实际依赖，或U自然形成依赖/首次直接完成，按相应路径记not_triggered，不注入Spec/Plan或诱导重跑。

先完成191/192补证和审阅，再冻结同一源码/配置唯一执行S/D/U，每题一次。unknown及提交身份不明不自动重发；失败与原记录保留。193随后使用持久结果做普通UI及只读刷新验收，分别记录自然运行和UI的适用源码SHA，不为界面重复调用模型。

启动前，`artifacts/issue189/live01/` 运行器完成两轮离线公共Flask/Job受控smoke：第二轮0真实provider、3受控Attempt、分页30页、读取新增0次，公共Run保持产品原响应；第一轮保留。配置审计为独立启动快照，不混入Run原生字段。使用端口8119和独立data，用户8103不动。长期运行遵循[工程门禁](../engineering/development-gates.md)和现有30分钟检查合同，不用子代理轮询；实际首次启动结果见下节。

### live01 提交前拒绝

冻结9ca4212，于北京时间2026-11-17 06:39启动唯一后台实例与30分钟临时检查。
首题S的公开POST返回400，运行器停止后续题、未自动重发。原运行器使用
`issue189-live01-S` 作为幂等键，而公开入口要求UUIDv4；原离线smoke自行构造UUID，
未复用实际提交代码，因此未覆盖此错误。原响应体未保留，错误码不能事后冒称已捕获。

主控只读打开独立SQLite，workspace_jobs、runs、run_budgets、solver_states、solver_events
全部为0；没有Job/Run或provider调用，自然数学验收仍not_run。核对记录
`artifacts/issue189/live01/reconciliation.json`，S-terminal仅记录rejected_before_job_creation，
不是产品Job成功或数学终态。原guards、失败status与日志完整保留，原请求不重发。
主控按PID及创建时间释放服务，8119无监听，临时检查已删除。fresh子智能体仅修复
新ignored live02运行器，要求稳定离线红绿、实际提交代码复用和HTTP错误脱敏留存，
无修改产品源码或扩容。新运行须另行冻结与唯一启动，不能覆盖live01证据。

live02窄修复已完成：实际observe和离线smoke复用同一提交代码，UUIDv4红400转绿202；
真实faithful配置且worker关闭时，省略solver_mode的Job实际为star_reference，非legacy。
HTTP错误只留状态码和符号error code，400/timeout/重复预约均不自动重发。证据为
`artifacts/issue189/live02/{red,green,green-final,static-check,syntax-powershell}.json`；
0真实provider，服务配置与admission和live01逐字节相同，未修改产品。仓库外交接
`C:/Users/CQX/.codex/tmp/189-live02-runner-fix-20261117.md`。准备态not_run0/3，
无freeze/guards/后台运行；主控接回冻结和唯一启动所有权。此离线准入不算自然题验收。

### live02 原生启动失败

冻结df546df，于北京时间2026-11-17 06:46启动。新运行器把中文绝对UV环境路径
写进UTF8无BOM的PowerShell脚本，原生powershell.exe按ANSI解释后误建虚拟环境，
service-entry在导入dotenv时失败。此前AST/parser和进程内Flask检查未覆盖这一原生启动接缝。
观察器未启动，无submission guard、sqlite或Job/provider调用，自然题仍not_run。
原失败日志和冻结保留在 `artifacts/issue189/live02/`；主控核对后停止仍等待health的
精确owner，临时检查已删除，误建虚拟环境已按绝对目标核对清理，未触碰192保留环境。
`cleanup-verification.json`确认原进程退出、8119无监听、无临时检查。

原修复者接续只修新live03：PowerShell以运行时解析仓库路径生成UV环境，避免中文
字面量；补真实powershell.exe后台启动/health和失败落盘检查，不改依赖、产品或预算。
live01/live02原记录不覆盖，未因本次启动失败重发任何模型请求。

live03窄修已完成并由主控审阅：四份正式PS脚本通过PSScriptRoot运行时解析仓库/.venv，
全部ASCII；准备态补齐pid/created_at/log/job字段。原生PS5.1实际环境与Python前缀相等、
dotenv导入成功；后台逐字节复制的service-entry在隔离worker-off夹具中真实boot/health=ok，
零Job/provider/出站连接。失败路径实际落盘并由worker finally自动移除临时任务；
测试所属PID/创建时间清理，remaining_process_count=0。提交代码未变，不重复live02准入检查。

红绿与原失败记录位于 `artifacts/issue189/live03/`：environment-red/green.json、
native-smoke-result.json、static-check.json、syntax-powershell.json；仓库外交接为
`C:/Users/CQX/.codex/tmp/189-live03-runner-fix-20261117.md`。测试身份接缝不等于正式
自然冻结，真实容量/题目不变；live03准备not_run0/3、无正式freeze/guards/data/进程/任务，
主控负责后续唯一冻结和启动。以上检查不代表自然求解或数学效果。

### live03 首题自然失败

冻结源码316eaba8c681bb928f2d49ea14581db9f7617363，
北京时间2026-11-17 07:01启动；公开Job `run_bd94bd70b28a651ec30ebc2f66d97c52`。
S在194.885秒后failed，solver为partial_aborted/result_reason=route_requires_reevaluation，
无最终答案。无Explore，实际Intake、Planner、Reasoner和StepVerifier参与；不能作为
简单题有界直解通过，也不能仅凭多角色出现判为191自然成功。实际依赖与失败因果待离线诊断。

8次HTTP全部已返回，角色次数/物理耗时和分别为Intake 1/5.702s、Planner 1/5.423s、
Reasoner 3/94.898s、StepVerifier 3/82.594s；3次工具、未决请求0，recovery unknown_calls为空。
Reasoner存在invalid_role_schema、1次repair记录。预算未耗尽，原48模型/48HTTP/8工具、
2097152 token/3600秒不变；484483为本地UTF8估算计账，不是真实provider token用量。
provider usage缺失8项不能误写成8次未决调用。

证据 `artifacts/issue189/live03/S-{job,run,report,evidence,events,measurements,answer,terminal,identity}.json`。
S失败后停止，D/U未提交；原失败/guards/冻结不覆盖、不自动重发。主控按原PID/创建时间
释放服务，cleanup-verification.json确认原进程退出、8119无监听、临时任务已删除。
fresh只读诊断者负责仓库外最小离线回放与明确修复建议，零新增provider；尚未作代码修复或新自然运行。

离线诊断已确认：实际Intake保存explain_reason→solve_equation，违反已有“解释不制造依赖”
指令，路由忠实消费该边；本次不能据此评价2048首次探索容量。工具两次冲突是错误多项式
参数，非原方程的数学反例。Reasoner空next_action被schema正确拒绝，repair虽恢复内容，
checkpoint仍绑定原protocol_failed调用，导致review_record_mismatch，严格图来源无法刷新，
最终触发route_requires_reevaluation。真实绑定接缝离线回放两次稳定红；仅内存改为实际
completed repair身份即通过。此为定位证据，不是公共Job全链或自然修复成功。

报告与回放：`C:/Users/CQX/.codex/tmp/189-live03-S-diagnosis-20261117.md`及同名目录。
fresh实现者仅修成功repair的checkpoint来源传播并补公共Job红绿；不放宽schema/图守卫，
不改旧Run、失败判定或预算，不添加自然提示示例/硬编码绕路。模型遵循偏差仍保留。

下一自然登记为 `artifacts/issue189/preregistration/natural-cases-v2.json`：S2“求实数 x，使
3x + 2 = 11。”，题面SHA256 `9267e0e67d77935deda7153d99372506c1f499c53512ef83f21814a58c63c51d`。
仅去掉独立解释请求，以观察单数学目标的直解资格；未减少完整答案独立审查要求。
原S失败不改判，S2实际仍有依赖时不算直解通过；D题面/hash不变，U仍原独立登记，
均未提交。新live04仅准备，等待来源修复公共回归及受影响复查后才由主控冻结唯一运行，
每题一次，原unknown/失败不自动重发，不注入Spec/Plan或参考。

live04准备完成，主控已审阅：仅REG/顺序/停止列表换为S2/D/U及运行名替换，配置和
提交代码与live03字节一致；实际PS5门控证实S2 guard存在而terminal缺失时，在读取任何
进程元数据之前拒绝停止。证据 `artifacts/issue189/live04/{static-check,syntax-powershell,
stop-gate-result}.json`，外部交接 `C:/Users/CQX/.codex/tmp/189-live04-runner-handoff-20261117.md`。
0Job/provider/服务/定时任务，准备not_run0/3、无freeze/guards/data/运行进程。

### checkpoint 来源修复集成

来源9cf830d555de4263469322fae34d2b9a5abd7f90已由fresh merger集成至
08eeecded8fbebd73bf91e228017072215c9c87e，tree一致。challenge.py及step.py各一处
复用已有completed_call_id解析实际repair谱系，不改失败调用、schema/图守卫、旧Run或预算。
公共红绿、真实registry回执及各源码适用范围见[修复记录](checkpoint-repair-source-189-20261117.md)。
累计去重10项通过、零失败/错误/skip；最终补充4项包含3个重复，不能将较早9项冒称最终文件重跑。
24份ignored证据已复制root `artifacts/checkpoint-189/` 并逐文件哈希一致；原失败保留。

生产两轮上限下旧挑战链路仍以reasoner_checkpoint_round_limit终止；测试内三轮续算仅为
来源机制见证，未修改生产上限，不能声称旧S自然成功。新增普通Reasoner回归在生产两轮内
实际继续并交付，真实registry执行一次，检查回执身份/残差/预算及GET零新增请求。
08eeecd上主控fast5/5、3.307秒通过，原输出见integration-fast.json；受影响两轴独立复查
均确认0问题、0阻断，真实registry与生产两轮/测试三轮分层足以支持该来源修复，不代表旧S成功。
固定范围c4493ba…08eeecd，报告位于root `artifacts/checkpoint-189/independent-review/`，
外部原件为 `C:/Users/CQX/.codex/tmp/189-checkpoint-review-{standards,spec}-20261117.md`。
证据复制、clean及来源已合并核对后，所属工作树已安全移除。live04仍未冻结或启动。

## 工程验收结论与最后交付

UI两次修复、公共恢复、独立双轴及冻结源码最终gate02共同满足本轮工程退出条件；剩余仅主控最终提交、推送、PR ready及关票复核，发布前#189/#193仍open、PR198 draft、base user-solving-188，不合main。真实post-fix服务重启仍NOT_RUN / blocked_by_tool_approval，限制留仍开放#168，#183已closed。旧S/live01/live02/live03失败、U failed、自然AC2 not_triggered及gate01失败不改判；188门禁不代替本阶段，不声明数学能力或效率提升。最终交付SHA在提交后记录，不与冻结受验源码SHA混用。#189完成推送关票后停止，不接#156或其他票、不创建新session；当前所有权及停止范围见[交接](../engineering/unattended-ticket-handoff.md)。
