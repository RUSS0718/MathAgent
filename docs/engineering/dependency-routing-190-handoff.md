# #190 HANDOFF：目标依赖路由公共接缝

2026-11-17。仅 #190 实施交付，尚未经过阶段独立双轴审阅或整仓门禁；不代表 #189 整体完成或数学能力提升。

## 身份与集成

- worktree：`D:/project/mathagent-190`；branch：`feat/dependency-routing-190`。
- 初始基点：`1307aab40b8788cc408ef65fc94dfc7f2b1dc1f8`。
- 先行设计提交：`f59ca9f32609da9682634a0e1854d11b030d70a3`，见 [设计合同](dependency-routing-189-design.md)。
- 已合入集成 tip：`aeef15c66503f73e3d4145ce775b41c63e04b1b7`，merge 为 `7b4c51d4f9827aa4d42ac4eba96e5a5e52fc4711`；仅吸收主控交接/验收文档修改。
- 最终生产源码 SHA：`45aaae55c3c2781127506f034311ad50aaf55dc4`。最终 45 项在提交前运行，所测 Python 内容与该提交一致；本记录另作纯文档提交。
- 保留当前模型选择，未请求切换；不猜测具体型号。未修改 root、未读 `tests/test.md`、未 push 或写 GitHub。

## 交付合同及 owner

可信 faithful JSON 增加可选 `routing_policy_version: "objective-dependency-routing-v1"`，内部配置名为
`SHOWCASE_STAR_ROUTING_POLICY_VERSION`。缺席不输出新键，默认关闭；只在新 Run 创建前冻结
`routing_policy = {name: "objective-dependency-routing", version: 1}`。公开 CAS 不得改写该冻结项。
要求 adaptive_solving/problem_spec/auto_problem_spec/star_routing/final_generation/final_solution_review 启用及 strict 模式，拒绝未知版本、并发路由；population/配对组件不隐式采用。

Pipeline 恢复只还原这个新增配置键：A 旧无 adaptive、B 旧 adaptive185、C 新 policy 分别恢复原策略。
其他 config hash 仍严格比较，不回填旧 policy，不改变根预算、deadline、未知请求预留或调用 lineage。
新增 `dependency_routing.py` 复用当前 ProblemSpec 的 root.prerequisite_ids/aux.dependencies；不是按根数量判断。
控制、未知调用/工具守卫优先；已授权重试只能继续原 owner，新规划资格不能借重试绕过 unknown。
当前 spec 的依赖在探索入口/恢复/审查前复评；SOLVED 自评不能短路，已有完成响应不重派。

Planner 通过原 Plan/WorkUnit 校验建立顺序，Reasoner/Step Verifier 沿原执行和审查链推进。
finding 只作 `unverified_exploration` 参考；来源用既有完成调用的 call_id/request_revision/specification_version/round，无法确认则 source.status=unknown。
不迁移旧 finding，不新建审计系统，不写入 valid_sources 或已证账本。
首版唯一新增公开 reason 为既有 `adaptive_planning_required` 事件的 `objective_dependencies`；沿既有事件身份投影，不含自由题干或候选内容。

本票实际生产文件共 12 个（预计 15 文件不是配额）：

- 配置/冻结/恢复：`showcase/faithful_service_config.py`、`showcase/star_product_runtime.py`、`showcase/star_product_pipeline.py`、`showcase/solver_harness/harness.py`。
- 资格/推进/unknown：`showcase/solver_harness/dependency_routing.py`、`showcase/solver_harness/adaptive_solving.py`、`showcase/solver_harness/controller.py`、`showcase/star_product_recovery.py`。
- 材料/事件：`showcase/solver_harness/explore.py`、`showcase/solver_harness/planning.py`、`showcase/solver_harness/step.py`、`showcase/star_product_events.py`。
- 公共接缝测试：`tests/test_dependency_routing_job_190.py`（4 项）、`tests/test_dependency_routing_recovery_190.py`（6 项）、`tests/test_dependency_routing_config_190.py`（4 项）。复用 `StarJobFixture` 及自动 Intake/S03 fixture，只替代 provider HTTP 等外部边界。

#191 在此合同通过后统一登记自然题、真实 Intake/provider 运行与数学核对；#192 拥有首次 Explore 容量、已知截断和语义轮次切片，cap 数值未定，旧样本 token 未知，未编造数值。
后续容量策略采用独立新版本，仅冻结新 Run；不得迁移本票已建 Run。#193 消费真实事件/reason；共享文件变更由主控顺序分配 owner。

## 验收及可复跑命令

