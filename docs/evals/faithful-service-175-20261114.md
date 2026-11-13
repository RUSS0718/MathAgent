# #175 同任务安全串并行切换验收

日期：2026-11-14（Asia/Shanghai）；状态：实施中，未达到退出条件。父规格 #168，[任务合同](../engineering/faithful-service-175-contract.md)。起点 `bc386a09`；集成分支 `faithful-autonomous-population`。

## 已执行

- `7c67d31` 接入工作台和报告的独立 `execution_switch` 投影，初始选择保留为历史，不用初始选择代替热切换。
- 前端红见证：在前端目录执行 `node --experimental-strip-types --test tests/execution-switch.test.ts`，因缺少“切换中”文本失败；同一用例修复后通过。此前从仓库根运行因 Vite 根目录错误失败，仅为命令定位错误，不作产品失败证据。
- `node --experimental-strip-types --test tests/execution-switch.test.ts tests/population-report.test.ts`：2/2 通过；`npm run typecheck` 通过。
- `npx playwright test tests/browser/execution-switch.spec.ts --workers=1`：1/1 通过。真实 Chromium 在受控 API 数据下区分收敛、待复核、已切换，移动刷新保留检查点版本 17，零修改请求、零 pageerror、无水平溢出。截图已目检。此项只证明界面投影。
- 前端日志：`artifacts/issue-175/ui-{red,green,browser}.log`；截图：`artifacts/ui-unification/browser/execution-switch-saved-swi-b9e54-ening-on-desktop-and-mobile/switch-mobile.png`。

## 后端聚焦结果

后端实现 `afb9f8f`，合并集成后为 `2c49ef2`。原样保留实现工作树证据到 `artifacts/issue-175/backend-evidence/`：`backend-final.json` 7 项、`recovery-regression.json` 2 项通过，均 0 skip。取消收敛的红见证 `fault-red` 为 canceled 与 converging 不符，修复后通过。各次失败和诊断日志均保留，未覆盖或未执行场景不由这些汇总替代。切换期间专用进程崩溃尚未单独实测。

## 首轮双轴审查：未通过

比较 `bc386a09...2c49ef2`（并检查随后 UI 原因摘要）。标准轴 1 项 P1：收敛 unknown 后显式新身份重试被派发冻结阻塞。规格轴 2 项 P1 与 1 项 P2：永久禁止第二次扩展、串行 checkpoint 缺少合法消费者、切换没有消费停滞或运行中 Agent 决策。审查为静态证据，不是运行时失败复现。原报告在仓库外 `C:/Users/CQX/.codex/175-standards-review.md`、`175-spec-review.md`；新鲜实现代理正按公共失败见证修复，尚未复查。

不在已知缺陷源码上启动真实模型，减少无效调用。需要补的切换专用崩溃恢复证据保持未完成；原有普通恢复回归不冒充覆盖本次切换窗口。

## 真实验收准备（not_run）

`artifacts/issue-175/live01/` 保存独立服务、观察器与输入合同，尚未启动。复用 #174 的应用配置（其 SHA256 在启动时重新记录），根预算和 deadline 不在任务中修改。普通输入为 4×8 棋盘骨牌覆盖，独立逐列状态递推参考值 2245；参考值只供验收核对，不发送给模型。没有强制技术模式。

真实切换、正确答案、来源绑定、只读刷新、崩溃/unknown/取消、合法串行 checkpoint、两轴审查及最终工程门禁尚未通过。具体执行结果和冻结源码 SHA 在完成后更新，不能从 UI 通过推断 #175 或 #168 已完成。

## live01：未通过

冻结产品源码 `010befd`，普通 4×8 棋盘输入，Run/Job `run_b207ef83d4d9b71cb05d38405016e66b`。配置 SHA256 `9170fa5f39e8262e2ea780a54478bdd14d10e4c6da6531381d3f9a055cf97364`；应用实际模型 intern-s2，配置名称不代表本助手型号。自然选择 serial，只有一条独立前沿；7 Attempt 全部 success 并已结算，最终 `failed / star_needs_review / partial_aborted`，没有完整交付，也没有热切换。HTTP 成功不算解题成功。输入、普通浏览器提交、公开 Job、只读持久投影、报告和刷新记录均在 `artifacts/issue-175/live01/`，刷新无修改请求。原根预算、deadline 和 config hash 观察中不变。服务按 PID/创建时间核对后停止，临时检查已删除，不恢复或重提旧任务。

该题指定先做逐列递推，模型合法认为只有单一方法；第二轮将改为允许独立完整方法竞争的代表题，而非强制技术模式。期间增量审查发现父级模式 Meta 调用的完成回执/消费窗口与 unknown 恢复漏洞、串行 checkpoint 后续过期，均待修复复查；live01 不作为这些路径通过证据。

## 第二轮审查与实际崩溃红见证

固定目标 `010befd` 的增量审查确认原路线 unknown 重试与再次扩展已有修复，但新增模式 Meta 的持久身份/回执消费、模式 unknown 显式重试及串行 checkpoint 后续刷新仍有缺陷。审查原件为仓库外 `175-standards-review-final.md` 与 `175-spec-review-final.md`，当前仍未通过。

新增公共进程见证在真实子进程的 completed call_audit 提交后执行 `os._exit(75)`，随后新进程在同一数据库/Job 通过公开 resume 继续。两次红测稳定发现已完成 `execution-mode:116` 被重发为 `execution-mode:122`，预期一次、实际两次；只读 GET 不派发，配置、根预算起点/deadline/limits/预留保持。证据 `artifacts/switch-mode-receipt-witness-{01,02}/`（第二次约14.5秒）。该红测尚未在修复源码上通过，不宣称崩溃恢复已完成。

