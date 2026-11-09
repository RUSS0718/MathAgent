# #156 Population/APRS 接管与验收

日期：2026-11-09（Asia/Shanghai）。状态：离线工程门禁通过（engineering-preview）；真实容量与数学效果未验证，不声明能力提升。

## 身份

唯一集成树 `C:/Users/CQX/.codex/worktrees/faithful-integration/Challenge-Cup-2026`，分支 `mathagent-faithful`。接管 HEAD 为 `0aec0ff2bd422237782c4ae82af62fe770f4387f`，保留其后全部未提交实现，未 reset/clean。原 session `01a1bbc7-b9a3-7003-8f13-127ba65275ce` 为 idle；开工未发现相关测试或临时检查。

已核对 #156、#155 最终决议、#146 与本地 accepted implement-spec。前置证据见[上一阶段记录](faithful-s06-s08-exit-20261108.md)，不将旧门禁用于新源码。继续当前所选模型，未指定子代理模型；实际型号与继承无法核实。

## 失败与修复

原公开恢复用例在接管源码返回 `star_needs_review`。授权与新动作准入已成功，但重试复用了旧 `step_dispatched` 事件 ID。修复按 action 去重并生成持久事件 ID；完整 calls 快照携带旧调用时保留旧归属，禁止改写历史。

后续失败验收定位并修复：路线快照缺少调用来源身份、completed receipt 接管后被丢弃、旧 owner 的最终请求缺少预算 fencing、冻结后仍可启动预留调用、真实 session 历史未进入 WorkUnit/最终候选预算预估、再次冻结事件 ID 重复、共享收尾失败未立即暂停、HTTP 用量已提交但结算 callback 丢失。

timeout/error 曾被 Population 当作已结清，父账本却保留未知预留。修复保留 pending 与占用。公开恢复测试加强为：答案成功交付，同时旧请求仍待结算且预留大于零；未放宽数学完成条件。

`drive_population` 不再复制推进循环，直接委托既有 `controller.advance_product`。路线复用 `run_plan` 的单 WorkUnit、step/verifier/challenge；最终生成、整题审查与 exact-text 继续走既有 finalization。

## 八组公共验收映射

| 组 | 当前证据 | 限制 |
| --- | --- | --- |
| 1 并发/公平 | schedule 固定轮次/新成员；loopback 双路线重叠；快路线第二 WorkUnit 在慢 HTTP 返回前派发 | 不代表 provider 吞吐/SLA |
| 2 准入/占用 | store 原子准入、单路线在途、unknown 预留、冻结后发送栅栏 | 受控 429 暂停新探索已验证；真实机器压力与容量未实测 |
| 3 共享/版本/replay | evidence/adoption 依赖测试；公共出站上下文采用另一条路线已接受证据，action 持久化依赖；APRS 重算拒绝篡改 | 不以全局图版本代替实际依赖；不声明数学收益 |
| 4 owner/恢复 | `test_independent_process_takeover_fences_previous_dispatch_owner` 跨进程接管后拒绝旧 owner；`test_public_resume_after_worker_process_exit_reuses_persisted_receipt` 在回执已存、未合并且另一路线HTTP inflight时终止旧worker，由新服务实例启动恢复并经公开Job `/resume` 复用结果 | 跨进程旧owner fencing 为独立 store 验收；公共服务重启验收终止了旧进程，未测试两个仍存活进程并发争抢；loopback 不等同真实provider故障矩阵 |
| 5 unknown | 普通 resume 零重发；显式新 ID lineage；timeout 保留旧预留；公共 GET/report 修复丢失结算 callback | 本地 timeout 不代表远端停止 |
| 6 冻结/终止 | 公共首次 REJECT 后恢复合法路线并再次整题审查；cancel/deadline 迟到不改根义务或交付 | 无形式内核验收 |
| 7 交付/结算 | 公共答案先交付、迟到后结算；报告/Evidence 分开投影；桌面/手机 Chromium 刷新重连零 POST、隐私检查 | 浏览器受控 API fixture；后端公共测试独立覆盖真实 HTTP |
| 8 policy/兼容 | 独立 preset、五项预算身份；同 key 返回同 Job；旧路径回归与 baseline 快速检查 | 最终覆盖以门禁05及其42项Docker专项补跑分层记录 |

## 聚焦证据

产物位于忽略目录 `artifacts/faithful-population-takeover/`。原始 `resume-red.log` 及各失败日志保留，文件名不代替退出码。

