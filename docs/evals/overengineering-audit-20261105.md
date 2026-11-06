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

### 复杂度处理优先级

1. **流片段持久化**：潜在收益最高，改动成本和恢复风险均为中高。先做离线写放大、事件数量和崩溃恢复对比，再决定是否合并中间片段写入。
2. **role 顶层 schema 放宽**：收益中等，改动成本低，已通过局部收窄降低误接收风险；保留 `partial_exploration` 的登记字段兼容，避免再次阻断合法交接。
3. **空状态与关闭功能分支**：删除收益低，兼容风险高。已有恢复、pair 和公开 snapshot/restore 消费者，因此保留并等待状态合同迁移时再评估。

## 2026-11-05 修复工作树追加

在 #127 仍为 `FAIL / open`、#128 仍为 `NOT_RUN / open` 的前提下，继续处理第一项性能候选，但保留逐片段持久化和完整历史读取合同：

- Job 状态投影现在通过 `persisted_solver(..., projection_only=True)` 只加载 `tool_dispatched` 与 `tool_receipt`；完整 `persisted_solver()` 仍供候选回放使用。未配对的工具派发仍会进入 `unknown_tools`，答案绑定继续使用持久化答案和 Solver state。
- 新增回归覆盖无关 `call_activity` 历史被排除、孤立工具派发仍可见、已配对工具不会被误报，以及候选回放仍保留完整事件历史。
- 只读归档测量：`handoffloose-02` 目标 Run 的完整事件为 10,840 条、8,398,807 bytes；同一查询在投影模式下为 6 条、10,136 bytes。五次本地读取中位耗时约由 0.0823 秒降至 0.0194 秒。该测量只说明展示投影的读取成本下降，不证明线上截止根因被修复。
- 没有合并中间流片段，也没有删除 `candidate_registry`、Best-Effort、恢复或 pair 的空状态分支。它们分别受崩溃恢复和公开状态消费者约束，仍不具备安全删除证据。

本追加没有启动 provider-live、#128 pair 或全量测试。新增及相关聚焦回归通过；官方 baseline、硬预算、身份追踪、unknown 防重发、整题审查和最终文本绑定保持不变。

## 2026-11-05 审计口径更正与 readiness-01 复核

### 独立根因计数更正

先前“已简化 2 项”的合并口径遗漏了 Solver 投影路径。按不同事件表和读取消费者拆分后，当前审计范围内已有 **3 项已简化的过度复杂度根因**：

1. `workspace_events` 的 Job 快照重复/无界读取；
2. Solver 展示投影读取与展示无关的完整历史；
3. 所有 role 顶层 schema 一律允许附加字段。

前两项分别由 `job_events.py` 分页和 `star_product_projection.py` 的投影模式处理，属于不同读取路径，不能合并计数。传输 profile 与业务 schema 的旧耦合是更早已修复的第 4 项，不属于本次三候选。

当前**没有已确认且仍存在的过度开发项**；仍有 **2 项待量化的性能复杂度疑点**，均不据此改写恢复语义：

- 每个流片段同步 checkpoint。现有测试明确要求下一个片段前已保存 partial text，并验证进程退出后可恢复该文本；尚无证据表明当前每片段完整快照写入的成本超过该恢复收益。
- 每次 checkpoint 前后的调用路径会重复物化完整 Solver 事件历史：`calls._save()` 读取一次，`harness.commit_event()` 再读取一次。代码可确认重复读取行为，但没有 profile 证明它是本次失败的主因，也没有验证更轻的提交接口能保留并发终态保护。

第二项局部 schema 兼容范围仍受 `meta.partial_exploration` 限定，但仓库未保存可独立复核的脱敏原始 provider 响应；“字段曾在线上出现”目前只见于已有运行记录。保持例外并继续记为证据缺口，不扩大到其它 role，也不在缺乏样本时撤销。

第三候选 `candidate_registry` / `best_effort_decision` 等可选字段保留：实现、公开投影、配对和回放路径有实际消费者。可确认配对及 opt-in 消费者；没有独立证据说明恢复机制依赖这些字段的 `None` 值，不再沿用这一过强表述。readiness 中 Best-Effort 仍关闭。

### 新 Run 与修复后状态

`readiness-01` 的完整冻结信息和结果见 [独立运行记录](provider-live-natural-20261105-readiness-01.md)。该 Run 确实生成自然多步 trace，并执行了工具回执；Job 因步骤核验返回矛盾的 `ACCEPT + PARTIAL + PASS` 组合而安全终止。模型输出矛盾不是代码应当放行的合法 verdict。

围绕本 Run 和 #128 证据路径，又修复 5 个代码问题，均与“过度开发”分开计数：

