# S04 进展与停滞调度工程退出验收

日期：2026-11-08（Asia/Shanghai）。状态：工程退出通过（`engineering-preview`）。分支：`mathagent-faithful`。
门禁源码 SHA：`13641c643d85eb6a55aee62b0afc17126e5c6648`。实现提交 `831b9b97c9e7304331972c62e2ba2756e502716a`，完成义务辅助进展修复提交为上述门禁源码。之后的验收/索引提交仅修改文档，最终交接 SHA 以本记录所在文档提交及交接回复为准，不冒称该文档提交重新运行了产品门禁。

## 行为与范围

依据 [S04 合同](../engineering/faithful-s04-contract.md)和 [#144 阶段决议](https://github.com/RUSS0718/MathAgent/issues/144#issuecomment-6703147321)。沿用单一 SolverHarness、S03 根义务、收尾预留、独立整题审查和 exact-text 绑定。

- 可信服务端显式启用 `progress_scheduling`，要求 S03；默认 CORE 不启用。新 Run 冻结 `progress-v1`，旧 Run 不迁移。
- WorkUnit 方法使用小型受控 `method_id` 集合；未知名称统一 `unknown`。不同方法可探索，但不能通过自由命名制造无限方法。
- 完成有效数学审查才计回合；连续三个无新增有效证据回合进入停滞建议/Meta。相同目标和方法的第二次无进展失败触发局部阻断；同动作改名、换措辞、重复异议和重规划不清零。
- 新进展为首次满足的根义务，或冻结规格中明确通向开放根义务、且经过有效 ACCEPT 的前提辅助目标。自由文本引理、重复接受和只服务已完成根义务的辅助目标不取得信用。相关新证据解锁对应动作，无关义务保持阻断。
- 计数和安全事件摘要与原审查同事务 CAS；重复事件不重复计数，冲突整次拒绝，重开数据库保留计数。没有新增求解循环。继续被阻断动作或整体停滞后再次派发数学动作时有界停止；没有 Meta 端口时保持可审阅的 META_DECIDE，不自动新增调用。
- 停止保持原 budget、calls 和 counters；修复、回退、重规划继续受原 deadline、共享预算及 unknown 预留约束。S04 重规划重新绑定 WorkUnit 与受控方法，不继承旧映射。

官方 `user_agent.py`、`implementations/`、`BASELINE.json`、默认评分预算均未修改。`tests/test.md` 未读取、修改或提交。前端未修改，未提前实现 S05 展示、S07 证明图、S08 路线/APRS 或完整并发。

## 验收结果与证据

原始证据在集成工作树被忽略的 `artifacts/faithful-s04/` 和 `artifacts/final-gates/faithful-s04-02/`。

| 检查 | 结果与覆盖 | 证据 |
| --- | --- | --- |
| S04 专属 | 24 项通过：18 项进展/身份/事务/恢复/预算/重规划合同，6 项启用 S04 的公共 Job/report/replay 合同 | `tests/test_faithful_s04_progress.py`、`tests/test_faithful_s04_job.py`；门禁 tests.json 与 diagnostics.log |
| S03/S04 聚焦回归 | 71 项通过；含 S03 收尾实际共享预留和独立整题审查、S04 默认关闭与公共接缝 | `uv run python -m unittest discover -s tests -p "test_faithful_s0[34]*.py"`；`artifacts/faithful-s04/focused-final-03.log` |
| 相关 replan 回归 | 17 项，0 失败/错误，1 skip；skip 不计通过，最终完整门禁再次覆盖 | `uv run python -m unittest discover -s tests -p "*replan*.py"`；完整门禁诊断保留同类 Docker skip |
| 双轴审查 | Standards 与 Spec 的阻塞项已修复并复查；追加完成 root 辅助信用修复通过 Spec 复查 | `artifacts/faithful-s04/review.txt` 与本节下方记录 |
| 六阶段最终门禁 | 6/6，通过；`source_changed=false` | `uv run python scripts/run_final_gate.py --root . --output-dir artifacts/final-gates --run-id faithful-s04-02`；`status.json`、`source-manifest.json` |
| 仓库完整回归 | 1472 项，0 failure、0 error、42 skip，用时 1336.095 秒；skip 不计通过 | `repository-check/tests.json`、`diagnostics.log`、`offline.log` |
| 发布与官方边界 | fast 检查通过；release 27 项通过；baseline、官方 JSON/导入、Demo CLI 与 HTTP 合同通过 | `fast.log`、`release.log`、`offline.log` |
| 前端 | npm ci、audit、check 通过；0 漏洞；typecheck、单元测试、构建通过 | `frontend-install.log`、`frontend-audit.log`、`frontend-check.log` |
| 当前源码浏览器回归 | Chromium 13 项通过，含 ProblemSpec 刷新/SSE 重连零新增调用；这是既有 UI 回归，S04 专属调度由上列 Harness/Job 验收覆盖 | `npm run test:browser -- --config playwright.product.config.ts --output ../../../artifacts/faithful-s04/browser`；`artifacts/faithful-s04/browser.log` |
| Ruff 与差异 | 变更 Python 文件 Ruff 通过；差异格式通过 | 终端执行记录；最终纯文档提交只做文档检查 |

唯一成功门禁 PID 为 40856，开始于北京时间 15:24:32，耗时 1459.297 秒。临时 30 分钟检查任务及检查脚本已清理。Vite 保留既有 509.85 kB bundle 的非阻塞体积提示，退出码为 0。

## 审查修复与中止记录

最初失败验收确认缺失调度接口。Standards 指出不同辅助目标共享动作桶；修复为冻结辅助目标 ID。Spec 指出新前提证据没有解锁相关 root 方法桶；失败用例复现后修复，且无关 root 不解锁。同时补齐实际 guard 停止预算/unknown 不变、真实 Meta→replan 映射替换、关闭开关、Job/report/replay 合同。

冻结 `831b9b9` 后的门禁 `faithful-s04-01` 在 offline 阶段主动中止：追加复核发现已完成 root 的前提也能重置停滞计数。失败用例稳定复现期望 3、实际 0；最小修复后 71 项聚焦回归通过，Spec 复查通过，再以 `13641c6` 启动全新门禁。旧目录保留 `aborted.txt` 和 `aborted_for_fix` 状态，不计为通过，也没有与新门禁并行重复运行。

## 能力边界与依赖退出

42 项 Docker/Reference 相关测试仍跳过，真实隔离工具环境覆盖未完成。provider-live、容量/SLA、自然题规格抽取及方法标识的语义忠实性、数学能力收益均 `not_verified/not_run`；本轮没有付费 provider 实验。有限结构化目标信用是保守工程策略，不能识别任意自由文本中间定理的新颖性；受控模型和结构审查不证明数学正确性。

S03 与 S04 工程退出共同解除 F1/S07 的工程前置，允许按其独立合同开工；不表示 F1 已实现。S05 工程前置已满足，S06 仍等待 S05。总票 #146 保持开放，既有 live readiness 与能力票不因本次验收升级。

交接继续使用当前选择的同一模型，不主动切换；本窗口无法核实上一窗口的具体型号或继承结果，不声称锁定型号。