- 最初五模块 18 项通过；相关恢复/最终绑定 55 项通过，101.346 秒。之后源码已变，不是最终证据。
- 整合 44 项通过，47.524 秒，`focused-integrated01.log`；之后新增验收，仍不是冻结回归。
- 公共专项：`no-barrier03.log`、`completed-restart-green01.log`、`final-reject03.log`、`reconcile-public02.log`、`shared-public01.log`、`idempotency-export02.log`。
- `fast01.log` 快速检查通过，覆盖 baseline、Demo HTTP/JSON 与 CLI，不替代完整检查。
- Chromium 2 项通过：`artifacts/population-report-chromium-20261109-r4/`。无后缀及 r2 目录保留早期 fixture 失败；已查看手机截图。

## 2026-11-09 接续更新

中断前 `focused-integrated04.log` 共53项通过（60.120秒），接续确认进程已结束。加入交付守卫后 `delivery-integrated01.log` 共14项通过（55.775秒）；旧恢复/整题绑定 `legacy-regression02.log` 共37项通过（91.307秒），临时检查已删除。

`delivery-public-ledger02.log` 的公共故障与正常交付场景通过，首轮同组单测失败是夹具缺 logical 调用记录，修正后两个守卫单测通过。该故障模拟资源动作记录丢失；较早删除整份账本引发 run_control TypeError 的日志保留，不将其称作产品已修复。

`new-route01.log` 通过公共 Job 中受控注入可信控制器注册动作，验证已有轮次成员不被改写；运行中路线生成仍没有新的 Planner 生产者，本轮未添加自主循环或新 HTTP 干预入口。

整合02/03的失败保留。最终候选与结算的 revision 竞态修复仅重试本地 CAS，不重发 provider；曾尝试跨观察器持全局锁导致死锁，已撤除该方案，`deadlock-probe.log` 保留栈。调用与 session 簿记重读再提交，最终候选还核对冻结、owner、数学快照及候选历史不变。

## 冻结前检查补充

- `short-integrated05.log`：43项短聚焦通过。
- `runtime-stack07.log`：15项真实loopback公共运行时通过，65.651秒；90秒超时栈未触发。较早runtime06无输出等待被终止，根因未核实，不冒称已修复。
- `http-ledger-red.log` 复现删去已完成审查HTTP仍错误交付；`http-ledger-green02.log` 四项通过，之后补缺attempt ID拒绝，守卫单测3项通过。HTTP按solver/logical关系核对，并逐条核对workspace attempt事件。
- transport policy与profile集指纹已进入population配置和幂等身份，`identity-delivery05.log` 11项通过。该补丁测试先落盘但未单独运行补丁前红阶段，如实保留流程缺口。
- Standards审查未确认可行动阻塞，但完整锁顺序检查范围有限；Spec提出HTTP账本完整性，已按上述故障用例修复。动态Planner、机器压力和容量仍不在已验证范围。

## 门禁01中断与公共回放补缺

源码提交 `36844cb32f68987450a56b213594123b2c45d168`，门禁01快速阶段通过后进入offline。冻结后只读复核发现并发评分没有公共replay接线或历史，协调者停止唯一门禁树，临时检查已删除。原status停在running仅是强制停止时快照，实际结果以 `artifacts/final-gates/faithful-population-01/interruption.json` 为中断，不计最终通过。

store同事务保存rating_history，公共candidate-replay对并发Run重算全部历史，只返回policy/count/matches，不输出私有路线输入。`replay-public-red.log` 先复现缺字段；`replay-tamper-green.log` 5项通过，含持久历史篡改后replay不匹配、零模型新调用。

门禁02源码 `d77267bddccf546910738b572a37f3849443ed58`：定向Spec复查发现连续相同评分跨轮被去重，协调者中断门禁，`interruption.json` 记录source_changed=true，不计通过。已用失败测试复现历史只有轮1，改为按(round,rating)保留后store/schedule共16项通过（`replay-round-red.log`、`replay-round-green.log`）。01/02均未形成完整回归结论，不复用为最终退出证据。

## 门禁03失败与预算兼容修复

源码 `7925b093c30ad26e18d1eb117c739548a5c89a52`，门禁03失败于offline：1585项，42failure、69error、42skip；测试1168.677秒，门禁1180.453秒，source_changed=false。发布与前端未执行，日志和原始摘要保留。

64个error直接指向独立RunBudget账本不存在solver_states；新接缝无条件查询导致旧模型/工具准入失败，进一步引发零请求与超时断言失败。修复仅先查表是否存在，缺表沿旧预算行为；12项旧预算与迟到结算先通过，30个失败模块回归153项全部通过，85.752秒，`gate03-failed-regression01.log`；没有放宽旧断言。定向Standards/Spec复查覆盖该四行修复与默认预算隔离，无新增阻塞。

