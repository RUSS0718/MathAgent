# 实验 CLI #124–#128 阶段记录

日期：2026-11-03。集成分支：`feat(setup)-流式与CLI实验组件设置`。本记录区分源码合同、受控测试和 provider-live readiness；不把离线结果解释为真实服务兼容或数学能力提升。

## 目前完成的源码切片

- **#124**：按登记 transport profile 对兼容调用选择 stream；未登记或不兼容调用拒绝执行，不在同一 Run 静默改用非流式。stream 的启用、终止与用量通过受控 loopback/provider fixtures 验证。provider-live 兼容未验证。
- **#125**：冻结 manifest 的串行 Job 执行、同身份恢复、只读状态与独立核验已接入 CLI。状态日志尾部由固定白名单事件摘要构成；轮询中的新事件会持久化，敏感事件载荷不进入 status。默认 idempotency lookup 路由关闭，实验服务需显式启用。
- **#126**：verify/export 从持久状态与公共只读 Job 证据核验 attempt、usage/reservation、Job、整题审查和交付绑定；核验不发起模型或工具请求。
- **#128 安全前置**：pair manifest 限制为一个登记因素差异，并绑定调用授权。缺 readiness 时记录 `NOT_RUN`；核验器不信任 runner 的 PASS。实际 pair Job 派发、组件配置接线和独立 arm 重核尚未实现，矩阵继续标记 `NOT_COVERED`。

## 尚未通过的验收

**#127 保持 `NOT_RUN`。** 当前没有由新冻结 manifest CLI 完成并独立核验的简单题和自然多步 provider-live readiness 记录。既有历史 live 运行、loopback、scripted 与 Docker 测试均不能代替该 readiness。

由于 #128 依赖 #127 的 readiness，当前 pair CLI 只证明注册和拒绝路径会失败关闭；尚不能执行 baseline/variant，也不能报告两臂已完成。

本阶段未发送 provider-live 请求，也未关闭 #127 或 #128。需要完成这两项票时，必须先为具体冻结批次创建独立登记、预算、停止条件和执行授权；然后实现并独立核验 readiness 收据，再接通 pair 的公共 Job 组件配置和两臂报告复核。

## 验证

定向检查覆盖实验执行、公共 Job API、pair CLI 注册/拒绝、伪造 PASS 降级、单因素差异与审查不变量；补充回归覆盖远端 Job 已成功时的安全恢复，以及事件摘要分页跨越被过滤事件。聚焦回归共 **72 项通过**，改动范围 Ruff 检查通过，`git diff --check` 通过。

2026-11-03 在固定 Docker 镜像 `sha256:fc913659cd06c9164aacf32cb498b1cf0a6f4b1b8aff66f55f4cd9ff31673a2d` 下完成唯一一次严格最终门禁，运行目录为 `artifacts/final-gates/issues-122-128-final-20261103-r3/`。`scripts/run_final_gate.py --require-reference` 返回 `final_gate=PASS`，六个阶段均通过，源码快照前后相同：

- `check_fast.py`：PASS。
- `check.py --offline`：**1186 项通过、0 失败、2 跳过**，`repository_check=PASS`；两项跳过是显式要求 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 的历史 readiness 集成用例，未计为通过。
- `check_showcase_release.py --require-reference`：**41 项通过、0 失败**，`showcase_release=PASS`。
- 前端 `npm ci --no-audit --no-fund`、`npm audit --audit-level=high` 和 `npm run check`：均通过，audit 报告 0 项漏洞。
- 随后启用 `RUN_STAR_READINESS_DOCKER_INTEGRATION=1` 并复跑离线阶段跳过的两项 Docker 集成用例：**2 项通过**。该补充运行不重跑全量门禁。

上述门禁只证明当前源码的工程合同、受控恢复、固定镜像隔离和前端检查可复现；它没有产生 provider-live 请求，也没有改变 #127 的 `NOT_RUN` 或 #128 的 `NOT_COVERED` 状态。

## 2026-11-04 #128 离线配对执行切片

#128 的专用 `experiment pair` 路径现已串行派发冻结 baseline 与 variant，并将各自样本通过公共 Job 路径执行为独立 Run。持久 pair 状态包含每个样本的脱敏执行结果；独立 `pair-verify` 重新核对 Run manifest、样本与 Job 身份、公共 Job 的实际组件配置、执行顺序及单因素差异。readiness 先经服务端预检，实际 arm 创建时再次核验；预检本身不创建 Job。

离线 scripted / fake-public-API 合同覆盖该执行与复核切片：聚焦 unittest **54 项通过**，改动范围 Ruff 检查和 `git diff --check` 通过，coverage matrix JSON 可解析。2026-11-04 运行 `uv run python scripts/check.py --offline`，全仓 **1,234 项测试中 3 项失败、42 项跳过**；失败分别为 `test_star_product_guidance_consumption...test_recovery_after_meta_ruling_applies_it_exactly_once` 超时、`test_star_rb03_obligations...test_invalid_declaration_target_and_type_cannot_be_accepted` 调用数不符、`test_star_rb06_faults...test_public_http_deadline_stops_waiting_and_only_late_usage_can_settle` 未决 attempt 断言不符，均不在本切片改动文件内。该证据不包含 provider-live 调用：#127 readiness 仍为 `NOT_RUN`，因此没有运行 live pair，也不支持 pair complete 或数学能力提升结论。
