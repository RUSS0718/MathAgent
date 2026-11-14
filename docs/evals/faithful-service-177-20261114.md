# #177 并发收敛后干预验收记录

日期：2026-11-14（Asia/Shanghai）；当前状态：达到用户授权调整后的开发接线退出条件。父规格 #168 和真实服务验收 #183 保持开放。要求见[任务合同](../engineering/faithful-service-177-contract.md)，循环规则见[接续合同](../engineering/unattended-ticket-loop.md)。最终门禁采用同源码失败后的受影响复验，详见末节；不宣称单次完整门禁通过。

## 身份及证据范围

起点 `fbd2a8ebe7ea69823b1a8507e9035e7324692702`，复用 `faithful-autonomous-population`。当前只持有 #177；#175/#176 在实时 GitHub 核对中均已关闭，#177 open/ready-for-agent，显式前置已满足。继续当前模型与思考设置，无覆盖；具体型号及继承结果未知。服务的 provider 配置不代表本助手型号。

## 当前验证

- 前端 `artifacts/issue-177/frontend-red.log` 保留“并发收敛后干预”缺失的失败见证；`frontend-green.log` 同一断言通过。组件沿用现有状态、来源及证据等级显示，无新操作入口。
- `browser.log`：受控串行及并发两组通过，均覆盖320/768/1024/1440宽度、来源展示、刷新零写请求、无页面脚本错误及无水平溢出。截图 `population-reopened.png`、`serial-reopened.png`。此证据使用拦截响应，不是自然干预或真实模型证据。
- `typecheck.log`、`build.log` 通过；构建仍提示现有 bundle 大小警告，不据此宣称性能通过。
- 后端受控组合及修复回归、独立增量复审与冻结源码组合门禁已完成。两次真实模型运行未覆盖自然D2。失败诊断文件保留，不能因名称含 green 就判通过。

## 首次真实尝试与独立审查

live01 源码 `6040dd502a3406afa4dc5f005b68eaead58cdc17`，配置文件 SHA256 `5e639bc68672b93967c40e0cce71f1b8d8e51832b2db5a056f1712d991d174c0`。普通浏览器提交双参数非负四次多项式题；Run/Job `run_17a6a5b720840a4f46ec1ae6c2082e37`，11 个持久调用完成、根预算/deadline/config 保持，无 native 分臂，整题审查未绑定。自然初始选择串行，干预选择 keep/skipped；最终 `failed/job_execution_failed`，solver `partial_aborted`，原因 `route_duplicate_route_frontier`。没有已验证最终答案，D2 自然路径未覆盖。首次观察器因服务未监听连接失败，零提交，资料独立归档 `startup-failure-*`；健康检查后才启动实际唯一提交。

证据：`artifacts/issue-177/live01/contract.json`、`submit-receipt.json`、`job-final.json`、`persisted-latest.json`、`browser-mutations.json`、`browser-errors.json` 与截图。观察器检查刷新前后写请求数不变，无页面脚本错误；总写请求包含会话创建和原始提交，不能将总数称为刷新写请求数。服务实际 PID8128、uv11844 已按创建时间核对停止，观察器42396终态退出，临时检查已清理。

独立审查固定起点 `fbd2a8e`，审查源码 `6040dd5`。Standards 发现1项P2：completion更新缺字段白名单；Spec发现2项P1：二次干预复用旧pair伪完成、成果回接缺可校验推理来源。报告 `artifacts/issue-177/reviews/standards.md`、`spec.md`；构造来源查找见证 `source-witness.py` 不是公共运行故障复现。

修复提交 `d5faad6972de3fecdbb58844e14ae96566636261` 限制完成回写字段并核对完成状态、来源、所选路线和持久pair；明确拒绝同Run第二次干预，保留旧来源；以 `native_report_sources` 封存真实reasoner报告及回执，父Verifier独立核验后才生成父账本权威。共享来源解析接通证明图与Population依赖核对，不导入子臂权威账本。前端修复 `0d4f792` 区分权限撤销等已知阻止与unknown等待。

