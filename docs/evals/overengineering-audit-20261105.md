# 过度开发审计与修复记录（2026-11-05）

## 范围和边界

本记录持久化本轮审计结论及随后修复过程。基于当前源码、相关 ADR、聚焦测试、Git 历史和 provider-live Run 的脱敏状态；不把离线检查当作线上验收，也不评价数学正确率。

保留官方 baseline、预算与 unknown 账本、Run/Job/调用身份、工具权限、整题审查和最终文本绑定。没有因为这些约束较严格就判定过度设计。

本次检查不读取或修改用户保留的 `tests/test.md`，不启动新 provider 请求、#128 配对或耗时全量测试。现有 #127 Run 独立于本修复分支继续运行。

## 尝试方案

截至本记录建立时，针对自然多步线上失败共尝试六个代码方案：

1. `4a486fd`：SQLite 失败事务回滚、读取快照后释放读锁，以及安全失败诊断；对应的聚焦回归通过。
2. `e54f070`：为已观察到的 Meta `partial_exploration` 请求形状增加精确流 profile。独立线上探针通过，随后被第 4 项替代。
3. `e6fd1ba`：文件型数据库中隔离 Job 写入连接与 Run 读取连接；脏读/SQLite `SQLITE_ROW` 有确定性复现，聚焦隔离测试通过。
4. `0a58425`：将业务回复 schema 与 provider 传输 profile 解耦。真实合法 Meta 路径曾被旧白名单挡在出网前；新策略仍拒绝未经登记的传输配置。
5. `eec1d26`：Challenge 路径接入一次预算内、使用新调用身份的已知格式错误修复。后续线上观察到一次格式修复成功。
6. `e6b6b89`：允许 role 回复带顶层附加交接字段，仍要求 role 自有核心字段并严格验证嵌套结构。没有证据证明此项是此前线上失败的根因。

运行层面另有：七个 #127 provider-live 批次（最初批次一个，后续六个）、一次独立 Meta 流探针；一次离线全仓门禁运行约 18 分钟后取消，未通过。`handoffloose-01` 曾因旧服务占用端口而访问了错误服务/数据库，判为已执行但验收无效，不并入修复效果。

这六项是本地实现方案数，不表示六种方案都成功解决线上 readiness。首发失败根因仍未完全还原；不能把 SQLite 清理阶段异常认定为首发原因。

## 审计发现

以下计数按独立根因，多个文件中的同一问题不重复计数。

### 初次只读审计时疑似过度开发：3 项

#### 1. 流片段引发完整状态高频持久化和全事件读取

- **位置**：`showcase/solver_harness/calls.py` 的 `_save()`、`_consume()`、`checkpoint()`；`showcase/solver_harness/storage.py` 的 `commit_event()`、`_read_run()`；`showcase/experiment_job_adapter.py` 的 `_wait_for_job()`；`showcase/experiment_execution.py` 的 `_record_execution_events()`。
- **证据**：流片段可能提交 call/state 更新；每次提交读取 snapshot 和历史 events；Job 观察循环以约 0.25 秒间隔轮询。既有 live 样本出现数千 state revision 和较高 CPU 时间，当前 Run 也在短时间内接近一万 revision，长时间停在 `CHALLENGE`。
- **判断**：疑似过度设计/性能风险，尚未证明全量事件读取是唯一瓶颈，也未证明具体复杂度阶数。
- **理由**：验收要求首末正文时间、30 秒无活动停止、脱敏尾部、可恢复调用身份和状态变更的原子记录；尚无证据表明每个增量 token 都必须重写完整业务快照。
- **建议**：先测定事件数量与耗时、SQLite 写入量和恢复正确性；若中间 token 快照不参与恢复决策，可合并流指标写入，关键业务转换仍保留原子事件。行为影响主要在中途进程崩溃时可见进度精度，不能降低 unknown 防重发、预算和最终绑定保证。最小验证：定量对比小/大事件量及崩溃恢复，不发新 provider 请求。

#### 2. 一次交接容错被扩大到所有顶层 role schema