工作目录均为 `D:/project/mathagent-190`；日志与 JSON 都在被忽略的 `artifacts/issue190/`，没有提交 raw。
所有 Python 共用以下环境；无需安装或同步依赖：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
```

最终源码聚焦及受影响自适应/审查/请求回归：**45/45 通过，零跳过，30.461 秒**。

```powershell
uv run --no-sync python scripts/run_unittest_report.py --expect-count 45 --summary-json artifacts/issue190/focus-adaptive-final.json --diagnostics artifacts/issue190/focus-adaptive-final.log tests.test_dependency_routing_job_190 tests.test_dependency_routing_recovery_190 tests.test_dependency_routing_config_190 tests.test_adaptive_solving_185 tests.test_adaptive_solving_job_185 tests.test_star_product_final_binding tests.test_request_attempts
```

此前源码 `24dc22c5a88753bd3b895bbdaf94058dd4ac548f` 上，恢复 **29/29**（75.279 秒）及配置/规格/Intake **48/48**（2.620 秒）通过；最后 unknown 修复只作用于新增 frozen policy，最终 45 项再次覆盖其 A/B/C 恢复。
这两组是较早快照的回归证据，没有声称在最终 SHA 上全部重跑。恢复运行已结束，无在途进程或需接管的监控。

```powershell
uv run --no-sync python scripts/run_unittest_report.py --expect-count 29 --summary-json artifacts/issue190/regression-recovery.json --diagnostics artifacts/issue190/regression-recovery.log tests.test_star_product_recovery
uv run --no-sync python scripts/run_unittest_report.py --expect-count 48 --summary-json artifacts/issue190/regression-config-spec-intake.json --diagnostics artifacts/issue190/regression-config-spec-intake.log tests.test_faithful_service_config tests.test_faithful_s03_specification tests.test_faithful_auto_intake tests.test_faithful_auto_intake_budget
uv run --no-sync ruff check showcase/solver_harness/dependency_routing.py showcase/solver_harness/adaptive_solving.py showcase/solver_harness/controller.py showcase/solver_harness/explore.py showcase/solver_harness/planning.py showcase/solver_harness/step.py showcase/solver_harness/harness.py showcase/star_product_recovery.py showcase/star_product_pipeline.py showcase/star_product_runtime.py showcase/star_product_events.py showcase/faithful_service_config.py tests/test_dependency_routing_job_190.py tests/test_dependency_routing_config_190.py tests/test_dependency_routing_recovery_190.py
git diff --check
```

Ruff 与 diff 检查通过。累计覆盖 122 个不同测试方法（45+29+48），不是最终源码上运行了 122 项。

| 公共行为 / 红例 | 修复与绿证据 |
| --- | --- |
| `red-01`：期望 Planner，实际 Intake→Explore→whole review（1 failure） | `green-01d`、最终 Job：Intake→Planner→Reasoner→StepVerifier→Reasoner→StepVerifier→final_generator→whole_solution_verifier，8 次实际受控 HTTP，输出 2、公开 reason、刷新零调用 |
| `red-02`：未知工具恢复仍改 revision（3 项中 1 failure） | `green-02`；最终恢复不转路由/不审查 |
| `red-03`：实际 HTTP 材料缺 provenance（1 error，KeyError） | `green-03`；Planner 和 Reasoner 同收未验证材料及原调用来源 |
| `red-05`：冻结策略可被公开 CAS 修改（4 项中 1 failure） | `green-05`；最终 4 项配置检查通过 |
| `red-07`：未知工具后的公开 solve 仍派发 Planner（1 failure） | `green-07`；外层推进守卫；`focus-final` 又发现过度阻挡显式重试，最终 45 项完整通过 |
| SOLVED/当前 spec/无依赖双根/旧身份 | 最终 14 项新测试覆盖；双根 Intake→Explore→whole review 共 3 次；A/B/C 各恢复原 hash 集合、预算 limits/deadline/未知预留 |

所有阶段文件保留。`green-01/01b/01c` 的早期失败涉及 fixture 缺少合法 Plan 字段/step_id；
`compatibility-01/02` 的候选不足以履行 proof，后改为完整论证，未弱化断言。
`red-06` 是 fixture 缺 RunBudget 表，`red-06b` 补齐公共账本后已通过，不能算生产红例。
`red-04`/`regression-01` 中错误进入 Planner 后触发缺预算表，提示了恢复短路回归，但不是独立完备的红断言；
最终公共恢复用例明确检查一次修正及派发次数。重复中间绿证据不累加成新覆盖数。

## 未验证与退出边界

未运行 provider/paid、自然数学验收、浏览器、整仓门禁；未宣称等待时间、准确率或数学收益。
真实自然验收交 #191；Explore cap/截断语义交 #192；UI/组合验收交 #193。
主控用 fresh merger 集成，独立双轴审阅和阶段门禁仍待执行。
