# #191 自然终态、受控验收与退出映射

2026-11-17。当前：live04 S2/D 自然验收通过；CHALLENGE 仅受控覆盖。建议主控完成 #191 关票审核，GitHub 本次未操作；#189 整体未退出。

## 本票自然退出与证据入口

自然源码 `aac4cf6498cefb9b8761976f479b90e52303537f`，分支 dependency-routing-189。依据独立 `C:/Users/CQX/.codex/tmp/189-live04-{S2,D}-assessment-20261117.md`，D 报告后半部补证解除第一轮 spec/WorkUnit/来源消费缺口；root `artifacts/issue189/live04/independent-D/manifest.json` 对应主控已校验复制的15文件，manifest SHA256 `c77800d41698009f592c6b718d4cab93cd1ec9f39e9603e69fbe9ff7529b3582` 复用报告，非本次重算。

S2/D 自然正向证据通过，建议主控审核 #191 退出；CHALLENGE 只沿 I191-3 允许的既有受控公共证据，D 实际0次，不把 YIELD 当异议。不证明自然异议、恢复全路径或数学能力提升。本次不访问库/raw/参考解，不新运行。跨票状态与条款解释集中见[#189 当前退出映射](dependency-routing-189-20261117.md)，本页保存本票自然因果证据与测量。

## live04 自然证据与测量

S2 Job/Run `run_27f2b6b3af04031e3ba41094ed501222`；D Job/Run `run_2242f342feea32d8922e2f65f501b078`。均显式 Run 身份而非 JobID fallback；有效配置快照 SHA256 `d1956b3dc50e6bb8c76f4edf176cde9ae6ed79a841df490312e1e672f2e17843`。

D 实际 spec1/plan1：solve_a→enumerate_solutions→prove_completeness；WorkUnits S1→S2→S3。S1/1、S1/2、S2/1、S2/2、S3/1 五轮全 ACCEPT，前两单元分别 YIELD→FINAL；S1 第2轮 request1498、S2 首轮2021及第2轮2946、S3 首轮3736 中的来源/检查点消费已由持久请求安全投影核实。S1/S2 完成义务分别在 revision2018/3733，review event2019/3734 后派发下一单元；S3 完整性4770、review4771 后进入 final_generator request4773 及 whole review5017。不同 revision/事件序号不直接混用。WorkUnit schema 无独立 owner 字段，不补造；S2 来源 llm_reviewed 不升级 verified。三步进入最终 step_proofs，EXACT artifact SHA256 `b230e1859d8069aa8ca1d1d5befff6355913b174a8ae4bd6ac4c9446c47422cc`。

S2 spec root1/existence，Intake 原响应 prerequisite_ids=[]、auxiliary_goals=[]；规范化 spec 省略空字段，不能说源对象保存了空数组。自然直解一次 Explore→whole review，artifact SHA256 `b8478134ca41533393dbf434adc69d580346a7ed2c7ecbf7cdd67a7caf0926fc`。人工数学核对正确结论沿独立报告，不复制 raw 或参考解。

| 样本 | 角色实际 HTTP 次数 / 物理秒数 | 总计与 Run wall time |
| --- | --- | --- |
| S2 | Intake1/4.050；Explore1/2.815；whole review1/5.669 | 3 HTTP，物理12.534s；Run13.01368260383606s；0工具 |
| D | Intake1/14.052；Planner1/10.779；Reasoner5/301.601；StepVerifier5/191.278；final_generator1/59.046；whole review1/37.970 | 14 HTTP，物理614.726s；Run638.6060099601746s；4工具/2.610s |

根上限均48模型/48HTTP/8工具、2097152 token/3600s，未耗尽。S2 charged89558/reserved87704，provider known total1854/completion124 只覆盖部分请求；用量未知2项。D charged=reserved1039861（本地估算），14项 provider usage 均缺失。两者 unresolved_attempts=0；用量未知不等于远端结果未知，不填零或把本地计账当 provider 实耗。solver HTTP 计数不声称覆盖全部 presentation 请求。本样本不证明旧 Run/恢复/unknown 全情形成立。

本次文档映射验证仅 `git diff --check`；不新增运行或重跑测试。以下实现、命令与准备段均为 live04 前的历史快照，历史 NOT_RUN/待接管语句不再代表当前状态；原红例、失败和未执行检查保持原判。

## 历史：源码与文件所有权

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