`review-red.json` 保留3项审查反例失败，`review-green-01.json` 为3项通过。`review-regression-01.json` 为15项中1项失败；`review-focused-02.json` 正向仍失败，均不计通过。最后修复旧本地报告误匹配及原生报告规范化差异后，`review-focused-03.json` 正向7.873秒通过；`review-regression-02.json` 最终15项、51.775秒、0failure/error/skip。命令选择两个模块：`uv run python scripts/run_unittest_report.py --expect-count 15 tests.test_population_intervention_177 tests.test_serial_intervention_176`，报告输出参数见该脚本 `--help`。源码SHA256清单 `review-source-sha256-02.json`；Ruff及diff检查通过。以上均为受控provider证据。增量复审及最终门禁尚未完成。

增量 Standards 复审 `standards-recheck.md` 关闭原P2且无新增阻塞。Spec `spec-recheck.md` 关闭原两项P1，但发现预算拒绝后投影仍带未创建pair，导致completion查询失败的新P1。公共Job见证 `budget-red.json` 为1failure、4.925秒，异常链到 `pair_not_found`；`reserved-budget-red.json` 为1failure、4.931秒，展示已持久reserved异常被错误投影为skipped。两项失败均保留，修复与终审仍待完成。运行中的live02使用冻结产品源码；这两项测试文件新增不进入真实服务运行路径。

live02在源码 `d5faad6972de3fecdbb58844e14ae96566636261`、同一配置文件SHA256上，由普通浏览器提交单参数题。Run/Job `run_711be219ec5f44dbc07410161673725e`，13个调用，出现串行 `intervene` 决策但实际 `skipped`，pair_id为空、0 native分臂；最终 `failed/star_needs_review`，solver `partial_aborted`，原因 `invalid_meta_decision`，整题审查未绑定，无已验证答案。刷新前后写请求数不变，page errors为空；总写请求2包含会话与原提交。证据同live01结构，位于 `artifacts/issue-177/live02/`。服务PID32496已按创建时间核对停止，uv16280随服务退出；观察30400已终态退出，临时检查已清理。

依据接续合同，两次有诊断目的自然尝试后，D2-4调整为开发接线退出；合同与GitHub #177/#183已同步。自然正向闭环、完整正确答案、实际干预UI终态及进程退出后D2续跑仍未实证，不再碰运气重复模型调用。

预算修复提交 `04d493b958e997fef71ac4b4c96de3ae4c3a0328` 保留store严格校验：异常时直接查pair是否已持久化，未创建则清空投影pair_id并跳过；已创建则保留原预留、needs_review/pending，禁止自动重跑。公共用例暴露续接时父calls修订高于route修订，恢复误认未消费动作；completion补路线接收事件并同步快照修订，调用身份保持原样。`budget-green.json` 的1failure/1error、`budget-green-02.json` 的1清理连接error不计通过；修复连接关闭后 `budget-regression-01.json` 为10项、48.641秒、0failure/error/skip，覆盖两条预算路径、正向及#176七项。命令：`uv run python scripts/run_unittest_report.py --expect-count 10 tests.test_population_intervention_177.PopulationInterventionTest.test_unreserved_pair_skips_intervention_and_continues tests.test_population_intervention_177.PopulationInterventionTest.test_reserved_pair_failure_preserves_holds_and_blocks_replay tests.test_population_intervention_177.PopulationInterventionTest.test_population_converges_before_native_intervention tests.test_serial_intervention_176`，另带同名 `--summary-json` 和 `--diagnostics` 输出。Ruff及diff检查通过；最终窄复审和门禁待完成。

后端 `backend-regression-01.json/.log`：12项、52.398秒、0failure/error/skip，覆盖D2五项和#176七项，仅证明受控接线。此前 red、debug、green-01至05、focused-01/02 等失败保留原判，不因文件名改判。前端另补权限撤销不能显示“未知结果”误导文案的红绿，见 `frontend-blocked-red/green.log`。

## 合同映射

| 合同 | 公共入口和断言 | 证据 | 当前结果 |
| --- | --- | --- | --- |
| D2-1 | POST普通Job、收敛、合法checkpoint、原生F4 | `PopulationInterventionTest.test_population_converges_before_native_intervention`；`review-regression-02` | 受控pass；自然未覆盖 |
| D2-2 | 同任务来源、配置、根预算/deadline及显式采用 | 同一公共Job正向、`ReviewBoundaryTest`来源/回写反例，复用#176根预算检查 | 受控pass；自然未覆盖 |
| D2-3 | unknown/取消/版本冲突/权限撤销及完成回执重放不重复 | `PopulationInterventionTest`四项故障及正向重放、`ReviewBoundaryTest`二次拒绝；只读Job无新增调用 | 受控pass；实际进程退出后D2续跑not_run |
| D2-4 | 工作台与只读重开；两次自然尝试如实留档 | 受控浏览器2组；live01/02均未覆盖D2，合同与Issue同步 | 开发UI pass；自然未覆盖留#183 |

