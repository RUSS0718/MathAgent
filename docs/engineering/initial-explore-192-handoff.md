# #192 HANDOFF：首次探索容量与安全交接

2026-11-17，Asia/Shanghai。交付给主控 fresh merger，未 push、未写 GitHub。
当前模型选择保持不变；不能独立确认具体型号或跨 session 继承结果。

## 集成身份与可消费合同

- worktree：D:/project/mathagent-192；branch：feat/initial-explore-192。
- 核对初始 HEAD：adc01500a6bdfae8c76bdcd8ed6f0871663de6b0；初始工作树干净。
- 实现：7a87eb2；合 integration 96de94f1e1963af29787548d7e2adc0489de84bc 为 c4b6e30。
- 最终生产及测试源码：b2b1a50（按有效cap估计adaptive准入）；21项最终检查在该提交运行。
- 最终复核 integration 仍为96de94f，merge返回Already up to date；本交接另作纯文档提交。
- [冻结入口与原因合同](initial-explore-192-contract.md)。2048始终是工程假设，非token测量分位数。

可信JSON新增 initial_explore_policy_version="initial-explore-v1-2048"，服务键
SHOWCASE_STAR_INITIAL_EXPLORE_POLICY_VERSION，Pipeline参数同名小写。
Harness config同JSON键；新Run state.initial_explore_policy={version:"initial-explore-v1-2048"}。
依赖既有objective-dependency-routing-v1及其strict/feature前提，未启用时新键缺席。
旧无policy、旧190 Run不回填；Pipeline仅重建新增冻结键，其他config hash严格。

首次仅1语义轮次；单请求max_output_tokens=2048、transport_override="nonstream"。
工具续接和正常有限协议repair从原请求复制并继承cap；具体whole-review数学异议
仍最多一次修正，使用基础cap/transport。已知length不repair，转PLAN；已知无候选、
NEED_PLAN/PARTIALLY_SOLVED/UNKNOWN评估及首次协议耗尽转PLAN。远端unknown沿原待审，
无自动重发/Planner/fallback，显式retry保持原谱系及未知预留。

公开生产者：既有adaptive_planning_required事件reason白名单新增
initial_explore_output_limit、initial_explore_incomplete。仅首轮标记对应原因；
修正失败沿原complete_candidate_unavailable等合同。#193负责普通投影和前端文案，
本票未改其文件或新建DTO。事件理由不表示Planner已实际调用。

## 实际生产界面与必要修改

13个生产文件：adapters.py、faithful_service_config.py、star_product_runtime.py、
star_product_pipeline.py、star_product_events.py、stream_preference.py，以及solver_harness下
initial_explore.py、explore.py、adaptive_solving.py、adaptive_resources.py、calls.py、
harness.py、intern_port.py。没有按候选15文件铺开；controller/recovery无需再改。
没有修改intern_instructions.py，#191 Intake七行保持提交基点内容。

adapter complete/stream_complete增加可选max_output_tokens，缺省原行为，不修改实例字段。
port的流/非流、serialized估计、transport匹配/fingerprint都用请求有效值。
原ModelCallBudget.before_attempt从实际Attempt.max_tokens预留，账本无需改写；
adaptive_resources当前工作及其repair余量使用有效cap，closing review仍保留基础cap。
受控7000根预算实例证明2048实际预留可通过而8192不可；另一公开Job以基础32768、
原理独立的220000测试额度见证adaptive估计正确，生产预算基值完全未改。

transport复用单请求显式非流，保留Run原policy/profile_set身份锁；审查和其他角色
仍按原stream profile。非流决策标documented、真实payload fingerprint和effective_max_tokens，
不带旧profile验证指纹。stream覆盖仅在独立匹配2048 profile时通过；旧8192 profile
在受控HTTP零派发拒绝。未添加provider-live profile，未宣称2048线上已验证。

length/repair失败只解析完整JSON作为unverified材料，不修补残缺结构；取实际最新请求
revision来源，unknown来源不伪造。已知length审计后崩溃恢复通过；calls保留已有调用ID
于CallInterrupted，便于owner识别而不重发。旧190 finding来源选择保持原分支。

## 证据、命令和准确计数

全部运行在本worktree，命令前设置：

```powershell
$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'
uv run --no-sync python scripts/run_unittest_report.py --expect-count 21 --summary-json artifacts/issue192/focus-final/summary.json --diagnostics artifacts/issue192/focus-final/diagnostics.log tests.test_initial_explore_192 tests.test_initial_explore_config_192 tests.test_initial_explore_transport_192
```

