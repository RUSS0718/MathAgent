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

## 2026-11-04 追加结果

上一段记录的是 2026-11-03 代码合入前的状态，以下结果追加到原记录，不改写旧批次。

- #124 已加入 `researcher.counterexample_check` 的精确 stream profile 变体白名单，并将派发前已知拒绝投影为 `transport_policy_rejected`；真实 schema 探针通过。聚焦回归 52 项通过。
- #127 的简单题和中等题已有 `completed 1/1` 的非空答案返回；中等题这次仍是 FASTPATH，没有自然 planner/steps。困难题新 Run 已实际完成 Explore、planner、reasoner，并进入自然步骤核验，但步骤核验流在进程退出前没有 completion/finish、最终答案、整题审查或 S4 绑定。该 Run 定性为 **已执行但未完成，结果 UNKNOWN**；因此 #127 readiness **未通过**。
- #128 已接通离线 scripted / fake-public-API 配对执行与逐臂核验；因 #127 provider-live readiness 未通过，没有启动线上两臂 Run。详见下方配对切片记录。
- 新代码的实验 profile、消费者、已知拒绝投影和 pair 安全路径聚焦回归共 52 项通过；这不改变 provider-live readiness 结论，也不构成数学能力提升证据。
统计修复固定登记分母，并分别报告已审计、未观察到路径、路径未完成、未知和明确失败；聚焦回归 62 项通过，Ruff 与 `git diff --check` 通过。该统计只说明实验路径可达性，不代表答案正确率或论文能力提升。

## 2026-11-04 #128 离线配对执行切片

#128 的专用 `experiment pair` 路径现已串行派发冻结 baseline 与 variant，并将各自样本通过公共 Job 路径执行为独立 Run。持久 pair 状态包含每个样本的脱敏执行结果；独立 `pair-verify` 重新核对 Run manifest、样本与 Job 身份、公共 Job 的实际组件配置、执行顺序及单因素差异。readiness 先经服务端预检，实际 arm 创建时再次核验；预检本身不创建 Job。

离线 scripted / fake-public-API 合同覆盖该执行与复核切片：聚焦 unittest **54 项通过**，改动范围 Ruff 检查和 `git diff --check` 通过，coverage matrix JSON 可解析。2026-11-04 运行 `uv run python scripts/check.py --offline`，全仓 **1,234 项测试中 3 项失败、42 项跳过**；失败分别为 `test_star_product_guidance_consumption...test_recovery_after_meta_ruling_applies_it_exactly_once` 超时、`test_star_rb03_obligations...test_invalid_declaration_target_and_type_cannot_be_accepted` 调用数不符、`test_star_rb06_faults...test_public_http_deadline_stops_waiting_and_only_late_usage_can_settle` 未决 attempt 断言不符，均不在本切片改动文件内。该证据不包含 provider-live 调用：#127 readiness 仍为 `NOT_RUN`，因此没有运行 live pair，也不支持 pair complete 或数学能力提升结论。

## 2026-11-05 修复工作树与最新运行状态

新增 [handoffloose-02 脱敏运行记录](provider-live-natural-20261104-handoffloose-02.md)：最新自然多步 Run 完成 1/2，在 3600 秒 Run 截止时 Job 仍运行于 `STEP_VERIFY`，随后 Job 以 `run_deadline_exhausted` 失败。原批次 stop reason 对未知 usage 的分类遮住硬截止；已修正本地观察顺序并增加回归。coverage/usage 保持 UNKNOWN，task 与 process_path 为 FAIL，transport PASS 仅指登记配置匹配。

当前工作树还修复了两个既有实现缺陷（观察器丢失安全错误类别、非法非字符串 message role 可触发 `TypeError`），并把事件 snapshot 改为 SQL 限量页、避免 Job 快照重复读全量事件历史；Meta handoff 只允许已登记字段，其余 role 保持严格 schema。聚焦验证结果见本轮审计记录。没有启动新的 provider 请求；#127 仍 FAIL / open，#128 两臂仍 NOT_RUN / open，离线通过不替代线上验收。

## 2026-11-05 readiness-01 与 pair admission 修复

新的 #127 自然多步 Run 已执行未通过，冻结身份、trace、逐调用首末正文及整题交付缺口见 [readiness-01 记录](provider-live-natural-20261105-readiness-01.md)。步骤核验返回矛盾 ACCEPT，系统拒绝接受；后续修复只增加精确诊断，不改变该 Run 结果或 verdict 合同。

#128 离线合同中又修复：pair variant 异常时误复用 baseline 结果、readiness 报告未在所有 admission 层核对 `issue_number=127`、低层 pair 的来源标签与实际传输能力不匹配。后续审查还发现，拦截所有 `provider_live` 声明会误阻断既有 SH22 的显式 Intern 用法；现改为校验固定 provider endpoint 与 strict loopback 边界，不再仅信任来源字符串。#128 仍必须走 readiness-gated 公共入口。聚焦回归和最近一轮完整聚焦测试结果以本记录追加为准。标准公共路由仍是显式 opt-in，并要求受信任服务端注入独立 readiness verifier。

