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
