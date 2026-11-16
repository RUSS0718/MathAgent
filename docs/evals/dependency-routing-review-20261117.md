# #189 后端审阅限制补证（2026-11-17）

适用：独立 worktree `D:/project/mathagent-189-reviewfix`，分支
`fix/dependency-routing-review`；初始 HEAD
`5582e86419f0b806ab0d8d5ed72337cb242c3cfb`、工作树干净。
原两轴报告为仓库外 `189-backend-review-{standards,spec}-20261117.md`。
本记录只关闭其两项受控证据限制，不是 #189 阶段退出或数学能力结论。

## 实现与实证缺陷

实现提交 `ccae83c`；合入 integration 当时 tip `c7679793a12f80f6984deb31436335429de919da`
后测试源码 SHA 为 `1037ec977049014bf4c2af69858fc71d4735a9cf`。
再次 merge `dependency-routing-189` 返回 Already up to date。
当时该引用为 `576c7c0d296cb0c728bc636f5a9f7b30593e8a09`，已被当前历史包含；
未修改集成工作树、未 push 或写 GitHub。

1. 实际 HTTP body 含 native tools，但显式 nonstream fingerprint 没有包含 tools。
   `red-http`：2 testsRun，1 failure、0 error/skip，独立 hash 实际 body 不相等。
   修复仅把 port 已有 provider_tools 传到 select_transport，并纳入显式非流 payload。
   未创建 adapter/DTO，也未改变 cap、实例配置或 stream profile。
2. 工具续接已知协议失败审计后进程退出，公开 resume 额外派发 Explore repair，
   与不中断续接直接结束该语义尝试的行为不同。`focus-05` 保留该失败：
   3 testsRun，protocol 子场景 1 failure、0 error/skip。实际发送了额外的
   `explore:1:repair-1`，其错误消费后续 Planner 夹具，终态 failed。
   必要修复在 Explore 原修复分支前增加一个窄判断：首次探索中，已知失败且
   请求带真实 tool_receipts 时交回原 known-failure 处理，不额外 repair。
   这是恢复证据暴露的必要 owner 分支修复，除此之外未改恢复框架或 unknown 授权。

## 公共证据映射

新增 `tests/test_dependency_routing_review.py`，复用 StarJobFixture、现有角色回复及
WorkspaceStore 进程故障注入方式；小型 subprocess 入口同文件，不增加通用测试框架。

| 限制 | 实际覆盖与断言 |
| --- | --- |
| native tools 出站身份 | public port.complete 两次实际 HTTP，第二次有 receipt；tools 含 Unicode，独立读取 serialized body 校验字节估计、canonical SHA256、2048 reservation 与 Attempt；实例基础 cap 未改 |
| 公共 server-tool 续接 | POST Job → Registry 实际执行 → Explore 续接；真实 HTTP body 的字节数与 ContextPack persisted payload hash 对齐，public serialized_payload_size 与 transport fingerprint 对齐；Attempt 为8192/2048/2048/8192 |
| 公开跨进程恢复 | 每个子场景独立持久库；进程A在已提交 call_audit 后 os._exit(71)，进程B新 app 经公开 POST Job resume，零私有 recovery flag/直接 resume_solver；length、tool-length、tool-invalid-schema 三场景 |
| 身份和预算 | 同一 Job/Run，旧 Attempt 列表逐项保持，旧 outbound 前缀保持，恢复后只有 Planner/Reasoner/StepVerifier/FinalGenerator/whole review；原 deadline、limits、config_hash 不变，HTTP总数与实发一致，unknown为0 |
| 最新 partial 来源 | Planner 实际请求引用最后的 Explore call；续接场景明确为 tool-1，worked 只含 LATEST_REVIEW_PARTIAL、不取根请求 STALE_REVIEW_PARTIAL；仍为 unverified_exploration |

测试通过公开 port API 观察估计/决策，不直接调用私有 payload 函数。
恢复不引入新请求身份授权，不重发已审计原请求，不重置预算或 deadline。

## 最终命令与计数

所有测试命令均在本 worktree，每次先设
`$env:UV_PROJECT_ENVIRONMENT='D:/project/工程化MathAgent/Challenge-Cup-2026/.venv'`，
使用 `uv run --no-sync python scripts/run_unittest_report.py`，各目录位于 ignored
`artifacts/issue189/reviewfix/`。参数如下（每组同时设置该目录的
`--summary-json .../summary.json --diagnostics .../diagnostics.log`）：

| 目录 | --expect-count / selectors | testsRun / elapsed / failure / error / skip |
| --- | --- | --- |
| initial-final | 13 / tests.test_initial_explore_192.InitialExploreJobTest | 13 / 27.609s / 0 / 0 / 0 |
| merged-final | 11 / tests.test_dependency_routing_review.DependencyRoutingReviewTest tests.test_initial_explore_transport_192 tests.test_initial_explore_config_192 | 11 / 20.385s / 0 / 0 / 0 |
| regression-final | 27 / tests.test_stream_preference_124 tests.test_dependency_routing_recovery_190 tests.test_baseline_snapshot tests.test_boundary_check_path | 27 / 1.123s / 0 / 0 / 0 |

共51个不同测试；恢复测试的三个子场景不另加 testsRun。以上均在合并后源码
1037ec9 上执行；较早 transport-config 的8项和 focus-06 的3项为重复检查，不累加。
修改文件 ruff check、git diff --check 通过。baseline及official导入边界8项包含于27项。

失败记录不覆盖：green-http 的第二次累计输入估计断言错误（1 failure），已改为增量；
restart-01/02 的 Planner method_id 与夹具未启用 progress_scheduling 不匹配（各2 failure），
修复夹具后 focus-03 通过；focus-final/04 曾错误假设续接应自动repair/使用非已知枚举错误
（各1 failure），改用 missing-required-field 的实际 invalid_role_schema 后形成 focus-05 真红。
focus-06 为三项转绿；最终 merged-final 在合并源码复验。所有组 error/skip 均为0。
中间一次只读证据检查直接调用共享 Python，偏离 uv 入口约定；未运行测试或修改依赖。

## 审查与交接边界

唯一 fresh 实现者对新增差异按规范/规格两轴复核：生产仅三文件九行净增；
不改191指令、193 UI、official、依赖、根预算、旧Run策略或unknown权限。
本轮不冒称新增独立双审者结论。原两轴的受控证据限制已有对应测试，真实模型
效果、native server tool端到端语义、provider-live兼容性仍非本记录的覆盖范围。

未运行 live/provider、真实服务、浏览器、整仓/最终阶段门禁；自然 S/D/U 仍 **not_run**。
单组测试最长27.609秒，无预期长测试、无创建的定时检查需要清理或转移。
保留当前同一模型选择，具体型号与跨session继承无法独立确认；接续不得覆盖模型。
未读 tests/test.md 或 root 用户未跟踪合同，未删除其他 worktree。
