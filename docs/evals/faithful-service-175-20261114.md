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
