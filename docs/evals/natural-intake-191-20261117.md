# #191 受控验收与 HANDOFF

2026-11-17。状态：代码/受控聚焦完成；#191 **保持 open**，真实 S/D **NOT_RUN**，不关闭父票、不宣称数学效果或等待改善。

## 源码与文件所有权

- 唯一 worktree：`D:/project/mathagent-191`，branch `feat/natural-intake-191`，初始干净基点 `975560a9bd9c546d7e7b1ae7e8133071c3a41cf4`。
- 先行合同提交 `4cc7c90`；代码/测试提交 `77314530cadcb5263d5c37a96432ddb639e49394`。
- 在本 worktree 合入集成分支最新 tip `3d1765a2092624d2a897007ef6b33a0928794d3f`，merge `bcc39690723b7e9fae8a4b8dc0a0c2714c457733`，无冲突，仅吸收主控交接文档。未写 root 工作树、未更新 PR/GitHub。fresh merger 仍由主控安排。
- 生产仅改 `showcase/solver_harness/intern_instructions.py` 的 Intake 段 7 行：自然“使用前目标结果”映射到依赖方 root.prerequisite_ids / aux.dependencies，仅用已声明 ID；不因难度、长度、解释或完整性制造依赖。
- 独立 `tests/test_natural_intake_job_191.py` 两项公共测试；复用现有 StarJobFixture，不改全局 fixture。另有 [任务合同](../engineering/natural-intake-191-contract.md) 和本记录。
- Planner/Reasoner 指令、#190 路由/恢复/来源/unknown/Run/预算/config/adapter 均未修改。README、用户合同、tests/test.md 未读写。继承当前模型，不覆盖，不猜测具体型号。

## 精确红绿与边界

所有报告/日志位于该 worktree 的 ignored `artifacts/issue191/`。以下是实际结果，不把重跑累计为额外覆盖。

| 记录 | 精确结果 / 可证明内容 |
| --- | --- |
| red-guidance（首次脚手架） | 1 方法，8 failure/0 error：7 个指引子断言缺失，加一个对规范化空依赖数组的错误比较；后者是测试错误，已改按实际语义检查。原日志保留，非8个产品缺陷。 |
| red-guidance-clean | 1 方法，1 failure/0 error/0 skip：真实 Job 直解成功，但实际 provider HTTP system 消息缺字段映射及反向保护；稳定必要红例。 |
| green-guidance | 同一方法1/1通过，0 failure/error/skip；生产仅追加7行。 |
| challenge-01 | 1 方法，0 failure/1 error：真实依赖 Challenge链已完成，但错误读取 fixture.report 返回形状；修正测试读取，不改产品。不是生产红例。 |
| green-public | 新增2方法，2/2通过，0 skip；独立无依赖双根3次HTTP；aux前置→root后继及具体CHALLENGE链10次HTTP。 |
| focus-public-final | **12/12通过，0 failure/error/skip，22.423秒**：新增2项 + #190公共Job4项 + adaptive185公共Job6项。 |
| regression-role-final | **14/14通过，0 failure/error/skip，0.394秒**：Planner checkpoint5项 + Reasoner checkpoint9项。 |
| regression-intake-final | **9/9通过，0 failure/error/skip，0.827秒**：自动Intake聚焦回归。 |

最终代码共覆盖 **35个不同测试方法**（12+14+9）；其中公共 Job 组12项。新功能红绿为1项必要指引红例→绿，不把已有门控反例或测试脚手架错误包装为生产修复。

新增依赖用例：只从公开 POST 的 message 进入；受控 HTTP 返回规格和计划，实际顺序为 Intake→Planner→Reasoner→Verifier(CHALLENGE)→Reasoner→Verifier(ACCEPT)→后继Reasoner→Verifier(ACCEPT)→final_generator→whole_solution_verifier。同一Job/Run、spec版本、前置目标ID及Planner依赖可回溯；第二次Reasoner收到原异议，后继只在前置通过后派发并收到accepted_results；公开事件含真实路由和CHALLENGE，最终whole_review=accepted、binding=same_artifact，GET不增HTTP。

该补例弥补 #190 依赖链只含 ACCEPT 的观察空位；既有 `test_star_product_challenge.py::test_three_rounds_keep_latest_history_and_accept_only_after_verifier` 可作通用异议历史证据，但未以它替代本次依赖后继门控。无额外生产状态机修改。受控规格/响应**不证明自然模型识别了依赖**。