- **位置**：`showcase/solver_harness/intern_schemas.py` 的 `handoff_obj()` 和多个 `SCHEMAS` 项。
- **证据**：当前所有 role 顶层 schema 接受额外属性；测试验证附加字段可接受且缺核心字段仍拒绝。真实线上已确认的 `provider_profile_unverified` 根因是传输 profile 与业务 schema 耦合，并非 role schema 拒绝字段。
- **判断**：疑似局部修复扩大；并未证明已导致错误结果。
- **理由**：可能只需对有真实交接扩展字段的协议放宽；但目前缺少各 role/provider 返回额外字段的真实分布和拒绝证据，立即收紧有重新阻断合法流程的风险。
- **建议**：先用现有脱敏响应/replay 列明 role 字段需求，再决定保持或按实际需要缩小范围。最小验证覆盖附加顶层字段、缺核心字段、错误嵌套工具/checkpoint 字段；不改变 provider 白名单。

#### 3. 尚未启用功能保留空状态和分支

- **位置**：`showcase/solver_harness/initial_state.py` 的 `candidate_registry`、`best_effort_decision`；`showcase/solver_harness/harness.py` 中相关 feature flags；ADR-0013。
- **证据**：当前 readiness 明确 best-effort 关闭，部分可选字段保持 `None`。ADR 说明它们为后续切片预留。
- **判断**：疑似过度开发，证据弱；默认关闭且未观察到增加模型调用或当前运行成本。
- **理由**：空字段可能只是稳定快照合同的低成本占位；只有确定无旧 Run、restore、pair 或产品消费者依赖时，删除才有收益。
- **建议**：暂时保留；在下次状态 schema 迁移时，检查恢复兼容和所有读取者后再删除。最小验证是现有状态恢复和公开 snapshot 合同测试。

### 历史已确认并已简化：1 项

#### 业务回复 schema 与 provider 传输准入耦合

- **位置**：旧版 `showcase/stream_preference.py` 与 `showcase/experiment_transport.py`；简化见 `0a58425` 和 ADR-0015。
- **证据**：Meta 的合法 `partial_exploration` 请求因业务 schema 指纹未登记，被传输层以 `provider_profile_unverified` 在出网前拒绝；随后曾先增加逐 schema profile。
- **判断**：已确认的过度耦合，已经修复，不计入当前仍存在的 3 项。
- **建议/影响**：保留单一传输准入身份，业务结果仍由业务校验器严格验证；未知 endpoint/model/payload 仍 fail-closed。验证多个 role 共用已验证传输配置，非法业务响应仍被业务层拒绝。

## 已确认 bug，与“过度设计”分开计数

截至 2026-11-05 00:16 的只读审计曾列出三项候选；进一步核对后，前两项是待修实现/诊断缺陷，第三项被证伪：

1. **观察器异常类别丢失**：`experiment_execution.py` 的 `_safe_observer_error()` 对没有安全 `code` 的异常返回 `None`，而 `_record_execution_events()` 还会吞掉异常。无法据此区分观察链路错误；保持 UNKNOWN 与禁止恢复语义不变，只需增加安全、稳定的错误类别。
2. **非法 role 类型可能触发 TypeError**：`stream_preference.py` 的 `_valid_text_chat_messages()` 对 `role` 直接做集合成员查询；list/dict 不可哈希，导致异常而不是干净拒绝。应在成员查询前做类型校验。
3. **监控投影问题（不成立）**：`process.json`、批次 status、Job 状态和 Solver 状态各自有不同范围；monitor 同时输出 runner 与实际 Run phase。usage 在 Job 未终态前保持上个样本累计也符合当前 batch 计量流程。没有证据证明程序误判或漏报，因此从 bug 计数中剔除。

## 明确属于必要复杂度

- 官方 baseline 字节与默认路径隔离；硬预算、调用截止和空闲停止；请求身份与 unknown attempt 账本；未知请求不能自动重发。
- Solver 数学状态、Job 对外执行状态、checkpoint 执行位置的职责分离及一致性核对。
- 工具允许集与回执；整题审查和最终文本绑定；未验证传输配置拒绝派发。
- usage 缺失时保留 UNKNOWN，而非伪造 PASS。
- 有界格式修复使用新 call identity 且继续遵守原账本，是已知完整协议失败的处理；调用点有多个 owner 是维护遗漏风险，但不能直接把统一风险控制判成多余。

