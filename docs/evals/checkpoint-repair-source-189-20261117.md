# #189 checkpoint repair 来源修复（2026-11-17）

## 合并前窄补充（2026-11-17，适用本记录最新提交）

下文首次提交状态保留为历史快照；本节覆盖其中“step.py留后续风险”和“registry缺口”。

公共直接Reasoner用例：自然输入、Intake依赖、Planner后，第一轮直接Reasoner
FINAL空next_action导致协议失败，repair返回合法YIELD checkpoint；StepVerifier
ACCEPT+Answer后下一轮实际派发并完成，再完成后继步骤、整题审查和只读GET。
不patch轮次上限，生产MAX_CHECKPOINT_ROUNDS=2原样保留。

`direct-red.json/log`：原step.py公共红灯，testsRun=1、failures=1、errors=0、skip=0，
5次受控HTTP后route_requires_reevaluation；图review_record_mismatch，checkpoint引用
原protocol_failed调用，而repair确为completed。明确确认同caller来源缺陷。
step.py仅将checkpoint来源改用既有completed_call_id，从最新持久calls解析实际成功来源；
没有泛化重构或失败调用状态覆盖。challenge.py沿用首次修复。

直接用例复用现有ToolRegistry.register_polynomial_check与真实PolynomialChecker，
repair checkpoint中只加入一次有限候选代回请求：x-4=0，candidate=4。
验证实际回执executed、run_id、tool、candidate_status=pass、residual=0及持久receipt_id
匹配；Run工具计账与公开tool_results各1，GET零新增HTTP。原easy-verify标签保持原样，
没有expected_output就不声称其已升级verified，更不将候选代回当完整性证明。
真实socket.connect仍禁止出站，0真实provider，不Docker、不新服务。此为直接repair
路径的工具回执见证，不声称复现原S的工具数学语义。

`direct-green.json/log`最初已完成身份/续算/交付，但错误预期label=verified导致失败；
该断言按现有合同改为easy-verify，保留失败日志。最终无schema/守卫/容量改动。