1. 矛盾 verifier verdict 的 `invalid_verifier_verdict` 原因被自由文本覆盖，Job 只呈现笼统的 `star_needs_review`；现在保留稳定原因并在 Job 错误类别中展示。
2. 只有已核实为终态 Job 失败、且停止原因确认为 `job_failed_or_canceled` 时才清理 intent；账本/传输核验失败仍保留 intent 和 UNKNOWN。
3. Pair variant 执行异常时可能沿用 baseline 的局部 `result`，污染 variant 的 phase/Job ID；现在每臂独立初始化。
4. Pair 核心 admission 与 arm Job 路由都强制 readiness 报告属于 Issue #127。
5. 低层 `SolverHarness.PairedRunner` 的来源声明曾只按字符串分类：脚本 port 可冒称 `provider_live`，而带外部网络能力的 `InternModelAdapter` 可冒称 `offline_injected`；随后加入的 blanket provider-live guard 又会拒绝旧 SH22 合同支持的真实 Intern 调用。现在离线注入只接受严格 loopback client，`provider_live` 只接受固定 Intern endpoint 的 provider-only client；低层真实 live pair 保留原 `needs_review` 结论，#128 仍只能走 readiness-gated 公共入口取得 Issue 证据。

前三项曾影响 #127 分类或未来 #128 证据真实性；后两项是 #128 证据路径缺陷。总计为此前记录的 4 项修复、本次 5 项修复及后续来源/传输核验这一项，共 10 项已确认实现/诊断缺陷修复；不将模型提供矛盾内容或数学正确性列为代码 bug。

配对公共服务路由默认关闭且 readiness verifier 需要受信任宿主注入，这是显式 opt-in 保护边界，不在本轮改成默认开放。当前仓库没有可独立使用的默认 verifier，故线上 pair 仍需由受信任运行配置提供；缺少该配置时应保持 NOT_RUN，而不是降级验收。

聚焦验证：先前的 103 项测试记录对应来源核验修正前的工作树。当前来源核验新增了低层 pair 回归；最新重新执行结果以本记录后续追加为准。官方 baseline 路径保持无差异。#127 仍 FAIL/open；#128 仍 NOT_RUN/open。

## 2026-11-05 独立复核追加：恢复与来源证明

对当前修复工作树做的两轮只读独立复核又定位了 2 个实现缺陷：

1. 最后一个样本提交后、删除 `dispatch_intent.json` 前进程中断时，恢复循环已无下一样本可进入，会把 Run 标为 `completed` 却留下未决 intent；独立核验因该文件将 coverage 降为 UNKNOWN。现在只有 intent 与已完成样本记录的 session、key、digest 和 deadline 完全匹配时，恢复才清理它；未知或不匹配 intent 仍停止并保留。
2. pair source 校验此前只验证 `port.adapter`，但实际 Solver Harness 调用 port 方法。自定义 `InternModelPort` 子类可以挂载固定 endpoint adapter 并覆写 `complete()`；精确类型 adapter 或 client 实例也能覆写实际 dispatch 方法，造成 `provider_live` 或 `offline_injected` 来源被错误确认。现在来源声明要求使用未覆写 dispatch 方法的精确 port、adapter 与 Intern client，再核对 adapter、client 类型和 endpoint；不触网的回归覆盖 port、adapter、client 三层覆写及两个 source 标签。

单样本崩溃回归曾因断言位于临时目录销毁后而失效；修正后先稳定复现“completed 且 intent 仍存在”，再加恢复清理并验证通过。进一步的负向恢复用例证明计数不一致时不会清理 intent。当前聚焦 unittest 为 **113 项通过**，包含执行、独立核验、公共 Job API、pair CLI/来源、配对执行和 STAR gate；快速合同门禁及改动文件 Ruff 通过，`git diff --check` 通过，`BASELINE.json`、`user_agent.py` 与 `implementations/` 无差异。该数字是定向工程证据，不是全仓门禁或 provider-live readiness 结论。

本次审查采取 3 类路径：复用 readiness-01 已冻结证据定位缺口；通过定向 unittest 与源码检查审查既有修复和 3 项审计简化；再用独立子智能体审查恢复、来源证明及新 Run 前置条件。readiness-01 保持原样并仍为已执行未通过；readiness-02 尚未派发；#128 仍 NOT_RUN。上述修复只是本次已知缺陷，不代表已穷尽整个仓库所有潜在 bug。

## readiness-02 后续复核（2026-11-05）

`readiness-02` 已于 2026-11-05 派发并完成 `1/2`，详见 [独立运行记录](provider-live-natural-20261105-readiness-02.md)。自然多步 Job 以 `star_needs_review` 失败；源码和持久事件确认 Meta 解析器拒绝合法业务响应上的流式 `usage` 附加字段。现有修复将只对调用审计证明的 stream 响应剥离该 sidecar，业务键集合仍严格。另一个独立 verifier 修复仍在进行；以上未完成的单测或投影不能记为已修 bug。

