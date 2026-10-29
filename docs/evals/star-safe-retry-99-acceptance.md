# #99 安全传输重试离线验收

日期：2026-10-29（任务客户端日期）；宿主 UTC 时间另存日志，不改写历史批次。代码验收提交 `59788e27ffba25cca4d60fcb6e68f4acf97c5643`。实施范围见[合同](../engineering/star-safe-retry-99-contract.md)，前置见 [#98 验收](star-timeout-98-acceptance.md)。

## 行为与逐项映射

| #99 条件 | 实测结果 | 公共接缝 / 专属用例 |
| --- | --- | --- |
| 显式最多 6 attempts | 1–6 总次数逐值通过；6 次失败只等待 5 次，6 次成功可完成 | call：`test_explicit_attempt_configuration_is_bounded_and_counts_initial_request`、`test_explicit_six_attempts_have_bounded_backoff_and_one_logical_identity`、lazy adapter 用例 |
| 安全退避 1/2/4/8/15 | 两种传输均匹配；旧配置仍最多 3 次、等待 1/2，非 metered 历史行为保持 | call：上述六次用例、`test_old_three_cap_and_unmetered_retry_behavior_are_preserved` |
| F02 有效 429 | 秒数与 HTTP 日期通过；缺失、空、非法、负数、NaN、Inf 和超过原截止的值均不等待、不重发 | call：两个 `test_f02_*retry_after*` 用例 |
| 未知或不可重试故障 | 400/401/500/503、ReadTimeout、一般连接中断、断流异常均只派发一次；带 429 响应的 ReadTimeout 仍零重发 | call：`test_f02_unknown_and_terminal_failures_are_never_resent`；Job：`test_read_timeout_retains_one_unknown_attempt_and_review_gate` |
| 单一重试权威与独立账 | 每 logical 最多 6 个唯一 attempt；非流式由 client 重试、流式由 adapter 重试；公共 Job 的一次协议 repair 是独立 logical，共 4 logical / 14 HTTP / 已知 40 tokens / 零未决预留 | Job：`test_transport_retry_and_protocol_repair_use_independent_logical_identities`，两种传输 |
| 等待前资源准入 | HTTP 耗尽或 429 未知预留使下一次 token 不足时立即停止；请求/阶段/Run/批次时间不够均不等待；等待中配额被并发动作占用后，派发准入仍阻止第二次 HTTP | call：`test_exhausted_http_or_held_429_tokens_stop_before_waiting`、两个时间/并发准入用例 |
| 原 attempt / 预留 / deadline | Job 的 ReadTimeout 保留一个原 attempt、未知预留与原截止，进入 needs_review；5 个 429 的未知费用各自保留，不当作免费 | Job unknown 用例、call 有效 429 用例；#98 迟到对账模块回归 |
| 官方边界 | 11 个冻结文件 hash、官方 JSON 入口及预算常量核对通过；默认模型调用上限 6、首调用输出 16384、截止 1150 秒。空回复离线替身实际观察 1 次调用，无 `_attempt_budget` 注入 | `test_baseline_snapshot`、`test_solver_release` 官方入口用例及离线预算探针 |

新增选项为 `InternChatClient(safe_retry_attempts=6)`，只在绑定 Run 账本时生效。延迟创建 client 的 adapter 使用 `client_safe_retry_attempts=6`。没有新 CLI 参数；既有 Showcase CLI 和 #97 CLI 完整模块只做回归，没有执行真实 provider 批次。注入的流 client 未提供 retry 时，仍默认只尝试一次。格式修复、恢复、诊断及历史登记实现未改。

## 红绿记录

1. 六次 tracer：`uv run python -m unittest tests.test_star_safe_retry_99 -v` 最初因缺少 `safe_retry_attempts` 报错；实施后通过。第一片与完整传输/预算模块合计 35 项通过（29.061 秒）。
2. 等待前配额：`uv run python -m unittest tests.test_star_safe_retry_99.SafeRetryCallTest.test_exhausted_http_or_held_429_tokens_stop_before_waiting -v` 最初 4 个 subcase 失败，观察到多余的 1 或 2 秒等待；修复后通过。随后专属/完整预算/产品预算模块合计 20 项通过（10.298 秒）。
3. F02 与接线：两个专属 F02/lazy adapter 用例先失败，分别观察到附带 429 的 ReadTimeout 被重发和缺少 adapter 选项；实施后专属 12 项通过（5.343 秒）。
4. 注入 client 兼容：`test_stream_client_without_retry_option_keeps_single_attempt_default` 先因访问不存在的 retry 属性失败；保留旧 `getattr(..., 1)` 后通过。最终专属 13 项、完整传输 21 项、baseline 1 项合计 35 项通过（29.546 秒）。

## 已执行命令与证据

固定镜像先实际执行 `docker image inspect sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d --format '{{.Id}} {{.Os}} {{.Architecture}}'`，输出同 SHA、`linux amd64`。下列组合运行设置 `MATHAGENT_TEST_PYTHON_IMAGE` 为该 SHA，`RUN_STAR_READINESS_DOCKER_INTEGRATION=1`。

```powershell
uv run python -m unittest tests.test_star_safe_retry_99 tests.test_star_transport_policy tests.test_run_budget tests.test_star_product_budget tests.test_star_product_protocol_failure tests.test_request_attempts tests.test_request_transport_loopback tests.test_request_transport_late_callback tests.test_llm_late_settlement tests.test_star_readiness_late tests.test_star_deadline_98 tests.test_star_job_unknown_98 tests.test_star_strict_98 tests.test_star_dispatch_boundary_98 tests.test_star_dispatch_recheck_98 tests.test_star_default_envelope_98 tests.test_star_job_parse_deadline_98 tests.test_star_parse_deadline_98 tests.test_star_late_durable_98 tests.test_star_stream_late_race_98 tests.test_star_transport_lock_deadline_98 tests.test_star_nonstream_late_98 tests.test_star_ledger_lock_deadline_98 tests.test_star_job_ledger_lock_98 tests.test_baseline_snapshot tests.test_solver_release tests.test_showcase_cli tests.test_star_readiness_cli -v
uv run python -m unittest tests.test_adapters tests.test_solver_harness_intern tests.test_live_tool_continuation -v
uv run python -m unittest tests.test_star_safe_retry_99 tests.test_star_transport_policy tests.test_baseline_snapshot -v
uv run ruff check llm_client.py showcase/adapters.py showcase/run_budget.py tests/test_star_safe_retry_99.py
uv run python scripts/check_test_seams.py
uv run python artifacts/issue-99-validation/official-budget.py
git diff --check
```

第一条在 F02/adapter 切片执行 186 项通过（179.903 秒），包括完整协议修复模块的两个 Docker Reference 用例；第二条 16 项通过（23.118 秒）。两组均零 skip、零 expected-failure。随后只有共享限额函数恢复旧流 client 的一次默认 fallback，第三条针对最终代码复验 35 项通过，零 skip。Ruff 改动文件、测试接缝和 diff 检查均通过。上述次数有重叠，不相加为独立用例总数。

本地 ignored 证据：`artifacts/issue-99-validation/{launch.json,related.log,adapter-regression.log,final-transport.log,source-and-ruff.json,ruff-repository.log,official-budget.py,official-budget.log}`。预算探针只核对冻结常量与上述实际观察的单次空回复路径，没有宣称运行到第六次调用。主组合 shell PID 为 42576，创建时间 `2026-10-28T18:15:28.2785830Z`，已退出 0。`source-and-ruff.json` 保存主组合代码内容 hash；兼容修正后代码身份以上述验收提交为准。

## 限制与待组合门禁

`uv run ruff check .` 返回 1：16 个文件共 25 个已有错误；逐字节核对均与基点 `dc9dc807` 相同，本票不处理。该失败没有标成通过。

本票未重跑约 22 分钟的全仓 offline/release 组合门禁，交主聊天协调。整个系列的最终两轴代码审查仍未由本票执行。未发真实 provider 请求，未续跑历史批次，不声称 provider-live 兼容、远端取消或数学能力提升。未知费用保留不代表确认远端仍在运行。等待前检查是提示性准入，实际派发仍以原子预留为准；不承诺检查后资源不会被其他 worker 消费。
