# SP-08 安全恢复与显式未知重试验收

日期：2026-10-23。责任：#64，SP-AC-13/14。实现合同见 [SP-08 合同](../engineering/star-product-sp08-contract.md)，状态职责遵循 ADR-0014。

## 已执行的公共产品证据

所有用例经认证 ChatSession、Job 创建、公共 resume/cancel、Run、SSE、报告与 Evidence；HTTP 提供方为 scripted/fault-injection，实际经过 Adapter、STAR 调度、S3 账本和持久数据库。没有真实 Intern 调用，不声称数学能力提升。

| 触发 → 决策 → 实际动作 | 持久状态与用户结果 |
| --- | --- |
| 子进程第二步 `step_reviewed` 落盘后 `os._exit(71)` → 重启公共 resume | 同一 Job 从第三步起请求；总计 10 次模型/HTTP 动作，三次接受各一次，原 deadline 保留 |
| 第二步 Verifier 的 completed call audit 落盘、数学状态尚未推进时退出 → 重用响应 | 不重发第二步 Verifier；仍为 10 次出站、三次接受 |
| 第二步 session exchange 已记录、数学接受尚未提交时退出 → 重用 exchange/响应 | 不重复追加角色对话，不重复接受与计费 |
| 第二步工具回执落盘后退出 → 复用回执再进入 Verifier | 工具总计一次，模型动作仍为 10 次，不重复工具计费 |
| 第二步工具执行中退出、无回执 → needs_review | 普通 resume 拒绝，不自动重放工具；保留原一次工具预留与 unknown |
| 第二步 Verifier 请求在途时子进程退出 → 公共读取 needs_review → 普通 resume 拒绝 → 人工新 UUID 重试 | 新 call 引用旧 ID；旧 unknown/预留保留，总计 11 次出站，原 deadline 保留 |
| Explore、polish、planner、reasoner、step verifier、final generator、final verifier 的结果未知 → 显式重试原动作 | 已完成前置动作不重发；最终审查复用已持久化候选，报告/Evidence/Job 的 Solver 与预算一致 |
| 第二次重试仍 unknown → 再次明确决定 | 追踪不可变重试链，两个旧 unknown 都保留 |
| 两个并发人工决定 → 现有控制事务裁定 | 仅一个 202，另一个 409；仅一次 resumed 事件、一次新出站 |
| 显式重试在途时 cancel → 迟到回执 | canceled 不被覆盖；已知迟到 usage 可结算；不再派发后续角色 |
| 非法旧 ID、新 ID、幂等正文冲突、过期 deadline、Run 旧 resume 旁路 | 拒绝且零新增出站；SSE 重连、报告和 Evidence 读取不续算 |

`tests/star_recovery_worker.py` 是真正退出的独立 Python 进程；父测试通过退出码 71 和持久 HTTP 请求日志核对窗口，不以关闭/重开应用代替进程退出。

## 检查记录

- RED：首个公共 unknown 测试因缺少 `solver.recovery` 失败。
- RED：最终 Verifier unknown 的公共重试测试发现重新生成候选后失败；修正为复用待审候选。
- `uv run python -m unittest tests.test_star_product_recovery tests.test_star_product_planning tests.test_solver_harness_streaming tests.test_solver_harness_sessions tests.test_solver_harness_finalize -q`：44 tests PASS，47.782s。
- 同步 SP-10 集成 `60270688e338395e5d076384cace8a9f1017fde8` 后，恢复、最终绑定、Job/预算/规划/Gate/Challenge/回退/指导、流式/会话/收尾、控制/幂等/SSE 共 103 tests PASS，132.281s。兼容修复确保审查 source 指向重试后实际 completed 的新 call，旧 unknown 保留，SP-10 的文本与 ACCEPT 绑定条件不放宽。
- 最后新增工具退出窗口后：`uv run python -m unittest tests.test_star_product_recovery tests.test_star_product_tools tests.test_star_product_private_receipt tests.test_star_product_final_binding tests.test_solver_harness_tools -q`：43 tests PASS，55.899s（其中恢复公共验收 19 项）。
- `uv run python -m tests.star_recovery_mutations`：绕过未知决策守卫和绕过 completed 响应复用，两种修改均被原公共验收断言识别；正常实现无此旁路。
- 前端 `npm ci --no-audit --no-fund` 成功；`npm audit --audit-level=high` 为 0 vulnerabilities；`npm run check` 通过类型、13 个单元测试和构建。
- Chromium `star-recovery.spec.ts`：320/1440px 两项 PASS；人工点击前零 resume、SSE 重连零 resume、点击发送新 UUID 与旧调用引用；无横向溢出、无页面错误、Axe 零违规。该证据仅证明界面与请求合同，不代替 Python 产品验收。

## 独立审查后的恢复限额修复

独立合并审查发现最终候选循环恢复时重新获得完整 `max_final_solution_retries + 1` 次数。新增公共 RED 用例：同一计划尝试先拒绝两个候选，第三候选审查 unknown；显式重试第三次审查为 REJECT，并向提供方准备第四、第五候选回复。未修复时真实出站记录出现五次 final_generator，而允许上限是三次。

修复按持久 `final_solution_attempts` 中同一 `plan_version` / `attempt_index` 计算剩余生成额度，并继续注入该尝试最近的审查。已生成的待审候选不再占用新生成额度，仍允许合法的显式审查重试：第三候选重试为 ACCEPT 可完成并绑定新调用；重试为 REJECT 则在三次生成、四次审查（包含旧 unknown 与新重试）、总计 11 次出站后终止，不生成第四候选。拒绝用例保留 25 次共享调用预算，证明限制来自候选额度而非共享硬预算兜底。

先执行新拒绝回归、既有最终审查/生成恢复及最终绑定相关测试：18 tests PASS，16.917s。随后执行 `uv run python -m unittest tests.test_star_product_recovery tests.test_solver_harness_finalize tests.test_star_product_final_binding tests.test_star_product_traceback tests.test_star_product_planning -q`：45 tests PASS，89.175s，包含生成额度用尽时待审第三候选重试 ACCEPT 的正例。最新集成 `6027068` 已包含。此修复仅更正恢复后的候选生成次数，不增加其他机制。

## 边界与下一切片

unknown 显示为现有 failed Job 的 needs_review 恢复信息，不新增一套 Job 状态或预算。角色数学状态、控制事务、唯一 S3 账本与 checkpoint 继续分别拥有原有职责。内部重试决定不进入公开 Job/Run 输出；公开调用 ID 继续脱敏。

完整 reference 模式仍拒绝启动；此票的通过不解除 SP-11 的候选/硬预算、SP-12 的完整 Workbench 生命周期、SP-13 的真实模型与最终发布门槛。整题交付对象绑定由 SP-10 负责，已合入并通过兼容回归。工具没有持久回执时保持待人工复核，本票不提供自动工具重放。全量 offline 和最终发布检查由集成分支统一执行。官方冻结入口、`implementations/`、`BASELINE.json` 与 `requirements.txt` 对基点为空差异。
