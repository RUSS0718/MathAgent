# #189 最终门禁01四组修复验收（2026-11-17）

范围：8个唯一方法、原10条failure/error（checkpoint 5 error；restart 1方法3 subtest failure；并发2方法各1 failure）。仅离线工程验证，不是数学能力或全仓门禁结论。

基点 d21e9daeac0cc0d78033bfab422d01de959a99e2 / tree 641eacc628329f4295aa6f581b90776e0779d05c。修复后合并 integration a59450a2c650f760f73e0f4017e2af7afb6cea43；测试源码 fc461b574d54f14cc9a306072338bec96ad9bc5e / tree 7b0f824e58fa9bf8913c28775f798116b95b4098。

原因与最小修改：
- 未启用 stream_recovery 时 dispatch 不创建 calls；step/challenge 按同一开关决定是否解析审计 lineage，审计启用仍严格读取 calls，未使用默认空字典掩盖契约。已有 checkpoint 与 repair 来源回归覆盖两个模式。
- discover 将模块加载成顶层名字，子进程 cwd 无此模块；固定 tests.test_dependency_routing_review 包入口，覆盖 discover 与 package 两种父进程入口。
- native 夹具在 HTTP 前 transport_selected 阻塞，等待冻结可能依赖另一路继续调度；冻结后新派发也应被预算拒绝。改为两路均到达 HTTP 后暂停 completed 审计，验证冻结后真实完成记录可持久化，不修改生产锁、预算或 unknown 栅栏。YIELD 接续仍由原独立测试覆盖。
- projection 全局补丁可能暂停持有 store 锁的后台 source_job 投影；仅暂停目标 reader，继续验证真实写入在 reader 释放前提交。生产 snapshot 已在 projection 前 commit，无需放宽锁。

证据均位于独立 worktree artifacts/gate-fixes-189/，不覆盖原 gate。原报告位于 root artifacts/final-gates/dependency-routing-189-01/repository-check/。

红：red-package.log（11次执行，9个checkpoint方法+2并发，5 error）；red-discover.log（16次执行，3个subtest失败）；red-races.log（两并发方法各5次，projection 1失败）；red-native-repeat.log（native 6次，1失败）。有限复现不声称每次必现。green-races-initial.log、green-races-repeat.log保留被否决调度实验失败，不能算通过。

绿：green-checkpoint.log 9/9；green-discover.log 16/16；green-races-settlement.log 两并发方法各5次、10/10；green-eight.json 指定8方法8/8、0skip；regression.json 25/25、0skip；postmerge.json 为合并后同25项复验。重叠执行不累加为唯一覆盖项。

命令环境：PowerShell先设置 `$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'`；所有测试使用 `uv run --no-sync python`。

红命令：`-m unittest tests.test_solver_harness_reasoner_checkpoint tests.test_faithful_population_native_budget.NativePopulationBudgetTest.test_inflight_transport_audit_can_settle_after_another_route_freezes tests.test_job_projection_read_lock_127.JobProjectionReadLockTest.test_projecting_a_snapshot_does_not_block_another_job_progress`；discover：`-m unittest discover -s tests -p test_dependency_routing_review.py`。并发有限重复通过 unittest.TestSuite 重复加载指定名字，5轮和6轮分别记录。

绿聚焦：`scripts/run_unittest_report.py --expect-count 8` 后接原8方法；完整选择器见 green-eight.log。相关回归：`scripts/run_unittest_report.py --expect-count 25 --summary-json artifacts/gate-fixes-189/postmerge.json --diagnostics artifacts/gate-fixes-189/postmerge.log tests.test_checkpoint_repair_source_189 tests.test_solver_harness_reasoner_checkpoint tests.test_faithful_population_native_budget tests.test_job_projection_read_lock_127 tests.test_population_controller_wait tests.test_population_transport_identity`。

未运行全仓、服务、真实模型；未push。baseline、依赖锁及默认预算无差异；root四项用户dirt原样保留，禁读文件未访问。沿用当前模型选择，无法核实具体型号，未设置或猜测。独立worktree保留供主控merger。