## 初次只读审计计数（修复前）

- 当前已确认过度开发：0 项。
- 当前疑似过度开发：3 项。
- 历史已确认并已修复过度耦合：1 项。
- 已确认实现/诊断 bug：3 项（不算进过度设计项数）。

## 初次审计给出的处理优先级（修复前）

1. **先量化流持久化成本**：收益可能最高，改动成本中高、恢复风险中高；先只读 profile 和受控恢复验证，再决定是否简化。
2. **补观察器安全错误分类**：直接改善 FAIL/UNKNOWN/未完成的区分，改动低、风险低。
3. **评估顶层 schema 放宽范围**：改动低到中，兼容/误接收风险中高；先依据真实脱敏响应确定需求，避免贸然收紧。

## 范围限制

审计覆盖本轮相关的 Solver Harness、传输准入、实验 Job 观察、SQLite 读写、相关 ADR/开发门禁、focused tests、Git 变更和已有脱敏线上批次。未审全仓所有模块、前端、所有 Issue 和完整历史运行；未做性能 profiler，也未启动耗时全量测试。因此不外推整个项目中过度设计的比例，不把当前 Run 的阶段循环直接定性为数学错误。

## 2026-11-05 最终处置

### 尝试次数口径

- 历史上针对 #127 provider-live 问题记录了 **6 种代码方案**：SQLite 事务/锁处理、Meta 流 profile 登记、Run 读写连接隔离、业务 schema 与传输准入解耦、预算内格式修复、role 顶层交接字段放宽。它们是不同实现尝试，不代表 6 个根因都已证实或全部解决线上 readiness。
- 历史运行记录另计 **7 个 #127 provider-live 批次和 1 次 Meta 流探针**。`handoffloose-01` 误连旧服务/数据库，验收无效，不作为有效 live 证据；`handoffloose-02` 是最新有效批次。运行尝试数不与代码方案数相加。
- 本修复工作树没有启动 provider 请求，也没有修改/续跑任何旧 Run。

### 本轮修复及新发现

确认并修复 4 项实现/诊断 bug（与过度开发计数分开，其中第 4 项是收窄 schema 时发现并立即修正的兼容回归）：

1. 观察器异常此前只保留安全 `code`，可能丢失 `category` 或异常类型；现只持久化受字符集/长度限制的安全类别或异常类型，并保留有限 HTTP status，不保留异常文本。
2. provider message 的 `role` 若为 list/dict，会在集合成员检查时触发 `TypeError`；现先确认其为字符串，再正常拒绝非法消息形状。
3. 最新 `handoffloose-02` 的自然多步 Job 于 **2026-11-05 00:43:25（北京时间）**以 `run_deadline_exhausted` 失败，Solver 留在 `STEP_VERIFY` / revision 10839，登记 Run 1/2 完成；末正文为 00:43:21.879，无 completion，未发生 30 秒空闲停止。独立报告为 task/process_path `FAIL`、coverage/usage `UNKNOWN`、transport 配置 `PASS`。旧 runner 却将批次 stop reason 记为 `incomplete_or_unresolved_usage`。回归测试复现了“running Job + 截止已过 + unresolved usage”优先显示 usage 的问题；现先按过期硬截止记 `hard_limit`，同时保留 UNKNOWN 请求状态、不恢复、不重发。这个分类修复不会让 Job 完成。
4. 收窄 Meta handoff schema 时，曾把可选的 `role/action/findings/allowed_tools` 一并设成必填，可能拒绝运行时实际只消费 `decision/reason` 的合法响应。独立代码审查发现后，已将必填项收回到 `decision/reason`，其它登记字段仍按类型和枚举校验；`meta_strategist` 别名可返回 `meta` 或 `meta_strategist`。测试覆盖最小响应、两种别名、非法附带值和未登记字段拒绝。