此前的本地预算疑点已由独立核对撤销。`2,104,894` 是两 Run charged/reserved 的批次和，低于 `4,194,304` 批次限额；两个 Run 分别为 `119,709` 与 `1,985,185`，均低于各自 `2,097,152` 限额。Provider usage 仍为 `UNKNOWN`，本地预留值不代表 provider 实际计量。

三项复杂度候选的当前处置：

1. Job 事件读取已按游标分页，Solver 展示投影已只读相关工具事件；`readiness-02` SQLite 文件为 `100,626,432` bytes，仍有 `10,819` 条 Solver event 和 `10,825` 条 Job event。高频流片段写入及提交路径重复物化事件历史尚未 profile，归为疑似性能复杂度，保留 checkpoint/恢复语义并先量化。
2. 所有 role 放宽顶层字段的全局复杂度已收窄到局部 Meta handoff 字段；其它 role 仍严格拒绝未登记字段。新 `usage` 兼容只适用于 transport audit 明确标记的 stream sidecar，不扩大业务 schema。
3. `candidate_registry` 与 `best_effort_decision` 空状态有 opt-in Best-Effort、回放和结果投影消费者，保持为必要状态，不删除。

本轮按独立根因计，当前已确认且仍存在的过度开发 **0 项**；疑似性能复杂度 **2 项**，两者都缺少成本剖析来证明应删。三项审计候选中，一项读取范围简化已完成，一项 schema 过度放宽已收窄，一项经消费者审查归为必要复杂度。#127 为 `FAIL / open`，#128 为 `NOT_RUN / open`。没有修改官方 baseline、预算、身份、审查、最终绑定，也没有宣称数学能力提升。

## 2026-11-05 只读量化追加

子智能体从静止的readiness-02数据库确认同一call_activity路径重复物化完整Solver历史：`calls.observe_activity`、`calls._save`、`Harness.commit_event`各读取一次；storage已通过validated_run避免第四次。该Run有10592事件、约8.0MB JSON，其中6924条call_activity。累计历史长度模型估算三次读取约77.13GiB逻辑JSON处理量（不是实测磁盘读取量）。只读SQL全历史查询中位约18.75ms、末条约0.08ms，未包含生产JSON解析/校验耗时。当前只确认可避免的重复工作，尚不能归因线上未交付。

因此当前尚存候选更新为1项已确认重复成本（Solver活动路径重复全历史物化）、1项疑似写放大（每活动完整state_json写入，缺历史大小/恢复代价剖析）。初次三项候选的其它处置不变。建议在下一次必要修复窗口复用一次已验证快照，保留CAS、身份、事件追加和文本checkpoint；尚未实施，不另建框架。readiness-06源码已冻结，本次只补文档，不在运行中修改它。

## 2026-11-05 readiness-06 终态后的最小简化

06真实Run仍未通过：第二步在有界Meta继续处理后仍受有效CHALLENGE质疑，以challenge_meta_limit_reached终止。它不是传输拒绝或预算耗尽；不放宽预算或改写审查判据。终态证据另见06记录。

已处理量化确认的重复历史读取：活动回调只用本调用自己维护的流metrics，保存时读取一次最新Run，并交给Harness内部提交路径复用。公开commit_event签名和其读取持久身份的路径保持；内部仍执行身份、终态检查和原存储CAS。没有持久缓存、新配置或通用框架。每次activity完整历史读取由3降至1，文本checkpoint由2降至1，逐活动事件、每个文本checkpoint及首末正文时间继续持久化。

RED回归实测每次activity读取[3,3]；GREEN为[1,1]，checkpoint为[1]，同时验证首末正文、完整partial文本和两条活动事件。新增负向用例确认过期revision冲突、错误Run身份和终态业务冻结仍拒绝。基础20项通过；新增负向、迟到流、恢复、公开证据共33项通过，用时41.278秒，Ruff与diff-check通过。只证明读取路径成本减少及工程边界，不据此保证真实答案完成或数学能力提升。

当前尚存过度复杂度候选：已确认待处理0项；疑似1项（每活动重写完整state_json的写放大，缺少恢复代价与历史大小测量，不删除原子checkpoint）。初次三项中，重复读取已进一步简化；role字段兼容保持局部；未启用功能的空状态有实际消费者，仍保留为必要复杂度。以上按独立根因计，不以文件数或重复出现次数累加。

本续轮另外处理3个运行/实现缺陷（Windows原子替换短暂读锁、误连旧服务的源码身份隔离、verifier误滤零索引），以及1个过时测试预期（已有一次claim-target-repair应计5次调用）。重复读取单列为1项成本问题，不把模型核验分歧算代码bug。旧报告与Run身份均保留，下一次使用全新manifest。既有两个测试文件的4项F401/I001 lint诊断早于本轮并不在运行源码，本轮未顺手格式化或删除原有导入；新增源码/测试定向Ruff通过，不声称全仓质量门禁已过。