另有test_star_experiment的Docker daemon不可用环境错误；用户于本次接续手动打开Docker，实测server29.6.1，已有固定镜像SHA `fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` 一致，未构建/下载镜像。42skip不计通过，后续完整门禁按实际环境重新记录。

## 门禁04与交接结论

门禁04源码 SHA：`eaaadc0b9df401b77a10b30e26546374e3e6600d`，其结果仅覆盖该提交。新增真实进程退出测试、预算预留关联断言与最终文档冻结后，门禁05在源码 SHA `088a307d0ba8d332cc2f0e6c767c405a8de4180e` 上运行：`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-population-05`。

| 检查 | 实际结果 |
| --- | --- |
| 完整门禁05 | 6/6，1555.765秒，source_changed=false，`artifacts/final-gates/faithful-population-05/status.json` |
| 完整回归 | 1606项，0failure、0error、42skip，1427.257秒；同目录repository-check/tests.json与diagnostics.log |
| 发布检查 | 27项通过，39.921秒，release.log |
| 前端 | npm ci/audit/check全部通过，0漏洞；chunk大于500kB提示不计性能验收 |
| 浏览器 | 先前桌面/手机Chromium两项通过，前端源码其后未变化，r4证据复用 |
| 官方隔离 | 快速边界检查通过；相对接管HEAD的user_agent.py、implementations/、BASELINE.json无差异 |

门禁05的42项skip主要是需要显式验证镜像配置的隔离工具/Reference专项；该次完整门禁摘要如实保留skip。Docker开启后，使用仓库固定镜像ID `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` 和Docker readiness标志，对解析出的全部42个原skip用例单独重跑：`Ran 42 tests in 263.685s — OK`，日志 `artifacts/faithful-population-takeover/faithful-population-docker-skip-20261109-r2/tests.log`。该专门回放不改写门禁05摘要，也不以设置环境变量替代测试通过。S09 Lean仍unavailable，没有L2/L3，不解除F3/S10前置，不实现干预或记忆。

**#156的本轮离线并发工程实现与工程门禁达到engineering-preview。** 公开恢复、受控真实HTTP、取消/截止、证据共享、持久回放、交付与结算以及报告浏览器证据分别保留；不以浏览器fixture代替后端公共HTTP，不以单元测试代替真实服务容量。运行中路线注册由可信控制器注入验收，未新增自主Planner生产者；实际跨进程接管有store与公共恢复证据。

新增真实退出窗口聚焦验收 `test_public_resume_after_worker_process_exit_reuses_persisted_receipt`：子进程在 completed receipt 已持久化、尚未 accept 且另一条路线已有 dispatched HTTP 时被终止；新 `create_app` 实例启动时自动将 Job 恢复为可审查失败态，再经公开 `/resume` 复用已完成动作。断言原 inflight action ID 精确变为 unknown，且同一 action ID 下仍有含 input/output estimate 的 reserved/unknown/error HTTP budget entry；reasoner/verifier 调用身份不重复，独立答案交付成功。三次重复日志：`artifacts/faithful-population-takeover/process-exit-replay-20261109.log`。相关11项回归 `Ran 11 tests in 37.760s — OK`，包含跨进程旧owner拒写、explicit retry、迟到结算、cancel/deadline与正常双路线并发。该证据覆盖受控 loopback 的真实独立进程退出窗口，不等同于真实provider或全故障矩阵。

路线扩展范围核对#155 Resolution：必须满足“运行中加入时进入下一轮”的调度合同，没有要求新增自主或无界Planner生产循环。现有初始Planner已返回并登记有效alternatives；受控可信控制器注册用例覆盖晚加入路线的轮次规则。本轮不增加额外Planner调用/API，也不把该验收描述成生产中的动态Planner路线生成。

真实provider、服务/账户/机器容量、自然机器压力、SLA、自然题和独立数学效果未验证；faithful-D研究批次not_run。保留#156开放以追踪剩余真实环境/完整覆盖验收，不关闭完整F6、F3或总票#146。原挂起runtime06根因未知，后续带超时栈15项通过和完整门禁04通过不被写成已定位修复该挂起。

门禁01/02中断、03失败、04成功及05成功全部保留。05开始和结束的dirty tracked/untracked均为空，`source_changed=false`。门禁源码/门禁SHA为`088a307d0ba8d332cc2f0e6c767c405a8de4180e`；文档索引及本验收记录随后由独立docs提交更新。临时30分钟检查、runner脚本及测试后台进程均已清理；无未完成运行。未push。接续仍使用当前选择模型，具体型号与实际继承未独立核实，不猜测。

官方baseline和默认评分预算未变；`tests/test.md` 未读、未改、未提交、未删除。完整记录只支持所列工程覆盖，不声明数学能力提升。