最新 Run 的 source revision 是 `e6b6b8919ac266694c36eb0205e5f79fb3ef3953`，source SHA-256 为 `bd1893119502900fd4f80651fbbefd43d4a089c093efd9f08e433ee160f1e192`，manifest SHA-256 为 `2a1d31d96a1789b7dd2a47e6222c9f34e80d805dcc4a5c1ae5cb86af88d0a005`。只确认了“3600 秒 Run 硬截止”这一直接停因；为什么步骤核验续接未能在截止前交付，不能据现有证据归结为数学错误或单一循环根因。

### 三项复杂度候选的处理结果

1. **流事件全量读取与高频写入**：确认 Job snapshot 路由曾调用完整 `get_job()`（包括事件与 attempt 投影），随后又调用 `events()`；现已移除 snapshot 路径重复完整投影。`workspace.events()` 增加可选 SQL limit，snapshot 取 `limit+1` 条原始行计算 `has_more`，保持 cursor 按原始事件推进；`job_read_snapshot` 用 `MAX(event_id)` 取游标，仅加载 request-attempt 行。SSE 和原子状态/工具/身份/预算写入不变。这解决重复全量读取/无界 snapshot 查询这一子项。已有 10840 solver events 和约 120 MB 本次 SQLite 数据库，说明存储成本可观，但未做写放大或恢复剖析；每个 stream delta 是否需合并提交仍是 **1 项待量化性能风险**，本轮没有改动 token/状态持久化语义。
2. **所有 role 接受附加顶层字段**：已收窄。全局 `additionalProperties` 仍为 false；仅 `meta.partial_exploration` 显式容纳已观察到的 `role/action/findings/allowed_tools` 交接字段，其它 role 仍拒绝未登记字段。测试覆盖 `meta` 与 `meta_strategist` 的已登记字段、缺核心字段、未登记字段和 `reasoner` 未登记字段。没有声称所有线上 role 返回分布均已采样。
3. **未启用功能的空状态与配置分支**：保留。`candidate_registry`、Best-Effort、恢复、pair 和公开 snapshot/restore 合同存在实际消费者；删除缺少证据且有兼容与持久状态风险。best-effort 在 readiness Run 中仍关闭。

### 验证与 Issue 结论

按独立根因计数，本轮**已确认并简化 2 项过度复杂度**（snapshot 重复/无界事件读取；全局 role schema 放宽范围）；**当前仍有 1 项疑似性能复杂度**（每个小流事件的完整状态提交，证据不足以安全改变崩溃恢复语义）。第三项空状态候选经消费者检查后归为必要复杂度，不计入过度设计问题。历史业务 schema 与传输准入耦合另在此前提交修复，不重复计数。已修复的 4 项代码 bug 单独计数，不混入复杂度统计。

- 最终兼容修正后，聚焦 unittest `tests.test_solver_harness_intern`、`tests.test_solver_harness_star_routing`、`tests.test_solver_harness_explore` 和 `tests.test_stream_preference_124`：**41 项通过**。硬截止与观察器分类的两个定向回归也通过。修正前的更广聚焦组为 84 项通过、1 项按条件跳过；没有运行全仓测试。
- Ruff 对改动的源码和测试通过；`git diff --check` 通过；`git diff --exit-code -- user_agent.py implementations BASELINE.json requirements.txt` 无差异。
- 没有运行完整全仓门禁、耗时发布测试或新的 live Run。离线结果只验证受控合同，不等于线上能力证据。
- **#127：FAIL / open**。缺自然多步的最终非空答案、整题审查和同文本绑定。`usage=UNKNOWN`，不作为答案完成的阻断理由，也不标 PASS。
- **#128：NOT_RUN / open**。baseline 和 variant 均未派发，没有线上 applied config 或逐臂核验。
- 官方 baseline、硬预算、Run/Job/call identity、unknown 防重发、工具回执权限、整题审查与最终文本绑定均保留；不宣称数学能力提升。

GitHub #127/#128 评论已按以上终态更新；两个 Issue 均保持开放。
