# Faithful S01 首个纵切：流式调用生命周期合同

状态：首个纵切离线验收通过；S01 仍未完整退出。本文件只记录本纵切的合同与证据。

## 决议来源与适用顺序

- #130《MathAgent Faithful 全目标开发路线决策地图》记录目标来源、实施基线及官方路径边界。地图所列 ZIP SHA-256 为 `14651a0adb075ba466814f2b618ccc2bdefe5f0eb6cc291fbd5b897557305433`，PDF SHA-256 为 `370a37110d4104ff839daf3f08d933b004bc42d41868a7df15f6576cfa14091e`；本 worktree 的项目父目录未提供这两份原件，本合同不声称复核过原件哈希。
- #135《确定调用生命周期与恢复验收合同》的决议评论 `6686145136` 是本纵切的调用生命周期权威细节。
- #144《冻结开发切片、发布门禁与路线交接》的 resolution 评论 `6703147321` 给出 S01–S10 阶段门禁、Run 冻结策略和旧 Run 兼容要求。
- #146《交接 Faithful F1–F8 实施与分层验收》引用的远端 implement-spec 为 `docs/wayfinder-chat-output-prototype-20261106` 分支上的 `docs/specs/mathagent-faithful-implement-spec-20261107.md`（Git blob SHA `c30deb2c51ccf60fa87f68b4a5ac0eaf4630511d`）。
- 与上述决议冲突的 ADR-0014 三次尝试限制，仅对旧策略保留；本纵切的新策略按 #135 执行，并在 ADR-0014 追加迁移说明。

## 本纵切范围

本纵切只覆盖显式 Showcase/STAR 路径中的 `InternStreamAdapter`：服务端可选择一个版本化 stream call policy；创建 Job 时冻结版本，执行与恢复继续读取该 Job 的版本。默认关闭；未启用策略或历史 Job 缺少版本时沿用原语义。不得修改 `user_agent.py`、`implementations/`、官方预算或官方评分路径。

本纵切不登记或推断任何 provider SLA。没有可核验的 provider 公布上限时，不能以 client 的 30/180 秒配置作为整次调用或首响应的应用层截止；请求仍受原 Run/phase/batch 硬截止约束。新策略的 Requests connect/read inactivity 参数以 client 连接值和 Run 剩余硬预算为边界，30 秒 effective-idle 由动态 watchdog 单独收口。实际 provider、endpoint、role 与可验证的公开限制来源应在调用证据中分别记录；未知值保持未知。

## 新策略行为

1. Run policy 记录稳定的 `policy_version`，由服务端显式启用，缺省为关闭。相同幂等 POST 恢复原 Job 和其冻结版本；策略配置变化不改写已创建 Job 或历史 Run。
2. 流式调用开始 1200 秒时最多发出一次软提示。提示不取消调用、不重发请求、不修改数学状态；有效增量持续到达时，调用可继续。
3. 首个有效增量后启动 30 秒 effective-idle 时钟。非空 content 或非空 reasoning 增量可刷新该时钟；reasoning 只记录长度/时间，不公开其文本。heartbeat、空事件、role、usage 和可识别的重复事件均不刷新。只在显式 SSE `id` 与载荷都重复时去重；无 ID 的相同 payload 仍是独立 delta，必须保留、刷新 idle 并与最终文本一致。
4. 首个有效增量到达前不施加臆造的首响应或 idle 上限；此阶段由原硬 deadline 收口。30 秒有效 idle 到期时结束该流并保留已收到的正文与可知计量。已派发但不能证明完成的调用保留 unknown 和未结算预留；未知 usage 仍为 `null`。
5. 没有公开 provider 上限时，完成后的本地处理不另加 30 秒硬截止；它仍受原 Run/phase/batch deadline 限制。较早到期的原 Run deadline 始终优先。只有 reader 已明确读到 EOF 时，排队的终态和本地慢处理才可继续；未完成 reader 的 queued bytes 不豁免 effective idle。迟到回执继续由原 Run deadline 与 Requests read timeout 约束，不新增全局清理上限。
6. 新策略不设应用层总尝试次数上限。共享 Run HTTP/token/时间预算及服务端实际限制仍然生效；只有明确未发送的失败或带有效 `Retry-After` 且仍在原硬 deadline 内的 429 可以自动重试。其他可能已发送的失败保持 unknown，不自动重发。显式用户重试使用新调用身份并保留旧 unknown 账目。
7. 旧策略的重试、timeout 语义不追溯更改。任何 Job 未冻结新版本时都使用旧语义。

## 可复现验收

所有时序用虚拟时钟和受控传输，不访问付费 provider。最小验收从 adapter、RunBudget 与公共 Job 幂等边界观察行为。

