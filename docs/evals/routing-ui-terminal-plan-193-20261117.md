# #193 终态计划显示补充合同与验收

日期：2026-11-17。基线 a0a4cd2abe7524eab51cdd2d7a4b87986045d42c；独立分支 fix/showcase-terminal-plan-193。
本补充服从 routing-ui-193-contract.md；只处理浏览器新发现的终态计划矛盾。

## 合同与退出条件

公共接缝：projectWorkbench(events, result, replay, status)，用户已指定并授权。
Job 是执行控制状态，保存计划步骤是历史数学进展；终态不能把 current 当成仍在运行，也不能由 Job 成功推断全部步骤通过。
failed/canceled/cancelled/partial/incomplete/budget_exhausted/succeeded/completed 时，未裁决 current 显示“任务已结束，步骤结果未确认”，pending 显示“历史记录：等待执行”。这只说明记录，不断言从未执行。
回放 current 显示“历史记录：执行中（结果未确认）”，pending 同样标为历史。回放只用所选事件，不借用最终 Job 结果。
unknown/needs_review/unknown_outcome 或公开 faithful.phase 的 unknown/needs_review，未裁决 current 显示结果未知；不强判完成、安全取消或远端停止。
ACCEPT 且 valid、CHALLENGE 与原撤回规则保持优先；运行中、缺失或未识别状态不自动终结。无计划仍为空。
实现限定现有纯投影和文案映射，不写回输入，不改 ledger/solver/call/budget/policy/schema/oldRun。

步骤与验证：公共失败红例→最小投影修复→终态/成功/历史/unknown 边界及相关回归→类型与差异检查→合并集成 tip 并交接。

## 证据与结果

浏览器现象引用 C:/Users/CQX/.codex/tmp/193-browser-acceptance-20261117.md 和 root artifacts/issue193-browser/after-detail/observations.json 的 U.visiblePlan；该记录的 S1 执行中、S2–S4 等待，不是本次重新打开浏览器的结果。

| 验收 | 入口/断言 | 结果 |
| --- | --- | --- |
| 失败最小红例 | 公共 failed Job + 保存 current/pending/ACCEPT/CHALLENGE，显示终态和历史，不改输入 | red.log 1失败 → green-slice.log 1通过 |
| 终态及成功 | 取消、部分、预算结束、成功仍不虚构未裁决步骤完成；真实 ACCEPT 保持 pass | pass |
| 历史重放 | 事件中的旧 current/pending 显示历史；同事件 running 仍 active | pass |
| 未知边界 | 三种 unknown 状态及 faithful needs_review 保守；未来状态不自动完成 | pass |
| 缺计划、实时输入 | 无计划为空，running/queued/缺状态保持记录 | pass |
| 相关回归 | terminal-plan-193、routing-193、causal-progress、presentation-mode | 17通过，0失败/取消/跳过/todo |
| 类型与格式 | npm.cmd run typecheck；git diff --check | exit 0 |

证据仅自有 ignored artifacts/issue193-terminal-plan/。命令在独立工作树根：

```powershell
node --experimental-strip-types --test showcase/frontend/chat-frontend/tests/terminal-plan-193.test.ts
node --experimental-strip-types --test showcase/frontend/chat-frontend/tests/terminal-plan-193.test.ts showcase/frontend/chat-frontend/tests/routing-193.test.ts showcase/frontend/chat-frontend/tests/causal-progress.test.ts showcase/frontend/chat-frontend/tests/presentation-mode.test.ts
# 在 showcase/frontend/chat-frontend 目录
npm.cmd run typecheck
```

红例有1项，绿切片1项，最终17项（其中新增5项）；红例确由执行中/等待执行与合同文案不符而失败。测试是受控公共输入，未读取真实 Job 的 solver 快照，不能冒充同组自然 Job 浏览器重验。

## 边界与交接

复用 #193 外部设计候选的 Vue/W3C/Chrome 指导，并核对 Vue computed 官方说明；派生计算无副作用，不增加依赖。共享 node_modules junction，无安装、锁文件修改、Python、provider、服务、新 Job、浏览器、全仓或最终门禁。
仅本地自审，未作独立双轴审查。主控负责 fresh merger/review/browser/gate；实际 U/D/S2 普通页面、窄屏、刷新及重启仍由主控验证。
提交前 dependency-routing-189 仍为基线 a0a4cd2，merge --ff-only 为 Already up to date。最终精确提交及 tree 写外部 handoff，避免文档自引用 SHA。
保留独立工作树及 junction 供合并审阅；未创建长测试、定时任务、服务或后台进程，无检查所有权转移。主控合并后清理工作树和 junction。
继续当前选择的同一模型；未指定或覆盖型号，无法独立验证父子型号继承。