源码b2b1a50：21项，29.542秒，0failure/error/skip。覆盖13 Job/恢复案例、4配置案例、
4transport/ledger案例；含子用例的参数组合不另加testsRun计数。
artifacts均为本worktree ignored产物，不提交raw；fresh merger应读取该目录或主控归档。

回归A：7a87eb2相同生产内容、合并前运行；--expect-count 27，选择
 tests.test_dependency_routing_job_190 tests.test_dependency_routing_config_190
 tests.test_dependency_routing_recovery_190 tests.test_adaptive_solving_job_185
 tests.test_adaptive_resources_185；证据artifacts/issue192/regression-a/{summary.json,diagnostics.log}。
27项/18.702秒，0failure/error/skip。

回归B：7a87eb2；--expect-count 47，选择tests.test_stream_preference_124
 tests.test_stream_preference_job_124 tests.test_star_product_explore_compute
 tests.test_faithful_service_config tests.test_baseline_snapshot tests.test_boundary_check_path；
证据artifacts/issue192/regression-b/{summary.json,diagnostics.log}。
47项/14.390秒，0failure/error，1skip：
StarFullReferenceExploreComputeTest.test_reference_explore_executes_own_isolated_computation
需独立验证本地Docker image ID；未启动Docker补测。

b2b1a50前最后资源切片：resource-final，--expect-count 8，选择新增准入Job案例与
 tests.test_adaptive_resources_185；8项/1.318秒，0failure/error/skip。
最终21项+回归A/B为95个不同选择器测试；其中7个资源回归在最终切片另复验，
不要将重复8项加作独立覆盖。回归A/B不是最终SHA的整组重跑，最终只变资源估计，
其受影响7项和新增公开边界已重跑；合并integration只带文档。

所有报告入口命令前缀相同，summary-json/diagnostics各用对应目录，未运行全仓门禁。
最终修改文件ruff check通过、git diff --check通过；baseline与boundary8项在回归B通过。

保留失败记录：
- 最初误用--output-dir，CLI退出2，未执行测试（终端记录，尚未生成报告）。
- red-01/02：裸标量候选被既有proof qualification拒绝；夹具错误，不算容量红例。
- red-03：实际cap8192而期望2048，1failure；green-01通过。
- red-04：length被repair且失败，1failure；green-02两项通过。
- red-05：首次仍有完整长解指令，1failure；green-03三项通过。
- red-06：修正length仍repair，1failure；green-06通过。
- red-07：可解析partial worked丢失，1error；green-07通过。
- red-08：非法cap零未拒绝，1failure；transport-02四项通过。
- red-09：初版恢复测试使用普通solve未触发恢复；夹具错误。
- red-10：正确resume后失败缺call_id，1error；green-08已恢复PLAN，但测试继续
  错用solve触发不相关planner协议，1failure；缩为精确恢复边界后green-09通过。
- red-11：adapter在env设置前构造导致profile mismatch；red-12误传不支持api_base参数；
  均为夹具错误。red-13为真实adaptive旧cap错误，但180000对保留基础review估计仍不足，
  green-10仍1failure；固定220000后green-11通过，随后只撤去有效cap读法取得
  同一220000公共测试red-14的1failure，再恢复实现，resource-final通过。

前述报告目录全部保留，不覆盖历史失败。未预写live或数学能力通过。

## 审阅、限制和接续

本轮自查分标准/规格两轴：范围、旧hash、无共享实例修改、账本、known/unknown、
修正边界、来源与公共事件逐项检查；修复了恢复call ID及adaptive估计两个缺口。
当前工具没有可调用fresh subagent能力，未把自审标作独立双轴审阅；主控fresh merger
应独立审查后合并。未创建新chat冒充子代理。

自然S/D/U保持not_run；参考root预登记natural-cases-v1/natural-U-v1，但本轮未读
或执行runner。Boyle准备ignored runner，主控在191/192/193代码集成冻结后唯一运行。
U若首次完成、自然Intake有依赖或其他未触发情况，照合同not_triggered，禁止诱导补证。
2048适用范围、线上非流响应、TTFT/时长与数学正确性仍未实证。

未运行超过约30秒的单组测试，无后台长测试/定时检查需要移交；无重复启动。
未修改root、用户dirt、official、依赖锁、预算基值、前端，未读tests/test.md。
一次源码编辑命令漏设UV_PROJECT_ENVIRONMENT，uv --no-sync只创建本worktree ignored .venv，
未安装/同步依赖；所有测试均使用指定共享env。自动审批拒绝删除该自建目录，理由为
blocked by policy；保留ignored目录，不绕过审批，主控可按自身环境清理。

下一步：主控fresh merger审阅本票及公开合同，合并到integration，再由193消费原因和
真实角色事件；阶段全仓/provider/browser不属于本次执行授权，不冒称完成#189整体。