| 场景 | 通过条件 |
| --- | --- |
| 默认关闭与旧 Run | 新 Job 默认不带新 policy；策略关闭时旧行为保持；启用后已创建 Job 的版本不随服务配置变化。 |
| 有效流持续 1300 秒 | `client.timeout=180` 不会把活跃流当作 180 秒绝对截止；有效增量持续时 1300 秒后可完成。1200 秒恰发一次软提示，且不泄露 reasoning 文本。 |
| 首个有效增量等待 | 180 秒无首个有效增量但仍未到 Run deadline 时不因 client timeout 结束；抵达 Run deadline 才终止，远端结果与 usage 按 unknown 规则保留。 |
| 30 秒仅 heartbeat/非有效事件 | 首个有效增量之后，heartbeat、usage、role、空事件或重复事件不能刷新有效 idle；有效 idle 到期后结束并保留部分正文。 |
| 相同 delta 和 SSE 事件身份 | 无 ID 的完全相同 data 连续到达时两份均输出、拼接且刷新 idle；相同显式 SSE ID 和载荷的重放只输出一次，同 ID 的新载荷仍完整输出。 |
| 完成后的慢处理 | 慢于旧 client timeout 的本地完成处理，只要仍在 Run deadline 内即可结束；超出 Run deadline 时由 Run deadline 结束。 |
| EOF 排队与慢消费者 | 使用真实 `response_events` 和受控 Response；仅 reader 明确读到 EOF 后，排队的终态与慢速本地消费才豁免 idle；Run deadline 仍优先。未完成流即使心跳队列持续非空也按有效 idle 收口，并由测试事件解除 reader 后核对关闭。 |
| 请求超时审计字段 | 新策略的 Requests timeout 是 connect/read 二元组；旧公开单值 `requests_timeout_seconds` 对新策略记为 `null`，有效期限由 Run deadline 与冻结 policy 解释；旧策略保持已有单值。 |
| Run deadline 先到 | 不论有效流、heartbeat 或软提示状态如何，原 Run deadline 到期后均停止；不重置 deadline 或预算。 |
| 同 key 丢 POST 回包恢复 | 用同一用户、请求和 Idempotency-Key 重放 POST 时返回原 Job；不会新建 Job、Run、调用或预算账本，原冻结 policy 不变。 |
| 新策略重试边界 | 可证明未发送和有效 429 可在共享预算内重试超过三次；ReadTimeout/断流等 unknown 不自动重试；预算耗尽或原硬 deadline 到期时停止。 |

## 本切片明确不覆盖

- 完整非流式响应的 provider 等待与旧策略迁移验收。
- 取消、协议失败、迟到响应及本地处理竞态的完整状态转移矩阵。
- 浏览器刷新/SSE 重连不触发新求解、用户显式 unknown 重试 UI，以及跨进程故障恢复的完整端到端验收。
- provider-live 上限、长响应稳定性、自然题行为或数学效果。没有付费 provider 证据时均标记 `not_run` / `unknown`。
- S01 其他传输与错误分类、服务端限制发现及发布门禁；这些未通过本合同的首纵切测试时仍属于未完成。

## 本次验证记录

集成终审补充：同一 SSE ID 携带不同内容的适配器验收先失败（第二段被丢弃），改为同时核对 ID 与载荷摘要后通过。原有同 ID/同载荷去重及无 ID 同值增量验收继续通过。

显式启用入口为服务端 create_app 配置 SHOWCASE_STREAM_TIMEOUT_POLICY_VERSION=faithful-stream-v1；缺省为 None，新 Job 才冻结选择，不改写已有 Job/Run。

- `uv run --frozen python -m unittest discover -s tests -p 'test_faithful_s01_*.py' -v`：15 项通过。覆盖 1300 秒活跃流、首 delta 等待、heartbeat/usage/显式重复、无 ID 同值 delta、真实 transport EOF/idle 与心跳积压、Run deadline 优先、ConnectTimeout/429 重试 usage 初始化、超三次安全重试、脱敏软提示事件、timeout 审计字段及同 key 恢复。心跳积压反例在仅队列空时检查 idle 的实现下失败，改为消费每个事件前检查后通过。
- `uv run --frozen python -m unittest tests.test_request_transport_late_callback -v`：7 项通过；迟到回执仍受原 deadline/Requests read timeout 窗口约束，无新增全局清理计时器。
- `uv run --frozen python -m unittest tests.test_star_transport_policy -v`：21 项通过；包含旧策略迟到 usage 结算和既有单值 timeout 投影。
- `uv run --frozen python -m unittest tests.test_star_stream_late_race_98 tests.test_star_buffered_deadline_98 tests.test_metered_absolute_deadline tests.test_star_dispatch_boundary_98 -v`：25 项通过。
- `uv run --frozen python -m unittest tests.test_run_budget tests.test_job_control tests.test_workspace_jobs tests.test_flask_showcase tests.test_request_attempts tests.test_solver_harness_streaming_activity tests.test_solver_harness_streaming -v`：50 项通过。
- provider-live、完整 S01 错误/取消/恢复矩阵、非流式等待、浏览器刷新与 SSE 重连、完整全仓发布门禁：`not_run` 或仍未覆盖。本记录仅支持“流式 timeout policy 首纵切离线验收”，不构成 S01 阶段退出声明。

## 纵切退出声明

只有上表首纵切聚焦用例通过、官方 baseline 字节稳定且差异审查通过，才可称“流式 timeout policy 首纵切离线验收通过”。不得由此声称 S01 完成、provider-live 兼容或数学能力提升。
