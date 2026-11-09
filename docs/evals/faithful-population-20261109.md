# #156 Population/APRS 接管与验收

日期：2026-11-09（Asia/Shanghai）。状态：实施中，尚无最终门禁，不声明工程退出或数学能力提升。

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
| 4 owner/恢复 | 独立进程接管 SQLite 后拒绝旧 owner；公共 Job 在 completed receipt 与 accept 之间退出后复用结果，reasoner 数不增加 | completed 公共恢复包含独立进程接管；进程退出窗口仍用故障注入 |
| 5 unknown | 普通 resume 零重发；显式新 ID lineage；timeout 保留旧预留；公共 GET/report 修复丢失结算 callback | 本地 timeout 不代表远端停止 |
| 6 冻结/终止 | 公共首次 REJECT 后恢复合法路线并再次整题审查；cancel/deadline 迟到不改根义务或交付 | 无形式内核验收 |
| 7 交付/结算 | 公共答案先交付、迟到后结算；报告/Evidence 分开投影；桌面/手机 Chromium 刷新重连零 POST、隐私检查 | 浏览器受控 API fixture；后端公共测试独立覆盖真实 HTTP |
| 8 policy/兼容 | 独立 preset、五项预算身份；同 key 返回同 Job；旧路径回归与 baseline 快速检查 | 最终新源码门禁待完成 |

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

## 退出与未验证项

源码 SHA、门禁 SHA、source_changed、完整失败/skip、最终交接 SHA 待冻结后记录。55 项回归结束后临时检查已删除；最终门禁启动时重新建立唯一检查所有权。

真实 provider、服务/账户/机器容量、SLA、自然题和独立数学效果未验证。S09 Lean unavailable，无 L2/L3，不解除 F3/S10 依赖，不实施干预或记忆。不关闭完整 F6、F3 或总票 #146。官方 `user_agent.py`、`implementations/`、baseline 和默认预算隔离；`tests/test.md` 不读、不改、不提交、不删除。