已通过的受控工程检查不能证明数学正确性、自然选择或 #168 完整服务交付。旧 #176 自然失败保持原判，本票不恢复或重发其 unknown。live02 的 `reopened.png` 实际仍为加载态，不能证明真实UI稳定终态。

## 最终复审与组合门禁

下列结论更新前文各次尝试中“待复审、待门禁”的历史状态。最终窄复审 `artifacts/issue-177/reviews/spec-budget-recheck.md` 关闭预算P1；受影响Standards和Spec无新增阻塞。审查对象 `04d493b` 的三份受审文件与冻结HEAD无差异。此前初审、增量复审与红绿记录均保留。

冻结源码为 `0225fd9cd69a374d4cd9b26bba43eecc929655b7`，无tracked改动。门禁原入口为 `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-177/gates --run-id gate-01`，之后使用新run ID。

- `gate-01` worker异常退出，Windows状态码1073807364（0x40010004），原因未确认；报告的0项不是有效完整测试计数。进程已退出，原状态文件停留running，实际终态另存 `gate-control/gate-01.terminal-observation.json`，不覆盖原记录。
- `gate-02` 快速检查通过，完整测试2060项、0 failure、1 error、49 skip、1653.456秒。唯一error为 `test_star_experiment.setUpModule` 无法连接Docker Linux引擎，该模块20项未执行。门禁保持failed，source_changed=false；mutation及后续阶段当时未执行。
- 现场核对Docker Desktop无进程、服务停止；启动已安装的Docker Desktop后，`docker version` 返回真实Linux Server。未改生产代码、测试、依赖或配置。依据接续合同“失败只复查受影响部分”，复用同一源码已覆盖的2060项与快速检查，仅重跑未执行的20项并补齐余下检查。
- `gate-03` 是显式 `affected-recheck`，`final_status=passed_with_reuse`，440.172秒；不是标准入口单次全仓通过。续接脚本 `artifacts/issue-177/gate-control/resume-gate.py` 校验gate-02唯一错误、计数以及前后源码哈希一致，完成后再次核对source_changed=false。原gate-02失败不改判。

| 门禁要求 | 最终证据与结果 |
| --- | --- |
| 快速检查、baseline及官方入口 | `gate-02/fast.log`，pass |
| 全部测试覆盖 | `gate-02/repository-check/tests.json` 的2060项与 `gate-03/experiment-tests.json` 的20项组合，共2080项，49 skip；模块复验20项0 failure/error/skip，299.635秒。原setup error经复验解决，不从原报告删除 |
| mutation probes与两个服务CLI | `gate-03/offline.log`，六个既有probe和两个CLI均exit 0 |
| 发布检查 | `gate-03/release.log`，27项，0 failure/error，pass |
| 前端安装及审计 | `gate-03/frontend-install.log`、`frontend-audit.log`，pass，0漏洞 |
| 前端依赖合同、typecheck、测试与build | `gate-03/frontend-check.log`，65项全通过；保留现有bundle大小警告 |
| 源码冻结 | gate-02及gate-03的 `source-manifest.json`，前后哈希一致，无源码漂移 |

受影响模块的可复现命令为 `uv run python scripts/run_unittest_report.py --expect-count 20 --summary-json artifacts/issue-177/gates/gate-03/experiment-tests.json --diagnostics artifacts/issue-177/gates/gate-03/experiment-diagnostics.log tests.test_star_experiment`。续接顺序和其余完整命令见 `gate-control/finish-offline.py`、`resume-gate.py` 与各阶段日志。49项skip的逐项原因保留在gate-02诊断，包含未配置独立验证镜像及显式Docker集成开关，不记作通过。

最终受测源码之后只更新文档，保留上述门禁SHA。三个门禁进程均终态退出，临时检查均已清理；Docker Desktop作为共享本机工具保持运行，不由本票停止。自然并发干预、完整正确答案、真实干预UI终态与进程退出后D2续跑仍未实证，继续留#183，#168不关闭。