因此 #127 仍为 **已执行未通过 / FAIL / open**，#128 仍为 **NOT_RUN / open**。没有两臂线上 Run；离线结果不替代线上验收。复杂度审计按独立根因更正为 3 项已简化、2 项性能疑点待量化，见 [过度开发审计与修复记录](overengineering-audit-20261105.md)。

## 2026-11-05 readiness-02 前的补充修复

独立复核新增发现最后一个已提交样本在 intent 删除前进程退出时，Run 可 completed 而残留 intent；恢复现已只清理与连续已完成前缀、计数及运行记录完全匹配的 intent，不一致时保留并停止。来源核验也已覆盖实际 port、adapter 和 provider client dispatch 方法，防止实例覆写使 `provider_live`/`offline_injected` 来源标签与调用路径不符。

新增 RED→GREEN 回归后，执行相关 6 组聚焦合同共 **113 项通过**，`check_fast.py`、Ruff、`git diff --check` 通过；官方 baseline 差异检查通过。这些修复和简化仍没有替代 readiness-02 provider-live 证据。当前尚未派发 readiness-02；#128 仍 NOT_RUN，不关闭 Issue。

## 2026-11-05 readiness-02 与后续修复

新冻结 Run `issue127-natural-20261105-readiness-02-run01` 已执行并以 `1/2` 结束。简单题交付、整题审查和同文本绑定成功。自然多步 Job `run_568d8b454a0c9d9b8a80f4d38f8bc075` 生成 5 步计划，报告 3 步、接受 2 步并调用工具 2 次；Meta 解析器拒绝合法业务响应上的传输 `usage` 附加字段，Job 最终以 `star_needs_review` 失败。没有最终答案、整题审查或最终绑定。首末正文时间、冻结身份和独立报告见 [readiness-02 记录](provider-live-natural-20261105-readiness-02.md)。该 Run 不续跑、不恢复、不重发。

这次复核撤销了“预算超限”疑点：每个 Run 分别使用 `119,709` 和 `1,985,185` charged/reserved tokens，都低于单 Run 限额 `2,097,152`；两 Run 总计低于批次限额 `4,194,304`。usage 未知仍标 `UNKNOWN`。Meta 修复仅容许调用审计标记为 stream 的 usage 附加字段，非流式 usage 与未知业务字段仍拒绝。

独立 verifier 的 execution mode 映射、部分执行状态、plan/attempt 角色归属以及工具回执消费核验正在单独修复；离线报告通过前不启动新 readiness Run。复杂度候选复核结果为：事件分页与 Solver 投影缩小已完成，流片段写入/重复历史读取仍待量化；Meta schema 例外保持局部；Best-Effort 空状态保留为有消费者的必要合同。#127 维持 `FAIL / open`，#128 维持 `NOT_RUN / open`。

## 2026-11-05 readiness-05 执行观察器异常

新批次已实际派发，runner 完成计数为 1/2。简单题已交付并审查、绑定；自然多步服务端 Job 仍在推进，但 runner 因状态文件原子替换 WinError 5 退出，服务目录也沿用了 readiness-04。详细事实、冻结身份与证据限制见 [readiness-05 记录](provider-live-natural-20261105-readiness-05.md)。临时读锁解释尚待复现，不把观察器退出说成模型错误。旧 Run 不恢复、不重发；#127 readiness 未通过，#128 两臂 NOT_RUN，usage UNKNOWN。

## 2026-11-05 readiness-06 已派发

状态写入WinError 5的有界重试修复及回归通过后，05因确认服务源码身份不匹配被取消，等待最后在途调用结束。06使用独立8127服务、数据目录及启动source/script/PID核对后串行派发；当前简单题成功，多步自然进入Planner，完成1/2，尚未完成整题交付。见 [06冻结与初始运行证据](provider-live-natural-20261105-readiness-06.md)。不拼接05结果；#127未验收/open，#128两臂NOT_RUN/open，usage UNKNOWN。

### #128 配对准备（readiness-06仍运行时）

已准备独立本地freeze/launch脚本，尚未运行、未生成PASS收据或pair manifest，baseline/variant仍NOT_RUN。预登记同simple与vieta-equation两题，每臂分母2；baseline与06一致，variant仅skills由true改false，其余模型/thinking/传输/预算/审查/绑定及best-effort=false保持。触发判据为公共invocation事件存在非空active_skill_ids；完整记录无触发则not_triggered，缺证据UNKNOWN，失败与禁用臂仍留在分母。只有06独立PASS且source一致后才能冻结并经公共pair入口串行运行。

## readiness-06 最终结果

06已执行未通过，完成1/2。自然多步30次模型/HTTP、2次工具后在第二步以challenge_meta_limit_reached结束；Meta出网和交接成功，最终没有最终生成或整题审查，不是硬预算/900秒/30秒流空闲停止或数学正确性判定。首末正文及独立FAIL证据见 [06最终记录](provider-live-natural-20261105-readiness-06.md)。终态对照又发现并修复独立verifier误滤attempt_index=0，另校正RB03过时调用次数预期；43项相关回归通过，旧Run不升级。#127保持open；#128两臂NOT_RUN/open。