## 可复跑命令

工作目录为本 worktree；全部Python共享环境，不安装/同步依赖：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run --no-sync python scripts/run_unittest_report.py --expect-count 1 --summary-json artifacts/issue191/red-guidance-clean.json --diagnostics artifacts/issue191/red-guidance-clean.log tests.test_natural_intake_job_191.NaturalIntakeJobTest.test_intake_maps_result_dependencies_without_planning_independent_output_requirements
uv run --no-sync python scripts/run_unittest_report.py --expect-count 12 --summary-json artifacts/issue191/focus-public-final.json --diagnostics artifacts/issue191/focus-public-final.log tests.test_natural_intake_job_191 tests.test_dependency_routing_job_190 tests.test_adaptive_solving_job_185
uv run --no-sync python scripts/run_unittest_report.py --expect-count 14 --summary-json artifacts/issue191/regression-role-final.json --diagnostics artifacts/issue191/regression-role-final.log tests.test_solver_harness_planner_checkpoint tests.test_solver_harness_reasoner_checkpoint
uv run --no-sync python scripts/run_unittest_report.py --expect-count 9 --summary-json artifacts/issue191/regression-intake-final.json --diagnostics artifacts/issue191/regression-intake-final.log tests.test_faithful_auto_intake
uv run --no-sync ruff check showcase/solver_harness/intern_instructions.py tests/test_natural_intake_job_191.py
git diff --check
```

红命令是历史重现指针：必须使用指令修改前代码及本票测试；当前源码重跑应绿，禁止覆盖已保存红日志。Ruff与diff检查通过。上述成功检查在7731453提交前执行，所测Python内容与该提交一致；之后merge仅主控文档变化，无需为文档重跑同组检查。

## 自然运行准备（非执行）

已从候选前34行只提取两条引用题干，写入无BOM、无换行UTF-8的 `artifacts/issue191/natural-input/{S,D}.txt`。本地 `natural-input-manifest.json` 只含题号、文件、hash、NOT_RUN及主控另行登记标记，不存答案。题干摘要：

| 题号 | SHA256 |
| --- | --- |
| S | 072811fb42fd9742da652b480d371130d058adbe1ad7b765ed0bd669f3a766d8 |
| D | f63741b9fc73f0f92992bcba7c7ffe043e71d8b21c5b66b90b1cc2c7f0374e03 |

`artifacts/issue191/natural-run-commands.md` 是准备好的运行单：复用现有showcase_cli.py的session create/job submit/status/events/report，逐题独立session/Job，message仅从对应txt读取并先核对hash。没有新建通用DTO/运行器、服务或监控，不包含凭证、答案或prompt raw。真实服务/admission、认证及记录由主控原流程办理；不能复制受控fixture的容量/响应或full_gaps patch。

主控集成交接已记 `artifacts/issue189/preregistration/natural-cases-v1.json` 为 registered_not_run；该主控登记是权威，本地输入物料不替代它。主控核对摘要、冻结191/192集成源码和配置后唯一执行并独立人工数学核对。D未识别依赖为not_triggered，不补Spec/计划；失败、耗尽和unknown另记，不自动重复派发，不为凑异议重跑。所有角色/验证器只能看真实运行题干和合法运行材料，不能读参考答案；#193复用实际结果。

## 自查与待接管

规范轴自查：写范围、中文提交、先合同后实现、必要红绿、ignored证据与数据隔离均符合本次授权；无无关重构或新增依赖。规格轴自查：真实outbound指引可见、无依赖双根仍直解、已有依赖链与具体异议作用有公共证据；自然识别/数学效果尚无真实证据。此为实现者自查，**不冒称独立双轴审查**。

未运行：真实provider/live、S/D、服务、浏览器、整仓/发布门禁；主控尚需独立审查/集成与阶段门禁。不得关闭#191。无在途测试或监控/定时任务。临时题干/运行单及日志均只留ignored目录，由主控复制时核对哈希，勿git add。

HANDOFF：主控fresh merger合入本分支后释放intern_instructions.py给#192；主控独占真正prereg、真实运行、长期监控和数学核对。无需催促#192，不改变其他owner文件。继续同一模型选择，具体型号或跨session继承无法核实，不推测。
