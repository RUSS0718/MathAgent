# 重规划边界与 S09 环境核验

日期：2026-11-08（Asia/Shanghai）。起点 `9cf8ef4501f3227f4218530176ca98190a7ef9cc`；集成树 `faithful-integration/Challenge-Cup-2026`，分支 `mathagent-faithful`。

## 重规划诊断

结论：已确认产品缺陷，非夹具前提不匹配。公共 Job 最小复现为 `tests.test_faithful_s05_history`：冻结 ProblemSpec 的唯一根义务 `root:value` 无前提；初始步骤 `prove-value`、替换步骤 `fresh-value` 均映射此根义务。Meta 当前 APPROVE_REPLAN 合法，持久事件包含 plan_archived 和 plan_replaced；替换后未派发新 Reasoner 即终止。

初始 planning 根据 ProblemSpec 重建 WorkUnit；replan 却以 progress_policy.enabled 为条件。合法配置启用 problem_spec 而关闭 progress 时，替换计划沿用旧工作块，step 的严格查找无法找到 fresh-value，于是报 work_unit_prerequisites_incomplete。修复 `f180e7b` 将该条件与初始规划对齐，不放宽前提判断、完成条件或等待时间。

先将公共 Job 验收改为 succeeded，得到稳定失败；修复后公共 Job、S03 恢复及 Harness 共18项通过，包含真实 AND 前提阻断。证据：`artifacts/faithful-s06-s08-coordination/replan-red.log`、`replan-green.log`。原失败记录保留。

浏览器验收提交 `6f55402`：原真实受控 HTTP/SQLite 夹具不变，要求重规划成功、答案2、根覆盖1，继续断言归档/当前计划和刷新后的历史。命令：在前端执行 `npx playwright test --config playwright.s05.config.ts --grep 'real traceback and replan history'`。Chromium 1项通过（16.0秒），截图/trace 位于该次 `artifacts/faithful-s05-browser-run-*/`。这仅证明工程边界，不证明自然数学能力。

## S09 环境结果

状态：**unavailable**（Lean toolchain 与隔离编译不可用）；隔离容器执行本身可用。没有实现后端、安装组件、拉取镜像或调用付费服务。

- Docker Desktop 4.82.0 (233772)，Engine/Client 29.6.1，API 1.55；Linux amd64，WSL2 kernel 6.18.33.2-microsoft-standard-WSL2。
- Windows PATH 未发现 lean/lake/elan，用户 `.elan/bin` 无 Lean/elan；WSL 仅枚举到 docker-desktop，内亦未发现 Lean/lake。
- 现有 MathAgent 镜像固定身份：`mathagent-python@sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d`。未拉取或修改镜像。
- 实际运行使用 `--pull=never --network none --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 256m --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,size=16m`，默认 nobody 用户，隔离探针退出0。
- 隔离中写最小 `example : 1 + 1 = 2 := by decide` 后执行 `lean /tmp/Minimal.lean`，实际返回 `lean: not found`，退出127。证据 `artifacts/faithful-s06-s08-coordination/s09-environment.log`。

Lean/Mathlib/toolchain 精确版本无法核验；没有可报告的内核证明项或 L2/L3。上述有限环境探针不宣称穷尽机器中任意未登记目录。S09阶段未工程退出，F3保持未完成，S10依赖不解除。

## 独立双轴审查

针对 `git diff 9cf8ef4..6f55402`，两个继承模型默认值的独立只读审查分别检查仓库标准与用户重规划合同。Standards：无可行动项；Spec：无可行动项。未使用审查代替18项回归与真实 Chromium 验收。无法从工具结果核实具体模型型号，不声称锁定或已核验实际型号。