## 修复后的实际恢复与复审

`7857e6e` 修复父级模式 pending 身份、完成回执复用、marker 与 intent 原子消费、模式 unknown 的显式新身份路径和串行 checkpoint 结算后刷新。集成为 `ce46d0b`。同一个真实子进程退出见证在集成树运行：`uv run python scripts/run_unittest_report.py --expect-count 1 --summary-json artifacts/issue-175/crash-green.json --diagnostics artifacts/issue-175/crash-green.log tests.test_faithful_execution_switch_crash.ExecutionSwitchCrashTest.test_completed_mode_reply_before_marker_is_not_resent_on_public_resume`，1/1 通过，14.259秒、0 skip；旧两次红记录原判保留。测试提交 `3ccd1e5`。

固定修复范围 `010befd...7857e6e` 的两轴复审均无剩余确切缺陷，报告在仓库外 `175-{standards,spec}-review-final2.md`。静态结论不代替真实自然切换或最终门禁。第二轮 live02 已在 `3ccd1e5` 启动，Run/Job `run_d79f2812f014e876b2e576ef78c0ebea`，仍待终态。

## live02 与开发退出口径

冻结 `3ccd1e5`，普通6×10棋盘可任选独立完整方法。Job `run_d79f2812f014e876b2e576ef78c0ebea`，6 Attempt 全部success并结算；最终 `failed / partial_aborted / invalid_problem_spec_work_units`，Planner有界修复后仍未进入路线选择，未热切换、无完整答案。参考值4213133未发送模型。输入、提交、报告、刷新和持久记录在 `artifacts/issue-175/live02/`；服务按PID/创建时间停止，检查已删除。两个真实失败不因调整而升级。

依已授权接续合同，将本票改为开发接线验收，自然真实切换、完整交付和真实UI正向闭环交给#183。原要求、障碍、替代证据与限制见[更新合同](../engineering/faithful-service-175-contract.md)；尚未取得最终工程门禁结果。产品仅随后 `7d9d59e` 修正本票7处局部导入排序，未改运行行为；最终冻结SHA及门禁将另记。

## gate-01 失败与责任范围修复

冻结 `75c1eab63dbc66fe1b12609b499d427d3a5dfac7`，`uv run python scripts/run_final_gate.py --root . --output-dir artifacts/issue-175/gates --run-id gate-01`：快速通过，完整离线 2061 项、2 failure、2 error、49 skip，停止在第二阶段；`source_changed=false`。失败原件保留于 `artifacts/issue-175/gates/gate-01/`，临时检查已删除。

- 旧 native checkpoint 脚本未响应新增运行中 Meta；补充 `keep` 回复后，公共入口继续复现真实版本竞态：模式回执完成后，路线提交可使消费 marker 的 CAS 失败。确定性故障见证 `gate-fix/consume-red` 稳定失败；修复只重读版本重试持久消费，复用原回执、不重新调用模型。
- 后续持久诊断发现在途调用 dispatch 与 transport 审计之间，另一条路线进入收尾冻结；原规则拒绝 `transport_selected`，造成调用被记为 unknown 且缺物理账本。确定性公共见证 `gate-fix/transport-red` 失败。修复只允许 `transport_selected/rejected` 的调用审计落盘；终态仍只允许 calls，数学写入继续冻结。
- checkpoint 刷新测试原探针 patch 定义处，实际 accept 使用 runtime 中已导入别名；改为 patch 使用处，不删除原来源/实际 reserve_pair 断言。取消测试先检查公开 canceled，再等待实际 worker 退出以释放临时 SQLite，不改变产品停止语义。
- 两竞态修复后 `gate-fix/race-green` 2/2；native checkpoint 模块 `gate-fix/native-final` 6/6、0 skip，原根预算与完整交付断言保留。`fence-final` 因命名类选择错误执行 0 项，不计通过；修正后的 `fence-final02` 4/4、0 skip，覆盖实际 checkpoint 刷新/消费、切换取消及既有迟到交付/取消隔离。所有路径前缀均为 `artifacts/issue-175/`。
- 四文件增量 Standards/Spec 复审均 PASS，仅为静态结论，报告 `C:/Users/CQX/.codex/175-gatefix-{standards,spec}-review2.md`；11 个 baseline 文件逐份 SHA256 无变化，受影响四个 Python 文件 Ruff 与 diff 格式检查通过。新冻结最终门禁尚待完成。

## gate-02：旧双路审查测试时序失败

冻结 `fac899bf081d0071377957a08f301d6d67b5204b`，同一最终入口使用新 run-id `gate-02`。快速通过，完整离线 2063 项、2 failure、0 error、49 skip；`source_changed=false`，临时检查自删除。失败为 native 普通 checkpoint 与工具预算用例各仅观察到一次 step_verifier HTTP；首路合格后冻结其余新工作符合产品合同，旧测试没有同步“两路已进入 HTTP”的初态，不能要求随机调度保证两次调用。

只在受控 provider 为非 continuation 审查增加双路 barrier，确保两条审查实际发出后才允许任一路取得合格裁决。原双路序列化、完整交付、工具次数与根预算断言全部保留，产品源码未变；竞态专项 continuation 不受同步影响。`artifacts/issue-175/gate-fix/native-sync-final.{json,log}` 6/6、0 skip、36.214秒通过。门禁失败原判保留，新冻结最终门禁仍待完成。