合并前再次 `git merge dependency-routing-189` 返回Already up to date，tip仍c4493ba。
新增测试文件去除末尾多余空白，ruff排序及格式化仅该独立测试。

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run --no-sync python scripts/run_unittest_report.py --expect-count 3 --summary-json artifacts/checkpoint-189/supplement-focused.json --diagnostics artifacts/checkpoint-189/supplement-focused.log tests.test_checkpoint_repair_source_189
uv run --no-sync python scripts/run_unittest_report.py --expect-count 1 --summary-json artifacts/checkpoint-189/step-context.json --diagnostics artifacts/checkpoint-189/step-context.log tests.test_reasoner_repair_context_127.ReasonerRepairContextTest.test_step_and_challenge_repair_include_exact_failed_reply_and_error
uv run --no-sync ruff check tests/test_checkpoint_repair_source_189.py showcase/solver_harness/step.py showcase/solver_harness/challenge.py
uv run --no-sync ruff format --check tests/test_checkpoint_repair_source_189.py
```

最终补充：3/3（12.475秒）+1/1（8.421秒），去重4项，0failure/error/skip；ruff与diff
格式检查通过。跨首次与补充总去重10项，未重复运行无影响的continue/unknown组。
生产文件只修改challenge.py和step.py来源解析各一处。新增ignored证据direct-red、
direct-green、supplement-focused、step-context各JSON/log均保留在原worktree。
未root写入、未自然运行、未push，未改模型选择；最终SHA由交接与git记录提供。

## 范围与源码（首次提交历史快照）

基点及集成 tip：`c4493ba3b6956eb8667dde3f67d98336dd69ff69`，分支
`fix/checkpoint-repair-source-189`，独立目录 `D:/project/mathagent-189-checkpoint-fix`。
开始 HEAD 一致且 clean；完成前 `git merge dependency-routing-189` 返回 Already up to date。
本记录随唯一逻辑修复提交；最终交付 SHA 由提交记录及交接提供。

真实生产路径是 `showcase/solver_harness/challenge.py`，没有 controller 子目录。
checkpoint 创建时从最新持久 calls 使用现有 completed_call_id 解析实际 repair/retry
谱系，保留原失败调用。仅该文件生产行为变化，无 schema、图守卫、容量、预算、依赖、
Intake、工具或 official 改动，无旧 Run/旧 checkpoint 回填。

已全文读取外部诊断 `C:/Users/CQX/.codex/tmp/189-live03-S-diagnosis-20261117.md`。
原 S 冻结316eaba、failed；未打开原库、未执行原回放或真实 Job，0真实 provider。
当前模型选择未修改；具体模型及跨会话继承无法独立确认，不猜测。

## 公共红绿与限制

独立 TemporaryDirectory SQLite，通过真实 public Job、受控 provider HTTP、真实业务校验、
持久调用审计及图导入；socket.connect 拒绝真实连接。原创2+2最小数据不包含原 prompt/raw。
本 fixture 无工具请求（0工具），没有覆盖真实 registry 工具回执链；这部分仍是本任务的
验收缺口，不将无工具成功冒充工具链已验证。未启动Docker或服务。

自然输入 → Intake依赖 → 两步Planner → YIELD → CHALLENGE → FINAL空next_action →
repair YIELD → ACCEPT+Answer。原失败调用保持protocol_failed，repair保持completed。

- `red3`：首次有效公共红灯，1测试失败：7请求、来源仍是原失败调用，图
  review_record_mismatch，终止route_requires_reevaluation。
- `red-final`：最终2测试在原生产文件上均同样红。summary中failures=2/errors=0；
  临时恢复原文件的PowerShell finally使组合shell退出0，不能把该shell退出码当测试退出码。
- `green3`：2测试通过。自然上限用例证明失配消除、实际来源匹配，终止改为
  reasoner_checkpoint_round_limit；当前生产MAX_CHECKPOINT_ROUNDS=2，此链路已用满两轮。
- 续算用例仅在测试内patch上限为3，确认下一Reasoner携带repair checkpoint为parent
  实际派发，再以合法FINAL完成第一步、第二步及whole review，13次受控HTTP；
  Job/Run/report/evidence GET均200且零增请求。生产上限没有修改。

因此“原自然配置该链路修复后继续第三轮并成功”的前提不成立；不得宣称自然S已成功。
测试内第三轮见证单独标记，不能算生产容量或自然数学能力证据。

首次red/red2为fixture调试失败（缺method_id、非法evidence_category），保留但不计bug红灯。
green/green2暴露两轮上限，不计通过。普通step.py发现同类checkpoint来源写法；
未形成独立公共红绿，本次不纳入生产修改，留后续修复风险。
原模型把FINAL修成YIELD的动作遵循偏差、解释拆依赖、工具参数偏差另见外部诊断，
本次不修改prompt或以身份修复宣称解决这些偏差。

## 命令与最终聚焦结果

每次Python设置共享环境，不创建venv，不同步依赖：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run --no-sync python scripts/run_unittest_report.py --expect-count 2 --summary-json artifacts/checkpoint-189/red-final.json --diagnostics artifacts/checkpoint-189/red-final.log tests.test_checkpoint_repair_source_189
# red-final在原基点challenge.py上运行，随后恢复修复文件
uv run --no-sync python scripts/run_unittest_report.py --expect-count 9 --summary-json artifacts/checkpoint-189/focused.json --diagnostics artifacts/checkpoint-189/focused.log tests.test_checkpoint_repair_source_189 tests.test_reasoner_repair_context_127 tests.test_star_product_continue_identity.StarContinueIdentityTest tests.test_star_job_unknown_98.PublicJobUnknownTest.test_stream_without_done_stops_public_job_and_reserves_known_usage
```

最终聚焦：testsRun=9、failures=0、errors=0、skipped=0、26.410秒。
去重9项（新增2、repair context 3、continue identity 3、unknown 1）；重复红绿不累加。
覆盖unknown不重发、显式继续身份/恢复等已有合同。没有运行整仓、最终门禁或provider-live。
审阅生产diff仅来源解析；图守卫仍严格拒绝失败来源。git diff --check通过。

ignored证据保留在本工作树 `artifacts/checkpoint-189/`：
red、red2、red3、red-final、green、green2、green3、focused，各有 `.json` 和 `.log`。
均为受控测试诊断，无真实运行raw。工作树及证据保留给fresh merger，不push/GitHub/合main。
主控README、合同及tests/test.md未读改。下一会话继续当前模型选择，不覆盖设置。
